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

DEFAULT_OFFICE_POSITIONS_M: tuple[int, ...] = (1, 3, 7, 10, 13, 17, 19)
DEFAULT_EV_CORRIDOR_POSITIONS_M: tuple[int, ...] = (5, 15)


def build_building_graph(
    n_floors: int = 5,
    n_offices_per_floor: int = 7,
    office_positions_m: tuple[int, ...] = DEFAULT_OFFICE_POSITIONS_M,
    ev_corridor_positions_m: tuple[int, ...] = DEFAULT_EV_CORRIDOR_POSITIONS_M,
    corridor_length_m: float = 20.0,
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
        for n_office, corr_pos in enumerate(office_positions_m):
            g.add_node(
                f"floor_{floor_str}_office_{n_office}",
                type="office",
                floor=floor_int,
                office_id=n_office,
                corridor_position_m=int(corr_pos),
            )

    # B1F support nodes — placed at center near floor_B1_center (per user request).
    # Both nodes co-located ~1 m apart, both 2 m from floor_B1_center.
    g.add_node("b1f_charging", type="support", floor=-1, kind="charging")
    g.add_node("b1f_waiting", type="support", floor=-1, kind="waiting")

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
    add_walk("b1f_waiting", "floor_B1_center", 2.0)
    add_walk("b1f_charging", "b1f_waiting", 1.0)

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
