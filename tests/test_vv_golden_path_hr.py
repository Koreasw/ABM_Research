"""Step A4 — HR golden-path hand calculation (2 cases, every stamp 0-tick exact).

Sibling of `test_vv_golden_path.py` (H0). Same method: zero pedestrians, a
synthetic scenario, a degenerate floor profile, and a hand-derived closed-form
chain that every recorded stamp must equal EXACTLY. What is new is that the
order's timeline now has two owners — the courier's record ends at the handoff,
the robot's leg record finishes the story — so the chain is checked across the
`ord_id` join, not inside one record.

THE THREE TRAPS THIS MODULE EXISTS TO PIN (HANDOFF_phase_a §3.4, 구현 로그 §A2-②):

  1. **Dispatch has NO tick lag.** `_inject_riders` runs at the top of
     `model.step` and `control.step` right after, so a courier that walks in on
     tick T is assigned a robot on tick T — and because the robot steps after
     the dispatcher, it also takes its first walking step on tick T.
  2. **The handoff HAS a one-tick lag.** The courier calls
     `notify_rider_ready` from its own step, by which time the robot has
     already stepped, so the robot enters HANDOFF one tick later. The two
     `handoff_started_sec` stamps (courier record, robot leg record) therefore
     differ by exactly one tick. That is a consequence of the tick order, and
     the tick order is load-bearing — reversing it deletes this lag.
  3. **`WAIT_EV` can be 0 ticks.** An idle car standing on the call floor opens
     and boards within the tick the hall call is registered, so both robot EV
     waits are exactly 0.0 here. A chain that assumes a positive lift wait is
     wrong, not conservative.

TICK GRAMMAR (dt = 1; w(d, v) = `_walk_ticks`, tt(x) = `_timer_ticks`). Whether
a leg costs w or w-1 ticks depends on WHERE the walk was planned in the step
order — this is the single most error-prone part of the derivation:

  * planned by an earlier actor in the same tick (dispatcher → robot, or the
    courier's own constructor) → the walk's first tick IS that tick
                                                       → arrive at T + w - 1
  * planned inside the walker's own step, in a branch the MOVING branch already
    passed (handoff end, drop end)                     → arrive at T + w
  * planned by a LATER actor (elevator `on_alight`; lifts step after robots)
                                                       → arrive at T + w

CHAIN, case 1 (one order, idle fleet). T_e = the tick the courier enters:

    courier   counter  = T_e + w(7.0, 1.2) − 1                        [= T_e+5]
    robot     counter  = T_e + w(5.0, 1.0) − 1                        [= T_e+4]
    handoff start (courier) = max(courier_counter + 1, robot_counter)
        (+1 because the courier sets WAIT_ROBOT in the arrival branch and only
         evaluates the WAIT_ROBOT branch from the NEXT tick)
    handoff start (robot)   = courier's + 1                           [trap 2]
    handoff end   (courier) = start + tt(60)
    courier exit            = handoff end + w(7.0, 1.2)
    handoff end   (robot)   = robot start + tt(60) ≡ depart for the lift
    robot at lift 1F        = depart + w(7.0, 1.0)
    board up                = same tick (idle car at 1F)              [trap 3]
    alight 7F               = board + tt(door) + tt(travel(1,7))
    at office               = alight + w(d_office, 1.0)
    DELIVERED               = at office + tt(30)  ≡ depart for the lift
    robot at lift 7F        = delivered + w(d_office, 1.0)
    board down              = same tick (the car it just left is idle there)
    alight 1F               = board + tt(door) + tt(travel(7,1))
    robot home              = alight + w(4.0, 1.0)

CHAIN, case 2 (two orders, ONE robot). Order 0 is case 1 verbatim — a second
order queued behind it must not perturb it. Order 1's courier reaches the
counter long before the robot is free, so its wait is set by the fleet:

    robot idle again   = order 0's `returned_at_sec`
    dispatched         = that + 1   (the robot goes IDLE in its own step, which
                                     is AFTER `control.step` in that same tick)
    robot at counter   = dispatched + w(5.0, 1.0) − 1
    handoff start      = robot at counter   (the courier is already waiting, and
                                             it steps after the robot)
    robot_wait_sec     = handoff start − counter arrival

GEOMETRY (asserted separately against the spec, not read off the graph):
robot zone → counter 5 m · counter → shared-lift landing 7 m · 1F lift → robot
zone 4 m · lift(18 m) → office = 1 m lift branch + |18 − pos| corridor + 3 m
office branch. Robot speed 1.0 m/s, courier 1.2 m/s.
"""

