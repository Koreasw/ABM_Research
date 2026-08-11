"""Step A1 — RobotAgent as an elevator passenger, and heterogeneous capacity.

Why so much of this is synthetic
--------------------------------
Three of A1's branches **cannot be reached by any corpus run** and are tested
by construction instead:

  * **Boarding refusal.** A deny needs >= 12 people in a shareable car. With
    four cars the v2 corpus rarely gets there, so `robot_board_denied == 0` in a
    smoke run proves nothing (계획서 §2 A1-2, §4-4). The stuffed-car cases below
    may be the only execution of that branch in the whole project.
  * **Low-SOC recovery.** At 1,300 Wh a delivery costs ~9-10 Wh, so a lunch-peak
    run ends at 43-90 % SOC and the 20 % threshold never fires (결정 #26). The
    chain is driven here from a hand-set SOC.
  * **People-only cars and basements.** Correct behaviour is that these *never
    happen*, so the only way to test the guard is to ask for them explicitly.

A2 has not lifted the mode gate yet, so no run builds robots on its own; these
tests attach a robot to an H0 model and drive it directly.
"""

from __future__ import annotations

import dataclasses

import pytest

from simulation.agents.robot import (
    COUNTER_NODE,
    HOME_NODE,
    REPORT_BUCKETS,
    RobotAgent,
    RobotLeg,
    RobotState,
)
from simulation.model import ROOT, BuildingHandoffModel, HandoffMode
from simulation.space import load_config

pytestmark = pytest.mark.vv

SCENARIO = "data/data1/K50_1.json"


@pytest.fixture
def model():
    """A paper-track H0 model, used purely as a building + elevator fixture."""
    return BuildingHandoffModel(
        mode=HandoffMode.H0_DIRECT,
        config=load_config(ROOT / "configs/baseline_10f.yaml"),
        scenario_path=SCENARIO,
        rng_seed=42,
        dynamic_pool=True,
        scenario_window=True,
        floor_profile="uniform",
        floor_seed=42,
    )


class _Person:
    """Minimal passenger implementing the elevator's duck-typed protocol."""

    kind = "pedestrian"

    def __init__(self, dest: int) -> None:
        self.ev_dest_floor = dest
        self.ev_wait_started_sec = 0.0
        self.boarded = False

    def on_board(self, ev) -> None:  # noqa: ANN001
        self.boarded = True

    def on_alight(self, ev, floor) -> None:  # noqa: ANN001
        self.boarded = False


def _shared(model) -> list:  # noqa: ANN001
    return [ev for ev in model.elevators if ev.shared_with_robot]


def _dedicated(model) -> list:  # noqa: ANN001
    return [ev for ev in model.elevators if not ev.shared_with_robot]


# ==========================================================================
# Heterogeneous capacity — R0-1 · R0-2
# ==========================================================================


def test_shared_ev_set_is_ev3_ev4(model) -> None:
    """Pin the declarative wiring the whole phase depends on."""
    assert [ev.ev_id for ev in _shared(model)] == ["EV3", "EV4"]
    assert [ev.ev_id for ev in _dedicated(model)] == ["EV1", "EV2"]
    assert all(ev.capacity_people == 15 for ev in model.elevators)
    assert all(ev.capacity_people_with_robot == 11 for ev in model.elevators)


def test_robot_may_not_board_a_people_only_car(model) -> None:
    """B3's defensive half, enforced at the door rather than only asserted after."""
    robot = RobotAgent(model)
    for ev in _dedicated(model):
        assert ev.can_board(robot) is False


@pytest.mark.parametrize("people, expected", [(10, True), (11, True), (12, False)])
def test_robot_boards_only_while_people_at_most_11(model, people, expected) -> None:
    """R0-2 boundary. 11 admits, 12 refuses — the off-by-one that would silently
    let a 16th occupant in."""
    ev = _shared(model)[0]
    ev.passengers = [_Person(5) for _ in range(people)]
    assert ev.can_board(RobotAgent(model)) is expected


def test_one_robot_per_car(model) -> None:
    """R0-1: a second robot is refused even in an otherwise empty car."""
    ev = _shared(model)[0]
    ev.passengers = [RobotAgent(model)]
    assert ev.can_board(RobotAgent(model)) is False


def test_people_limit_drops_to_11_while_a_robot_rides(model) -> None:
    """The eviction rule works in the other direction too: with a robot aboard
    the 12th person is refused, though 15 would fit without one."""
    ev = _shared(model)[0]
    ev.passengers = [RobotAgent(model)] + [_Person(5) for _ in range(11)]
    assert ev.can_board(_Person(5)) is False
    ev.passengers = [_Person(5) for _ in range(11)]
    assert ev.can_board(_Person(5)) is True


