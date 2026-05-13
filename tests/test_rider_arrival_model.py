"""Tests for analysis.rider_arrival_model (framework §2.5 calibration)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from analysis.load_data import Rider, load_scenario
from analysis.rider_arrival_model import (
    RiderArrivalEvent,
    compute_w_R_krw_per_h,
    estimate_lambda_rider_K,
    sample_rider_arrivals,
)

DATA = Path(__file__).resolve().parent.parent / "data" / "data1"
K50_1 = DATA / "K50_1.json"
K50_2 = DATA / "K50_2.json"
START = 11.5 * 3600.0


def test_data_present() -> None:
    if not K50_1.exists():
        pytest.skip(f"data not present at {K50_1}")


def test_compute_w_R_matches_formula() -> None:
    r = Rider(
        type="BIKE",
        speed_mps=5.29,
        capa=100,
        var_cost=60.0,
        fixed_cost=5000.0,
        service_time_sec=120.0,
        available_number=10,
    )
    # 5000 + 60 * 50 = 8000
    assert compute_w_R_krw_per_h(r, throughput_per_rider_h=50.0) == pytest.approx(8000.0)


def test_event_count_matches_K() -> None:
    events = sample_rider_arrivals(K50_1, seed=42)
    assert len(events) == 50
    for e in events:
        assert isinstance(e, RiderArrivalEvent)


def test_events_sorted_by_arrival_time() -> None:
    events = sample_rider_arrivals(K50_1, seed=42)
    times = [e.t_arrival_sec for e in events]
    assert times == sorted(times)


def test_arrival_time_decomposition_holds_for_zero_noise() -> None:
    """With sigma_eps=0, t_arrival = start + ORD_TIME + COOK_TIME + DIST/speed."""
    scenario = load_scenario(K50_1)
    pdd_lookup = scenario.dist[
        np.arange(scenario.K), np.arange(scenario.K) + scenario.K
    ]
    events = sample_rider_arrivals(K50_1, seed=42, sigma_eps=0.0)
    by_id = {e.order_id: e for e in events}

    for order in scenario.orders:
        e = by_id[order.ord_id]
        rider = next(r for r in scenario.riders if r.type == e.rider_type)
        expected = (
            START
            + order.ord_time_sec
            + order.cook_time_sec
            + pdd_lookup[order.ord_id] / rider.speed_mps
        )
        assert e.t_arrival_sec == pytest.approx(expected, rel=1e-9, abs=1e-6)


def test_rider_type_distribution_follows_available_number() -> None:
    """K=50 is small; aggregate across 50 seeds for a stable distribution.

    Weights are BIKE:10, WALK:15, CAR:50 (total 75). Expected p_CAR ~ 0.667.
    """
    types: list[str] = []
    for s in range(50):
        events = sample_rider_arrivals(K50_1, seed=s)
        types.extend(e.rider_type for e in events)
    n = len(types)
    p_car = sum(1 for t in types if t == "CAR") / n
    p_bike = sum(1 for t in types if t == "BIKE") / n
    p_walk = sum(1 for t in types if t == "WALK") / n
    # 50 scenarios x 50 orders = 2500 samples; expect within ~0.05 of weights
    assert abs(p_bike - 10 / 75) < 0.05
    assert abs(p_walk - 15 / 75) < 0.05
    assert abs(p_car - 50 / 75) < 0.05


def test_noise_mean_close_to_one() -> None:
    """Unbiased lognormal: E[travel * eps] / travel should ~ 1 across many draws."""
    scenario = load_scenario(K50_1)
    pdd = scenario.dist[np.arange(scenario.K), np.arange(scenario.K) + scenario.K]

    # Deterministic baseline travel for a fixed type assignment
    deterministic_events = sample_rider_arrivals(K50_1, seed=42, sigma_eps=0.0)
    base_travel = np.array(
        [
            e.t_arrival_sec - START - o.ord_time_sec - o.cook_time_sec
            for e, o in zip(deterministic_events, scenario.orders, strict=False)
        ]
    )
    # NOTE: the deterministic_events are re-sorted by t_arrival, so the order doesn't match.
    # Instead, build a per-order lookup.
    det_by_id = {e.order_id: e for e in deterministic_events}
    base_travel_by_id = {
        o.ord_id: det_by_id[o.ord_id].t_arrival_sec
        - START
        - o.ord_time_sec
        - o.cook_time_sec
        for o in scenario.orders
    }
    # ensure positive baselines
    assert all(v > 0 for v in base_travel_by_id.values())

    # average noisy/base ratio across many seeds with same type assignment seed=42
    ratios: list[float] = []
    for s in range(200):
        # use a different seed for noise but lock type assignment is not separable;
        # instead just measure ratio per order across seeds and average
        events = sample_rider_arrivals(K50_1, seed=s, sigma_eps=0.15)
        by_id = {e.order_id: e for e in events}
        for o in scenario.orders:
            e = by_id[o.ord_id]
            # find baseline for SAME rider_type
            rider = next(r for r in scenario.riders if r.type == e.rider_type)
            base = pdd[o.ord_id] / rider.speed_mps
            noisy = e.t_arrival_sec - START - o.ord_time_sec - o.cook_time_sec
            ratios.append(noisy / base)
    assert 0.95 < float(np.mean(ratios)) < 1.05  # unbiased to within 5% over 10k draws


def test_zero_noise_is_deterministic_for_seed() -> None:
    a = sample_rider_arrivals(K50_1, seed=42, sigma_eps=0.0)
    b = sample_rider_arrivals(K50_1, seed=42, sigma_eps=0.0)
    assert [(e.order_id, e.t_arrival_sec) for e in a] == [
        (e.order_id, e.t_arrival_sec) for e in b
    ]


def test_lambda_estimate_returns_expected_keys() -> None:
    out = estimate_lambda_rider_K([K50_1, K50_2], K=50, bootstrap_iters=100)
    for key in (
        "bin_edges",
        "bin_centers",
        "lambda_per_sec",
        "lambda_per_h",
        "ci_lo_per_h",
        "ci_hi_per_h",
        "n_scenarios",
        "K",
    ):
        assert key in out
    assert out["n_scenarios"] == 2
    assert out["K"] == 50
    assert out["lambda_per_sec"].shape == out["bin_centers"].shape
    assert (out["ci_lo_per_h"] <= out["lambda_per_h"]).all()
    assert (out["lambda_per_h"] <= out["ci_hi_per_h"]).all()


def test_lambda_integral_recovers_K() -> None:
    """sum(lambda_per_sec * bin_sec) per scenario should equal K (=50)."""
    out = estimate_lambda_rider_K([K50_1, K50_2], K=50, bootstrap_iters=10)
    bin_sec = float(out["bin_edges"][1] - out["bin_edges"][0])
    # mean across 2 scenarios; multiplying back gives the mean K
    estimated_K = (out["lambda_per_sec"] * bin_sec).sum()
    assert estimated_K == pytest.approx(50.0, abs=0.5)


def test_lambda_K_filter_raises_on_empty() -> None:
    with pytest.raises(ValueError):
        estimate_lambda_rider_K([K50_1], K=999, bootstrap_iters=10)
