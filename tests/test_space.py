"""Tests for simulation.space (H0 v2 geometry, etc/plan_h0_revision.md §1).

Verifies node/edge structure of the B2..10F / 1,200 m² / 34 m double-loaded
corridor building with 4 cross-placed EVs (north EV1+EV3 / south EV2+EV4,
EV3·EV4 robot-shareable) and two people-only basements (plan §1.6): B1/B2
carry a floor_center and EV stops only — no office, no corridor, no robot
facility (the robot still idles+charges at the 1F lobby zone, §1.3).
"""

from __future__ import annotations

from pathlib import Path

import networkx as nx
import pytest

from simulation.space import (
    DEFAULT_EV_CORRIDOR_POSITIONS_M,
    DEFAULT_EV_SIDES,
    DEFAULT_OFFICE_POSITIONS_M,
    DEFAULT_OFFICE_SIDES,
    DEFAULT_SHARED_EV_IDS,
    LOBBY_ZONE_NODES,
    add_lobby_handoff_zones,
    build_building_graph,
    build_from_config,
    elevator_nodes,
    floor_label,
    floor_of,
    floor_rank,
    load_config,
    offices_on_floor,
    shortest_walk_path,
)

CONFIG_10F = Path(__file__).resolve().parent.parent / "configs" / "baseline_10f.yaml"

ALL_EV_IDS = ("EV1", "EV2", "EV3", "EV4")
OFFICE_FLOORS = tuple(range(2, 11))
BASEMENT_FLOORS = (-2, -1)                 # B2, B1 (plan §1.6)
ALL_FLOORS = BASEMENT_FLOORS + tuple(range(1, 11))   # 12 served levels


@pytest.fixture(scope="module")
def baseline_graph():
    return build_building_graph()


def test_baseline_node_count_breakdown(baseline_graph) -> None:
    """v2+§1.6 defaults: 12 floor_center (B2,B1,1..10F) + 9 office floors x 35
    corridor positions (34 m / 1 m grid) + 9 x 12 offices + 4 EVs x 12 floors.

    Basements add exactly one floor_center and one EV stop each -- no corridor
    and no office row -- which is what makes them boarding levels rather than
    occupied floors.
    """
    g = baseline_graph
    by_type: dict[str, int] = {}
    for _, data in g.nodes(data=True):
        by_type[data["type"]] = by_type.get(data["type"], 0) + 1
    assert by_type["floor_center"] == 12
    assert by_type["corridor"] == 9 * 35
    assert by_type["office"] == 9 * 12
    assert by_type["elevator"] == 4 * 12
    assert "support" not in by_type            # the robot dock stayed at 1F
    assert g.number_of_nodes() == 12 + 9 * 35 + 9 * 12 + 4 * 12
    # the v1 robot charging dock is gone and does NOT come back with §1.6:
    # the new basements are for people only (plan §1.3 unchanged)
    assert "b1f_charging" not in g
    assert "floor_B1_center" in g
    assert "floor_B2_center" in g


def test_basements_carry_no_offices_or_corridor(baseline_graph) -> None:
    """A10-1 (plan §1.6): each basement is exactly floor_center + one stop/EV."""
    g = baseline_graph
    for floor in BASEMENT_FLOORS:
        nodes = [n for n, d in g.nodes(data=True) if d.get("floor") == floor]
        by_type = sorted(g.nodes[n]["type"] for n in nodes)
        assert by_type == ["elevator"] * 4 + ["floor_center"], (floor, by_type)


def test_basement_center_connects_only_via_elevators(baseline_graph) -> None:
    """No stairs/ramp edge out of a basement: the EVs are the only way up.

    Pedestrians are elevator_only anyway, but pinning it here keeps a future
    'add a basement corridor' change from silently creating a walking route
    that bypasses the cars (which is what the basements exist to load).
    """
    g = baseline_graph
    for floor in BASEMENT_FLOORS:
        center = f"floor_{floor_label(floor)}_center"
        for nbr in g.neighbors(center):
            assert g.nodes[nbr]["type"] == "elevator", (center, nbr)
            assert g.nodes[nbr]["floor"] == floor


