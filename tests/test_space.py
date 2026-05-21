"""Tests for simulation.space.build_building_graph (STAGE 2.1).

Verifies node/edge structure of the 5F Korean small-office baseline graph
per STAGE2_plan.md §5 + framework §5.
"""

from __future__ import annotations

import pytest

import networkx as nx

from simulation.space import (
    DEFAULT_EV_CORRIDOR_POSITIONS_M,
    DEFAULT_OFFICE_POSITIONS_M,
    DEFAULT_OFFICE_SIDES,
    LOBBY_ZONE_NODES,
    add_lobby_handoff_zones,
    build_building_graph,
    elevator_nodes,
    floor_of,
    offices_on_floor,
    shortest_walk_path,
)


@pytest.fixture(scope="module")
def baseline_graph():
    return build_building_graph()


def test_baseline_node_count_breakdown(baseline_graph) -> None:
    """5F baseline: 6 floor_center + 80 corridor + 32 office + 12 EV + 1 support = 131.

    Robot idle/standby lives at lobby_robot_pickup_zone (1F, added in STAGE 2.3);
    B1F retains only the charging dock — robot returns there only when SOC is low.
    """
    g = baseline_graph
    by_type: dict[str, int] = {}
    for _, data in g.nodes(data=True):
        by_type[data["type"]] = by_type.get(data["type"], 0) + 1
    assert by_type["floor_center"] == 6        # B1F + 1F + 2F-5F
    assert by_type["corridor"] == 4 * 20        # 4 office floors x 20 positions (0..19)
    assert by_type["office"] == 4 * 8           # 4 floors x 8 offices (4 north + 4 south)
    assert by_type["elevator"] == 2 * 6         # 2 EVs x 6 floors
    assert by_type["support"] == 1              # b1f_charging only
    assert g.number_of_nodes() == 6 + 80 + 32 + 12 + 1     # 131
    assert "b1f_waiting" not in g  # removed per design pivot (robot idles at 1F)


def test_corridor_consecutive_connectivity(baseline_graph) -> None:
    """Corridor positions p and p+1 are connected by walk edges in both directions."""
    g = baseline_graph
    for floor in (2, 3, 4, 5):
        for p in range(19):  # 0..18 connect to p+1 (last is 19)
            a = f"floor_{floor}_corr_{p}"
            b = f"floor_{floor}_corr_{p + 1}"
            assert g.has_edge(a, b), f"missing walk edge {a} -> {b}"
            assert g.has_edge(b, a), f"missing reverse walk edge {b} -> {a}"
            assert g[a][b]["walk"]["distance_m"] == pytest.approx(1.0)


def test_office_branch_positions_match_floor_plan(baseline_graph) -> None:
    """Floor plan layout: 4 north offices [3, 8, 13, 17] + 4 south offices [3, 8, 14, 17].
    Office 8 at corr[17] (paired with Office 4 on the north side) gives an equal-width
    south split for Office 7 (x=12.5-15.75) and Office 8 (x=15.75-19) with each office
    centered on its branch — no wasted buffer space."""
    assert DEFAULT_OFFICE_POSITIONS_M == (3, 8, 13, 17, 3, 8, 14, 17)
    assert DEFAULT_OFFICE_SIDES == (
        "north", "north", "north", "north",
        "south", "south", "south", "south",
    )
    g = baseline_graph
    for floor in (2, 3, 4, 5):
        for n_office, (expected_pos, expected_side) in enumerate(
            zip(DEFAULT_OFFICE_POSITIONS_M, DEFAULT_OFFICE_SIDES, strict=True)
        ):
            office_node = f"floor_{floor}_office_{n_office}"
            corr_node = f"floor_{floor}_corr_{expected_pos}"
            assert g.has_edge(office_node, corr_node), (
                f"office {office_node} should branch to {corr_node}"
            )
            assert g[office_node][corr_node]["walk"]["distance_m"] == pytest.approx(3.0)
            data = g.nodes[office_node]
            assert data["corridor_position_m"] == expected_pos
            assert data["office_id"] == n_office
            assert data["side"] == expected_side


