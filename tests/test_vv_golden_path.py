"""V-GP golden-path hand-calculation tests (Stage V2, etc/plan_h0_verification.md §2 L1).

Zero pedestrians + a synthetic single-order scenario with a SINGLE rider type
(so type assignment is forced) drive the full pipeline; every recorded stamp
must equal a hand-derived closed-form chain EXACTLY (not just within the plan's
1-tick-per-segment allowance). Tick grid: clock_start = min(ORD_abs) - margin,
integer seconds (dt = 1).

Hand chain (dt ticks; w(d) = walk ticks of distance d at 1.2 m/s, faithful
float accumulation; tt(x) = countdown-timer ticks of x seconds):

  pre-building (dynamic): ready = ord_abs + cook; dispatch = first grid point
  >= ready; arrival = dispatch + D/v (continuous, sigma=0); entered = first
  grid point >= arrival. (static: arrival comes precomputed from the loader,
  same formula.)

  elevator, single rider, both EVs idle at 1F (tie -> EV1):
    T_board   = T_e + w(d1) - 1        # creation tick walks; hall call tick,
                                       #   IDLE car at floor opens+boards SAME
                                       #   tick -> ev_wait_up == 0.0
    T_alight  = T_board + tt(door) + tt(move(1,f))   # doors then kinematic move
    T_office  = T_alight + w(d2)       # alight tick only plans; walk starts +1
    T_deliver = T_office + tt(service)
    T_evback  = T_deliver + w(d2)      # EV1 went IDLE at f -> boards same tick,
    T_alight1 = T_evback + tt(door) + tt(move(1,f))  #   ev_wait_down == 0.0
    T_exit    = T_alight1 + w(d1)
  d1 = walk dist lobby_entry -> ev_EV1_1, d2 = ev_EV1_f -> office node.

  stairs (off-graph timers, access nodes lobby_direct_corridor / corr_14):
    T_stair   = T_e + w(s1) - 1
    T_corr    = T_stair + tt((f-1)*stair_sec)
    T_office  = T_corr + w(s2)
    T_deliver = T_office + tt(service)
    T_corrbk  = T_deliver + w(s2)
    T_stairbk = T_corrbk + tt((f-1)*stair_sec)
    T_exit    = T_stairbk + w(s1)
  s1 = lobby_entry -> lobby_direct_corridor, s2 = floor_f_corr_{mid} -> office
  (mid = corridor midpoint, g.graph["corridor_mid_pos"]).

  return_leg (dynamic, pool size 1, second order queued):
    release  = T_exit(order 0) + D0/v   (continuous; model applies it at the
                                         next grid point — tick quantization)
    dispatch(order 1) = first grid point >= release
    arrival(order 1)  = dispatch + D1/v

Cases: {EV, stairs} x {dynamic, static} + return_leg = 5 (plan L1). Floor is
pinned by a degenerate demand profile (all mass on 7F); the vertical mode is
pinned by searching vertical.mode_seed so sample_mode(0, 7) yields the desired
branch (mode stream is isolated, nothing else consumes it). audit=True on all
runs (V1 tick-level conservation asserts ride along for free).
"""

from __future__ import annotations

import json
import math

import pytest

from analysis.verify_h0 import _timer_ticks, _walk_ticks
from simulation.elevator_physics import ElevatorKinematics
from simulation.floor_demand import FloorDemandModel
from simulation.model import ROOT, BuildingHandoffModel, HandoffMode
from simulation.space import add_lobby_handoff_zones, build_from_config, load_config
from simulation.vertical_transport import VerticalTransportModel
from simulation.agents.walker import shortest_walk_only_path

FLOOR = 7
BIKE_SPEED = 5.291
D0 = 1000.0                       # order 0 shop->drop road distance
D1 = 500.0                        # order 1 (return_leg case)
COOK = 900.0
SERVICE = 120.0
ORD_ABS = 41400.0                 # ORD_TIME = 0 at lunch-peak start
MARGIN = 60.0                     # shortened warm-up (chain is margin-free)


# ------------------------------------------------------------- scenario setup


def _riders_row(stock: int) -> list:
    # [type, speed, capa, var_cost, fixed_cost, service_time, available]
    return ["BIKE", BIKE_SPEED, 100, 60, 5000, SERVICE, stock]


