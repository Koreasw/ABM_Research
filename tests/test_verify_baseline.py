"""S6 — analysis/verify_baseline.py (plan_abm_baseline_h0.md Part E).

Positive path: the shipped baseline results JSON passes all six checks.
Negative paths: each seeded violation must be caught by its check — a
verifier that cannot fail is not a verifier.
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

import pytest

from analysis.verify_baseline import ROOT, load_inputs, main, run_checks

RESULTS_PATH = ROOT / "results" / "baseline_h0_K50_1.json"

pytestmark = pytest.mark.skipif(
    not RESULTS_PATH.exists(),
    reason="baseline results JSON not generated yet (run simulation.run first)",
)


def _load_inputs() -> dict:
    args = argparse.Namespace(scenario=None, mapping=None, travel_times=None)
    return load_inputs(RESULTS_PATH, args)


@pytest.fixture(scope="module")
def inputs() -> dict:
    return _load_inputs()


def _result_by_name(results: list, prefix: str):
    return next(r for r in results if r.name.startswith(prefix))


# ------------------------------------------------------------------- positive


def test_all_checks_pass(inputs: dict) -> None:
    results, _ = run_checks(inputs)
    assert len(results) == 6
    failed = [(r.name, r.failures) for r in results if not r.passed]
    assert not failed, f"checks failed: {failed}"


def test_cli_exit_code_zero(capsys) -> None:
    assert main([str(RESULTS_PATH)]) == 0
    out = capsys.readouterr().out
    assert "6/6 checks passed" in out
    assert "FAIL" not in out


def test_lb_report_within_one_tick_allowance(inputs: dict) -> None:
    """check #4's contract is T_e2e >= LB_strict − 1 tick: the rider's first
    walk leg shares its creation tick (verify_h0 A5 accounts for this
    explicitly), so the continuous-time LB may exceed the tick-grid outcome by
    up to one tick. v1's geometry happened to keep slack_min at +0.14 s; the
    v2 geometry (plan_h0_revision.md §1.1) lands one order at −0.04 s — still
    well inside the allowance."""
    _, report = run_checks(inputs)
    assert report["slack_min_sec"] > -1.0  # 1 tick (simulation.tick_sec)
    assert report["slack_mean_sec"] >= report["slack_min_sec"]
    assert report["slack_mean_sec"] > 0  # the bound is tight, not broken


# ------------------------------------------------------------------- negative
# Each seeded violation targets exactly one check; the untouched checks must
# keep passing so a regression cannot hide behind an unrelated failure.


def _mutated(inputs: dict) -> dict:
    mut = dict(inputs)
    mut["res"] = copy.deepcopy(inputs["res"])
    return mut


def _assert_only_fails(mut: dict, prefix: str) -> None:
    results, _ = run_checks(mut)
    assert not _result_by_name(results, prefix).passed
    others = [r for r in results if not r.name.startswith(prefix)]
    assert all(r.passed for r in others), (
        f"seeded violation for check {prefix!r} leaked into "
        f"{[r.name for r in others if not r.passed]}"
    )


def test_detects_duplicate_ord_id(inputs: dict) -> None:
    mut = _mutated(inputs)
    rec = copy.deepcopy(mut["res"]["per_order"][0])
    mut["res"]["per_order"][1] = rec  # duplicate ord_id 0, drop one order
    results, _ = run_checks(mut)
    assert not _result_by_name(results, "1").passed


def test_detects_arrival_time_shift(inputs: dict) -> None:
    mut = _mutated(inputs)
    mut["res"]["per_order"][0]["entered_at_sec"] += 5.0
    results, _ = run_checks(mut)
    assert not _result_by_name(results, "2").passed


def test_detects_floor_mismatch(inputs: dict) -> None:
    mut = _mutated(inputs)
    rec = mut["res"]["per_order"][0]
    rec["floor"] = rec["floor"] + 1 if rec["floor"] < 10 else rec["floor"] - 1
    results, _ = run_checks(mut)
    assert not _result_by_name(results, "3").passed


def test_detects_mode_mismatch(inputs: dict) -> None:
    mut = _mutated(inputs)
    rec = mut["res"]["per_order"][0]
    flipped = "stairs" if rec["vertical_mode"] == "elevator" else "elevator"
    rec["vertical_mode"] = flipped
    results, _ = run_checks(mut)
    assert not _result_by_name(results, "3").passed


def test_detects_lower_bound_violation(inputs: dict) -> None:
    mut = _mutated(inputs)
    rec = mut["res"]["per_order"][0]
    # a physically impossible delivery: faster than cook + travel + service
    shift = rec["t_e2e_sec"] - 1.0
    rec["t_e2e_sec"] -= shift
    rec["delivered_at_sec"] -= shift  # keep t_e2e arithmetic (check #6) intact
    mut["res"]["per_order"][0]["sla_violation"] = (
        rec["delivered_at_sec"] > rec["deadline_abs_sec"]
    )
    results, _ = run_checks(mut)
    assert not _result_by_name(results, "4").passed


def test_detects_undelivered_order(inputs: dict) -> None:
    mut = _mutated(inputs)
    mut["res"]["kpi_summary"]["simulation"]["terminated_by_cap"] = True
    _assert_only_fails(mut, "5")


def test_detects_residual_agents(inputs: dict) -> None:
    mut = _mutated(inputs)
    mut["res"]["model_vars"]["riders_in_building"][-1] = 2
    _assert_only_fails(mut, "5")


def test_detects_capacity_violation(inputs: dict) -> None:
    mut = _mutated(inputs)
    mut["res"]["kpi_summary"]["elevator"]["EV1"]["capacity_violations"] = 1
    _assert_only_fails(mut, "6")


def test_detects_board_alight_mismatch(inputs: dict) -> None:
    mut = _mutated(inputs)
    mut["res"]["kpi_summary"]["elevator"]["EV2"]["n_alights"] -= 1
    _assert_only_fails(mut, "6")


def test_detects_stairs_rider_with_ev_wait(inputs: dict) -> None:
    mut = _mutated(inputs)
    rec = next(r for r in mut["res"]["per_order"] if r["vertical_mode"] == "stairs")
    rec["ev_wait_up_sec"] = 12.0
    _assert_only_fails(mut, "6")
