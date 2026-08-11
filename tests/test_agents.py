"""Smoke tests for H0 model construction and agent wiring."""

from __future__ import annotations

import pytest

from simulation.agents.building_manager import BuildingManagerAgent
from simulation.agents.control_system import ControlSystemAgent
from simulation.agents.customer import CustomerAgent
from simulation.agents.elevator import ElevatorAgent
from simulation.agents.handoff_rider import HandoffRiderAgent
from simulation.model import ROOT, BuildingHandoffModel, HandoffMode

DATA = ROOT / "data" / "data1" / "K50_1.json"


def test_data_present() -> None:
    if not DATA.exists():
        pytest.skip(f"data not present at {DATA}")


def test_all_agents_instantiate() -> None:
    m = BuildingHandoffModel()
    assert m.K == 50
    assert len(m.agents_of(CustomerAgent)) == 50
    assert len(m.elevators) == 4
    assert [ev.ev_id for ev in m.elevators] == ["EV1", "EV2", "EV3", "EV4"]
    assert [ev.shared_with_robot for ev in m.elevators] == [
        False, False, True, True
    ]
    assert isinstance(m.elevators[0], ElevatorAgent)
    assert isinstance(m.control, ControlSystemAgent)
    assert isinstance(m.manager, BuildingManagerAgent)
    assert len(m.rider_events) == 50
    assert m.n_floors == 10
    # the clock always starts at the window start; WHERE that is depends on the
    # window policy (R8), which this test is not about
    assert m.clock_sec == m.clock_start_sec
    assert m.start_time_sec == 41400.0


def test_customers_match_v4_mapping() -> None:
    m = BuildingHandoffModel()
    for o in m.orders:
        c = m.customer_by_ord_id[o.ord_id]
        assert c.floor == o.floor
        assert c.office_id == o.office_id
        assert c.dlv_deadline_sec == o.deadline_abs_sec
        assert c.delivered_at_sec is None


def test_service_times_from_riders_data() -> None:
    m = BuildingHandoffModel()
    assert m.service_time_for("BIKE") == 120.0
    assert m.service_time_for("WALK") == 120.0
    assert m.service_time_for("CAR") == 180.0


def test_only_h2_and_h3_are_still_unimplemented() -> None:
    """A2 opened H1_SYNC. H2/H3 must stay closed until their agents exist.

    An open gate on an unimplemented mode is worse than a crash: H2 and H3 would
    silently run as H1 (same rider, same fleet, no queue/balk, no locker) and
    produce numbers that look publishable.
    """
    for mode in (HandoffMode.H2_QUEUED, HandoffMode.H3_LOCKER):
        with pytest.raises(NotImplementedError):
            BuildingHandoffModel(mode=mode)


def test_h1_sync_is_open_and_builds_a_robot_fleet() -> None:
    m = BuildingHandoffModel(mode=HandoffMode.H1_SYNC)
    assert len(m.robots) == m.n_robots
    assert m.rider_cls is HandoffRiderAgent


def test_graph_has_lobby_zones_and_10_floors() -> None:
    m = BuildingHandoffModel()
    for zone in ("lobby_entry", "lobby_direct_corridor"):
        assert zone in m.graph
    assert "floor_10_office_11" in m.graph
    for ev_id in ("EV1", "EV2", "EV3", "EV4"):
        assert f"ev_{ev_id}_10" in m.graph
