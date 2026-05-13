"""Demand model — NHPP lambda(t), cook time, volume, lead time (framework §4.1).

Fitted parameters loaded from `analysis/fitted_params.json`:
- arrivals_by_K[K].lambda_t      (piecewise-constant 5-min bins)
- cook_time: Gamma(shape=4.70, scale=223.3) per AIC fit
- volume: empirical distribution [5, 100], mean ~28, median 24
- lead_time: q05=2280s (~38m), q50=3360s (~56m), q95=7200s (~120m)
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DemandModel:
    """Sampling front-end for NHPP / cook / volume / lead-time."""

    K: int | None = None  # None = pooled corpus; else K-stratum
    rng_seed: int = 42

    def lambda_t(self, t_sec: float, scale: float = 1.0) -> float:
        """Piecewise-constant arrival rate at simulation time t_sec."""
        raise NotImplementedError

    def sample_interarrival(self, t_sec: float, scale: float = 1.0) -> float:
        """Thinning-compatible inter-arrival sample."""
        raise NotImplementedError

    def sample_cook_time(self) -> float:
        """Gamma(shape=4.70, scale=223.3) cook time in seconds."""
        raise NotImplementedError

    def sample_volume(self) -> int:
        """Order volume in [5, 100]."""
        raise NotImplementedError

    @property
    def lead_time_q05_sec(self) -> float:
        return 2280.0  # ~38 min

    @property
    def lead_time_q50_sec(self) -> float:
        return 3360.0  # ~56 min