from __future__ import annotations

import json
import math

import pytest

from analysis.verify_h0 import _timer_ticks, _walk_ticks
from simulation.agents.robot import COUNTER_NODE, HOME_NODE
from simulation.agents.walker import shortest_walk_only_path
from simulation.elevator_physics import ElevatorKinematics
from simulation.floor_demand import FloorDemandModel
from simulation.model import ROOT, BuildingHandoffModel, HandoffMode
from simulation.space import add_lobby_handoff_zones, build_from_config, load_config

pytestmark = pytest.mark.vv

FLOOR = 7
BIKE_SPEED = 5.291
D0 = 1000.0                       # order 0 shop->drop road distance
D1 = 500.0                        # order 1 (contention case)
COOK = 900.0
SERVICE = 120.0                   # courier office service — NOT performed in H1
ORD_ABS = 41400.0
MARGIN = 60.0
HANDOFF_SEC = 60.0                # sd pinned to 0 below, so the draw is exact
ORD1_OFFSET = 100.0


# ------------------------------------------------------------- scenario setup


def _riders_row(stock: int) -> list:
    # [type, speed, capa, var_cost, fixed_cost, service_time, available]
    return ["BIKE", BIKE_SPEED, 100, 60, 5000, SERVICE, stock]


def _scenario_k1() -> dict:
    return {
        "name": "HRGP1",
        "K": 1,
        "RIDERS": [_riders_row(1)],
        "ORDERS": [[0, 0.0, 0, 0, 0, 0, COOK, 10, 5400.0]],
        "DIST": [[0.0, D0], [D0, 0.0]],
    }


def _scenario_k2() -> dict:
    """Two orders, two couriers — the contention is over the ROBOT, not the pool.

    A one-courier pool would serialize the orders outside the building and the
    second order would never queue at the counter, which is the thing case 2
    measures.
    """
    return {
        "name": "HRGP2",
        "K": 2,
        "RIDERS": [_riders_row(2)],
        "ORDERS": [
            [0, 0.0, 0, 0, 0, 0, COOK, 10, 5400.0],
            [1, ORD1_OFFSET, 0, 0, 0, 0, COOK, 10, 5400.0],
        ],
        "DIST": [
            [0.0, 50.0, D0, 60.0],
            [50.0, 0.0, 70.0, D1],
            [D0, 70.0, 0.0, 80.0],
            [60.0, D1, 80.0, 0.0],
        ],
    }


@pytest.fixture(scope="module")
def paths(tmp_path_factory):
    d = tmp_path_factory.mktemp("golden_hr")
    p1 = d / "HRGP1.json"
    p1.write_text(json.dumps(_scenario_k1()))
    p2 = d / "HRGP2.json"
    p2.write_text(json.dumps(_scenario_k2()))
    return {"k1": p1, "k2": p2}


def _hr_cfg() -> dict:
    """baseline_10f + zero pedestrians, short warm-up, degenerate 7F profile,
    and a DETERMINISTIC handoff (sd = 0), so the chain has no random term.

    The vertical mode is not searched for here (unlike the H0 module): the H1
    courier never uses the vertical system, so `sample_mode` cannot influence
    any stamp below.
    """
    cfg = load_config(ROOT / "configs" / "baseline_10f.yaml")
    cfg["pedestrian"]["arrival_rate_per_min"] = 0.0
    cfg["pedestrian"]["window_margin_sec"] = MARGIN
    cfg["simulation"]["warmup_sec"] = MARGIN
    cfg["demand"]["floor_profiles"]["single7"] = [0, 0, 0, 0, 0, 1, 0, 0, 0]
    cfg["handoff"]["service_sd_sec"] = 0.0
    return cfg


def _model(cfg: dict, scenario, **kw):  # noqa: ANN001
    params = {
        "mode": HandoffMode.H1_SYNC,
        "config": cfg,
        "scenario_path": scenario,
        "dynamic_pool": True,
        "scenario_window": True,
        "rng_seed": 7,
        "floor_profile": "single7",
        "floor_seed": 7,
        "audit": True,
    }
    params.update(kw)
    return BuildingHandoffModel(**params)


