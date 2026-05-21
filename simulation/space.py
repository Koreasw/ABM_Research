"""Building space — networkx graph of floors, corridors, elevators, offices.

Framework §5 + STAGE2_plan.md §5. Baseline 5F Korean small office:
  500 m²/floor, 22m x 23m footprint, 3.6m floor height, 20m corridor,
  7 offices/floor at positions [1, 4, 7, 10, 13, 16, 19] m,
  2 EVs (EV1 people-only, EV2 shared people+robot).

The graph is a *static* networkx MultiDiGraph; dynamic resource state
(EV occupancy, corridor density) is held by Agents (STAGE 3).
"""

from __future__ import annotations

import networkx as nx

DEFAULT_OFFICE_POSITIONS_M: tuple[int, ...] = (3, 8, 13, 17, 3, 8, 14, 17)
DEFAULT_OFFICE_SIDES: tuple[str, ...] = (
    "north", "north", "north", "north",
    "south", "south", "south", "south",
)
DEFAULT_EV_CORRIDOR_POSITIONS_M: tuple[int, ...] = (11, 12)

LOBBY_ZONE_NODES: tuple[str, ...] = (
    "lobby_entry",
    "lobby_handoff_counter",
    "lobby_queue_zone",
    "lobby_locker_bank",
    "lobby_robot_pickup_zone",
    "lobby_direct_corridor",
)