def test_office_sides_split_evenly(baseline_graph) -> None:
    """4 offices on north (사무실 1-4) + 4 on south (사무실 5-8) per floor."""
    g = baseline_graph
    for floor in (2, 3, 4, 5):
        north_count = sum(
            1 for _, d in g.nodes(data=True)
            if d.get("type") == "office" and d.get("floor") == floor and d.get("side") == "north"
        )
        south_count = sum(
            1 for _, d in g.nodes(data=True)
            if d.get("type") == "office" and d.get("floor") == floor and d.get("side") == "south"
        )
        assert north_count == 4
        assert south_count == 4


def test_ev_positions_central_hall(baseline_graph) -> None:
    """Floor plan: EV1 at corridor[11], EV2 at corridor[12] — central EV hall, side by side."""
    g = baseline_graph
    assert g.graph["ev_corridor_positions_m"] == (11, 12)
    assert DEFAULT_EV_CORRIDOR_POSITIONS_M == (11, 12)
    for floor in (2, 3, 4, 5):
        # EV1 ↔ corridor[11]
        assert g.has_edge(f"ev_EV1_{floor}", f"floor_{floor}_corr_11")
        assert g[f"ev_EV1_{floor}"][f"floor_{floor}_corr_11"]["walk"]["distance_m"] == pytest.approx(1.0)
        # EV2 ↔ corridor[12]
        assert g.has_edge(f"ev_EV2_{floor}", f"floor_{floor}_corr_12")
        assert g[f"ev_EV2_{floor}"][f"floor_{floor}_corr_12"]["walk"]["distance_m"] == pytest.approx(1.0)
        # Office floor floor_center should NOT directly connect to EV
        assert not g.has_edge(f"floor_{floor}_center", f"ev_EV1_{floor}")
        assert not g.has_edge(f"floor_{floor}_center", f"ev_EV2_{floor}")


def test_b1f_charging_dock_co_located_at_center(baseline_graph) -> None:
    """B1F has only the charging dock (b1f_charging), placed 2m from floor_B1_center.
    Robot idle/standby lives at 1F (lobby_robot_pickup_zone, STAGE 2.3)."""
    g = baseline_graph
    assert g.has_edge("b1f_charging", "floor_B1_center")
    assert g["b1f_charging"]["floor_B1_center"]["walk"]["distance_m"] == pytest.approx(2.0)


def test_elevator_node_attributes(baseline_graph) -> None:
    """EV1 people-only (robot_accessible=False); EV2 shared (robot_accessible=True)."""
    g = baseline_graph
    for floor_str in ("B1", "1", "2", "3", "4", "5"):
        ev1 = g.nodes[f"ev_EV1_{floor_str}"]
        ev2 = g.nodes[f"ev_EV2_{floor_str}"]
        assert ev1["ev_id"] == "EV1"
        assert ev2["ev_id"] == "EV2"
        assert ev1["robot_accessible"] is False
        assert ev2["robot_accessible"] is True


def test_floor_center_evs_only_on_b1_and_1f(baseline_graph) -> None:
    """Only B1F and 1F floor_center connect directly to EV nodes (4m).
    Office floors (2-5) connect EVs to corridor positions instead (see test above)."""
    g = baseline_graph
    for floor_str in ("B1", "1"):
        center = f"floor_{floor_str}_center"
        for ev_id in ("EV1", "EV2"):
            ev_node = f"ev_{ev_id}_{floor_str}"
            assert g.has_edge(center, ev_node), f"expected {center} → {ev_node}"
            assert g[center][ev_node]["walk"]["distance_m"] == pytest.approx(4.0)


def test_ev_vertical_connectivity_all_floor_pairs(baseline_graph) -> None:
    """EV nodes connect every floor pair via 'ev' type edge in both directions."""
    g = baseline_graph
    floor_strs = ("B1", "1", "2", "3", "4", "5")
    for ev_id in ("EV1", "EV2"):
        for i, fs_i in enumerate(floor_strs):
            for j, fs_j in enumerate(floor_strs):
                if i == j:
                    continue
                a = f"ev_{ev_id}_{fs_i}"
                b = f"ev_{ev_id}_{fs_j}"
                edges = g.get_edge_data(a, b)
                assert edges is not None and "ev" in edges, (
                    f"missing ev edge {a} -> {b}"
                )
                ev_data = edges["ev"]
                assert ev_data["ev_id"] == ev_id