def _run(model, need: int, limit: int = 20_000) -> None:  # noqa: ANN001
    """Run until `need` ROBOT legs have been published.

    The courier record is not the finish line in H1 — it is filed at the
    handoff, long before the delivery (A2 함정 2).
    """
    while len(model.robot_leg_records) < need and model.tick_count < limit:
        model.step()
    assert len(model.robot_leg_records) == need, "run did not complete within limit"


# ------------------------------------------------------------ chain formulas


def _grid_ceil(x: float, start: float, dt: float = 1.0) -> float:
    return start + math.ceil((x - start) / dt - 1e-9) * dt


def _graph(cfg: dict):  # noqa: ANN001
    return add_lobby_handoff_zones(
        build_from_config(cfg), n_locker_compartments=cfg["locker"]["n_compartments"]
    )


def _dists(cfg: dict, office: int, ev_id: str = "EV3") -> dict[str, float]:
    g = _graph(cfg)
    return {
        "courier_counter": shortest_walk_only_path(g, "lobby_entry", COUNTER_NODE)[1],
        "robot_counter": shortest_walk_only_path(g, HOME_NODE, COUNTER_NODE)[1],
        "counter_ev": shortest_walk_only_path(g, COUNTER_NODE, f"ev_{ev_id}_1")[1],
        "ev_office": shortest_walk_only_path(
            g, f"ev_{ev_id}_{FLOOR}", f"floor_{FLOOR}_office_{office}"
        )[1],
        "ev_home": shortest_walk_only_path(g, f"ev_{ev_id}_1", HOME_NODE)[1],
    }


def _chain(cfg: dict, office: int, t_entered: float, t_assigned: float) -> dict:
    """The whole hand chain, from the module docstring. dt = 1."""
    dt = 1.0
    v_c = cfg["rider_process"]["walk_speed_mps"]
    v_r = cfg["robot"]["speed_mps"]
    drop = cfg["robot"]["service_time_drop_sec"]
    kin = ElevatorKinematics.from_config(cfg)
    d = _dists(cfg, office)

    w_cc = _walk_ticks(d["courier_counter"], v_c, dt)
    w_rc = _walk_ticks(d["robot_counter"], v_r, dt)
    w_ce = _walk_ticks(d["counter_ev"], v_r, dt)
    w_off = _walk_ticks(d["ev_office"], v_r, dt)
    w_home = _walk_ticks(d["ev_home"], v_r, dt)
    h = _timer_ticks(HANDOFF_SEC, dt)
    dr = _timer_ticks(drop, dt)
    lift_up = _timer_ticks(kin.door_open_close_sec, dt) + _timer_ticks(
        kin.travel_time_sec(1, FLOOR), dt
    )
    lift_dn = _timer_ticks(kin.door_open_close_sec, dt) + _timer_ticks(
        kin.travel_time_sec(FLOOR, 1), dt
    )

    courier_at_counter = t_entered + w_cc - 1
    robot_at_counter = t_assigned + w_rc - 1
    h_start_courier = max(courier_at_counter + 1, robot_at_counter)
    h_start_robot = h_start_courier + 1                       # trap 2
    h_end_courier = h_start_courier + h
    exit_courier = h_end_courier + w_cc

    depart_up = h_start_robot + h
    board_up = depart_up + w_ce
    alight_up = board_up + lift_up
    at_office = alight_up + w_off
    delivered = at_office + dr
    board_down = delivered + w_off
    alight_down = board_down + lift_dn
    home = alight_down + w_home

    return {
        "courier_at_counter": courier_at_counter,
        "handoff_started_sec": h_start_courier,
        "handoff_ended_sec": h_end_courier,
        "exited_at_sec": exit_courier,
        "t_lobby_sec": exit_courier - t_entered,
        "robot_wait_sec": h_start_courier - courier_at_counter,
        "leg_handoff_started_sec": h_start_robot,
        "delivered_at_sec": delivered,
        "returned_at_sec": home,
        "walked_m_courier": 2.0 * d["courier_counter"],
        "walked_m_robot": (
            d["robot_counter"] + d["counter_ev"] + 2.0 * d["ev_office"] + d["ev_home"]
        ),
        "walk_ticks_robot": w_rc + w_ce + 2 * w_off + w_home,
    }