def _scenario_k1() -> dict:
    return {
        "name": "GP1",
        "K": 1,
        "RIDERS": [_riders_row(1)],
        # [ORD_ID, ORD_TIME, SHOP_LAT, SHOP_LON, DLV_LAT, DLV_LON, COOK, VOL, DEADLINE]
        "ORDERS": [[0, 0.0, 0, 0, 0, 0, COOK, 10, 5400.0]],
        "DIST": [[0.0, D0], [D0, 0.0]],
    }


def _scenario_k2() -> dict:
    return {
        "name": "GP2",
        "K": 2,
        "RIDERS": [_riders_row(1)],  # pool of exactly one rider
        "ORDERS": [
            [0, 0.0, 0, 0, 0, 0, COOK, 10, 5400.0],
            [1, 100.0, 0, 0, 0, 0, COOK, 10, 5400.0],
        ],
        # pickup i -> drop K+i: DIST[0][2] = D0, DIST[1][3] = D1
        "DIST": [
            [0.0, 50.0, D0, 60.0],
            [50.0, 0.0, 70.0, D1],
            [D0, 70.0, 0.0, 80.0],
            [60.0, D1, 80.0, 0.0],
        ],
    }


@pytest.fixture(scope="module")
def paths(tmp_path_factory):
    d = tmp_path_factory.mktemp("golden")
    p1 = d / "GP1.json"
    p1.write_text(json.dumps(_scenario_k1()))
    p2 = d / "GP2.json"
    p2.write_text(json.dumps(_scenario_k2()))
    mp = d / "GP1_floor_mapping_v4.json"
    mp.write_text(json.dumps(
        {"K": 1, "orders": [{"ord_id": 0, "floor": FLOOR, "office_id": 3}]}
    ))
    return {"k1": p1, "k2": p2, "mapping": mp}


def _golden_cfg(mode_for: str) -> dict:
    """baseline_10f + zero pedestrians, short margin, degenerate 7F profile,
    and a mode_seed searched so sample_mode(0, FLOOR) == mode_for."""
    cfg = load_config(ROOT / "configs" / "baseline_10f.yaml")
    cfg["pedestrian"]["arrival_rate_per_min"] = 0.0
    # Shorten the warm-up head under BOTH window policies so the tick grid
    # origin stays min(ORD_abs) - MARGIN: `window_margin_sec` is the legacy
    # knob, `warmup_sec` the delivery one (R8, plan_h0v21_window.md §2.1).
    # The chain under test is margin-free, so the head only sets the origin.
    cfg["pedestrian"]["window_margin_sec"] = MARGIN
    cfg["simulation"]["warmup_sec"] = MARGIN
    cfg["demand"]["floor_profiles"]["single7"] = [0, 0, 0, 0, 0, 1, 0, 0, 0]
    for seed in range(10_000):
        cfg["vertical"]["mode_seed"] = seed
        vt = VerticalTransportModel.from_config(cfg)
        if vt.sample_mode(0, FLOOR) == mode_for:
            return cfg
    raise AssertionError(f"no mode_seed in [0, 10000) yields {mode_for} at floor {FLOOR}")


def _run(model: BuildingHandoffModel, need: int, limit: int = 20_000) -> None:
    while len(model.rider_records) < need and model.tick_count < limit:
        model.step()
    assert len(model.rider_records) == need, "run did not complete within limit"


# ------------------------------------------------------------ chain formulas


def _grid_ceil(x: float, start: float, dt: float = 1.0) -> float:
    """First clock grid point (start + k*dt) at or after x."""
    return start + math.ceil((x - start) / dt - 1e-9) * dt


def _legs(cfg: dict, mode: str, office: int) -> tuple[float, float]:
    g = add_lobby_handoff_zones(
        build_from_config(cfg), n_locker_compartments=cfg["locker"]["n_compartments"]
    )
    office_node = f"floor_{FLOOR}_office_{office}"
    if mode == "elevator":
        d1 = shortest_walk_only_path(g, "lobby_entry", "ev_EV1_1")[1]
        d2 = shortest_walk_only_path(g, f"ev_EV1_{FLOOR}", office_node)[1]
    else:
        d1 = shortest_walk_only_path(g, "lobby_entry", "lobby_direct_corridor")[1]
        mid = g.graph["corridor_mid_pos"]
        d2 = shortest_walk_only_path(g, f"floor_{FLOOR}_corr_{mid}", office_node)[1]
    return d1, d2


