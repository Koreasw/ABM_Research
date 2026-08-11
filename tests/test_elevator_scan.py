"""Unit tests for ElevatorAgent SCAN behavior (plan_abm_baseline_h0.md §D).

Uses the real BuildingHandoffModel as the harness (pedestrian rate zeroed,
rider events cleared) so kinematics/clock/graph wiring is exercised, with
stub passengers implementing the elevator's passenger protocol.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from simulation.model import ROOT, BuildingHandoffModel
from simulation.space import load_config

DATA = ROOT / "data" / "data1" / "K50_1.json"


def _quiet_model() -> BuildingHandoffModel:
    config = load_config(ROOT / "configs" / "baseline_10f.yaml")
    config["pedestrian"]["arrival_rate_per_min"] = 0.0
    m = BuildingHandoffModel(config=config)
    m.rider_events.clear()  # elevators-only testbed
    return m


class StubPassenger:
    kind = "stub"

    def __init__(self, model: BuildingHandoffModel, dest_floor: int) -> None:
        self.model = model
        self.ev_dest_floor = dest_floor
        self.ev_wait_started_sec = model.clock_sec
        self.boarded_at_sec: float | None = None
        self.alighted_floor: int | None = None
        self.alighted_at_sec: float | None = None
        self.node: str | None = None

    def on_board(self, ev) -> None:  # noqa: ANN001
        self.boarded_at_sec = self.model.clock_sec

    def on_alight(self, ev, floor: int) -> None:  # noqa: ANN001
        self.alighted_floor = floor
        self.alighted_at_sec = self.model.clock_sec
        self.node = f"ev_{ev.ev_id}_{floor}"


def _run(m: BuildingHandoffModel, ticks: int) -> None:
    for _ in range(ticks):
        m.step()


def test_data_present() -> None:
    if not DATA.exists():
        pytest.skip(f"data not present at {DATA}")


def test_single_call_pickup_and_delivery() -> None:
    m = _quiet_model()
    ev = m.elevators[0]
    p = StubPassenger(m, dest_floor=5)
    ev.register_hall_call(1, p)
    _run(m, 60)
    assert p.boarded_at_sec is not None
    assert p.alighted_floor == 5
    assert p.node == "ev_EV1_5"
    # EV idles in place after the last call (no parking floor)
    assert ev.state == ev.IDLE
    assert ev.current_floor == 5
    assert p.alighted_at_sec > p.boarded_at_sec


def test_scan_upward_sweep_serves_near_floor_first() -> None:
    m = _quiet_model()
    ev = m.elevators[0]
    p3 = StubPassenger(m, dest_floor=3)
    p7 = StubPassenger(m, dest_floor=7)
    ev.register_hall_call(1, p3)
    ev.register_hall_call(1, p7)
    _run(m, 120)
    assert p3.alighted_floor == 3
    assert p7.alighted_floor == 7
    assert p3.alighted_at_sec < p7.alighted_at_sec  # 3F stop precedes 7F


def test_direction_incompatible_waiter_served_on_return_sweep() -> None:
    """EV sweeping up must NOT pick up a down-bound waiter en route; it boards
    them on the way back (SCAN correctness, no starvation)."""
    m = _quiet_model()
    ev = m.elevators[0]
    up_pax = StubPassenger(m, dest_floor=5)     # boards at 1F, rides up
    down_pax = StubPassenger(m, dest_floor=1)   # waits at 3F to go down
    ev.register_hall_call(1, up_pax)
    ev.register_hall_call(3, down_pax)
    _run(m, 200)
    assert up_pax.alighted_floor == 5
    assert down_pax.alighted_floor == 1
    # down-bound boarding must happen after the up passenger was dropped at 5
    assert down_pax.boarded_at_sec > up_pax.alighted_at_sec


def test_capacity_overflow_waiter_remains_and_is_served_later() -> None:
    m = _quiet_model()
    ev = m.elevators[0]
    pax = [StubPassenger(m, dest_floor=5) for _ in range(16)]  # cap = 15
    for p in pax:
        ev.register_hall_call(1, p)
    _run(m, 10)
    n_onboard_first = sum(1 for p in pax if p.boarded_at_sec is not None)
    assert n_onboard_first == 15          # 16th left waiting
    assert ev.queue_length() == 1
    _run(m, 300)
    assert all(p.alighted_floor == 5 for p in pax)   # eventually all served
    assert ev.capacity_violations == 0
    assert ev.alight_count == 16


def test_min_wait_choice_prefers_less_loaded_ev() -> None:
    m = _quiet_model()
    ev1, ev2 = m.elevators[0], m.elevators[1]
    # load EV1 with pending work far away; the other three stay idle, so the
    # min-wait tie among EV2/EV3/EV4 resolves to the lowest ev_id (EV2)
    busy = [StubPassenger(m, dest_floor=9) for _ in range(3)]
    for p in busy:
        ev1.register_hall_call(9, p)
    chosen = m.control.choose_elevator(from_floor=1, to_floor=5)
    assert chosen is not ev1
    assert chosen is ev2


def test_idle_elevator_opens_doors_for_call_at_own_floor() -> None:
    m = _quiet_model()
    ev = m.elevators[0]
    assert ev.current_floor == 1
    p = StubPassenger(m, dest_floor=4)
    ev.register_hall_call(1, p)
    _run(m, 2)
    # no travel needed: door cycle starts immediately, passenger already aboard
    assert ev.state == ev.DOORS
    assert p.boarded_at_sec is not None


def test_boarding_log_and_conservation() -> None:
    m = _quiet_model()
    ev = m.elevators[1]
    pax = [StubPassenger(m, dest_floor=f) for f in (2, 4, 6)]
    for p in pax:
        ev.register_hall_call(1, p)
    _run(m, 200)
    assert len(ev.boarding_log) == 3
    assert ev.alight_count == 3
    assert all(b["wait_sec"] >= 0.0 for b in ev.boarding_log)
    assert all(b["kind"] == "stub" for b in ev.boarding_log)