def _profile_office(cfg: dict, floor_seed: int, ord_id: int = 0) -> int:
    fd = FloorDemandModel.from_config(cfg, "single7", floor_seed=floor_seed)
    floor, office = fd.sample(ord_id)
    assert floor == FLOOR
    return office


def _assert_order(model, ord_id: int, exp: dict) -> None:  # noqa: ANN001
    rec = next(r for r in model.rider_records if r["ord_id"] == ord_id)
    leg = model.robot_leg_records[ord_id]
    cust = model.customer_by_ord_id[ord_id]

    for key in ("handoff_started_sec", "handoff_ended_sec", "exited_at_sec",
                "t_lobby_sec", "robot_wait_sec"):
        assert rec[key] == exp[key], (ord_id, key, rec[key], exp[key])
    assert rec["handoff_sec"] == HANDOFF_SEC
    assert rec["vertical_mode"] == "handoff"
    # the courier never rides in H1: None, not 0.0 (a zero would average in)
    assert rec["ev_wait_up_sec"] is None and rec["ev_wait_down_sec"] is None
    assert math.isclose(rec["walked_m"], round(exp["walked_m_courier"], 2),
                        abs_tol=0.005)

    assert leg["handoff_started_sec"] == exp["leg_handoff_started_sec"]
    assert leg["handoff_ended_sec"] == exp["leg_handoff_started_sec"] + HANDOFF_SEC
    assert leg["delivered_at_sec"] == exp["delivered_at_sec"]
    assert leg["returned_at_sec"] == exp["returned_at_sec"]
    # trap 3: an idle car standing on the call floor boards within the tick
    assert leg["ev_wait_up_sec"] == 0.0
    assert leg["ev_wait_down_sec"] == 0.0

    assert cust.delivered_at_sec == exp["delivered_at_sec"]
    assert cust.t_e2e_sec == exp["delivered_at_sec"] - cust.ord_time_sec
    assert cust.sla_violation is False


# ------------------------------------------------- case 1: one order, idle fleet


def test_hr_golden_single_order(paths):
    cfg = _hr_cfg()
    model = _model(cfg, paths["k1"])
    office = _profile_office(cfg, floor_seed=7)
    order = model.orders[0]
    assert (order.floor, order.office_id) == (FLOOR, office)

    clock_start = ORD_ABS - MARGIN
    assert model.clock_start_sec == clock_start
    ready = ORD_ABS + COOK
    t_dispatch = _grid_ceil(ready, clock_start)
    arrival = t_dispatch + D0 / BIKE_SPEED
    t_entered = _grid_ceil(arrival, clock_start)

    _run(model, need=1)

    rec = model.rider_records[0]
    assert rec["entered_at_sec"] == t_entered
    # trap 1: assignment lands on the entry tick itself, not the one after
    leg = model.robot_leg_records[0]
    assert leg["assigned_at_sec"] == t_entered

    exp = _chain(cfg, office, t_entered, t_assigned=t_entered)
    _assert_order(model, 0, exp)
    assert leg["floor"] == FLOOR and leg["office_id"] == office

    robot = model.robots[leg["robot_id"] - model.robots[0].unique_id]
    assert robot.unique_id == leg["robot_id"]
    assert math.isclose(robot.distance_traveled_m, exp["walked_m_robot"],
                        abs_tol=1e-9)
    assert robot.trips_completed == 1