def test_every_ev_serves_every_basement(baseline_graph) -> None:
    """사용자 확정: all four cars run B2..10F, so the bank stays symmetric."""
    g = baseline_graph
    for ev_id in ALL_EV_IDS:
        for floor in BASEMENT_FLOORS:
            node = f"ev_{ev_id}_{floor_label(floor)}"
            assert node in g
            assert g.nodes[node]["floor"] == floor


def test_n_basements_zero_reproduces_pre_16_geometry() -> None:
    """n_basements=0 must rebuild the pre-§1.6 graph exactly (regression path)."""
    g = build_building_graph(n_basements=0)
    assert g.graph["n_basements"] == 0
    assert g.graph["basement_floors"] == ()
    assert not [n for n, d in g.nodes(data=True) if (d.get("floor") or 1) < 0]
    assert g.number_of_nodes() == 10 + 9 * 35 + 9 * 12 + 4 * 10
    assert "floor_B1_center" not in g


def test_negative_n_basements_rejected() -> None:
    with pytest.raises(ValueError, match="n_basements"):
        build_building_graph(n_basements=-1)


def test_floor_label_and_rank_round_trip() -> None:
    """Label <-> int round trip, and rank's contiguity across ground level."""
    assert floor_label(-1) == "B1"
    assert floor_label(-2) == "B2"
    assert floor_label(7) == "7"
    for f in ALL_FLOORS:
        assert floor_of(f"floor_{floor_label(f)}_center") == f
        assert floor_of(f"ev_EV1_{floor_label(f)}") == f
    # rank is contiguous and strictly increasing bottom-up; labels are not
    ranks = [floor_rank(f) for f in ALL_FLOORS]
    assert ranks == list(range(-1, 11))
    assert ranks == sorted(ranks)
    # the whole point: 1F->B1 is ONE storey even though the labels differ by 2
    assert abs(floor_rank(1) - floor_rank(-1)) == 1
    assert abs(1 - (-1)) == 2
    for bad in (0,):
        with pytest.raises(ValueError):
            floor_label(bad)
        with pytest.raises(ValueError):
            floor_rank(bad)


def test_corridor_consecutive_connectivity(baseline_graph) -> None:
    """Corridor positions p and p+1 are connected by walk edges in both directions."""
    g = baseline_graph
    for floor in (2, 6, 10):
        for p in range(34):  # 0..33 connect to p+1 (last is 34)
            a = f"floor_{floor}_corr_{p}"
            b = f"floor_{floor}_corr_{p + 1}"
            assert g.has_edge(a, b), f"missing walk edge {a} -> {b}"
            assert g.has_edge(b, a), f"missing reverse walk edge {b} -> {a}"
            assert g[a][b]["walk"]["distance_m"] == pytest.approx(1.0)


def test_office_branch_positions_match_floor_plan(baseline_graph) -> None:
    """12 offices/floor at [2, 7, 12, 22, 27, 32], mirrored north/south.

    Two mirror symmetries at once: each office pair faces directly across the
    double-loaded corridor (north list == south list), and the six positions are
    themselves mirrored about the corridor midpoint 17.0 m
    (2+32 = 7+27 = 12+22 = 34). The 10 m gap between 12 and 22 is the service
    core holding the EV bank at 16/18 — 사용자 확정 2026-08-04.
    """
    assert DEFAULT_OFFICE_POSITIONS_M == (
        2, 7, 12, 22, 27, 32, 2, 7, 12, 22, 27, 32
    )
    # mirrored about the midpoint, not merely evenly spaced
    north = DEFAULT_OFFICE_POSITIONS_M[:6]
    assert [a + b for a, b in zip(north, reversed(north))] == [34] * 6
    assert DEFAULT_OFFICE_SIDES == ("north",) * 6 + ("south",) * 6
    g = baseline_graph
    for floor in (2, 10):
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
    """6 offices on north + 6 on south per floor (중복도 유지)."""
    g = baseline_graph
    for floor in OFFICE_FLOORS:
        for side, expected in (("north", 6), ("south", 6)):
            count = sum(
                1 for _, d in g.nodes(data=True)
                if d.get("type") == "office" and d.get("floor") == floor
                and d.get("side") == side
            )
            assert count == expected


