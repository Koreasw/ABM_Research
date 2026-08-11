"""End-to-end tests for the profile-based floor-demand path (Stage 3,
etc/plan_demand_mapping_profile.md — etc/demand_mapping.md 단계 2·3).

Mirrors tests/test_dynamic_pool.py conventions: a module-scoped completed
fixture on K50_1 + baseline_10f driven by run_to_completion(). The core
invariant (test_per_record_matches_rederive) is per-record
(floor, office_id, vertical_mode) conformance to rederive_profile_assignment
— the future verify_h0 A9 gate.

Only load-time floor assertions are made for floor_seed independence: in the
dynamic pool, floors feed back into pool timing, so end-to-end arrival times
are deliberately NOT asserted floor_seed-independent (Stage 2 covers the
load-time-only guarantee).
"""

from __future__ import annotations

import numpy as np
import pytest

from simulation.floor_demand import rederive_profile_assignment
from simulation.kpi import summarize
from simulation.model import ROOT, BuildingHandoffModel, HandoffMode
from simulation.space import load_config
from simulation.visualize import build_kpi_report

DATA = ROOT / "data" / "data1" / "K50_1.json"
CONFIG_PATH = ROOT / "configs" / "baseline_10f.yaml"
MAPPING_V4 = ROOT / "data" / "floor_mapping" / "K50_1_floor_mapping_v4.json"


def _cfg() -> dict:
    return load_config(CONFIG_PATH)


def _profile_model(**overrides) -> BuildingHandoffModel:
    """Construct a profile-mode model on K50_1 (no run) with defaults matching
    the module fixture; `overrides` tweak individual kwargs per test."""
    params = {
        "mode": HandoffMode.H0_DIRECT,
        "config": _cfg(),
        "scenario_path": DATA,
        "rng_seed": 42,
        "dynamic_pool": True,
        "floor_profile": "uniform",
    }
    params.update(overrides)
    return BuildingHandoffModel(**params)


@pytest.fixture(scope="module")
def profile_model() -> BuildingHandoffModel:
    if not DATA.exists():
        pytest.skip(f"data not present at {DATA}")
    m = _profile_model()
    m.run_to_completion()
    return m


# --------------------------------------------------------------------------
# 1. end-to-end: all delivered, pool restored, no cap termination
# --------------------------------------------------------------------------


def test_profile_e2e_delivers_all_and_restores_pool(
    profile_model: BuildingHandoffModel,
) -> None:
    m = profile_model
    assert m.running is False
    assert m.terminated_by_cap is False
    assert all(c.delivered_at_sec is not None for c in m.customer_by_ord_id.values())
    assert len(m.rider_records) == 50
    assert len({r["ord_id"] for r in m.rider_records}) == 50  # no duplicates
    # pool fully restored (mirrors test_dynamic_pool.test_pool_fully_restored)
    pool = m.rider_pool
    assert pool.free == pool.initial
    assert not pool.waiting
    assert not m.pending_arrivals
    assert not m.pending_releases
    assert sum(pool.dispatch_count.values()) == 50


# --------------------------------------------------------------------------
# 2. profile-mode attributes
# --------------------------------------------------------------------------


def test_profile_mode_attributes(profile_model: BuildingHandoffModel) -> None:
    m = profile_model
    assert m.mapping_path is None
    assert m.floor_profile == "uniform"
    assert m.floor_seed == 42  # defaulted from rng_seed


# --------------------------------------------------------------------------
# 3. CORE INVARIANT — per-record (floor, office, mode) == rederive (A9 gate)
# --------------------------------------------------------------------------


def test_per_record_matches_rederive(profile_model: BuildingHandoffModel) -> None:
    m = profile_model
    ord_ids = [r["ord_id"] for r in m.rider_records]
    derived = rederive_profile_assignment(m.config, "uniform", 42, ord_ids)
    for r in m.rider_records:
        assert (r["floor"], r["office_id"], r["vertical_mode"]) == derived[r["ord_id"]]


# --------------------------------------------------------------------------
# 4. explicit floor_seed override wins (load only, no run)
# --------------------------------------------------------------------------


