"""Tests for FloorDemandModel (etc/demand_mapping.md 단계 2·3, profile floor demand).

Distribution-conformance tests use large synthetic N (20,000) with fixed
floor_seed — fully deterministic. Never test distribution shape on K=50
counts: under bottom_heavy a p≈0.033 floor is empty with prob ≈19% at K=50
(a documented sampling property, not a defect).
"""

from __future__ import annotations

import copy
import math

import numpy as np
import pytest

from simulation.floor_demand import (
    FLOOR_STREAM_TAG,
    FloorDemandModel,
    rederive_profile_assignment,
)
from simulation.model import ROOT
from simulation.space import load_config
from simulation.vertical_transport import VerticalTransportModel

CONFIG = load_config(ROOT / "configs" / "baseline_10f.yaml")

BOTTOM_RAW = [0.20, 0.20, 0.20, 0.10, 0.10, 0.10, 0.033, 0.033, 0.033]


def _model(profile: str = "uniform", floor_seed: int = 42) -> FloorDemandModel:
    return FloorDemandModel.from_config(CONFIG, profile, floor_seed=floor_seed)


# ---------------------------------------------------------------- loading


def test_named_profiles_load_and_normalize() -> None:
    uni = _model("uniform")
    assert uni.profile == "uniform"
    assert uni.n_floors == 10
    assert uni.offices_per_floor == 12
    assert all(p == pytest.approx(1.0 / 9.0, abs=1e-15) for p in uni.probs)

    bot = _model("bottom_heavy")
    assert sum(bot.probs) == pytest.approx(1.0, abs=1e-12)
    total = sum(BOTTOM_RAW)  # 0.999 -> normalized
    assert bot.probs[0] == pytest.approx(0.20 / total, abs=1e-15)
    assert bot.probs[8] == pytest.approx(0.033 / total, abs=1e-15)

    top = _model("top_heavy")
    assert top.probs == tuple(reversed(bot.probs))


def test_default_profile_resolution() -> None:
    m = FloorDemandModel.from_config(CONFIG, None, floor_seed=42)
    assert m.profile == "uniform"


def test_unknown_profile_lists_available() -> None:
    with pytest.raises(ValueError, match="bottom_heavy"):
        FloorDemandModel.from_config(CONFIG, "no_such_profile", floor_seed=42)


def test_missing_demand_block() -> None:
    cfg = {k: v for k, v in CONFIG.items() if k != "demand"}
    with pytest.raises(ValueError, match="demand"):
        FloorDemandModel.from_config(cfg, "uniform", floor_seed=42)


@pytest.mark.parametrize(
    "weights",
    [
        [1.0] * 8,                       # too short
        [1.0] * 10,                      # too long
        [1.0] * 8 + [-0.1],              # negative
        [1.0] * 8 + [float("nan")],      # NaN
        [1.0] * 8 + [float("inf")],      # inf
        [0.0] * 9,                       # zero-sum
    ],
)
def test_invalid_weights_rejected(weights: list[float]) -> None:
    with pytest.raises(ValueError):
        FloorDemandModel(
            profile="bad", probs=tuple(weights), n_floors=10,
            offices_per_floor=12, floor_seed=42,
        )


def test_negative_floor_seed_rejected() -> None:
    with pytest.raises(ValueError, match="floor_seed"):
        FloorDemandModel(
            profile="uniform", probs=(1.0,) * 9, n_floors=10,
            offices_per_floor=12, floor_seed=-1,
        )


def test_floors_and_expected_share() -> None:
    m = _model("bottom_heavy")
    assert m.floors == tuple(range(2, 11))
    assert sum(m.expected_share(f) for f in m.floors) == pytest.approx(1.0, abs=1e-12)
    assert m.expected_share(2) == m.probs[0]
    assert m.expected_share(10) == m.probs[8]
    with pytest.raises(ValueError):
        m.expected_share(1)
    with pytest.raises(ValueError):
        m.expected_share(11)


# ---------------------------------------------------------------- sampling


def test_sample_deterministic_across_instances() -> None:
    a = _model("bottom_heavy", floor_seed=42)
    b = _model("bottom_heavy", floor_seed=42)  # fresh instance, same params
    for oid in range(50):
        assert a.sample(oid) == a.sample(oid)
        assert a.sample(oid) == b.sample(oid)