def test_ev_cross_placement(baseline_graph) -> None:
    """4 EVs cross-placed at the corridor center (사용자 확정 2026-08-03):
    north EV1@16 + EV3@18, south EV2@16 + EV4@18; EV3·EV4 robot-shareable."""
    g = baseline_graph
    assert DEFAULT_EV_CORRIDOR_POSITIONS_M == (16, 16, 18, 18)
    assert DEFAULT_EV_SIDES == ("north", "south", "north", "south")
    assert DEFAULT_SHARED_EV_IDS == ("EV3", "EV4")
    assert g.graph["ev_ids"] == ALL_EV_IDS
    assert g.graph["ev_corridor_positions_m"] == (16, 16, 18, 18)
    assert g.graph["ev_sides"] == ("north", "south", "north", "south")
    assert g.graph["shared_ev_ids"] == ("EV3", "EV4")

    expected = {
        "EV1": (16, "north", False),
        "EV2": (16, "south", False),
        "EV3": (18, "north", True),
        "EV4": (18, "south", True),
    }
    for floor in (1, 5, 10):
        for ev_id, (pos, side, shared) in expected.items():
            data = g.nodes[f"ev_{ev_id}_{floor}"]
            assert data["ev_id"] == ev_id
            assert data["corridor_position_m"] == pos
            assert data["side"] == side
            assert data["robot_accessible"] is shared


def test_ev_corridor_connections_on_office_floors(baseline_graph) -> None:
    """Office floors: every EV connects to the corridor node at its position
    (1 m); floor_center has no direct EV edge there."""
    g = baseline_graph
    pos_by_ev = dict(zip(ALL_EV_IDS, (16, 16, 18, 18)))
    for floor in (2, 7, 10):
        for ev_id, pos in pos_by_ev.items():
            ev_node = f"ev_{ev_id}_{floor}"
            corr = f"floor_{floor}_corr_{pos}"
            assert g.has_edge(ev_node, corr)
            assert g[ev_node][corr]["walk"]["distance_m"] == pytest.approx(1.0)
            assert not g.has_edge(f"floor_{floor}_center", ev_node)


def test_ev_lobby_connections_on_1f(baseline_graph) -> None:
    """1F (no corridor nodes): every EV connects to floor_1_center at 4 m."""
    g = baseline_graph
    for ev_id in ALL_EV_IDS:
        ev_node = f"ev_{ev_id}_1"
        assert g.has_edge("floor_1_center", ev_node)
        assert g["floor_1_center"][ev_node]["walk"]["distance_m"] == pytest.approx(4.0)


def test_ev_vertical_connectivity_all_floor_pairs(baseline_graph) -> None:
    """EV nodes connect every floor pair (1..10) via 'ev' edges, both ways."""
    g = baseline_graph
    floors = tuple(range(1, 11))
    for ev_id in ALL_EV_IDS:
        for i in floors:
            for j in floors:
                if i == j:
                    continue
                a = f"ev_{ev_id}_{i}"
                b = f"ev_{ev_id}_{j}"
                edges = g.get_edge_data(a, b)
                assert edges is not None and "ev" in edges, (
                    f"missing ev edge {a} -> {b}"
                )
                assert edges["ev"]["ev_id"] == ev_id