def test_hr_golden_single_order_battery(paths):
    """SOC at return, recomputed from the same closed form (§3.5).

    Distance bills the walking ticks; every OTHER tick of the trip bills idle
    time — including riding and both service timers, because the drive train is
    idle but the robot is powered (결정 5). The time term dominates, which is why
    a trip that walks 45 m still costs ~9 Wh.
    """
    cfg = _hr_cfg()
    model = _model(cfg, paths["k1"])
    office = _profile_office(cfg, floor_seed=7)
    ready = ORD_ABS + COOK
    clock_start = ORD_ABS - MARGIN
    t_entered = _grid_ceil(_grid_ceil(ready, clock_start) + D0 / BIKE_SPEED,
                           clock_start)
    _run(model, need=1)

    exp = _chain(cfg, office, t_entered, t_assigned=t_entered)
    bat = cfg["robot"]["battery"]
    trip_ticks = exp["returned_at_sec"] - t_entered + 1
    idle_ticks = trip_ticks - exp["walk_ticks_robot"]
    drain = (exp["walked_m_robot"] * bat["wh_per_m"]
             + idle_ticks * bat["wh_per_min_idle"] / 60.0)
    # the arrival-home tick is docked, so it also takes one tick of charge
    charged = bat["charge_wh_per_min"] / 60.0
    expected_wh = bat["capacity_wh"] - drain + charged

    robot = model.robots[model.robot_leg_records[0]["robot_id"]
                         - model.robots[0].unique_id]
    assert math.isclose(robot.soc_wh, expected_wh, abs_tol=1e-9), (
        robot.soc_wh, expected_wh
    )
    # §3.5: 1.3 kWh against a ~9 Wh delivery — the threshold cannot fire here
    assert bat["capacity_wh"] - robot.soc_wh < 15.0
    assert robot.charge_events == 0
    assert robot.soc_min_pct > bat["soc_low_pct"]


# ------------------------------------------- case 2: two orders, ONE robot


def test_hr_golden_two_orders_one_robot(paths):
    """Contention: order 1's courier waits at the counter for the fleet.

    The wait is not a fitted number — it is the robot's own return time plus
    the one-tick re-dispatch, which is why this case is worth a golden path at
    all. It is also the only place the FCFS queue is exercised end to end
    against absolute clock stamps.
    """
    cfg = _hr_cfg()
    model = _model(cfg, paths["k2"], n_robots=1)
    assert len(model.robots) == 1
    office0 = _profile_office(cfg, floor_seed=7, ord_id=0)
    office1 = _profile_office(cfg, floor_seed=7, ord_id=1)

    clock_start = ORD_ABS - MARGIN
    t_entered0 = _grid_ceil(
        _grid_ceil(ORD_ABS + COOK, clock_start) + D0 / BIKE_SPEED, clock_start
    )
    t_entered1 = _grid_ceil(
        _grid_ceil(ORD_ABS + ORD1_OFFSET + COOK, clock_start) + D1 / BIKE_SPEED,
        clock_start,
    )

    _run(model, need=2)

    # --- order 0: identical to case 1 despite the queued second order --------
    exp0 = _chain(cfg, office0, t_entered0, t_assigned=t_entered0)
    _assert_order(model, 0, exp0)

    # --- order 1: dispatched one tick after the robot got home ---------------
    t_assigned1 = exp0["returned_at_sec"] + 1
    assert model.robot_leg_records[1]["assigned_at_sec"] == t_assigned1
    exp1 = _chain(cfg, office1, t_entered1, t_assigned=t_assigned1)
    # the courier is already parked at the counter, so the robot's arrival —
    # not the courier's — sets the handoff instant
    assert exp1["handoff_started_sec"] == t_assigned1 + _walk_ticks(
        _dists(cfg, office1)["robot_counter"], cfg["robot"]["speed_mps"], 1.0
    ) - 1
    _assert_order(model, 1, exp1)

    # the whole point of the case: this wait is minutes, not ticks
    rec1 = next(r for r in model.rider_records if r["ord_id"] == 1)
    assert rec1["robot_wait_sec"] > 60.0
    assert model.robots[0].trips_completed == 2


def test_hr_second_order_waits_for_the_fleet_not_the_lift(paths):
    """The contention must be attributable: the courier's wait is robot-bound.

    If a future change made order 1 wait on an elevator instead, `robot_wait`
    would stay small while the delivery still slipped — so the two are pinned
    apart here rather than trusting one aggregate.
    """
    cfg = _hr_cfg()
    model = _model(cfg, paths["k2"], n_robots=1)
    _run(model, need=2)

    leg0, leg1 = model.robot_leg_records[0], model.robot_leg_records[1]
    rec0 = next(r for r in model.rider_records if r["ord_id"] == 0)
    rec1 = next(r for r in model.rider_records if r["ord_id"] == 1)
    w_rc = _walk_ticks(5.0, cfg["robot"]["speed_mps"], 1.0)

    # every second of the second courier's wait is accounted for by the fleet:
    # the robot finishing, one tick of re-dispatch, and its walk to the counter
    assert leg1["assigned_at_sec"] == leg0["returned_at_sec"] + 1
    assert rec1["handoff_started_sec"] == leg1["assigned_at_sec"] + w_rc - 1
    # ...and none of it is lift wait, on either order
    assert leg1["ev_wait_up_sec"] == 0.0 and leg1["ev_wait_down_sec"] == 0.0
    # the same courier work, an order of magnitude more dwell — this is the
    # quantity §3.6 promotes to a saturation indicator
    assert rec1["robot_wait_sec"] > 100.0 * rec0["robot_wait_sec"]