def test_invalid_inputs_raise() -> None:
    with pytest.raises(ValueError):
        build_building_graph(n_floors=1)
    with pytest.raises(ValueError):
        build_building_graph(n_offices_per_floor=0)
    with pytest.raises(ValueError):
        build_building_graph(office_positions_m=(1, 4, 7))  # length mismatch
    with pytest.raises(ValueError):
        # out of range (corridor max position = 19 with 19m length + 1m grid)
        build_building_graph(office_positions_m=(3, 8, 13, 17, 3, 6, 14, 30))
    with pytest.raises(ValueError):
        build_building_graph(n_people_only_evs=0, n_shared_evs=0)
    with pytest.raises(ValueError):
        build_building_graph(ev_corridor_positions_m=(11,))  # wrong length
    with pytest.raises(ValueError):
        build_building_graph(ev_corridor_positions_m=(11, 100))  # out of range
    with pytest.raises(ValueError):
        # EV overlaps office position (3 is used by 사무실 1)
        build_building_graph(ev_corridor_positions_m=(3, 12))
    with pytest.raises(ValueError):
        # office_sides length mismatch
        build_building_graph(office_sides=("north",) * 5)
    with pytest.raises(ValueError):
        # office_sides invalid value
        build_building_graph(office_sides=("invalid",) * 8)


# --- STAGE 2.2: Query API -----------------------------------------------------


def test_floor_of_parses_all_node_kinds() -> None:
    assert floor_of("floor_B1_center") == -1
    assert floor_of("floor_1_center") == 1
    assert floor_of("floor_5_center") == 5
    assert floor_of("floor_3_corr_7") == 3
    assert floor_of("floor_4_office_2") == 4
    assert floor_of("ev_EV1_B1") == -1
    assert floor_of("ev_EV2_5") == 5
    assert floor_of("b1f_charging") == -1
    # Future lobby_zone nodes (STAGE 2.3) have no clear floor
    assert floor_of("lobby_entry") is None


def test_offices_on_floor_returns_all_eight(baseline_graph) -> None:
    for floor in (2, 3, 4, 5):
        offices = offices_on_floor(baseline_graph, floor)
        assert len(offices) == 8
        # Sorted by office_id ascending → 0..7
        assert offices == [f"floor_{floor}_office_{i}" for i in range(8)]
    # No offices on B1F or 1F
    assert offices_on_floor(baseline_graph, -1) == []
    assert offices_on_floor(baseline_graph, 1) == []


def test_elevator_nodes_all_and_filtered(baseline_graph) -> None:
    all_evs = elevator_nodes(baseline_graph)
    assert set(all_evs.keys()) == {"EV1", "EV2"}
    for ev_id in ("EV1", "EV2"):
        assert len(all_evs[ev_id]) == 6  # B1, 1, 2, 3, 4, 5
        # First node is B1F (floor=-1), last is 5F
        assert all_evs[ev_id][0] == f"ev_{ev_id}_B1"
        assert all_evs[ev_id][-1] == f"ev_{ev_id}_5"

    only_ev2 = elevator_nodes(baseline_graph, ev_id="EV2")
    assert set(only_ev2.keys()) == {"EV2"}
    assert only_ev2["EV2"] == [f"ev_EV2_{f}" for f in ("B1", "1", "2", "3", "4", "5")]


def test_shortest_walk_path_same_floor(baseline_graph) -> None:
    """Same-floor corridor traversal: 0→19 must walk the full 19m corridor."""
    path, dist = shortest_walk_path(
        baseline_graph, "floor_2_corr_0", "floor_2_corr_19"
    )
    assert dist == pytest.approx(19.0)
    # Path stays on floor 2 (no detour through EV)
    assert all(node.startswith("floor_2_") for node in path)
    assert len(path) == 20  # 0..19 inclusive