def test_invalid_inputs_raise() -> None:
    with pytest.raises(ValueError):
        build_building_graph(n_floors=1)
    with pytest.raises(ValueError):
        build_building_graph(n_offices_per_floor=0)
    with pytest.raises(ValueError):
        build_building_graph(office_positions_m=(1, 4, 7))  # length mismatch
    with pytest.raises(ValueError):
        # office out of range (corridor is 34 m long)
        build_building_graph(
            office_positions_m=(2, 7, 12, 22, 27, 40, 2, 7, 12, 22, 27, 32)
        )
    with pytest.raises(ValueError):
        build_building_graph(ev_corridor_positions_m=(), ev_sides=())  # no EV
    with pytest.raises(ValueError):
        # ev_sides length mismatch
        build_building_graph(ev_sides=("north", "south"))
    with pytest.raises(ValueError):
        # ev_sides invalid value
        build_building_graph(ev_sides=("north", "south", "north", "middle"))
    with pytest.raises(ValueError):
        # EV out of range
        build_building_graph(ev_corridor_positions_m=(16, 16, 18, 100))
    with pytest.raises(ValueError):
        # duplicate EV (position, side) slot
        build_building_graph(ev_corridor_positions_m=(16, 16, 16, 18),
                             ev_sides=("north", "south", "north", "south"))
    with pytest.raises(ValueError):
        # EV overlaps an office slot on the SAME side (12 is a north office)
        build_building_graph(ev_corridor_positions_m=(12, 16, 18, 18))
    with pytest.raises(ValueError):
        # off-grid branch position: 2.5 m is not on the 1 m corridor grid.
        # Before 2026-08-04 this built a graph with a dangling `corr_2.5` node,
        # orphaning the office from the corridor at run time instead of failing.
        build_building_graph(
            office_positions_m=(2.5, 7, 12, 22, 27, 32, 2, 7, 12, 22, 27, 32)
        )
    with pytest.raises(ValueError):
        build_building_graph(ev_corridor_positions_m=(16.5, 16, 18, 18))
    with pytest.raises(ValueError):
        # unknown shared EV id
        build_building_graph(shared_ev_ids=("EV3", "EV9"))
    with pytest.raises(ValueError):
        # office_sides length mismatch
        build_building_graph(office_sides=("north",) * 5)
    with pytest.raises(ValueError):
        # office_sides invalid value
        build_building_graph(office_sides=("invalid",) * 12)


def test_ev_office_same_position_opposite_side_allowed() -> None:
    """Side-aware overlap: an EV may face an office across the corridor
    (same position, opposite side) — only same-side slots collide."""
    g = build_building_graph(
        ev_corridor_positions_m=(14, 16, 18, 18),
        ev_sides=("south", "north", "north", "south"),
        office_positions_m=(4, 9, 14, 19, 24, 29, 4, 9, 13, 19, 24, 29),
        office_sides=("north",) * 6 + ("south",) * 6,
    )
    assert g.nodes["ev_EV1_2"]["corridor_position_m"] == 14
    assert g.nodes["ev_EV1_2"]["side"] == "south"


# --- Query API ----------------------------------------------------------------


def test_floor_of_parses_all_node_kinds() -> None:
    assert floor_of("floor_1_center") == 1
    assert floor_of("floor_10_center") == 10
    assert floor_of("floor_3_corr_7") == 3
    assert floor_of("floor_4_office_2") == 4
    assert floor_of("ev_EV1_1") == 1
    assert floor_of("ev_EV4_10") == 10
    assert floor_of("lobby_entry") is None


def test_offices_on_floor_returns_all_twelve(baseline_graph) -> None:
    for floor in (2, 10):
        offices = offices_on_floor(baseline_graph, floor)
        assert len(offices) == 12
        assert offices == [f"floor_{floor}_office_{i}" for i in range(12)]
    assert offices_on_floor(baseline_graph, 1) == []