def _expected_chain(cfg: dict, mode: str, office: int, t_entered: float) -> dict:
    """Hand-derived stamps from the module-docstring chain (dt = 1)."""
    dt = 1.0
    v_walk = cfg["rider_process"]["walk_speed_mps"]
    kin = ElevatorKinematics.from_config(cfg)
    d1, d2 = _legs(cfg, mode, office)
    w1 = _walk_ticks(d1, v_walk, dt)
    w2 = _walk_ticks(d2, v_walk, dt)
    s = _timer_ticks(SERVICE, dt)

    if mode == "elevator":
        vert = _timer_ticks(kin.door_open_close_sec, dt) + _timer_ticks(
            kin.travel_time_sec(1, FLOOR), dt
        )
    else:
        vert = _timer_ticks((FLOOR - 1) * cfg["vertical"]["stair_sec_per_floor"], dt)

    t_office = t_entered + (w1 - 1) + vert + w2
    t_deliver = t_office + s
    t_exit = t_deliver + w2 + vert + w1
    return {
        "delivered_at_sec": t_deliver,
        "exited_at_sec": t_exit,
        "t_lobby_sec": t_exit - t_entered,
        "t_e2e_sec": t_deliver - ORD_ABS,
        "walked_m": 2.0 * (d1 + d2),
    }


def _assert_chain(rec: dict, cfg: dict, mode: str, office: int, t_entered: float) -> None:
    exp = _expected_chain(cfg, mode, office, t_entered)
    assert rec["entered_at_sec"] == t_entered
    for key, val in exp.items():
        if key == "walked_m":
            assert math.isclose(rec[key], round(val, 2), abs_tol=0.005), (
                key, rec[key], val)
        else:
            assert rec[key] == val, (key, rec[key], val)
    if mode == "elevator":
        # idle car already at the hall-call floor boards the caller in the same
        # tick on both legs -> recorded waits are exactly zero
        assert rec["ev_wait_up_sec"] == 0.0
        assert rec["ev_wait_down_sec"] == 0.0
    else:
        assert rec["ev_wait_up_sec"] is None
        assert rec["ev_wait_down_sec"] is None
    assert rec["rider_type"] == "BIKE"
    assert rec["vertical_mode"] == mode
    assert rec["sla_violation"] is False


def _profile_office(cfg: dict, floor_seed: int, ord_id: int = 0) -> int:
    fd = FloorDemandModel.from_config(cfg, "single7", floor_seed=floor_seed)
    floor, office = fd.sample(ord_id)
    assert floor == FLOOR  # degenerate profile
    return office


# ------------------------------------------------------------------ dynamic


@pytest.mark.parametrize("mode", ["elevator", "stairs"])
def test_golden_dynamic(paths, mode):
    cfg = _golden_cfg(mode)
    model = BuildingHandoffModel(
        mode=HandoffMode.H0_DIRECT, config=cfg, scenario_path=paths["k1"],
        dynamic_pool=True, scenario_window=True, rng_seed=7,
        floor_profile="single7", floor_seed=7, audit=True,
    )
    office = _profile_office(cfg, floor_seed=7)
    order = model.orders[0]
    assert (order.floor, order.office_id, order.vertical_mode) == (FLOOR, office, mode)

    clock_start = ORD_ABS - MARGIN
    assert model.clock_start_sec == clock_start
    ready = ORD_ABS + COOK
    t_dispatch = _grid_ceil(ready, clock_start)          # == ready (on grid)
    arrival = t_dispatch + D0 / BIKE_SPEED
    t_entered = _grid_ceil(arrival, clock_start)

    _run(model, need=1)
    rec = model.rider_records[0]
    assert rec["ready_time_sec"] == ready
    assert rec["dispatch_time_sec"] == t_dispatch
    assert rec["rider_wait_sec"] == t_dispatch - ready
    assert math.isclose(rec["arrival_time_planned_sec"], arrival, rel_tol=1e-12)
    assert math.isclose(rec["horizontal_time_s"], D0 / BIKE_SPEED, rel_tol=1e-12)
    assert rec["was_fallback"] is False
    _assert_chain(rec, cfg, mode, office, t_entered)