def build_building_graph(
    n_floors: int = 5,
    n_offices_per_floor: int = 8,
    office_positions_m: tuple[int, ...] = DEFAULT_OFFICE_POSITIONS_M,
    office_sides: tuple[str, ...] = DEFAULT_OFFICE_SIDES,
    ev_corridor_positions_m: tuple[int, ...] = DEFAULT_EV_CORRIDOR_POSITIONS_M,
    corridor_length_m: float = 19.0,
    corridor_resolution_m: float = 1.0,
    floor_height_m: float = 3.6,
    n_people_only_evs: int = 1,
    n_shared_evs: int = 1,
) -> nx.MultiDiGraph:
    """Build the static building graph (framework §5 + STAGE2_plan.md §6.1).

    Node attributes:
        - type: 'floor_center' | 'corridor' | 'office' | 'elevator' | 'support'
        - floor: int  (-1 for B1F, 1..n_floors for above)
        - position_m: float (corridor nodes only)
        - office_id: int (office nodes only)
        - corridor_position_m: int (office nodes only, position the office branches off)
        - ev_id: 'EV1' | 'EV2' | ... (elevator nodes only)
        - robot_accessible: bool (False for EV1, True for EV2; True elsewhere)
        - kind: 'charging' | 'waiting' (support nodes only)

    Edge attributes (MultiDiGraph keyed):
        - walk edge: key='walk', type='walk', distance_m: float
        - ev edge: key='ev', type='ev', ev_id: str, from_floor: int, to_floor: int
    Walk and EV edges are added in both directions for bidirectional traversal.
    """
    if n_floors < 2:
        raise ValueError(f"n_floors must be >= 2 (need at least one office floor); got {n_floors}")
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
    n_evs_total = n_people_only_evs + n_shared_evs
    if n_evs_total < 1:
        raise ValueError("Must have at least 1 elevator (people-only or shared)")
    if len(ev_corridor_positions_m) != n_evs_total:
        raise ValueError(
            f"len(ev_corridor_positions_m)={len(ev_corridor_positions_m)} must equal "
            f"total EV count {n_evs_total}"
        )

    n_corridor_positions = int(round(corridor_length_m / corridor_resolution_m)) + 1
    max_pos = n_corridor_positions - 1
    for p in office_positions_m:
        if not (0 <= p <= max_pos):
            raise ValueError(
                f"office_positions_m contains {p}, outside corridor range [0, {max_pos}]"
            )
    for p in ev_corridor_positions_m:
        if not (0 <= p <= max_pos):
            raise ValueError(
                f"ev_corridor_positions_m contains {p}, outside corridor range [0, {max_pos}]"
            )
    overlaps = set(office_positions_m) & set(ev_corridor_positions_m)
    if overlaps:
        raise ValueError(f"EV positions overlap office positions: {sorted(overlaps)}")

    g = nx.MultiDiGraph()
    g.graph["n_floors"] = n_floors
    g.graph["corridor_length_m"] = corridor_length_m
    g.graph["corridor_resolution_m"] = corridor_resolution_m
    g.graph["floor_height_m"] = floor_height_m
    g.graph["n_offices_per_floor"] = n_offices_per_floor
    g.graph["office_positions_m"] = tuple(office_positions_m)
    g.graph["office_sides"] = tuple(office_sides)
    g.graph["ev_corridor_positions_m"] = tuple(ev_corridor_positions_m)
    g.graph["n_people_only_evs"] = n_people_only_evs
    g.graph["n_shared_evs"] = n_shared_evs

    floor_labels: list[tuple[int, str]] = [(-1, "B1")] + [
        (i, str(i)) for i in range(1, n_floors + 1)
    ]
    office_floor_ints = list(range(2, n_floors + 1))

    ev_ids: list[str] = [f"EV{i + 1}" for i in range(n_evs_total)]
    ev_robot_accessible: list[bool] = (
        [False] * n_people_only_evs + [True] * n_shared_evs
    )

    for floor_int, floor_str in floor_labels:
        g.add_node(
            f"floor_{floor_str}_center", type="floor_center", floor=floor_int
        )

    for ev_id, ev_pos, robot_acc in zip(
        ev_ids, ev_corridor_positions_m, ev_robot_accessible, strict=True
    ):
        for floor_int, floor_str in floor_labels:
            g.add_node(
                f"ev_{ev_id}_{floor_str}",
                type="elevator",
                floor=floor_int,
                ev_id=ev_id,
                corridor_position_m=int(ev_pos),
                robot_accessible=robot_acc,
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
                corridor_position_m=int(corr_pos),
                side=side,
            )

    # B1F support: charging dock only. Robot idle/standby lives at
    # lobby_robot_pickup_zone (1F, added in STAGE 2.3); the robot only
    # returns to B1F when SOC drops below RobotAgent's charge threshold.
    g.add_node("b1f_charging", type="support", floor=-1, kind="charging")

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
        for n_office, corr_pos in enumerate(office_positions_m):
            add_walk(
                f"floor_{floor_str}_office_{n_office}",
                f"floor_{floor_str}_corr_{corr_pos}",
                3.0,
            )
        mid_pos = n_corridor_positions // 2
        add_walk(
            f"floor_{floor_str}_center",
            f"floor_{floor_str}_corr_{mid_pos}",
            3.0,
        )

    add_walk("b1f_charging", "floor_B1_center", 2.0)

    for ev_id, ev_pos in zip(ev_ids, ev_corridor_positions_m, strict=True):
        for floor_int, floor_str in floor_labels:
            if floor_int in office_floor_ints:
                add_walk(
                    f"floor_{floor_str}_corr_{int(ev_pos)}",
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
        - direct_corridor ↔ ev_EV1_1 / ev_EV2_1 : 2 m each  (H0 direct EV)
        - each compartment ↔ locker_bank : 0.5 m

    Per §17 design pivot, lobby_robot_pickup_zone is the robot's idle home
    (pickup + standby co-located). RobotAgent only returns to b1f_charging
    when SOC drops below threshold.
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
        "lobby_robot_pickup_zone": 2,    # small fleet (1–3 robots)
        "lobby_direct_corridor": None,
    }
    for zone in LOBBY_ZONE_NODES:
        g.add_node(
            zone,
            type="lobby_zone",
            floor=1,
            capacity=zone_capacities[zone],
        )

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
    add_walk("lobby_direct_corridor", "ev_EV1_1", 2.0)
    add_walk("lobby_direct_corridor", "ev_EV2_1", 2.0)

    for i in range(n_locker_compartments):
        add_walk(
            f"lobby_locker_compartment_{i}", "lobby_locker_bank", 0.5
        )

    return g


def floor_of(node: str) -> int | None:
    """Extract floor number from a node name (B1F → -1).

    Parsing rules (kept in sync with naming in build_building_graph):
        floor_{F}_center / floor_{F}_corr_{P} / floor_{F}_office_{N} → F
        ev_{EVID}_{F}                                                → F
        b1f_charging                                                 → -1
        anything else (e.g., future lobby_zone)                      → None

    F is "B1" → -1, otherwise int("F").
    """
    if node == "b1f_charging":
        return -1
    if node.startswith("floor_"):
        floor_str = node.split("_", 2)[1]
        return -1 if floor_str == "B1" else int(floor_str)
    if node.startswith("ev_"):
        floor_str = node.rsplit("_", 1)[1]
        return -1 if floor_str == "B1" else int(floor_str)
    return None


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

    Each inner list is sorted by floor ascending (B1F first via floor=-1).
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
    and queue waiting separately in STAGE 3).

    If robot=True, people-only elevator nodes (robot_accessible=False) are
    excluded from the search so the path is guaranteed to avoid EV1.

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