def test_floor_seed_override_wins() -> None:
    if not DATA.exists():
        pytest.skip("data not present")
    m = _profile_model(floor_seed=7)
    assert m.floor_seed == 7
    ord_ids = [o.ord_id for o in m.orders]
    derived = rederive_profile_assignment(m.config, "uniform", 7, ord_ids)
    for o in m.orders:
        assert o.floor == derived[o.ord_id][0]
        assert (o.floor, o.office_id, o.vertical_mode) == derived[o.ord_id]


# --------------------------------------------------------------------------
# 5. guard ValueErrors
# --------------------------------------------------------------------------


def test_guard_floor_profile_and_mapping_path_mutually_exclusive() -> None:
    with pytest.raises(ValueError):
        BuildingHandoffModel(
            config=_cfg(),
            scenario_path=DATA,
            dynamic_pool=True,
            floor_profile="uniform",
            mapping_path=MAPPING_V4,
        )


def test_guard_floor_profile_requires_dynamic_pool() -> None:
    with pytest.raises(ValueError):
        BuildingHandoffModel(
            config=_cfg(),
            scenario_path=DATA,
            dynamic_pool=False,
            floor_profile="uniform",
        )


def test_guard_floor_seed_requires_floor_profile() -> None:
    with pytest.raises(ValueError):
        BuildingHandoffModel(
            config=_cfg(),
            scenario_path=DATA,
            dynamic_pool=True,
            floor_seed=7,
        )


# --------------------------------------------------------------------------
# 6. same-seed determinism (two independent runs)
# --------------------------------------------------------------------------


def test_same_seed_determinism() -> None:
    if not DATA.exists():
        pytest.skip("data not present")
    a = _profile_model()
    a.run_to_completion()
    b = _profile_model()
    b.run_to_completion()

    def triples(m: BuildingHandoffModel) -> list[tuple]:
        return sorted(
            (r["ord_id"], r["floor"], r["delivered_at_sec"] is not None)
            for r in m.rider_records
        )

    assert triples(a) == triples(b)
    ka, kb = summarize(a), summarize(b)
    assert ka["customer"]["n_delivered"] == kb["customer"]["n_delivered"] == 50
    assert ka["rider"]["n_exited"] == kb["rider"]["n_exited"]
    assert a.tick_count == b.tick_count


# --------------------------------------------------------------------------
# 7. seed diversification vs pinned floor_seed (load only)
# --------------------------------------------------------------------------


def test_seed_diversification_and_pinned_floor_seed() -> None:
    if not DATA.exists():
        pytest.skip("data not present")
    # floor_seed follows rng_seed by default → different load-time floor seqs
    m7 = _profile_model(rng_seed=7)
    m42 = _profile_model(rng_seed=42)
    assert [o.floor for o in m7.orders] != [o.floor for o in m42.orders]

    # pinning floor_seed decouples the floor draw from rng_seed → identical
    # load-time floor/office/mode sequences even though rng_seed differs
    p7 = _profile_model(rng_seed=7, floor_seed=42)
    p42 = _profile_model(rng_seed=42, floor_seed=42)

    def load_seq(m: BuildingHandoffModel) -> list[tuple]:
        return [
            (o.ord_id, o.floor, o.office_id, o.vertical_mode)
            for o in sorted(m.orders, key=lambda x: x.ord_id)
        ]

    assert load_seq(p7) == load_seq(p42)


# --------------------------------------------------------------------------
# 8. profile contrast: top_heavy mean floor > bottom_heavy (CRN coupling)
# --------------------------------------------------------------------------


def test_profile_contrast_bottom_vs_top_mean_floor() -> None:
    if not DATA.exists():
        pytest.skip("data not present")
    bottom = _profile_model(floor_profile="bottom_heavy", floor_seed=42)
    top = _profile_model(floor_profile="top_heavy", floor_seed=42)
    mean_bottom = float(np.mean([o.floor for o in bottom.orders]))
    mean_top = float(np.mean([o.floor for o in top.orders]))
    assert mean_top > mean_bottom


# --------------------------------------------------------------------------
# 9. build_kpi_report on the completed profile model (crash guard + meta)
# --------------------------------------------------------------------------


def test_build_kpi_report_profile_meta(profile_model: BuildingHandoffModel) -> None:
    md, csv_text, stem = build_kpi_report(profile_model)  # must not raise
    assert "profile:uniform" in md
    assert "profile:uniform" in csv_text
    assert stem  # non-empty file stem