def test_elevator_nodes_all_and_filtered(baseline_graph) -> None:
    all_evs = elevator_nodes(baseline_graph)
    assert set(all_evs.keys()) == set(ALL_EV_IDS)
    for ev_id in ALL_EV_IDS:
        assert len(all_evs[ev_id]) == 12          # B2, B1, 1..10
        assert all_evs[ev_id][0] == f"ev_{ev_id}_B2"   # sorted by floor asc
        assert all_evs[ev_id][-1] == f"ev_{ev_id}_10"

    only_ev4 = elevator_nodes(baseline_graph, ev_id="EV4")
    assert set(only_ev4.keys()) == {"EV4"}
    assert only_ev4["EV4"] == [
        f"ev_EV4_{floor_label(f)}" for f in ALL_FLOORS
    ]


def test_shortest_walk_path_same_floor(baseline_graph) -> None:
    """Same-floor corridor traversal: 0→34 must walk the full 34 m corridor."""
    path, dist = shortest_walk_path(
        baseline_graph, "floor_2_corr_0", "floor_2_corr_34"
    )
    assert dist == pytest.approx(34.0)
    assert all(node.startswith("floor_2_") for node in path)
    assert len(path) == 35  # 0..34 inclusive


def test_shortest_walk_path_1f_to_office(baseline_graph) -> None:
    """floor_1_center → 10F office_2 (north @12): 4 (center→EV@16) + 1
    (ev→corr_16) + 4 (corr 16→12) + 3 (branch) = 12 m; EV hop free.

    EV1/EV2 @16 beat EV3/EV4 @18 here: the office sits left of the core, so the
    nearer bank saves 2 corridor metres."""
    path, walk_m = shortest_walk_path(
        baseline_graph, "floor_1_center", "floor_10_office_2"
    )
    assert walk_m == pytest.approx(12.0)
    assert any(p.startswith("ev_") for p in path)


def test_shortest_walk_path_robot_uses_shared_evs_only(baseline_graph) -> None:
    """robot=True excludes people-only EV1/EV2; path crosses via EV3 or EV4
    (@18), costing 2 extra corridor meters to reach office_2 @12."""
    path, walk_m = shortest_walk_path(
        baseline_graph, "floor_1_center", "floor_10_office_2", robot=True
    )
    assert all(not p.startswith(("ev_EV1_", "ev_EV2_")) for p in path), (
        f"robot path must avoid people-only EVs, got: {path}"
    )
    assert any(p.startswith(("ev_EV3_", "ev_EV4_")) for p in path)
    assert walk_m == pytest.approx(14.0)  # 4 + 1 + 6 (corr 18→12) + 3


def test_shortest_walk_path_invalid_nodes_raise(baseline_graph) -> None:
    with pytest.raises(nx.NodeNotFound):
        shortest_walk_path(baseline_graph, "does_not_exist", "floor_5_office_0")
    with pytest.raises(nx.NodeNotFound):
        shortest_walk_path(baseline_graph, "floor_1_center", "does_not_exist")


# --- Lobby handoff zones ------------------------------------------------------


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
        # A0 (2026-08-06): 2 -> 5, tracking the baseline fleet `robot.n_robots`.
        # H1 terminates on "every robot back home and settled", so a home that
        # cannot hold the fleet would make the run unterminable, and B3 reads
        # this value to judge that invariant.
        "lobby_robot_pickup_zone": 5,
        "lobby_direct_corridor": None,
    }
    assert set(LOBBY_ZONE_NODES) == set(expected_capacities)
    for zone, expected_cap in expected_capacities.items():
        assert zone in g, f"missing zone {zone}"
        data = g.nodes[zone]
        assert data["type"] == "lobby_zone"
        assert data["floor"] == 1
        assert data["capacity"] == expected_cap


def test_robot_zone_is_charging_dock(graph_with_lobby) -> None:
    """v2 (plan §1.3, 사용자 확정 §8-6): the 1F robot zone doubles as the
    charging dock — waiting == charging opportunity. §1.6's people-only
    basements added no robot facility, so no basement dock exists."""
    g = graph_with_lobby
    assert g.nodes["lobby_robot_pickup_zone"]["charging"] is True
    assert "b1f_charging" not in g


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