def test_shortest_walk_path_b1_charging_to_5f_office(baseline_graph) -> None:
    """B1F charging → 5F office_2 (corr[13]) via shared EV2 (corr[12]).

    Walk segments: 2 (b1f→center) + 4 (center→ev_B1) + 1 (ev_5→corr_12)
                 + 1 (corr_12→corr_13) + 3 (corr→office) = 11 m.
    EV vertical hop (ev_EV2_B1 → ev_EV2_5) contributes 0 to walk distance.
    """
    path, walk_m = shortest_walk_path(
        baseline_graph, "b1f_charging", "floor_5_office_2"
    )
    assert walk_m == pytest.approx(11.0)
    # Path must traverse an EV node
    assert any(p.startswith("ev_") for p in path)
    # Path endpoints
    assert path[0] == "b1f_charging"
    assert path[-1] == "floor_5_office_2"


def test_shortest_walk_path_robot_avoids_ev1(baseline_graph) -> None:
    """robot=True excludes EV1 (people-only) nodes from the path."""
    path, _ = shortest_walk_path(
        baseline_graph, "b1f_charging", "floor_5_office_2", robot=True
    )
    assert all(not p.startswith("ev_EV1_") for p in path), (
        f"robot path must avoid EV1, got: {path}"
    )
    # Must still cross via EV2
    assert any(p.startswith("ev_EV2_") for p in path)


def test_shortest_walk_path_robot_picks_longer_corridor(baseline_graph) -> None:
    """When robot=True forces EV2 (corr[12]) instead of EV1 (corr[11]),
    reaching office_0 at corr[3] adds 1m of corridor walking.
    Non-robot: 2+4+1+8+3 = 18m via EV1.  Robot: 2+4+1+9+3 = 19m via EV2."""
    _, walk_no_robot = shortest_walk_path(
        baseline_graph, "b1f_charging", "floor_5_office_0"
    )
    _, walk_robot = shortest_walk_path(
        baseline_graph, "b1f_charging", "floor_5_office_0", robot=True
    )
    assert walk_no_robot == pytest.approx(18.0)
    assert walk_robot == pytest.approx(19.0)


def test_shortest_walk_path_invalid_nodes_raise(baseline_graph) -> None:
    with pytest.raises(nx.NodeNotFound):
        shortest_walk_path(baseline_graph, "does_not_exist", "floor_5_office_0")
    with pytest.raises(nx.NodeNotFound):
        shortest_walk_path(baseline_graph, "b1f_charging", "does_not_exist")


# --- STAGE 2.3: Lobby handoff zones -------------------------------------------


@pytest.fixture(scope="module")
def graph_with_lobby():
    g = build_building_graph()
    return add_lobby_handoff_zones(g, n_locker_compartments=4, queue_capacity=8)


def test_lobby_six_base_zones_added(graph_with_lobby) -> None:
    """Six lobby_zone nodes on floor=1 with correct types and capacities."""
    g = graph_with_lobby
    expected_capacities = {
        "lobby_entry": None,
        "lobby_handoff_counter": 1,
        "lobby_queue_zone": 8,
        "lobby_locker_bank": None,
        "lobby_robot_pickup_zone": 2,
        "lobby_direct_corridor": None,
    }
    assert set(LOBBY_ZONE_NODES) == set(expected_capacities)
    for zone, expected_cap in expected_capacities.items():
        assert zone in g, f"missing zone {zone}"
        data = g.nodes[zone]
        assert data["type"] == "lobby_zone"
        assert data["floor"] == 1
        assert data["capacity"] == expected_cap


def test_lobby_locker_compartments_sweep() -> None:
    """M ∈ {2, 4, 8} sweep produces M compartment nodes, each 0.5 m from bank."""
    for M in (2, 4, 8):
        g = add_lobby_handoff_zones(
            build_building_graph(), n_locker_compartments=M
        )
        compartments = [
            n for n, d in g.nodes(data=True)
            if d.get("type") == "locker_compartment"
        ]
        assert len(compartments) == M, f"M={M}: got {len(compartments)} compartments"
        assert g.graph["n_locker_compartments"] == M
        for i in range(M):
            node = f"lobby_locker_compartment_{i}"
            assert node in g
            assert g.nodes[node]["compartment_id"] == i
            assert g.nodes[node]["parent_zone"] == "lobby_locker_bank"
            assert g.has_edge(node, "lobby_locker_bank")
            assert g[node]["lobby_locker_bank"]["walk"]["distance_m"] == pytest.approx(0.5)


