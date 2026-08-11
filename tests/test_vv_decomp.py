"""Fast gate for analysis.vv_decomp (Stage V5a, V-DECOMP).

The heavy 39-scenario sweep lives in `python -m analysis.vv_decomp`; here we
run one small scenario (K50_1, seed 42, ~1 s) and exercise the decomposition
invariants that make the figure trustworthy:

  * every order's seven components sum to the recorded T_e2e within the tick
    tolerance (the item's stated pass criterion) — and in fact float-exact;
  * no component is negative and every elevator ride clears its kinematic floor
    (decompose_result reports these as integrity failures);
  * the mean aggregate is an exact partition (component means sum to T_e2e mean);
  * a deliberately corrupted component is caught by the residual gate (proving
    the gate is not vacuous).
"""

from __future__ import annotations

import copy

import pytest

from analysis.vv_decomp import (
    COMPONENTS,
    build_k_table,
    decompose_order,
    decompose_result,
    _Ctx,
)
from simulation.run import run_baseline


@pytest.fixture(scope="module")
def result() -> dict:
    return run_baseline(
        scenario_path="data/data1/K50_1.json", rng_seed=42, floor_profile="uniform"
    )


def test_smoke_integrity_passes(result: dict) -> None:
    """K50_1 decomposes with zero integrity failures (per-order gate PASS)."""
    rows, fails = decompose_result(result)
    assert fails == [], fails
    assert len(rows) == 50


def test_components_sum_to_t_e2e(result: dict) -> None:
    """Per-order: the seven components partition T_e2e (float-exact)."""
    rows, _ = decompose_result(result)
    for r in rows:
        assert abs(sum(r[c] for c in COMPONENTS) - r["t_e2e"]) < 1e-6, r["ord_id"]


def test_component_signs_and_ride_floor(result: dict) -> None:
    """No negative bands; stairs ride == exact climb; elevator ride >= floor."""
    ctx = _Ctx(result)
    tick = ctx.tick
    saw_elev = saw_stair = False
    for rec in result["per_order"]:
        row = decompose_order(rec, ctx)
        for c in COMPONENTS:
            assert row[c] >= -1e-6, (rec["ord_id"], c, row[c])
        if row["vertical_mode"] == "elevator":
            saw_elev = True
            assert row["ride_floor_slack"] >= -tick - 1e-6
        else:
            saw_stair = True
            assert row["ev_wait"] == 0.0  # stairs never wait for a car
    assert saw_elev and saw_stair  # K50_1 exercises both vertical modes


def test_mean_aggregate_is_exact_partition(result: dict) -> None:
    """build_k_table's mean row: component means sum to the T_e2e mean."""
    rows, _ = decompose_result(result)
    table = build_k_table({50: rows})
    mean_row = next(r for r in table if r["stat"] == "mean")
    total = sum(mean_row[c] for c in COMPONENTS)
    assert abs(total - mean_row["t_e2e"]) < 1e-3


def test_residual_gate_catches_tampering(result: dict) -> None:
    """Corrupting the recorded T_e2e by >1 tick trips the residual gate.

    (The elevator ride is a residual, so tampering with an *internal* stage is
    absorbed; the gate guards the reconciliation against the recorded T_e2e the
    bars must add up to, which is what we corrupt here.)
    """
    bad = copy.deepcopy(result)
    bad["per_order"][0]["t_e2e_sec"] += 100.0
    _, fails = decompose_result(bad)
    assert any("residual" in f for f in fails), fails
