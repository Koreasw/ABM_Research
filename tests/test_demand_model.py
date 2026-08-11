"""Tests for analysis.demand_model — NHPP fit + Gamma cook + samplers."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from analysis.demand_model import CookFit, DemandModel, fit_cook_time

DATA = Path(__file__).resolve().parent.parent / "data" / "data1"
K50_SCENARIOS = [DATA / "K50_1.json", DATA / "K50_2.json"]
K100_SCENARIOS = sorted(DATA.glob("K100_*.json"))
ALL_SCENARIOS = sorted(DATA.glob("K*_*.json"))


def test_data_present() -> None:
    if not K50_SCENARIOS[0].exists():
        pytest.skip(f"data not present at {K50_SCENARIOS[0]}")


def test_fit_cook_time_picks_gamma_or_alternative() -> None:
    rng = np.random.default_rng(0)
    samples = rng.gamma(shape=4.7, scale=223.3, size=2000)
    fit = fit_cook_time(samples)
    assert isinstance(fit, CookFit)
    assert fit.distribution in {"gamma", "lognormal", "weibull"}
    # Gamma should win on data generated from Gamma
    assert fit.distribution == "gamma"
    shape, _loc, scale = fit.params
    assert shape == pytest.approx(4.7, rel=0.15)
    assert scale == pytest.approx(223.3, rel=0.15)


def test_fit_cook_aic_alternatives_keyed() -> None:
    rng = np.random.default_rng(0)
    samples = rng.gamma(shape=4.7, scale=223.3, size=1000)
    fit = fit_cook_time(samples)
    assert set(fit.aic_alternatives) == {"gamma", "lognormal", "weibull"}
    # winning model's AIC equals minimum among alternatives
    assert fit.aic == min(fit.aic_alternatives.values())


def test_fit_from_corpus_K50() -> None:
    dm = DemandModel.fit_from_corpus(K50_SCENARIOS, K=50)
    assert dm.K == 50
    assert dm.n_scenarios_fit == 2
    assert dm.lambda_per_sec.sum() > 0
    # framework §4.1.2: cook mean ~ 17.5 min (1050s)
    assert 800 <= dm.cook_fit.mean() <= 1300
    # VOL range
    assert dm.vol_samples.min() >= 1
    assert dm.vol_samples.max() <= 100


def test_lambda_integral_recovers_mean_K() -> None:
    dm = DemandModel.fit_from_corpus(K50_SCENARIOS, K=50)
    bin_sec = float(dm.bin_edges[1] - dm.bin_edges[0])
    # sum(rate * bin_sec) gives mean K per scenario
    estimated_K = (dm.lambda_per_sec * bin_sec).sum()
    assert estimated_K == pytest.approx(50.0, abs=0.5)


def test_lambda_t_returns_zero_outside_horizon() -> None:
    dm = DemandModel.fit_from_corpus(K50_SCENARIOS, K=50)
    horizon = float(dm.bin_edges[-1])
    assert dm.lambda_t(-1.0) == 0.0
    assert dm.lambda_t(horizon + 1.0) == 0.0
    # somewhere inside horizon should be > 0
    assert dm.lambda_t(horizon / 2) >= 0.0


def test_lambda_t_respects_scale_parameter() -> None:
    dm = DemandModel.fit_from_corpus(K50_SCENARIOS, K=50)
    t = float(dm.bin_edges[1])  # first bin center-ish
    base = dm.lambda_t(t, scale=1.0)
    if base > 0:
        assert dm.lambda_t(t, scale=2.0) == pytest.approx(2.0 * base)
        assert dm.lambda_t(t, scale=0.5) == pytest.approx(0.5 * base)


def test_sample_interarrival_within_horizon() -> None:
    dm = DemandModel.fit_from_corpus(K50_SCENARIOS, K=50, rng_seed=42)
    deltas = []
    t = 0.0
    horizon = float(dm.bin_edges[-1])
    while t < horizon and len(deltas) < 1000:
        d = dm.sample_interarrival(t)
        if d == float("inf"):
            break
        deltas.append(d)
        t += d
    # expect roughly K=50 events per scenario, allow wide bounds for stochasticity
    assert 20 <= len(deltas) <= 90


def test_sample_cook_time_distribution_close_to_data() -> None:
    dm = DemandModel.fit_from_corpus(K50_SCENARIOS + K100_SCENARIOS, rng_seed=7)
    samples = np.array([dm.sample_cook_time() for _ in range(5000)])
    # framework §4.1.2: cook mean ~17.5 min, median ~15 min (900s)
    assert 800 < samples.mean() < 1300
    assert 700 < np.median(samples) < 1100


def test_sample_volume_within_data_range() -> None:
    dm = DemandModel.fit_from_corpus(K50_SCENARIOS, rng_seed=7)
    samples = np.array([dm.sample_volume() for _ in range(2000)])
    assert samples.min() >= dm.vol_samples.min()
    assert samples.max() <= dm.vol_samples.max()


def test_lead_time_quantiles_in_expected_range() -> None:
    dm = DemandModel.fit_from_corpus(K50_SCENARIOS + K100_SCENARIOS)
    # framework §4 expected q05~38m, q50~56m, q95~120m
    assert 25 * 60 < dm.lead_time_q05_sec < 50 * 60
    assert 40 * 60 < dm.lead_time_q50_sec < 80 * 60
    assert dm.lead_time_q05_sec < dm.lead_time_q50_sec < dm.lead_time_q95_sec


def test_roundtrip_to_dict_from_dict() -> None:
    dm = DemandModel.fit_from_corpus(K50_SCENARIOS, K=50, rng_seed=42)
    d = dm.to_dict()
    dm2 = DemandModel.from_dict(d, rng_seed=42)
    assert np.allclose(dm.bin_edges, dm2.bin_edges)
    assert np.allclose(dm.lambda_per_sec, dm2.lambda_per_sec)
    assert dm.cook_fit.distribution == dm2.cook_fit.distribution
    assert dm.cook_fit.params == dm2.cook_fit.params
    assert dm.lead_time_quantiles == dm2.lead_time_quantiles


def test_fit_from_corpus_empty_K_raises() -> None:
    with pytest.raises(ValueError):
        DemandModel.fit_from_corpus(K50_SCENARIOS, K=99999)


def test_invalid_bin_edges_raises() -> None:
    with pytest.raises(ValueError):
        DemandModel(
            bin_edges=np.array([0.0, 300.0, 600.0]),
            lambda_per_sec=np.array([0.01]),  # length mismatch
            cook_fit=CookFit("gamma", (4.7, 0.0, 223.3), aic=0.0),
            vol_samples=np.array([10, 20]),
            lead_time_quantiles={0.05: 1.0, 0.5: 2.0, 0.95: 3.0},
        )


def test_negative_lambda_raises() -> None:
    with pytest.raises(ValueError):
        DemandModel(
            bin_edges=np.array([0.0, 300.0]),
            lambda_per_sec=np.array([-0.01]),
            cook_fit=CookFit("gamma", (4.7, 0.0, 223.3), aic=0.0),
            vol_samples=np.array([10]),
            lead_time_quantiles={0.05: 1.0, 0.5: 2.0, 0.95: 3.0},
        )