def test_lobby_zones_all_connected_to_floor_1_center(graph_with_lobby) -> None:
    """All six zones must have a walk edge to floor_1_center (the lobby hub)."""
    g = graph_with_lobby
    expected_distances = {
        "lobby_entry": 4.0,
        "lobby_handoff_counter": 3.0,
        "lobby_queue_zone": 3.0,
        "lobby_locker_bank": 3.0,
        "lobby_robot_pickup_zone": 2.0,
        "lobby_direct_corridor": 2.0,
    }
    for zone, dist in expected_distances.items():
        assert g.has_edge(zone, "floor_1_center"), f"{zone} not connected to center"
        assert g.has_edge("floor_1_center", zone)
        assert g[zone]["floor_1_center"]["walk"]["distance_m"] == pytest.approx(dist)


def test_lobby_direct_corridor_to_evs(graph_with_lobby) -> None:
    """H0 vestibule: direct_corridor → EV1 and EV2 at 2 m each."""
    g = graph_with_lobby
    for ev in ("ev_EV1_1", "ev_EV2_1"):
        assert g.has_edge("lobby_direct_corridor", ev)
        assert g["lobby_direct_corridor"][ev]["walk"]["distance_m"] == pytest.approx(2.0)


def test_robot_idle_to_office_no_b1_detour(graph_with_lobby) -> None:
    """§17 critical: robot at lobby_robot_pickup_zone → 3F office_2 must NOT
    detour through B1F and must traverse exactly one EV2 vertical hop.

    Expected (shortest) path via direct_corridor:
        pickup → direct (2m) → ev_EV2_1 (2m) → ev_EV2_3 (0m)
              → corr_12 (1m) → corr_13 (1m) → office_2 (3m)
        = 9 m walk
    """
    g = graph_with_lobby
    path, walk_m = shortest_walk_path(
        g, "lobby_robot_pickup_zone", "floor_3_office_2", robot=True
    )

    # No B1F detour
    floors_seen = {floor_of(n) for n in path if floor_of(n) is not None}
    assert -1 not in floors_seen, f"path must not detour through B1F, got: {path}"

    # Exactly one EV2 vertical hop (1F→3F): two EV nodes in path
    ev_visits = [n for n in path if n.startswith("ev_")]
    assert ev_visits == ["ev_EV2_1", "ev_EV2_3"], (
        f"expected single EV2 hop 1→3, got: {ev_visits}"
    )

    # No EV1 (robot=True excludes people-only EV)
    assert not any(n.startswith("ev_EV1_") for n in path)

    assert walk_m == pytest.approx(9.0)


def test_floor_of_lobby_nodes_returns_none(graph_with_lobby) -> None:
    """floor_of is a name-parser: lobby_* and lobby_locker_compartment_* → None.
    Graph attribute g.nodes[n]['floor']==1 is still accessible for callers
    that need the actual floor."""
    g = graph_with_lobby
    for zone in LOBBY_ZONE_NODES:
        assert floor_of(zone) is None
        assert g.nodes[zone]["floor"] == 1
    assert floor_of("lobby_locker_compartment_0") is None


def test_add_lobby_invalid_inputs_raise() -> None:
    with pytest.raises(ValueError):
        add_lobby_handoff_zones(build_building_graph(), n_locker_compartments=0)
    with pytest.raises(ValueError):
        add_lobby_handoff_zones(build_building_graph(), queue_capacity=0)
    with pytest.raises(ValueError):
        # missing floor_1_center
        add_lobby_handoff_zones(nx.MultiDiGraph())
    with pytest.raises(ValueError):
        # double-add not allowed
        g = build_building_graph()
        add_lobby_handoff_zones(g)
        add_lobby_handoff_zones(g)