def test_capacity_violation_detector_covers_both_regimes(model) -> None:
    ev = _shared(model)[0]
    ev.passengers = [_Person(5) for _ in range(15)]
    assert ev._capacity_violated() is False
    ev.passengers.append(_Person(5))
    assert ev._capacity_violated() is True
    ev.passengers = [RobotAgent(model)] + [_Person(5) for _ in range(11)]
    assert ev._capacity_violated() is False
    ev.passengers.append(_Person(5))
    assert ev._capacity_violated() is True
    ev.passengers = [RobotAgent(model), RobotAgent(model)]
    assert ev._capacity_violated() is True


# ==========================================================================
# The deny path — reachable only by stuffing a car
# ==========================================================================


def test_full_car_denies_the_robot_and_counts_it(model) -> None:
    """The refusal branch, executed. Also pins that the robot stays queued:
    a denied robot must re-wait, not vanish (that would lose the order)."""
    ev = _shared(model)[0]
    ev.current_floor = 1
    ev.passengers = [_Person(5) for _ in range(12)]   # > 11 -> robot refused
    ev.car_calls = {5}

    robot = RobotAgent(model)
    robot.ev_dest_floor = 7
    robot.ev_wait_started_sec = model.clock_sec
    ev.register_hall_call(1, robot)

    ev._open_doors()

    assert ev.robot_board_denied == 1
    assert robot not in ev.passengers
    assert robot in ev.hall_calls[1]           # still queued for the next cycle
    assert robot.state is RobotState.IDLE      # untouched by the refusal


def test_direction_mismatch_is_not_counted_as_a_deny(model) -> None:
    """The metric must mean "the car was full", not "it was going the other way"
    — otherwise the deny profile in A7 is uninterpretable."""
    ev = _shared(model)[0]
    ev.current_floor = 5
    ev.direction = -1
    ev.passengers = [_Person(1)]               # committed downward
    robot = RobotAgent(model)
    robot.ev_dest_floor = 9                    # wants to go up
    robot.ev_wait_started_sec = model.clock_sec
    ev.register_hall_call(5, robot)

    ev._open_doors()

    assert ev.robot_board_denied == 0
    assert robot not in ev.passengers


def test_robot_boards_when_there_is_room(model) -> None:
    ev = _shared(model)[0]
    ev.current_floor = 1
    ev.passengers = [_Person(5) for _ in range(11)]   # exactly at the limit
    robot = RobotAgent(model)
    robot.ev_dest_floor = 7
    robot.ev_wait_started_sec = model.clock_sec
    robot.direction = 1
    ev.register_hall_call(1, robot)

    ev._open_doors()

    assert ev.robot_board_denied == 0
    assert robot in ev.passengers
    assert robot.state is RobotState.RIDING
    assert ev.boarding_log[-1]["kind"] == "robot"
    assert ev._capacity_violated() is False


# ==========================================================================
# FSM
# ==========================================================================


def _order(model, floor=7, office=2):  # noqa: ANN001
    return next(
        o for o in model.orders if o.floor == floor and o.office_id == office
    ) if any(
        o.floor == floor and o.office_id == office for o in model.orders
    ) else model.orders[0]


def test_robot_starts_home_idle_and_full(model) -> None:
    r = RobotAgent(model)
    assert r.node == HOME_NODE
    assert r.state is RobotState.IDLE
    assert r.is_available is True
    assert r.soc_pct == pytest.approx(100.0)
    assert r.kind == "robot"
    assert r.speed_mps == 1.0          # from config, not a local default
    assert r.capa == 100


def test_assign_walks_to_the_counter_then_waits_for_the_rider(model) -> None:
    r = RobotAgent(model)
    r.assign(model.orders[0])
    assert (r.state, r.leg) == (RobotState.MOVING, RobotLeg.TO_COUNTER)

    for _ in range(200):
        r.step()
        if r.state is RobotState.WAIT_RIDER:
            break
    assert r.state is RobotState.WAIT_RIDER
    assert r.node == COUNTER_NODE
    # home -> counter is 5 m (robot_pickup -2- floor_1_center -3- counter)
    assert r.walked_m == pytest.approx(5.0)
    assert r.is_available is False      # busy, not dispatchable


