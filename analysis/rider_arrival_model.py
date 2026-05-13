"""Rider arrival time synthesis (framework §2.5 — core handoff calibration).

t_rider_arrival(i) = ORD_TIME(i) + COOK_TIME(i) + travel_time(i) + eps
travel_time(i)     = DIST[i][K+i] / speed(rider_type(i))
eps                ~ Lognormal(0, sigma_eps^2),  sigma_eps = 0.15 baseline

rider_type(i) is sampled from Cat(p_BIKE, p_WALK, p_CAR) weighted by
RIDERS.available_number of the scenario.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RiderArrivalEvent:
    t_arrival_sec: float        # building-lobby arrival time
    order_id: int
    vol: int
    rider_type: str             # BIKE / WALK / CAR
    time_cost_per_sec: float    # w_R / 3600 — for monetizing lobby dwell
    deadline_sec: float


def sample_rider_arrivals(
    scenario_path: Path,
    seed: int = 42,
    sigma_eps: float = 0.15,
    start_time_sec: float = 11.5 * 3600.0,
) -> list[RiderArrivalEvent]:
    """Synthesize per-order rider arrival events for a scenario.

    Returns the events sorted by t_arrival_sec.
    """
    raise NotImplementedError


def estimate_lambda_rider_K(
    scenario_paths: list[Path],
    K: int,
    bin_sec: float = 300.0,
    bootstrap_iters: int = 1000,
) -> dict:
    """Estimate piecewise-constant lambda_rider,K(t) with bootstrap CI.

    Returns {"bin_edges": [...], "lambda": [...], "ci_lo": [...], "ci_hi": [...]}.
    """
    raise NotImplementedError
