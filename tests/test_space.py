"""Tests for simulation.space.build_building_graph (STAGE 2.1).

Verifies node/edge structure of the 5F Korean small-office baseline graph
per STAGE2_plan.md §5 + framework §5.
"""

from __future__ import annotations

import pytest

from simulation.space import (
    DEFAULT_EV_CORRIDOR_POSITIONS_M,
    DEFAULT_OFFICE_POSITIONS_M,
    DEFAULT_OFFICE_SIDES,
    build_building_graph,
)


@pytest.fixture(scope="module")
def baseline_graph():
    return build_building_graph()


def test_baseline_node_count_breakdown(baseline_graph) -> None:
    """5F baseline (floor plan): 6 floor_center + 80 corridor + 32 office + 12 EV + 2 support = 132."""
    g = baseline_graph
    by_type: dict[str, int] = {}
    for _, data in g.nodes(data=True):
        by_type[data["type"]] = by_type.get(data["type"], 0) + 1
    assert by_type["floor_center"] == 6        # B1F + 1F + 2F-5F
    assert by_type["corridor"] == 4 * 20        # 4 office floors x 20 positions (0..19)
    assert by_type["office"] == 4 * 8           # 4 floors x 8 offices (4 north + 4 south)
    assert by_type["elevator"] == 2 * 6         # 2 EVs x 6 floors
    assert by_type["support"] == 2              # b1f_charging + b1f_waiting
    assert g.number_of_nodes() == 6 + 80 + 32 + 12 + 2     # 132


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
    """Floor plan layout: 4 north offices [3, 8, 13, 17] + 4 south offices [3, 6, 14, 16],
    central EV hall at [11, 12]."""
    assert DEFAULT_OFFICE_POSITIONS_M == (3, 8, 13, 17, 3, 6, 14, 16)
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


def test_b1f_support_co_located_at_center(baseline_graph) -> None:
    """B1F charging and waiting are placed near floor_B1_center (2m walk) and adjacent to each other (1m)."""
    g = baseline_graph
    assert g.has_edge("b1f_charging", "floor_B1_center")
    assert g["b1f_charging"]["floor_B1_center"]["walk"]["distance_m"] == pytest.approx(2.0)
    assert g.has_edge("b1f_waiting", "floor_B1_center")
    assert g["b1f_waiting"]["floor_B1_center"]["walk"]["distance_m"] == pytest.approx(2.0)
    assert g.has_edge("b1f_charging", "b1f_waiting")
    assert g["b1f_charging"]["b1f_waiting"]["walk"]["distance_m"] == pytest.approx(1.0)


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