def test_full_delivery_chain_visits_every_state_in_order(model) -> None:
    """The whole relay, driven to completion, with the state sequence recorded.

    This is the A1 counterpart of the A4 golden path: it does not check absolute
    times (that is A4's job) but does check that the FSM is a *sequence* — no
    state skipped, none revisited out of order.
    """
    order = model.orders[0]
    r = RobotAgent(model)
    r.assign(order)

    seen: list[RobotState] = []

    def _sample() -> None:
        # Sampled after every sub-step, not once per tick: an idle car standing
        # at the robot's floor boards it inside the same tick the hall call is
        # registered, so WAIT_EV can last **zero ticks**. Tick-boundary sampling
        # would silently drop it and the sequence check would be vacuous there.
        if not seen or r.state is not seen[-1]:
            seen.append(r.state)

    _sample()
    for _ in range(4000):
        if r.state is RobotState.WAIT_RIDER and not r._rider_ready:
            r.notify_rider_ready(60.0)
        r.step()
        _sample()
        for ev in model.elevators:
            ev.step()
        _sample()
        model.clock_sec += model.dt
        if r.trips_completed:
            break

    assert r.trips_completed == 1
    assert r.state is RobotState.IDLE
    assert r.node == HOME_NODE
    assert seen == [
        RobotState.MOVING,        # to_counter
        RobotState.WAIT_RIDER,
        RobotState.HANDOFF,
        RobotState.MOVING,        # to_ev_up
        RobotState.WAIT_EV,
        RobotState.RIDING,
        RobotState.MOVING,        # to_office
        RobotState.DROP,
        RobotState.MOVING,        # to_ev_down
        RobotState.WAIT_EV,
        RobotState.RIDING,
        RobotState.MOVING,        # to_home
        RobotState.IDLE,
    ]
    assert model.customer_by_ord_id[order.ord_id].delivered_at_sec is not None


def test_robot_only_ever_rides_a_shared_car(model) -> None:
    """B3's positive form, over a full trip."""
    r = RobotAgent(model)
    r.assign(model.orders[0])
    for _ in range(4000):
        if r.state is RobotState.WAIT_RIDER and not r._rider_ready:
            r.notify_rider_ready(60.0)
        r.step()
        for ev in model.elevators:
            ev.step()
        model.clock_sec += model.dt
        for ev in _dedicated(model):
            assert r not in ev.passengers, f"robot boarded people-only {ev.ev_id}"
        if r.trips_completed:
            break
    assert r.trips_completed == 1


def test_assigning_a_basement_delivery_is_refused(model) -> None:
    """결정 #18 — robots never enter B1/B2. Refused at dispatch, not mid-trip."""
    basement_order = dataclasses.replace(model.orders[0], floor=-1)
    with pytest.raises(ValueError, match="basement"):
        RobotAgent(model).assign(basement_order)


def test_assigning_a_first_floor_delivery_is_refused(model) -> None:
    """F1 — the dispatch guard must agree with the FSM, which has no 1F path.

    Before the fix the guard was `floor < 1`, so a 1F order was accepted and
    then hung: `_register_call` computes `direction = -1` for a same-floor
    "up" leg, the robot rides 1F→1F, alights straight into TO_HOME and calls
    `_finish_trip` — `trips_completed` increments while `delivered_at_sec`
    stays None, so a full run can never satisfy `_delivery_complete()` and
    burns to the `max_overrun` cap. The assertions below re-run that chain to
    show it is still broken, which is exactly why the order must be refused.
    """
    first_floor_order = dataclasses.replace(model.orders[0], floor=1)
    with pytest.raises(ValueError, match="same-floor"):
        RobotAgent(model).assign(first_floor_order)

    # the FSM half of the claim, driven past the guard by hand: the "up" leg of
    # a same-floor delivery registers a DOWN hall call, which is the step that
    # sends the robot home instead of to the customer
    r = RobotAgent(model)
    r.order = first_floor_order
    r._depart_for_ev(1, first_floor_order.floor, RobotLeg.TO_EV_UP)
    for _ in range(200):
        r.step()
        if r.state is RobotState.WAIT_EV:
            break
    assert r.state is RobotState.WAIT_EV
    assert r.direction == -1, (
        "a same-floor up-leg still computes a DOWN hall call — the guard in "
        "assign() is the only thing keeping this out of a run"
    )


def test_busy_robot_refuses_a_second_order(model) -> None:
    """1 order / trip (R0-4) — the dispatcher must see this, not silently batch."""
    r = RobotAgent(model)
    r.assign(model.orders[0])
    with pytest.raises(ValueError, match="not dispatchable"):
        r.assign(model.orders[1])


def test_every_state_maps_to_a_report_bucket(model) -> None:
    """A new state must be given a bucket, not silently dropped from the figure."""
    covered = {s for members in REPORT_BUCKETS.values() for (s, _) in members}
    assert covered == set(RobotState)


