"""Tests for the dynamic rider-pool path S1~S3 (etc/plan_rider_pool_dynamic.md).

S1: cost / distance-priority functions (analysis.rider_arrival_model)
S2: load_dispatch_v5 dispatch timeline (analysis.scenario_loader)
S3: RiderPool deduct / release / FIFO queue (simulation.rider_pool)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from analysis.load_data import Rider, load_scenario, pickup_drop_distance
from analysis.rider_arrival_model import (
    compute_w_R_krw_per_h,
    delivery_cost_krw,
    type_priority,
)
from analysis.scenario_loader import DispatchOrder, load_dispatch_v5, load_replay_v4
from simulation.rider_pool import RiderPool
from simulation.space import load_config

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "data1" / "K50_1.json"
MAPPING = ROOT / "data" / "floor_mapping" / "K50_1_floor_mapping_v4.json"
CONFIG_PATH = ROOT / "configs" / "baseline_10f.yaml"
START = 11.5 * 3600.0

# data1's fixed RIDERS parameters (identical across scenarios)
BIKE = Rider("BIKE", 5.291005291005291, 100, 60, 5000, 120, 10)
WALK = Rider("WALK", 1.3227513227513228, 70, 30, 5000, 120, 15)
CAR = Rider("CAR", 4.2328042328042335, 200, 100, 5000, 180, 50)
RIDERS = [BIKE, WALK, CAR]


def _order(vol: int = 30, dist_m: float = 1500.0, ord_id: int = 0) -> DispatchOrder:
    return DispatchOrder(
        ord_id=ord_id,
        ready_time_sec=START,
        ord_time_abs_sec=START,
        deadline_abs_sec=START + 3600.0,
        cook_time_sec=600.0,
        vol=vol,
        dist_m=dist_m,
        floor=3,
        office_id=1,
        vertical_mode="elevator",
    )


# ------------------------------------------------------------------------ S1


def test_delivery_cost_matches_linear_formula() -> None:
    for r in RIDERS:
        for d in (0.0, 100.0, 1814.0, 4639.0):
            w_per_sec = compute_w_R_krw_per_h(r) / 3600.0
            expected = w_per_sec * (d / r.speed_mps + r.service_time_sec)
            assert delivery_cost_krw(r, d) == pytest.approx(expected)


def test_type_priority_three_distance_regimes() -> None:
    # etc/rider_type_assignment_inventory.md §3
    assert type_priority(RIDERS, 30.0) == ["WALK", "BIKE", "CAR"]
    assert type_priority(RIDERS, 100.0) == ["BIKE", "WALK", "CAR"]
    assert type_priority(RIDERS, 300.0) == ["BIKE", "WALK", "CAR"]
    assert type_priority(RIDERS, 500.0) == ["BIKE", "CAR", "WALK"]
    assert type_priority(RIDERS, 5000.0) == ["BIKE", "CAR", "WALK"]


def test_crossover_distances_53m_and_400m() -> None:
    # WALK/BIKE flip at ~52.9 m; WALK/CAR flip at ~399.8 m
    assert type_priority(RIDERS, 52.0)[0] == "WALK"
    assert type_priority(RIDERS, 54.0)[0] == "BIKE"
    assert type_priority(RIDERS, 399.0)[1] == "WALK"
    assert type_priority(RIDERS, 401.0)[1] == "CAR"


def test_bike_dominates_car_at_every_distance() -> None:
    for d in range(0, 10001, 250):
        assert delivery_cost_krw(BIKE, d) < delivery_cost_krw(CAR, d)


# ------------------------------------------------------------------------ S2


@pytest.fixture(scope="module")
def dispatch_events() -> list[DispatchOrder]:
    if not DATA.exists():
        pytest.skip(f"data not present at {DATA}")
    config = load_config(CONFIG_PATH)
    return load_dispatch_v5(DATA, MAPPING, config, start_time_sec=START)


def test_dispatch_v5_count_and_sorted(dispatch_events: list[DispatchOrder]) -> None:
    assert len(dispatch_events) == 50
    ready = [e.ready_time_sec for e in dispatch_events]
    assert ready == sorted(ready)


def test_dispatch_v5_ready_time_is_ord_plus_cook(
    dispatch_events: list[DispatchOrder],
) -> None:
    for e in dispatch_events:
        assert e.ready_time_sec == pytest.approx(
            e.ord_time_abs_sec + e.cook_time_sec
        )


def test_dispatch_v5_dist_matches_dist_matrix(
    dispatch_events: list[DispatchOrder],
) -> None:
    scenario = load_scenario(DATA)
    pdd = pickup_drop_distance(DATA)
    dist_by_ord = {o.ord_id: float(pdd[i]) for i, o in enumerate(scenario.orders)}
    for e in dispatch_events:
        assert e.dist_m == pytest.approx(dist_by_ord[e.ord_id])
        assert e.dist_m > 0


def test_dispatch_v5_floor_office_mode_match_v4(
    dispatch_events: list[DispatchOrder],
) -> None:
    """Type-independent fields must be bit-identical to the static v4 path."""
    config = load_config(CONFIG_PATH)
    v4 = {o.ord_id: o for o in load_replay_v4(DATA, MAPPING, config,
                                              start_time_sec=START)}
    for e in dispatch_events:
        o = v4[e.ord_id]
        assert e.floor == o.floor
        assert e.office_id == o.office_id
        assert e.vertical_mode == o.vertical_mode
        assert e.deadline_abs_sec == pytest.approx(o.deadline_abs_sec)
        assert e.vol == o.vol


# ------------------------------------------------------------------------ S3


def test_pool_initial_stock_from_available_number() -> None:
    pool = RiderPool(RIDERS)
    assert pool.free == {"BIKE": 10, "WALK": 15, "CAR": 50}


def test_pool_capa_filter_forces_car_and_raises() -> None:
    pool = RiderPool(RIDERS)
    t, fb = pool.try_dispatch(_order(vol=150, dist_m=100.0))  # only CAR fits
    assert t == "CAR" and fb is False  # CAR is rank 0 among eligible={CAR}
    with pytest.raises(ValueError):
        pool.try_dispatch(_order(vol=250))


def test_pool_cascade_bike_then_fallback() -> None:
    pool = RiderPool([Rider("BIKE", BIKE.speed_mps, 100, 60, 5000, 120, 1),
                      WALK, CAR])
    t1, fb1 = pool.try_dispatch(_order(dist_m=1500.0))
    assert (t1, fb1) == ("BIKE", False)
    # BIKE exhausted: far order falls back to CAR, near order to WALK
    t2, fb2 = pool.try_dispatch(_order(dist_m=1500.0))
    assert (t2, fb2) == ("CAR", True)
    t3, fb3 = pool.try_dispatch(_order(dist_m=200.0))
    assert (t3, fb3) == ("WALK", True)
    assert pool.fallback_count == 2


def test_pool_exhaustion_queue_and_release_fifo() -> None:
    pool = RiderPool([Rider("BIKE", BIKE.speed_mps, 100, 60, 5000, 120, 1),
                      Rider("WALK", WALK.speed_mps, 70, 30, 5000, 120, 1),
                      Rider("CAR", CAR.speed_mps, 200, 100, 5000, 180, 1)])
    for _ in range(3):
        assert pool.try_dispatch(_order(dist_m=1500.0)) is not None
    # all exhausted -> queue two orders FIFO
    o_a, o_b = _order(dist_m=1500.0, ord_id=101), _order(dist_m=1500.0, ord_id=102)
    assert pool.try_dispatch(o_a) is None
    pool.enqueue(o_a)
    assert pool.try_dispatch(o_b) is None
    pool.enqueue(o_b)
    assert len(pool.waiting) == 2
    # release one BIKE -> head of queue gets it (FIFO)
    out = pool.release("BIKE")
    assert [(o.ord_id, t) for o, t, _ in out] == [(101, "BIKE")]
    assert len(pool.waiting) == 1
    out = pool.release("CAR")
    assert [(o.ord_id, t) for o, t, _ in out] == [(102, "CAR")]
    assert not pool.waiting


def test_pool_queue_skip_respects_capa() -> None:
    """A freed type unusable by the queue head serves the next feasible order."""
    pool = RiderPool([Rider("WALK", WALK.speed_mps, 70, 30, 5000, 120, 1),
                      Rider("CAR", CAR.speed_mps, 200, 100, 5000, 180, 1)])
    assert pool.try_dispatch(_order(dist_m=1500.0)) == ("CAR", False)
    assert pool.try_dispatch(_order(dist_m=100.0)) == ("WALK", False)
    big, small = _order(vol=150, ord_id=201), _order(vol=30, ord_id=202)
    pool.enqueue(big)   # head needs CAR
    pool.enqueue(small)
    out = pool.release("WALK")  # WALK can't serve head -> serves small
    assert [(o.ord_id, t) for o, t, _ in out] == [(202, "WALK")]
    assert [o.ord_id for o in pool.waiting] == [201]


def test_pool_conservation_and_release_overflow() -> None:
    pool = RiderPool(RIDERS)
    orders = [_order(dist_m=d, ord_id=i) for i, d in enumerate(
        [100.0, 500.0, 1500.0, 3000.0, 250.0])]
    types = [pool.try_dispatch(o)[0] for o in orders]
    for t in pool.initial:
        assert pool.free[t] + pool.busy(t) == pool.initial[t]
        assert 0 <= pool.free[t] <= pool.initial[t]
    for t in types:
        pool.release(t)
    assert pool.free == pool.initial
    with pytest.raises(ValueError):
        pool.release("BIKE")  # already at initial
