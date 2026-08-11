"""Demand model — NHPP lambda(t), cook time, volume, lead time (framework §4.1).

Fitted from BaeMin corpus (pooled or K-stratum) via DemandModel.fit_from_corpus.
Pre-computed parameters are serialized to fitted_params.json by
analysis/run_analysis.py and reloaded via DemandModel.from_dict.

Sampling APIs:
  lambda_t(t_sec, scale)         — piecewise-constant rate at simulation t
  sample_interarrival(t, scale)  — NHPP thinning (Lewis & Shedler 1979)
  sample_cook_time()             — best-AIC distribution (Gamma typical)
  sample_volume()                — empirical bootstrap

Density-scale 'scale' is the §2.6 sensitivity multiplier (baseline 1.0).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from scipy import stats

from analysis.load_data import load_scenario


@dataclass(frozen=True)
class CookFit:
    """Best-AIC distribution among Gamma / Lognormal / Weibull (loc=0)."""

    distribution: str           # "gamma" | "lognormal" | "weibull"
    params: tuple[float, ...]   # scipy fit tuple, e.g. (shape, loc=0, scale)
    aic: float
    aic_alternatives: dict[str, float] = field(default_factory=dict)

    def rvs(self, rng: np.random.Generator, size: int | None = None) -> np.ndarray | float:
        dist = _DIST_MAP[self.distribution]
        return dist.rvs(*self.params, size=size, random_state=rng)

    def mean(self) -> float:
        return float(_DIST_MAP[self.distribution].mean(*self.params))


_DIST_MAP = {
    "gamma": stats.gamma,
    "lognormal": stats.lognorm,
    "weibull": stats.weibull_min,
}


def _fit_one(dist_name: str, samples: np.ndarray) -> tuple[tuple, float]:
    """Fit with loc=0 and return (params, AIC)."""
    dist = _DIST_MAP[dist_name]
    params = dist.fit(samples, floc=0)
    logL = dist.logpdf(samples, *params).sum()
    k = len(params) - 1  # loc is fixed so it doesn't count as a free param
    aic = 2 * k - 2 * logL
    return params, float(aic)


def fit_cook_time(samples: np.ndarray) -> CookFit:
    """Fit Gamma / Lognormal / Weibull (loc=0), return best-AIC."""
    samples = samples[samples > 0]
    results: dict[str, tuple[tuple, float]] = {}
    for name in ("gamma", "lognormal", "weibull"):
        results[name] = _fit_one(name, samples)
    best = min(results, key=lambda n: results[n][1])
    params, aic = results[best]
    aic_alt = {n: results[n][1] for n in results}
    return CookFit(distribution=best, params=params, aic=aic, aic_alternatives=aic_alt)


@dataclass
class DemandModel:
    """Calibrated demand model (NHPP arrivals + cook + volume + lead-time)."""

    bin_edges: np.ndarray            # shape (n_bins+1,), seconds from t=0
    lambda_per_sec: np.ndarray       # shape (n_bins,), per-scenario rate
    cook_fit: CookFit
    vol_samples: np.ndarray          # empirical VOL pool
    lead_time_quantiles: dict[float, float]   # {0.05: q05, 0.5: q50, 0.95: q95}
    K: int | None = None
    n_scenarios_fit: int = 0
    rng_seed: int = 42

    _rng: np.random.Generator = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if len(self.bin_edges) != len(self.lambda_per_sec) + 1:
            raise ValueError(
                f"bin_edges length {len(self.bin_edges)} must be lambda_per_sec "
                f"length {len(self.lambda_per_sec)} + 1"
            )
        if (self.lambda_per_sec < 0).any():
            raise ValueError("lambda_per_sec must be non-negative")
        self._rng = np.random.default_rng(self.rng_seed)

    # --- core sampling APIs ---

    def lambda_t(self, t_sec: float, scale: float = 1.0) -> float:
        """Piecewise-constant arrival rate at simulation time t_sec (per-second)."""
        idx = int(np.searchsorted(self.bin_edges, t_sec, side="right")) - 1
        if idx < 0 or idx >= len(self.lambda_per_sec):
            return 0.0
        return float(self.lambda_per_sec[idx]) * float(scale)

    def lambda_max(self, scale: float = 1.0) -> float:
        return float(self.lambda_per_sec.max()) * float(scale)

    def sample_interarrival(self, t_sec: float, scale: float = 1.0) -> float:
        """NHPP thinning: return delta such that t_sec + delta is next arrival.

        Returns +inf if no arrival fires before the end of the fitted horizon.
        """
        lam_max = self.lambda_max(scale)
        if lam_max <= 0:
            return float("inf")
        horizon = float(self.bin_edges[-1])
        t = float(t_sec)
        while t < horizon:
            t += float(self._rng.exponential(1.0 / lam_max))
            if t >= horizon:
                return float("inf")
            lam_t = self.lambda_t(t, scale)
            if self._rng.random() < lam_t / lam_max:
                return t - float(t_sec)
        return float("inf")

    def sample_cook_time(self) -> float:
        return float(self.cook_fit.rvs(self._rng))

    def sample_volume(self) -> int:
        return int(self._rng.choice(self.vol_samples))

    # --- quantile shortcuts ---

    @property
    def lead_time_q05_sec(self) -> float:
        return float(self.lead_time_quantiles[0.05])

    @property
    def lead_time_q50_sec(self) -> float:
        return float(self.lead_time_quantiles[0.5])

    @property
    def lead_time_q95_sec(self) -> float:
        return float(self.lead_time_quantiles[0.95])

    # --- fit / serialize ---

    @classmethod
    def fit_from_corpus(
        cls,
        scenario_paths: Iterable[str | Path],
        K: int | None = None,
        bin_sec: float = 300.0,
        rng_seed: int = 42,
    ) -> DemandModel:
        """Fit lambda(t), cook, volume, lead-time from a set of scenarios.

        If K is given, only scenarios with that K are used (stratum fit).
        """
        scenarios = [load_scenario(p) for p in scenario_paths]
        if K is not None:
            scenarios = [s for s in scenarios if s.K == K]
        if not scenarios:
            raise ValueError(f"no scenarios match K={K}")

        ord_times: list[float] = []
        cook_samples: list[float] = []
        vol_samples: list[int] = []
        lead_samples: list[float] = []
        max_horizon = 0.0
        for s in scenarios:
            for o in s.orders:
                ord_times.append(o.ord_time_sec)
                cook_samples.append(o.cook_time_sec)
                vol_samples.append(o.vol)
                lead_samples.append(o.dlv_deadline_sec - o.ord_time_sec)
                max_horizon = max(max_horizon, o.ord_time_sec)

        n_bins = max(1, int(np.ceil(max_horizon / bin_sec)))
        bin_edges = np.arange(n_bins + 1) * bin_sec
        counts, _ = np.histogram(ord_times, bins=bin_edges)
        # rate = counts / (bin_sec * n_scenarios) gives mean per-scenario per-sec rate
        lambda_per_sec = counts.astype(float) / (bin_sec * len(scenarios))

        cook_arr = np.array(cook_samples, dtype=float)
        cook_fit = fit_cook_time(cook_arr)

        lead_arr = np.array(lead_samples, dtype=float)
        lead_q = {
            0.05: float(np.quantile(lead_arr, 0.05)),
            0.5: float(np.quantile(lead_arr, 0.5)),
            0.95: float(np.quantile(lead_arr, 0.95)),
        }

        return cls(
            bin_edges=bin_edges,
            lambda_per_sec=lambda_per_sec,
            cook_fit=cook_fit,
            vol_samples=np.array(vol_samples, dtype=int),
            lead_time_quantiles=lead_q,
            K=K,
            n_scenarios_fit=len(scenarios),
            rng_seed=rng_seed,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serializable representation (numpy arrays -> lists)."""
        return {
            "bin_edges": self.bin_edges.tolist(),
            "lambda_per_sec": self.lambda_per_sec.tolist(),
            "cook_fit": {
                "distribution": self.cook_fit.distribution,
                "params": list(self.cook_fit.params),
                "aic": self.cook_fit.aic,
                "aic_alternatives": dict(self.cook_fit.aic_alternatives),
            },
            "vol_samples": self.vol_samples.tolist(),
            "lead_time_quantiles": {str(k): v for k, v in self.lead_time_quantiles.items()},
            "K": self.K,
            "n_scenarios_fit": self.n_scenarios_fit,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any], rng_seed: int = 42) -> DemandModel:
        cf = d["cook_fit"]
        return cls(
            bin_edges=np.array(d["bin_edges"], dtype=float),
            lambda_per_sec=np.array(d["lambda_per_sec"], dtype=float),
            cook_fit=CookFit(
                distribution=cf["distribution"],
                params=tuple(cf["params"]),
                aic=cf["aic"],
                aic_alternatives=dict(cf.get("aic_alternatives", {})),
            ),
            vol_samples=np.array(d["vol_samples"], dtype=int),
            lead_time_quantiles={float(k): float(v) for k, v in d["lead_time_quantiles"].items()},
            K=d.get("K"),
            n_scenarios_fit=int(d.get("n_scenarios_fit", 0)),
            rng_seed=rng_seed,
        )