def test_lobby_direct_corridor_to_all_four_evs(graph_with_lobby) -> None:
    """H0 vestibule: direct_corridor → each of the 4 declared EVs at 2 m."""
    g = graph_with_lobby
    for ev_id in ALL_EV_IDS:
        ev = f"ev_{ev_id}_1"
        assert g.has_edge("lobby_direct_corridor", ev)
        assert g["lobby_direct_corridor"][ev]["walk"]["distance_m"] == pytest.approx(2.0)


def test_robot_idle_to_office_uses_one_shared_hop(graph_with_lobby) -> None:
    """Robot at lobby_robot_pickup_zone → 3F office_2 (north @12) must use
    exactly one shared-EV vertical hop and no people-only EV.

    Shortest path: pickup → direct (2 m) → ev_EV3_1 or ev_EV4_1 (2 m)
        → ev_*_3 (0 m) → corr_18 (1 m) → corr 18→12 (6 m) → office (3 m)
        = 14 m walk
    """
    g = graph_with_lobby
    path, walk_m = shortest_walk_path(
        g, "lobby_robot_pickup_zone", "floor_3_office_2", robot=True
    )
    ev_visits = [n for n in path if n.startswith("ev_")]
    assert len(ev_visits) == 2, f"expected one vertical hop, got: {ev_visits}"
    assert all(n.startswith(("ev_EV3_", "ev_EV4_")) for n in ev_visits)
    assert walk_m == pytest.approx(14.0)


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


# --- config-driven build (configs/baseline_10f.yaml = v2 정본) -----------------


@pytest.fixture(scope="module")
def graph_10f():
    return build_from_config(load_config(CONFIG_10F))


def test_10f_config_matches_defaults(graph_10f) -> None:
    """The v2 config reproduces the builder defaults exactly (single source)."""
    g = graph_10f
    ref = build_building_graph()
    assert g.number_of_nodes() == ref.number_of_nodes()
    assert g.number_of_edges() == ref.number_of_edges()
    assert g.graph["ev_ids"] == ref.graph["ev_ids"]
    assert g.graph["ev_sides"] == ref.graph["ev_sides"]
    assert g.graph["shared_ev_ids"] == ref.graph["shared_ev_ids"]
    assert g.graph["office_positions_m"] == ref.graph["office_positions_m"]


def test_10f_graph_metadata(graph_10f) -> None:
    """Config-driven geometry + config-only metadata land on g.graph."""
    g = graph_10f
    assert g.graph["n_floors"] == 10
    assert g.graph["floor_height_m"] == pytest.approx(4.0)
    assert g.graph["corridor_length_m"] == pytest.approx(34.0)
    assert g.graph["corridor_mid_pos"] == 17
    assert g.graph["n_offices_per_floor"] == 12
    assert g.graph["occupancy_per_floor"] == 100
    assert g.graph["shared_ev_capacity_people_no_robot"] == 15
    assert g.graph["shared_ev_capacity_people_with_robot"] == 11


def test_10f_elevator_nodes_span_all_floors(graph_10f) -> None:
    all_evs = elevator_nodes(graph_10f)
    assert set(all_evs.keys()) == set(ALL_EV_IDS)
    for ev_id in ALL_EV_IDS:
        assert len(all_evs[ev_id]) == 12          # B2, B1, 1..10
        assert all_evs[ev_id][0] == f"ev_{ev_id}_B2"
        assert all_evs[ev_id][-1] == f"ev_{ev_id}_10"


def test_10f_offices_on_top_floor(graph_10f) -> None:
    offices = offices_on_floor(graph_10f, 10)
    assert offices == [f"floor_10_office_{i}" for i in range(12)]


def test_10f_lobby_pickup_zone_after_lobby_add() -> None:
    g = add_lobby_handoff_zones(build_from_config(load_config(CONFIG_10F)))
    assert g.nodes["lobby_robot_pickup_zone"]["floor"] == 1
    assert g.nodes["lobby_robot_pickup_zone"]["charging"] is True