# --------------------------------------------------------- the three traps


def test_dispatch_has_no_tick_lag_but_the_handoff_has_one(paths):
    """Traps 1 and 2, stated as the one-tick difference they actually are."""
    cfg = _hr_cfg()
    model = _model(cfg, paths["k1"])
    _run(model, need=1)
    rec = model.rider_records[0]
    leg = model.robot_leg_records[0]
    assert leg["assigned_at_sec"] == rec["entered_at_sec"]        # trap 1
    assert leg["handoff_started_sec"] == rec["handoff_started_sec"] + 1  # trap 2


def test_robot_lift_waits_are_zero_not_positive(paths):
    """Trap 3 — asserted as an equality, since 'small' would hide a regression."""
    cfg = _hr_cfg()
    model = _model(cfg, paths["k1"])
    _run(model, need=1)
    leg = model.robot_leg_records[0]
    assert leg["ev_wait_up_sec"] == 0.0
    assert leg["ev_wait_down_sec"] == 0.0


# ----------------------------------------------- absolute geometry (spec-pinned)


def test_robot_geometry_matches_the_hand_spec():
    """Hard-coded from the design spec, NOT read off the graph.

    The graph-derived chain above moves with the building: if the robot zone
    were placed 8 m from the counter, every expectation would move with it and
    the golden path would still pass. These numbers come from
    `plan_h0_revision.md` §1.3 + `space.py`'s declared lobby distances, so they
    fail when the building itself is wrong.
    """
    cfg = _hr_cfg()
    g = _graph(cfg)
    assert shortest_walk_only_path(g, HOME_NODE, COUNTER_NODE)[1] == 5.0
    assert shortest_walk_only_path(g, COUNTER_NODE, "ev_EV3_1")[1] == 7.0
    assert shortest_walk_only_path(g, COUNTER_NODE, "ev_EV4_1")[1] == 7.0
    assert shortest_walk_only_path(g, "ev_EV3_1", HOME_NODE)[1] == 4.0
    assert shortest_walk_only_path(g, "lobby_entry", COUNTER_NODE)[1] == 7.0
    # lift(18 m) → office = 1 m lift branch + |18 − pos| corridor + 3 m branch.
    # The north bank's six corridor gaps are {4, 6, 9, 11, 14, 16} (mean 10.0).
    positions = cfg["building"]["office_positions_m"]
    gaps = sorted({abs(18 - p) for p in positions})
    assert gaps == [4, 6, 9, 11, 14, 16]
    assert sum(gaps) / len(gaps) == 10.0
    # `office_positions_m` is NOT in office_id order (office_1 sits at 7 m, not
    # at 2 m), so the two halves of the claim are checked separately: the built
    # north bank occupies exactly the declared positions, and each office is
    # exactly one lift branch + corridor gap + office branch from the car.
    north = [
        g.nodes[n] for n in g.nodes
        if n.startswith(f"floor_{FLOOR}_office_") and g.nodes[n]["side"] == "north"
    ]
    assert sorted(a["corridor_position_m"] for a in north) == sorted(positions[:6])
    for attrs in north:
        pos = attrs["corridor_position_m"]
        d = shortest_walk_only_path(
            g, f"ev_EV3_{FLOOR}", f"floor_{FLOOR}_office_{attrs['office_id']}"
        )[1]
        assert d == 1.0 + abs(18 - pos) + 3.0, (attrs["office_id"], pos, d)
    assert cfg["robot"]["speed_mps"] == 1.0
    assert cfg["rider_process"]["walk_speed_mps"] == 1.2
