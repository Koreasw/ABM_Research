"""Rider arrival time synthesis (framework §2.5 — core handoff calibration).

t_rider_arrival(i) = start + ORD_TIME(i) + COOK_TIME(i) + travel_time(i) * eps
travel_time(i)     = DIST[i][K+i] / speed(rider_type(i))
eps                ~ Lognormal(-sigma_eps^2/2, sigma_eps^2)  // mean 1, unbiased

rider_type(i) is sampled from Cat(p_BIKE, p_WALK, p_CAR) weighted by
RIDERS.available_number of the scenario. The lognormal noise is
**multiplicative** on travel_time (additive interpretation of an O(1 s)
Lognormal would be meaningless on a minute-scale variable; see §2.5
sensitivity sweep sigma_eps in [0, 0.30]).

w_R (KRW/h) is calibrated per rider type as
    w_R(type) = fixed_cost + var_cost * throughput_per_rider_h
with throughput_per_rider_h = 50 (framework §4.1.5 baseline).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from analysis.load_data import Rider, Scenario, load_scenario, pickup_drop_distance


@dataclass(frozen=True)
class RiderArrivalEvent:
    t_arrival_sec: float        # building-lobby arrival time (absolute sim seconds)
    order_id: int
    vol: int
    rider_type: str             # BIKE / WALK / CAR
    time_cost_per_sec: float    # w_R / 3600 — for monetizing lobby dwell
    deadline_sec: float         # absolute sim seconds (anchored)


def compute_w_R_krw_per_h(
    rider: Rider, throughput_per_rider_h: float = 50.0
) -> float:
    """Calibrate per-type hourly wage from RIDERS table.

    w_R = fixed_cost + var_cost * throughput (framework §4.1.5).
    """
    return float(rider.fixed_cost) + float(rider.var_cost) * throughput_per_rider_h


def _sample_lognormal_unbiased(
    rng: np.random.Generator, sigma: float, size: int
) -> np.ndarray:
    """Lognormal(mu=-sigma^2/2, sigma^2): E[X] = 1, unbiased multiplier."""
    if sigma <= 0:
        return np.ones(size)
    return rng.lognormal(mean=-(sigma**2) / 2.0, sigma=sigma, size=size)


def _sample_rider_types(
    rng: np.random.Generator, riders: list[Rider], size: int
) -> np.ndarray:
    """Sample rider types weighted by RIDERS.available_number."""
    types = np.array([r.type for r in riders])
    weights = np.array([r.available_number for r in riders], dtype=float)
    if weights.sum() <= 0:
        raise ValueError("RIDERS.available_number sum must be > 0")
    probs = weights / weights.sum()
    return rng.choice(types, size=size, p=probs)


def sample_rider_arrivals(
    scenario_path: str | Path,
    seed: int = 42,
    sigma_eps: float = 0.15,
    start_time_sec: float = 11.5 * 3600.0,
    throughput_per_rider_h: float = 50.0,
) -> list[RiderArrivalEvent]:
    """Synthesize per-order rider arrival events for a scenario.

    Returns events sorted by t_arrival_sec.
    """
    scenario = load_scenario(scenario_path)
    rng = np.random.default_rng(seed)
    K = scenario.K

    type_by_order = _sample_rider_types(rng, scenario.riders, K)
    rider_index_by_type = {r.type: i for i, r in enumerate(scenario.riders)}
    speed_by_order = np.array(
        [scenario.riders[rider_index_by_type[t]].speed_mps for t in type_by_order]
    )
    w_R_by_type = {
        r.type: compute_w_R_krw_per_h(r, throughput_per_rider_h) for r in scenario.riders
    }
    pdd_m = pickup_drop_distance(scenario_path)  # length K
    base_travel_sec = pdd_m / speed_by_order
    eps = _sample_lognormal_unbiased(rng, sigma_eps, K)
    travel_noisy = base_travel_sec * eps

    events: list[RiderArrivalEvent] = []
    for i, order in enumerate(scenario.orders):
        t_arrival = (
            start_time_sec
            + order.ord_time_sec
            + order.cook_time_sec
            + float(travel_noisy[i])
        )
        rider_type = str(type_by_order[i])
        events.append(
            RiderArrivalEvent(
                t_arrival_sec=t_arrival,
                order_id=order.ord_id,
                vol=order.vol,
                rider_type=rider_type,
                time_cost_per_sec=w_R_by_type[rider_type] / 3600.0,
                deadline_sec=start_time_sec + order.dlv_deadline_sec,
            )
        )
    events.sort(key=lambda e: e.t_arrival_sec)
    return events


def estimate_lambda_rider_K(
    scenario_paths: list[str | Path],
    K: int | None = None,
    bin_sec: float = 300.0,
    bootstrap_iters: int = 1000,
    seed: int = 42,
    sigma_eps: float = 0.15,
    start_time_sec: float = 11.5 * 3600.0,
    throughput_per_rider_h: float = 50.0,
) -> dict:
    """Estimate piecewise-constant lambda_rider,K(t) with bootstrap CI.

    Parameters
    ----------
    scenario_paths : iterable of scenario JSON paths.
    K : if given, only scenarios whose Scenario.K matches are kept.
    bin_sec : histogram bin width in seconds (5-min = 300 s default).
    bootstrap_iters : number of scenario-level resample iterations.
    seed : base seed (per-scenario seed = seed + scenario_index for sampling).
    sigma_eps, start_time_sec, throughput_per_rider_h : passed to sampler.

    Returns
    -------
    dict with keys:
      "bin_edges"      : (n_bins+1,) seconds relative to start_time_sec
      "bin_centers"    : (n_bins,) seconds relative to start_time_sec
      "lambda_per_sec" : (n_bins,) mean rate (events / second)
      "lambda_per_h"   : (n_bins,) mean rate (events / hour)
      "ci_lo_per_h"    : (n_bins,) bootstrap 2.5th percentile rate
      "ci_hi_per_h"    : (n_bins,) bootstrap 97.5th percentile rate
      "n_scenarios"    : int, number of scenarios included
      "K"              : int | None, filter K value
    """
    paths = [Path(p) for p in scenario_paths]
    if K is not None:
        paths = [p for p in paths if load_scenario(p).K == K]
    if not paths:
        raise ValueError(f"no scenarios match K={K}")

    per_scenario_arrivals: list[np.ndarray] = []
    for i, p in enumerate(paths):
        events = sample_rider_arrivals(
            p,
            seed=seed + i,
            sigma_eps=sigma_eps,
            start_time_sec=start_time_sec,
            throughput_per_rider_h=throughput_per_rider_h,
        )
        rel = np.array([e.t_arrival_sec - start_time_sec for e in events])
        per_scenario_arrivals.append(rel)

    t_max = max(arr.max() for arr in per_scenario_arrivals if len(arr) > 0)
    n_bins = int(np.ceil(t_max / bin_sec))
    bin_edges = np.arange(n_bins + 1) * bin_sec
    bin_centers = 0.5 * (bin_edges[:-1] + bin_edges[1:])

    counts_per_scenario = np.zeros((len(paths), n_bins), dtype=float)
    for idx, arr in enumerate(per_scenario_arrivals):
        hist, _ = np.histogram(arr, bins=bin_edges)
        counts_per_scenario[idx] = hist

    rate_per_sec_per_scenario = counts_per_scenario / bin_sec
    lambda_per_sec = rate_per_sec_per_scenario.mean(axis=0)

    bs_rng = np.random.default_rng(seed + 9999)
    n_sc = len(paths)
    bs_means = np.empty((bootstrap_iters, n_bins))
    for b in range(bootstrap_iters):
        idx = bs_rng.integers(0, n_sc, size=n_sc)
        bs_means[b] = rate_per_sec_per_scenario[idx].mean(axis=0)
    ci_lo_per_sec = np.quantile(bs_means, 0.025, axis=0)
    ci_hi_per_sec = np.quantile(bs_means, 0.975, axis=0)

    return {
        "bin_edges": bin_edges,
        "bin_centers": bin_centers,
        "lambda_per_sec": lambda_per_sec,
        "lambda_per_h": lambda_per_sec * 3600.0,
        "ci_lo_per_h": ci_lo_per_sec * 3600.0,
        "ci_hi_per_h": ci_hi_per_sec * 3600.0,
        "n_scenarios": n_sc,
        "K": K,
    }
