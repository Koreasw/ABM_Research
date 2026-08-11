"""Building space — networkx graph of floors, corridors, elevators, offices.

H0 v2 geometry (etc/plan_h0_revision.md §1, 사용자 확정 2026-08-03):
  10F Korean office, ~1,200 m²/floor (~34.6 m footprint), 4.0 m floor height,
  34 m double-loaded corridor, 12 offices/floor at positions
  [2, 7, 12, 22, 27, 32] mirrored north/south (and mirrored about the corridor
  midpoint 17.0 m, leaving a 10 m service core around the EV bank at 16/18 —
  사용자 확정 2026-08-04), 100 residents/floor.
  4 EVs at the corridor center, cross-placed: north EV1 (people-only) +
  EV3 (robot-shareable), south EV2 (people-only) + EV4 (robot-shareable).
  Which EVs are robot-shareable is declarative config (building.shared_ev_ids).
  The robot waits AND charges at the 1F lobby robot zone (opportunistic
  charging while idle — plan §1.3); it never uses a basement.

Basements (plan_h0_revision.md §1.6, 사용자 확정 2026-08-03 3차): B1/B2 are
boarding-and-alighting levels for *people* only — they carry no office and no
corridor, just a floor_center hub and one stop node per EV, so that building
occupants can ride the EVs down to parking. They exist to load the elevators
(EV utilisation is the dependent variable of that change); they are not a
robot facility and §1.3's "robot idles+charges at 1F" is unaffected.

Floor labels and rank: floors are labelled -2 (B2), -1 (B1), 1..n_floors —
there is no floor 0, per Korean convention. Label arithmetic is therefore
NOT a floor count across ground level (1F -> B1 is a label gap of 2 but one
storey), so anything measuring a *distance* or interpolating a position must
go through floor_rank() below. Ordering comparisons are safe on raw labels
because rank is strictly increasing in the label.

The graph is a *static* networkx MultiDiGraph; dynamic resource state
(EV occupancy, corridor density) is held by Agents.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import networkx as nx
import yaml

# Mirrored about the corridor midpoint 17.0 m (2+32 = 7+27 = 12+22 = 34), with
# a 10 m service-core gap around the EV bank at 16/18 (사용자 확정 2026-08-04).
DEFAULT_OFFICE_POSITIONS_M: tuple[float, ...] = (
    2, 7, 12, 22, 27, 32,
    2, 7, 12, 22, 27, 32,
)
DEFAULT_OFFICE_SIDES: tuple[str, ...] = (
    "north", "north", "north", "north", "north", "north",
    "south", "south", "south", "south", "south", "south",
)
# EV order defines EV1..EV4. Cross placement (사용자 확정): north gets EV1
# (people-only) + EV3 (shareable), south gets EV2 (people-only) + EV4
# (shareable); the two banks face each other across the corridor center.
DEFAULT_EV_CORRIDOR_POSITIONS_M: tuple[int, ...] = (16, 16, 18, 18)
DEFAULT_EV_SIDES: tuple[str, ...] = ("north", "south", "north", "south")
DEFAULT_SHARED_EV_IDS: tuple[str, ...] = ("EV3", "EV4")

DEFAULT_N_BASEMENTS: int = 2


def floor_label(floor: int) -> str:
    """Node-name label for a floor number: -1 -> 'B1', -2 -> 'B2', 3 -> '3'.

    Inverse of :func:`floor_of` for the ``floor_{LABEL}_...`` / ``ev_{ID}_{LABEL}``
    naming schemes. There is no floor 0.
    """
    if floor == 0:
        raise ValueError("floor 0 does not exist (no ground-level index 0)")
    return f"B{-floor}" if floor < 0 else str(floor)


def floor_rank(floor: int) -> int:
    """Contiguous vertical index for a floor label: B2 -> -1, B1 -> 0, 1F -> 1.

    Labels skip 0, so ``abs(a - b)`` on labels overstates the storey count of
    any pair that straddles ground level (1F..B1 would read as 2). Rank closes
    that gap while staying strictly increasing in physical height, so:

        storeys between a and b  ==  abs(floor_rank(a) - floor_rank(b))

    Use rank for distances, nearest-stop selection and position interpolation;
    plain label comparison is still correct for *ordering* (rank is monotone).
    Above ground rank == label, so no existing 1..n_floors value changes.
    """
    if floor == 0:
        raise ValueError("floor 0 does not exist (no ground-level index 0)")
    return floor if floor >= 1 else floor + 1


LOBBY_ZONE_NODES: tuple[str, ...] = (
    "lobby_entry",
    "lobby_handoff_counter",
    "lobby_queue_zone",
    "lobby_locker_bank",
    "lobby_robot_pickup_zone",
    "lobby_direct_corridor",
)


def build_building_graph(
    n_floors: int = 10,
    n_basements: int = DEFAULT_N_BASEMENTS,
    n_offices_per_floor: int = 12,
    office_positions_m: tuple[float, ...] = DEFAULT_OFFICE_POSITIONS_M,
    office_sides: tuple[str, ...] = DEFAULT_OFFICE_SIDES,
    ev_corridor_positions_m: tuple[float, ...] = DEFAULT_EV_CORRIDOR_POSITIONS_M,
    ev_sides: tuple[str, ...] = DEFAULT_EV_SIDES,
    shared_ev_ids: tuple[str, ...] = DEFAULT_SHARED_EV_IDS,
    corridor_length_m: float = 34.0,
    corridor_resolution_m: float = 1.0,
    floor_height_m: float = 4.0,
) -> nx.MultiDiGraph:
    """Build the static building graph (plan_h0_revision.md §1.1–§1.3).

    `n_basements` (plan §1.6) adds people-only levels B1..B{n} below ground,
    labelled -1..-n. They get a floor_center and one stop node per EV, and
    nothing else: no corridor, no office, no robot facility. n_basements=0
    reproduces the pre-§1.6 building exactly.

    Node attributes:
        - type: 'floor_center' | 'corridor' | 'office' | 'elevator'
        - floor: int  (-n_basements..-1 for B1..Bn, 1..n_floors above ground)
        - position_m: float (corridor nodes only)
        - office_id: int (office nodes only)
        - corridor_position_m: float (office/elevator nodes, branch position in
          METRES — corridor node *indices* are metres / corridor_resolution_m,
          which coincide only at the default 1 m resolution; graph key
          `corridor_mid_pos` is an index, not metres)
        - side: 'north' | 'south' (office/elevator nodes)
        - ev_id: 'EV1' | 'EV2' | ... (elevator nodes only)
        - robot_accessible: bool (True iff the EV is in shared_ev_ids)

    Edge attributes (MultiDiGraph keyed):
        - walk edge: key='walk', type='walk', distance_m: float
        - ev edge: key='ev', type='ev', ev_id: str, from_floor: int, to_floor: int
    Walk and EV edges are added in both directions for bidirectional traversal.
    """
    if n_floors < 2:
        raise ValueError(f"n_floors must be >= 2 (need at least one office floor); got {n_floors}")
    if n_basements < 0:
        raise ValueError(f"n_basements must be >= 0; got {n_basements}")
    if n_offices_per_floor < 1:
        raise ValueError(f"n_offices_per_floor must be >= 1; got {n_offices_per_floor}")
    if len(office_positions_m) != n_offices_per_floor:
        raise ValueError(
            f"len(office_positions_m)={len(office_positions_m)} must equal "
            f"n_offices_per_floor={n_offices_per_floor}"
        )
    if len(office_sides) != n_offices_per_floor:
        raise ValueError(
            f"len(office_sides)={len(office_sides)} must equal "
            f"n_offices_per_floor={n_offices_per_floor}"
        )
    if any(s not in ("north", "south") for s in office_sides):
        raise ValueError(
            f"office_sides must contain only 'north' or 'south'; got {office_sides}"
        )
    n_evs = len(ev_corridor_positions_m)
    if n_evs < 1:
        raise ValueError("Must have at least 1 elevator")
    if len(ev_sides) != n_evs:
        raise ValueError(
            f"len(ev_sides)={len(ev_sides)} must equal "
            f"len(ev_corridor_positions_m)={n_evs}"
        )
    if any(s not in ("north", "south") for s in ev_sides):
        raise ValueError(
            f"ev_sides must contain only 'north' or 'south'; got {ev_sides}"
        )
    ev_ids: list[str] = [f"EV{i + 1}" for i in range(n_evs)]
    unknown_shared = set(shared_ev_ids) - set(ev_ids)
    if unknown_shared:
        raise ValueError(
            f"shared_ev_ids contains unknown EV ids {sorted(unknown_shared)}; "
            f"valid ids for {n_evs} EVs are {ev_ids}"
        )

    n_corridor_positions = int(round(corridor_length_m / corridor_resolution_m)) + 1

    def grid_index(pos_m: float, field: str) -> int:
        """Corridor node index for a branch position given in METRES.

        The corridor is a discrete node chain (`floor_{f}_corr_{i}`) spaced
        `corridor_resolution_m` apart, so a metre position is only representable
        if it lands on that grid.

        This conversion did not exist before 2026-08-04: the metre value was
        substituted straight into the node name, which is correct only while the
        resolution happens to be 1 m *and* every position is an integer. Off-grid
        values did not raise — `add_edge` silently created a dangling
        `corr_2.5` node, leaving the office unreachable from the corridor, so a
        config typo became undeliverable orders at run time instead of a build
        error. The old range check compared metres against an *index* bound
        (`n_corridor_positions - 1`), which is the same conflation.
        """
        if not (0.0 <= pos_m <= corridor_length_m):
            raise ValueError(
                f"{field} contains {pos_m} m, outside the corridor "
                f"[0, {corridor_length_m}] m"
            )
        idx = int(round(pos_m / corridor_resolution_m))
        if abs(pos_m - idx * corridor_resolution_m) > 1e-9:
            raise ValueError(
                f"{field} contains {pos_m} m, which is not on the "
                f"{corridor_resolution_m} m corridor grid (nearest grid point: "
                f"{idx * corridor_resolution_m} m). Lower "
                "building.corridor_resolution_m to place a branch here."
            )
        return idx

    office_idx = [grid_index(p, "office_positions_m") for p in office_positions_m]
    ev_idx = [grid_index(p, "ev_corridor_positions_m") for p in ev_corridor_positions_m]
    # side-aware overlap checks: an EV door and an office door may share a
    # corridor position only if they are on opposite sides; two EVs must not
    # share the same (position, side) slot at all.
    office_slots = set(zip(office_positions_m, office_sides, strict=True))
    ev_slots = list(zip(ev_corridor_positions_m, ev_sides, strict=True))
    if len(set(ev_slots)) != len(ev_slots):
        raise ValueError(
            f"duplicate EV (position, side) slots: {sorted(ev_slots)}"
        )
    overlaps = office_slots & set(ev_slots)
    if overlaps:
        raise ValueError(
            f"EV (position, side) slots overlap office slots: {sorted(overlaps)}"
        )

    g = nx.MultiDiGraph()
    g.graph["n_floors"] = n_floors
    g.graph["n_basements"] = n_basements
    g.graph["corridor_length_m"] = corridor_length_m
    g.graph["corridor_resolution_m"] = corridor_resolution_m
    g.graph["corridor_mid_pos"] = n_corridor_positions // 2
    g.graph["floor_height_m"] = floor_height_m
    g.graph["n_offices_per_floor"] = n_offices_per_floor
    g.graph["office_positions_m"] = tuple(office_positions_m)
    g.graph["office_sides"] = tuple(office_sides)
    g.graph["ev_ids"] = tuple(ev_ids)
    g.graph["ev_corridor_positions_m"] = tuple(ev_corridor_positions_m)
    g.graph["ev_sides"] = tuple(ev_sides)
    g.graph["shared_ev_ids"] = tuple(shared_ev_ids)

    # Basements first so every (floor_int, label) list is ordered bottom-up:
    # B{n}..B1, then 1F..nF. Basements are served by every EV (사용자 확정
    # 2026-08-03 3차) and hold no offices, so they fall through the same
    # "not an office floor" branches the ground floor already uses.
    floor_labels: list[tuple[int, str]] = [
        (-i, floor_label(-i)) for i in range(n_basements, 0, -1)
    ] + [(i, str(i)) for i in range(1, n_floors + 1)]
    office_floor_ints = list(range(2, n_floors + 1))
    g.graph["basement_floors"] = tuple(-i for i in range(n_basements, 0, -1))
    g.graph["floor_labels"] = tuple(f for f, _ in floor_labels)

    for floor_int, floor_str in floor_labels:
        g.add_node(
            f"floor_{floor_str}_center", type="floor_center", floor=floor_int
        )

    for ev_id, ev_pos, ev_side in zip(
        ev_ids, ev_corridor_positions_m, ev_sides, strict=True
    ):
        for floor_int, floor_str in floor_labels:
            g.add_node(
                f"ev_{ev_id}_{floor_str}",
                type="elevator",
                floor=floor_int,
                ev_id=ev_id,
                corridor_position_m=float(ev_pos),
                side=ev_side,
                robot_accessible=ev_id in shared_ev_ids,
            )

    for floor_int in office_floor_ints:
        floor_str = str(floor_int)
        for p in range(n_corridor_positions):
            g.add_node(
                f"floor_{floor_str}_corr_{p}",
                type="corridor",
                floor=floor_int,
                position_m=float(p) * corridor_resolution_m,
            )
        for n_office, (corr_pos, side) in enumerate(
            zip(office_positions_m, office_sides, strict=True)
        ):
            g.add_node(
                f"floor_{floor_str}_office_{n_office}",
                type="office",
                floor=floor_int,
                office_id=n_office,
                corridor_position_m=float(corr_pos),
                side=side,
            )

    def add_walk(a: str, b: str, distance_m: float) -> None:
        g.add_edge(a, b, key="walk", type="walk", distance_m=distance_m)
        g.add_edge(b, a, key="walk", type="walk", distance_m=distance_m)

    for floor_int in office_floor_ints:
        floor_str = str(floor_int)
        for p in range(n_corridor_positions - 1):
            add_walk(
                f"floor_{floor_str}_corr_{p}",
                f"floor_{floor_str}_corr_{p + 1}",
                corridor_resolution_m,
            )
        for n_office, corr_i in enumerate(office_idx):
            add_walk(
                f"floor_{floor_str}_office_{n_office}",
                f"floor_{floor_str}_corr_{corr_i}",
                3.0,
            )
        mid_pos = n_corridor_positions // 2
        add_walk(
            f"floor_{floor_str}_center",
            f"floor_{floor_str}_corr_{mid_pos}",
            3.0,
        )

    for ev_id, ev_i in zip(ev_ids, ev_idx, strict=True):
        for floor_int, floor_str in floor_labels:
            if floor_int in office_floor_ints:
                add_walk(
                    f"floor_{floor_str}_corr_{ev_i}",
                    f"ev_{ev_id}_{floor_str}",
                    1.0,
                )
            else:
                add_walk(
                    f"floor_{floor_str}_center",
                    f"ev_{ev_id}_{floor_str}",
                    4.0,
                )

    for ev_id in ev_ids:
        for i in range(len(floor_labels)):
            fi_int, fi_str = floor_labels[i]
            for j in range(i + 1, len(floor_labels)):
                fj_int, fj_str = floor_labels[j]
                a = f"ev_{ev_id}_{fi_str}"
                b = f"ev_{ev_id}_{fj_str}"
                g.add_edge(
                    a, b, key="ev", type="ev",
                    ev_id=ev_id, from_floor=fi_int, to_floor=fj_int,
                )
                g.add_edge(
                    b, a, key="ev", type="ev",
                    ev_id=ev_id, from_floor=fj_int, to_floor=fi_int,
                )

    return g


def add_lobby_handoff_zones(
    g: nx.MultiDiGraph,
    n_locker_compartments: int = 4,
    queue_capacity: int = 8,
) -> nx.MultiDiGraph:
    """Add the 1F lobby's six handoff zones + M locker compartments to g.

    Adds (all on floor=1):
        - 6 zone nodes (type='lobby_zone'):
          lobby_entry, lobby_handoff_counter, lobby_queue_zone,
          lobby_locker_bank, lobby_robot_pickup_zone, lobby_direct_corridor
        - M `lobby_locker_compartment_{i}` nodes (type='locker_compartment'),
          attached to lobby_locker_bank at 0.5 m.

    Walk edges added (all bidirectional):
        - Each zone ↔ floor_1_center (hub):
            entry 4m | counter/queue/locker 3m | robot_pickup/direct 2m
        - counter ↔ queue          : 2 m  (H1 synchronous → H2 queue flow)
        - locker_bank ↔ robot_pickup : 2 m  (robot accesses locker face)
        - robot_pickup ↔ direct_corridor : 2 m  (robot near EV vestibule)
        - direct_corridor ↔ every 1F EV node : 2 m each  (H0 direct EV)
        - each compartment ↔ locker_bank : 0.5 m

    Per plan_h0_revision.md §1.3, lobby_robot_pickup_zone is the robot's idle
    home AND its charging dock (`charging=True`): the robot charges
    opportunistically whenever it idles there — there is no separate charging
    trip and no basement dock. §1.6 later added people-only basements, which
    does not change this: they carry no robot facility.
    """
    if n_locker_compartments < 1:
        raise ValueError(
            f"n_locker_compartments must be >= 1; got {n_locker_compartments}"
        )
    if queue_capacity < 1:
        raise ValueError(f"queue_capacity must be >= 1; got {queue_capacity}")
    if "floor_1_center" not in g:
        raise ValueError(
            "Graph must contain floor_1_center (call build_building_graph first)"
        )
    if any(zone in g for zone in LOBBY_ZONE_NODES):
        raise ValueError(
            "Lobby zones already present (add_lobby_handoff_zones called twice?)"
        )

    zone_capacities: dict[str, int | None] = {
        "lobby_entry": None,             # ∞ (external boundary)
        "lobby_handoff_counter": 1,      # H1 synchronous counter (framework §5.4)
        "lobby_queue_zone": queue_capacity,
        "lobby_locker_bank": None,
        # Must not be below `robot.n_robots` (baseline 5, 사용자 확정
        # 2026-08-06): H1's termination condition is "every robot back home and
        # settled", so a home that cannot hold the fleet makes the run
        # unterminable. Node capacities are declarative today — only the EV
        # `capacity_people` is enforced — but B3 reads this to judge the
        # "all robots home" invariant, so a stale value gives a wrong verdict.
        "lobby_robot_pickup_zone": 5,
        "lobby_direct_corridor": None,
    }
    for zone in LOBBY_ZONE_NODES:
        g.add_node(
            zone,
            type="lobby_zone",
            floor=1,
            capacity=zone_capacities[zone],
        )
    # v2 (plan §1.3): the robot zone doubles as the charging dock —
    # waiting == charging opportunity (사용자 확정 2026-08-03 §8-6).
    g.nodes["lobby_robot_pickup_zone"]["charging"] = True

    for i in range(n_locker_compartments):
        g.add_node(
            f"lobby_locker_compartment_{i}",
            type="locker_compartment",
            floor=1,
            compartment_id=i,
            parent_zone="lobby_locker_bank",
        )

    g.graph["n_locker_compartments"] = n_locker_compartments
    g.graph["queue_capacity"] = queue_capacity

    def add_walk(a: str, b: str, distance_m: float) -> None:
        g.add_edge(a, b, key="walk", type="walk", distance_m=distance_m)
        g.add_edge(b, a, key="walk", type="walk", distance_m=distance_m)

    floor_1_center_distances: dict[str, float] = {
        "lobby_entry": 4.0,
        "lobby_handoff_counter": 3.0,
        "lobby_queue_zone": 3.0,
        "lobby_locker_bank": 3.0,
        "lobby_robot_pickup_zone": 2.0,
        "lobby_direct_corridor": 2.0,
    }
    for zone, dist in floor_1_center_distances.items():
        add_walk(zone, "floor_1_center", dist)

    add_walk("lobby_handoff_counter", "lobby_queue_zone", 2.0)
    add_walk("lobby_locker_bank", "lobby_robot_pickup_zone", 2.0)
    add_walk("lobby_robot_pickup_zone", "lobby_direct_corridor", 2.0)
    for ev_id in g.graph["ev_ids"]:
        add_walk("lobby_direct_corridor", f"ev_{ev_id}_1", 2.0)

    for i in range(n_locker_compartments):
        add_walk(
            f"lobby_locker_compartment_{i}", "lobby_locker_bank", 0.5
        )

    return g


def floor_of(node: str) -> int | None:
    """Extract floor number from a node name (B1 → -1, B2 → -2).

    Parsing rules (kept in sync with naming in build_building_graph):
        floor_{F}_center / floor_{F}_corr_{P} / floor_{F}_office_{N} → F
        ev_{EVID}_{F}                                                → F
        anything else (e.g., lobby_zone)                             → None

    F is a label, so "B1"/"B2" parse to -1/-2 (plan §1.6); everything else is
    a plain integer. Inverse of :func:`floor_label`.
    """
    if node.startswith("floor_"):
        return _parse_floor_label(node.split("_", 2)[1])
    if node.startswith("ev_"):
        return _parse_floor_label(node.rsplit("_", 1)[1])
    return None


def _parse_floor_label(label: str) -> int:
    """'B1' → -1, 'B2' → -2, '7' → 7."""
    if label.startswith("B"):
        return -int(label[1:])
    return int(label)


def offices_on_floor(g: nx.MultiDiGraph, floor: int) -> list[str]:
    """Return office node names on the given floor, sorted by office_id."""
    matches = [
        (d["office_id"], n)
        for n, d in g.nodes(data=True)
        if d.get("type") == "office" and d.get("floor") == floor
    ]
    matches.sort()
    return [n for _, n in matches]


def elevator_nodes(
    g: nx.MultiDiGraph, ev_id: str | None = None
) -> dict[str, list[str]]:
    """Return {ev_id: [floor_node, ...]} for elevator nodes.

    Each inner list is sorted by floor ascending (1F first).
    If ev_id is given, only that EV's mapping is returned.
    """
    by_ev: dict[str, list[tuple[int, str]]] = {}
    for n, d in g.nodes(data=True):
        if d.get("type") != "elevator":
            continue
        nid = d["ev_id"]
        if ev_id is not None and nid != ev_id:
            continue
        by_ev.setdefault(nid, []).append((d["floor"], n))
    return {k: [n for _, n in sorted(v)] for k, v in by_ev.items()}


def shortest_walk_path(
    g: nx.MultiDiGraph,
    source: str,
    target: str,
    robot: bool = False,
) -> tuple[list[str], float]:
    """Shortest path between source and target minimizing walking distance.

    Walk edges contribute their `distance_m`; `ev` edges contribute 0 (vertical
    travel is free for this query — ElevatorAgent models the actual EV time
    and queue waiting separately).

    If robot=True, people-only elevator nodes (robot_accessible=False) are
    excluded from the search so the path is guaranteed to use only the
    shared EVs (shared_ev_ids, default EV3/EV4).

    Returns:
        (path_nodes, walk_distance_m)

    Raises:
        nx.NodeNotFound: if source or target is not in the graph
        nx.NetworkXNoPath: if no path exists under the constraints
    """
    if source not in g:
        raise nx.NodeNotFound(f"source {source!r} not in graph")
    if target not in g:
        raise nx.NodeNotFound(f"target {target!r} not in graph")

    if robot:
        nodes_to_keep = [
            n for n, d in g.nodes(data=True)
            if not (d.get("type") == "elevator" and d.get("robot_accessible") is False)
        ]
        search_g = g.subgraph(nodes_to_keep)
    else:
        search_g = g

    def _edge_weight(u: str, v: str, edge_data: dict) -> float:
        # MultiDiGraph: edge_data is {key: attrs, ...} for parallel edges u→v.
        best = float("inf")
        for attrs in edge_data.values():
            if attrs.get("type") == "walk":
                w = float(attrs["distance_m"])
            elif attrs.get("type") == "ev":
                w = 0.0
            else:
                w = 0.0
            if w < best:
                best = w
        return best if best != float("inf") else 0.0

    path: list[str] = nx.shortest_path(
        search_g, source=source, target=target, weight=_edge_weight
    )

    total_walk = 0.0
    for u, v in zip(path[:-1], path[1:]):
        edge_data = search_g.get_edge_data(u, v)
        for attrs in edge_data.values():
            if attrs.get("type") == "walk":
                total_walk += float(attrs["distance_m"])
                break
    return path, total_walk


def load_config(path: str | Path) -> dict[str, Any]:
    """Parse a YAML building config (e.g. configs/baseline_10f.yaml)."""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_from_config(config: dict[str, Any]) -> nx.MultiDiGraph:
    """Build the building graph from a parsed config's ``building`` block.

    Wires the geometry keys (n_floors, n_basements, floor_height_m,
    corridor_length_m, office/EV position+side arrays, shared_ev_ids) through to
    :func:`build_building_graph`, then stamps config-only metadata that the
    graph builder does not own (occupancy_per_floor, shared-EV people
    capacities) onto ``g.graph`` for downstream agents.

    V-CFG guard (v2): the EV fleet is *declarative* — ``ev_corridor_positions_m``
    /``ev_sides`` size the fleet and ``shared_ev_ids`` marks robot-shareable
    cars. ``simulation.model`` instantiates one ElevatorAgent per declared EV
    and derives its KPI reporter names from the ids, so the graph, the agent
    list, and the KPI schema stay consistent by construction. Shape/content
    errors (side/position length mismatch, unknown shared id, slot overlap)
    are rejected by build_building_graph's validators.
    """
    b = config["building"]
    g = build_building_graph(
        n_floors=b["n_floors"],
        # Absent key => 0, NOT DEFAULT_N_BASEMENTS. A config is a full description
        # of one run's building, so a file that never mentions basements must
        # produce the pre-§1.6 building -- otherwise replaying an archived config
        # (results/pre_basement/, frozen fixtures) would silently gain two floors
        # the file never declared, and simulation.model, which reads the same key
        # with the same default, would disagree with its own graph.
        # build_building_graph's signature default stays 2 because a bare
        # build_building_graph() call means "the current building".
        n_basements=b.get("n_basements", 0),
        n_offices_per_floor=b["n_offices_per_floor"],
        office_positions_m=tuple(b["office_positions_m"]),
        office_sides=tuple(b["office_sides"]),
        ev_corridor_positions_m=tuple(b["ev_corridor_positions_m"]),
        ev_sides=tuple(b["ev_sides"]),
        shared_ev_ids=tuple(b["shared_ev_ids"]),
        corridor_length_m=b["corridor_length_m"],
        floor_height_m=b["floor_height_m"],
    )
    g.graph["occupancy_per_floor"] = b.get("occupancy_per_floor")
    g.graph["shared_ev_capacity_people_no_robot"] = b.get(
        "shared_ev_capacity_people_no_robot"
    )
    g.graph["shared_ev_capacity_people_with_robot"] = b.get(
        "shared_ev_capacity_people_with_robot"
    )
    return g