# ------------------------------------------------------------------- static


@pytest.mark.parametrize("mode", ["elevator", "stairs"])
def test_golden_static(paths, mode):
    cfg = _golden_cfg(mode)
    model = BuildingHandoffModel(
        mode=HandoffMode.H0_DIRECT, config=cfg, scenario_path=paths["k1"],
        mapping_path=paths["mapping"], dynamic_pool=False,
        scenario_window=True, rng_seed=7, audit=True,
    )
    order = model.orders[0]
    assert (order.floor, order.office_id, order.vertical_mode) == (FLOOR, 3, mode)

    clock_start = ORD_ABS - MARGIN
    # static loader precomputes arrival = ord_abs + cook + D/v (sigma = 0,
    # single rider type forces BIKE) — the same closed form, no pool stage
    arrival = ORD_ABS + COOK + D0 / BIKE_SPEED
    assert math.isclose(order.arrival_time_sec, arrival, rel_tol=1e-12)
    t_entered = _grid_ceil(arrival, clock_start)

    _run(model, need=1)
    rec = model.rider_records[0]
    for absent in ("ready_time_sec", "dispatch_time_sec", "rider_wait_sec",
                   "was_fallback", "dist_m"):
        assert rec[absent] is None  # dynamic-pool provenance only
    assert math.isclose(rec["arrival_time_planned_sec"], arrival, rel_tol=1e-12)
    _assert_chain(rec, cfg, mode, 3, t_entered)


# --------------------------------------------------------------- return leg


def test_golden_return_leg(paths):
    cfg = _golden_cfg("elevator")
    model = BuildingHandoffModel(
        mode=HandoffMode.H0_DIRECT, config=cfg, scenario_path=paths["k2"],
        dynamic_pool=True, return_leg=True, scenario_window=True, rng_seed=7,
        floor_profile="single7", floor_seed=7, audit=True,
    )
    office0 = _profile_office(cfg, floor_seed=7, ord_id=0)
    assert model.orders[0].vertical_mode == "elevator"

    clock_start = ORD_ABS - MARGIN
    ready0 = ORD_ABS + COOK
    t_dispatch0 = _grid_ceil(ready0, clock_start)
    t_entered0 = _grid_ceil(t_dispatch0 + D0 / BIKE_SPEED, clock_start)
    exp0 = _expected_chain(cfg, "elevator", office0, t_entered0)
    t_exit0 = exp0["exited_at_sec"]

    ready1 = ORD_ABS + 100.0 + COOK          # while the only rider is out
    assert ready1 < t_exit0                  # order 1 must queue

    # return leg: the rider re-enters the pool one road trip after exiting,
    # applied at the next tick boundary; the queued order dispatches then
    release = t_exit0 + D0 / BIKE_SPEED
    t_dispatch1 = _grid_ceil(release, clock_start)

    _run(model, need=2)
    rec0 = next(r for r in model.rider_records if r["ord_id"] == 0)
    rec1 = next(r for r in model.rider_records if r["ord_id"] == 1)

    # order 0's in-building chain is untouched by return_leg
    assert rec0["dispatch_time_sec"] == t_dispatch0
    _assert_chain(rec0, cfg, "elevator", office0, t_entered0)

    assert rec1["ready_time_sec"] == ready1
    assert rec1["dispatch_time_sec"] == t_dispatch1
    assert rec1["rider_wait_sec"] == t_dispatch1 - ready1
    assert rec1["rider_wait_sec"] > 0
    assert rec1["was_fallback"] is False     # single type, rank 0 by definition
    assert math.isclose(
        rec1["arrival_time_planned_sec"], t_dispatch1 + D1 / BIKE_SPEED,
        rel_tol=1e-12,
    )
    # run out the final return leg: pool must be fully restored (audit=True
    # asserted the per-tick conservation throughout)
    while model.pending_releases and model.tick_count < 30_000:
        model.step()
    assert model.rider_pool.free["BIKE"] == 1