def test_sample_call_order_independent() -> None:
    m = _model("bottom_heavy")
    ord_ids = list(range(100))
    forward = {oid: m.sample(oid) for oid in ord_ids}
    shuffled = {oid: m.sample(oid) for oid in reversed(ord_ids)}
    assert forward == shuffled


def test_floor_seed_sensitivity() -> None:
    m1 = _model("uniform", floor_seed=1)
    m2 = _model("uniform", floor_seed=2)
    floors1 = [m1.sample(oid)[0] for oid in range(200)]
    floors2 = [m2.sample(oid)[0] for oid in range(200)]
    assert floors1 != floors2


def test_profile_crn_monotone_coupling() -> None:
    # Same floor_seed -> same per-order u inverted through each CDF:
    # cum_bottom >= cum_top elementwise, so floor_top >= floor_bottom per order.
    bot = _model("bottom_heavy", floor_seed=42)
    top = _model("top_heavy", floor_seed=42)
    pairs = [(bot.sample(oid)[0], top.sample(oid)[0]) for oid in range(500)]
    assert all(f_top >= f_bot for f_bot, f_top in pairs)
    assert any(f_top > f_bot for f_bot, f_top in pairs)


@pytest.mark.parametrize("profile", ["uniform", "bottom_heavy"])
def test_large_n_floor_conformance(profile: str) -> None:
    m = _model(profile, floor_seed=42)
    n = 20_000
    floors = np.array([m.sample(oid)[0] for oid in range(n)])
    for f in m.floors:
        p = m.expected_share(f)
        freq = float(np.mean(floors == f))
        band = 4.0 * math.sqrt(p * (1.0 - p) / n)
        assert abs(freq - p) <= band, f"floor {f}: freq {freq:.4f} vs p {p:.4f}"


def test_office_uniform_and_in_range() -> None:
    m = _model("uniform", floor_seed=42)
    n = 20_000
    offices = np.array([m.sample(oid)[1] for oid in range(n)])
    assert offices.min() >= 0 and offices.max() < 12
    p = 1.0 / 12.0
    band = 4.0 * math.sqrt(p * (1.0 - p) / n)
    for office in range(12):
        freq = float(np.mean(offices == office))
        assert abs(freq - p) <= band, f"office {office}: freq {freq:.4f}"


def test_degenerate_profile_constant_floor() -> None:
    cfg = copy.deepcopy(CONFIG)
    cfg["demand"]["floor_profiles"]["only_7f"] = [0, 0, 0, 0, 0, 1, 0, 0, 0]
    m = FloorDemandModel.from_config(cfg, "only_7f", floor_seed=42)
    assert all(m.sample(oid)[0] == 7 for oid in range(300))


# ------------------------------------------------- stream-family separation


def test_stream_families_do_not_collide() -> None:
    # First uniform of each per-order stream family, floor_seed == mode_seed
    # == rng_seed == 42 (the worst case for collisions).
    for i in range(300):
        floor_u = np.random.default_rng([FLOOR_STREAM_TAG, 42, i]).random()
        mode_u = np.random.default_rng(np.uint64(42) ^ np.uint64(i)).random()
        noise_u = np.random.default_rng([42, i]).random()
        assert floor_u != mode_u
        assert floor_u != noise_u


def test_naive_xor_form_would_collide_with_mode_stream() -> None:
    # Documents the trap FLOOR_STREAM_TAG prevents: a naive
    # default_rng(uint64(floor_seed) ^ uint64(ord_id)) floor stream with
    # floor_seed=42 is bit-identical to the mode stream (mode_seed=42).
    for i in range(50):
        naive_floor_u = np.random.default_rng(np.uint64(42) ^ np.uint64(i)).random()
        mode_u = np.random.default_rng(np.uint64(42) ^ np.uint64(i)).random()
        assert naive_floor_u == mode_u


# ------------------------------------------------------------- re-derivation


def test_rederive_round_trip() -> None:
    m = _model("top_heavy", floor_seed=7)
    vt = VerticalTransportModel.from_config(CONFIG)
    ord_ids = list(range(50))
    derived = rederive_profile_assignment(CONFIG, "top_heavy", 7, ord_ids)
    assert set(derived) == set(ord_ids)
    for oid in ord_ids:
        floor, office = m.sample(oid)
        assert derived[oid] == (floor, office, vt.sample_mode(oid, floor))
