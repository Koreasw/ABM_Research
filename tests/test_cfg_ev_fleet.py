"""V-CFG (v2): declarative EV fleet — config ↔ graph ↔ model ↔ KPI schema.

plan_h0_revision.md §1.2: the EV fleet is declared by config
(ev_corridor_positions_m / ev_sides / shared_ev_ids). simulation.model builds
one ElevatorAgent per declared car and derives the collector's per-EV series
names from the ids, so the graph, agent list, and KPI schema stay consistent
by construction. These tests pin that construction and the config validators.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from simulation.model import BuildingHandoffModel, HandoffMode
from simulation.space import build_from_config, load_config

ROOT = Path(__file__).resolve().parent.parent
CONFIG_10F = ROOT / "configs" / "baseline_10f.yaml"


@pytest.fixture(scope="module")
def cfg() -> dict:
    return load_config(CONFIG_10F)


def test_baseline_10f_declares_four_evs_cross_placed(cfg) -> None:
    b = cfg["building"]
    assert b["ev_corridor_positions_m"] == [16, 16, 18, 18]
    assert b["ev_sides"] == ["north", "south", "north", "south"]
    assert b["shared_ev_ids"] == ["EV3", "EV4"]


def test_graph_fleet_matches_config(cfg) -> None:
    g = build_from_config(cfg)
    assert g.graph["ev_ids"] == ("EV1", "EV2", "EV3", "EV4")
    accessible = {
        ev_id: g.nodes[f"ev_{ev_id}_1"]["robot_accessible"]
        for ev_id in g.graph["ev_ids"]
    }
    assert accessible == {"EV1": False, "EV2": False, "EV3": True, "EV4": True}


def test_model_fleet_and_kpi_schema_match_config(cfg) -> None:
    """One ElevatorAgent per declared EV; shared flags from shared_ev_ids;
    collector schema carries ev1..ev4 series (the V-CFG consistency core)."""
    model = BuildingHandoffModel(
        mode=HandoffMode.H0_DIRECT,
        config=cfg,
        scenario_path=ROOT / "data/data1/K50_1.json",
        dynamic_pool=True,
        floor_profile="uniform",
    )
    assert [ev.ev_id for ev in model.elevators] == ["EV1", "EV2", "EV3", "EV4"]
    assert [ev.shared_with_robot for ev in model.elevators] == [
        False, False, True, True
    ]
    df = model.datacollector.get_model_vars_dataframe()
    for i in (1, 2, 3, 4):
        for sfx in ("queue", "floor", "pax", "util_window"):
            assert f"ev{i}_{sfx}" in df.columns, f"missing series ev{i}_{sfx}"
    assert "ev5_queue" not in df.columns


@pytest.mark.parametrize(
    "mutate",
    [
        # ev_sides length mismatch
        lambda b: b.update(ev_sides=["north", "south"]),
        # unknown shared id
        lambda b: b.update(shared_ev_ids=["EV3", "EV9"]),
        # duplicate (position, side) slot
        lambda b: b.update(ev_corridor_positions_m=[16, 16, 16, 18],
                           ev_sides=["north", "south", "north", "south"]),
        # EV collides with a same-side office slot (12 is a north office)
        lambda b: b.update(ev_corridor_positions_m=[12, 16, 18, 18]),
        # off-grid EV position (1 m corridor grid)
        lambda b: b.update(ev_corridor_positions_m=[16.5, 16, 18, 18]),
        # empty fleet
        lambda b: b.update(ev_corridor_positions_m=[], ev_sides=[],
                           shared_ev_ids=[]),
    ],
)
def test_invalid_fleet_configs_raise(cfg, mutate) -> None:
    bad = copy.deepcopy(cfg)
    mutate(bad["building"])
    with pytest.raises(ValueError):
        build_from_config(bad)


def test_two_ev_config_still_builds(cfg) -> None:
    """The fleet size is not hardcoded: a 2-EV config builds a 2-EV graph
    (regression against reintroducing a fixed-count assumption)."""
    small = copy.deepcopy(cfg)
    small["building"]["ev_corridor_positions_m"] = [16, 18]
    small["building"]["ev_sides"] = ["north", "south"]
    small["building"]["shared_ev_ids"] = ["EV2"]
    g = build_from_config(small)
    assert g.graph["ev_ids"] == ("EV1", "EV2")
    assert g.nodes["ev_EV2_1"]["robot_accessible"] is True
