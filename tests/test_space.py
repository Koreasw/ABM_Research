"""Tests for simulation.space.build_building_graph (STAGE 2.1).

Verifies node/edge structure of the 5F Korean small-office baseline graph
per STAGE2_plan.md §5 + framework §5.
"""

from __future__ import annotations

import pytest

from simulation.space import (
    DEFAULT_OFFICE_POSITIONS_M,
    build_building_graph,
)


@pytest.fixture(scope="module")
def baseline_graph():
    return build_building_graph()


def test_baseline_node_count_breakdown(baseline_graph) -> None:
    """5F baseline: 6 floor_center + 84 corridor + 28 office + 12 EV + 2 support = 132."""
    g = baseline_graph
    by_type: dict[str, int] = {}
    for _, data in g.nodes(data=True):
        by_type[data["type"]] = by_type.get(data["type"], 0) + 1
    assert by_type["floor_center"] == 6        # B1F + 1F + 2F-5F
    assert by_type["corridor"] == 4 * 21        # 4 office floors x 21 positions (0..20)
    assert by_type["office"] == 4 * 7           # 4 floors x 7 offices
    assert by_type["elevator"] == 2 * 6         # 2 EVs x 6 floors
    assert by_type["support"] == 2              # b1f_charging + b1f_waiting
    assert g.number_of_nodes() == 6 + 84 + 28 + 12 + 2     # 132


def test_corridor_consecutive_connectivity(baseline_graph) -> None:
    """Corridor positions p and p+1 are connected by walk edges in both directions."""
    g = baseline_graph
    for floor in (2, 3, 4, 5):
        for p in range(20):  # 0..19 connect to p+1
            a = f"floor_{floor}_corr_{p}"
            b = f"floor_{floor}_corr_{p + 1}"
            assert g.has_edge(a, b), f"missing walk edge {a} -> {b}"
            assert g.has_edge(b, a), f"missing reverse walk edge {b} -> {a}"
            assert g[a][b]["walk"]["distance_m"] == pytest.approx(1.0)


def test_office_branch_positions_match_D2(baseline_graph) -> None:
    """D2: each office_N branches off corridor at positions [1, 4, 7, 10, 13, 16, 19] m."""
    g = baseline_graph
    for floor in (2, 3, 4, 5):
        for n_office, expected_pos in enumerate(DEFAULT_OFFICE_POSITIONS_M):
            office_node = f"floor_{floor}_office_{n_office}"
            corr_node = f"floor_{floor}_corr_{expected_pos}"
            assert g.has_edge(office_node, corr_node), (
                f"office {office_node} should branch to {corr_node}"
            )
            assert g[office_node][corr_node]["walk"]["distance_m"] == pytest.approx(3.0)
            data = g.nodes[office_node]
            assert data["corridor_position_m"] == expected_pos
            assert data["office_id"] == n_office


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


def test_floor_center_connected_to_all_evs_on_floor(baseline_graph) -> None:
    """Each floor_center has 4m walk edges to all EV nodes on that floor (and to corridor mid for office floors)."""
    g = baseline_graph
    for floor_str in ("B1", "1", "2", "3", "4", "5"):
        center = f"floor_{floor_str}_center"
        for ev_id in ("EV1", "EV2"):
            ev_node = f"ev_{ev_id}_{floor_str}"
            assert g.has_edge(center, ev_node)
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
        build_building_graph(office_positions_m=(1, 4, 7, 10, 13, 16, 30))  # out of range
    with pytest.raises(ValueError):
        build_building_graph(n_people_only_evs=0, n_shared_evs=0)