# ==========================================================================
# Battery — 결정 #26
# ==========================================================================


def test_walking_bills_distance_and_waiting_bills_time(model) -> None:
    """The two drain terms, isolated."""
    r = RobotAgent(model)
    r.node = COUNTER_NODE                 # off the dock, so charging is off
    r.state = RobotState.WAIT_RIDER
    before = r.soc_wh
    r.step()
    assert r.soc_wh == pytest.approx(before - 1.0 / 60.0)   # 1.0 Wh/min * 1 s

    r2 = RobotAgent(model)
    r2.assign(model.orders[0])
    start = r2.soc_wh
    for _ in range(5):                    # 5 m at 1.0 m/s
        r2.step()
    assert r2.walked_m == pytest.approx(5.0)
    assert start - r2.soc_wh == pytest.approx(5.0 * 0.14)   # 0.14 Wh/m, no idle term


def test_docked_robot_charges_and_clamps_at_full(model) -> None:
    r = RobotAgent(model)
    r.soc_wh = r.battery.wh_for_soc_pct(50.0)
    r.step()
    # net = +13.0 Wh/min charge - 1.0 Wh/min idle = +12.0 Wh/min
    assert r.soc_wh == pytest.approx(r.battery.wh_for_soc_pct(50.0) + 12.0 / 60.0)
    r.soc_wh = r.battery.capacity_wh
    r.step()
    assert r.soc_wh == pytest.approx(r.battery.capacity_wh)   # never overfills


def test_low_soc_triggers_only_after_the_drop_completes(model) -> None:
    """결정 5: a robot never abandons food mid-delivery to go charge."""
    r = RobotAgent(model)
    r.assign(model.orders[0])
    r.soc_wh = r.battery.wh_for_soc_pct(5.0)      # far below the 20 % cut-off

    saw_drop = False
    for _ in range(4000):
        if r.state is RobotState.WAIT_RIDER and not r._rider_ready:
            r.notify_rider_ready(60.0)
        if r.state is RobotState.DROP:
            saw_drop = True
            # still en route: the trip is not abandoned despite SOC < 20 %
            assert r.return_reason == "idle"
        r.step()
        for ev in model.elevators:
            ev.step()
        model.clock_sec += model.dt
        if r.state is RobotState.CHARGING_BLOCKED:
            break
    assert saw_drop
    assert r.state is RobotState.CHARGING_BLOCKED
    assert r.node == HOME_NODE
    assert r.is_available is False        # blocked: dispatcher must skip it
    assert r.charge_events == 1
    assert model.customer_by_ord_id[model.orders[0].ord_id].delivered_at_sec is not None


def test_charging_blocked_releases_at_the_resume_threshold(model) -> None:
    r = RobotAgent(model)
    r.state = RobotState.CHARGING_BLOCKED
    r.soc_wh = r.battery.wh_for_soc_pct(20.0)
    ticks = 0
    while r.state is RobotState.CHARGING_BLOCKED and ticks < 10_000:
        r.step()
        ticks += 1
    assert r.state is RobotState.IDLE
    assert r.is_available is True
    assert r.soc_pct >= 20.0 + 20.0 - 1e-6
    # 20 -> 40 % = 260 Wh at a net 12.0 Wh/min = 21.7 min (13.0 gross = 20 min);
    # the idle draw is what makes it longer than the nameplate hour-rate.
    assert ticks == pytest.approx(260.0 / (12.0 / 60.0), rel=0.02)
    assert r.charge_blocked_sec == pytest.approx(ticks * model.dt)


def test_threshold_does_not_fire_over_a_realistic_trip_count(model) -> None:
    """결정 #26's headline: charging is *not* binding at the lunch-peak horizon.

    Pinned as a test so a future rate change that silently makes the battery
    binding shows up here rather than as a mystery in the Phase D results.
    """
    r = RobotAgent(model)
    for _ in range(25):                      # ~5 robots x 25 trips >= K100
        r.state, r.node, r.leg = RobotState.IDLE, HOME_NODE, None
        r.assign(model.orders[0])
        for _ in range(4000):
            if r.state is RobotState.WAIT_RIDER and not r._rider_ready:
                r.notify_rider_ready(60.0)
            r.step()
            for ev in model.elevators:
                ev.step()
            model.clock_sec += model.dt
            if r.trips_completed and r.state in (
                RobotState.IDLE, RobotState.CHARGING_BLOCKED
            ):
                break
    assert r.trips_completed == 25
    assert r.charge_events == 0
    assert r.soc_min_pct > r.battery.soc_low_pct
