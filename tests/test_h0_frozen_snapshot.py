"""H0 frozen-snapshot regression gate (Phase A pre-flight, etc/scie_phase/
phase_A_robot_h1.md §1 completion criterion 2 / plan_hr_extension.md R1 gate
②: "V5d determinism + golden path bit-identical").

Gap this closes: V5d (tests/test_vv_determinism.py) re-runs the model twice
*with the same code* and compares -- it proves determinism, not "unchanged
by Phase A's robot code". The golden path (test_vv_golden_path.py) only
covers synthetic 1-2 order scenarios, not realistic K50/K300/K1000 paths
(EV contention, SCAN direction, dispatch heuristics). `results/baseline_h0_*`
JSON snapshots already exist on disk but nothing re-executes `run_baseline`
against current code and diffs the result -- test_verify_h0.py only re-runs
the A1..A9 *gate* on the frozen file's own content.

This module pins that: for each frozen paper-track snapshot, replay
`run_baseline` with the exact params recorded in the snapshot and assert
the *simulated behavior* (`per_order` event trace, `model_vars` time
series, and every KPI key that already existed in the snapshot) is
unchanged. Any Phase A change to a shared H0 code path (elevator boarding
loop, audit asserts, etc.) that alters H0 behavior even for robot-free
scenarios will flip one of these to red immediately -- the "H0 bit
identity" gate is otherwise only checked implicitly, after the fact, by
eyeballing V5d/golden path.

Two things learned writing this test, both baked into the comparison
below:

1. **Do not diff full-result JSON strings with a plain `assert a == b`.**
   A first version of this test serialized the whole `run_baseline()`
   result to one JSON string per side and asserted string equality. Run
   against `baseline_h0_K50_1_uniform_s42.json` (captured before the
   V6-KPIWIN `*_orderspan` KPI fields existed) that assertion is *expected*
   to fail on an additive, benign diff -- but pytest's assertion-rewriter
   tried to compute a full diff of the two ~1-2KB JSON strings and hung for
   38+ minutes without producing output (observed directly: killing the
   process and re-running the same comparison as a plain script, with a
   structured key-level diff instead of a raw string diff, completed in
   under a second and showed the real cause was 4 new orderspan keys).
   Moral: never let a large-blob equality assertion hit pytest's default
   introspection -- diff structured (dict/key) rather than serialized.
2. **The comparison must tolerate additive KPI schema evolution.** This
   codebase's own convention (`etc/verification_report_h0.md` §5 decision
   1, V6-KPIWIN) is that new KPI fields are added with existing fields
   left byte-for-byte unchanged. `baseline_h0_K50_1_uniform_s42.json`
   predates that extension and is missing `elevator.EV1/EV2
   .utilization_orderspan`, `building.opex_running_krw_orderspan`,
   `simulation.{wall_span,orderspan_window}_orderspan_sec` -- a real,
   already-reviewed diff unrelated to Phase A. A strict full-dict-equality
   gate would therefore be permanently red before Phase A even starts.
   This test instead asserts a superset invariant on `kpi_summary`: every
   key present in the *snapshot* must still be present in the replay with
   an unchanged value; new keys in the replay are fine. `config` is
   intentionally excluded from the comparison for the same reason (a
   separate, unrelated, already-in-flight config refactor moved several
   `rider.*` wage/patience keys elsewhere; since `per_order`/`model_vars`
   below are still byte-identical, that refactor provably didn't change
   simulated behavior, which is the only thing this gate cares about).

Uses `simulation.run.run_baseline` in-process. Scenario set (사용자 확정
2026-08-03, `etc/plan_h0v2_verification.md` §6-1): **K50_1 / K100_1 / K200_1 /
K300_4** -- the three primary-tier K levels that carry the paper's main
analysis, plus K300 as the extreme-tier representative. K1000 was dropped from
the frozen set: it is outside the 28-file modelling corpus, so the
only coverage given up is bit-level regression detection on that one case.

RE-FREEZE, 2026-08-03 (plan §1.6 / §3 R6): the four snapshots were regenerated
after the people-only basements B1/B2 were added. That change *is expected* to
move every number here -- pedestrians now ride to and from parking, so EV
occupancy, hall-call queues and therefore rider EV waits all shift. The old
values are not lost: they live in `results/pre_basement/` and are pinned by
`test_nobasement_replay_matches_pre_basement_snapshot` below, which replays
them under `configs/regression_nobasement_10f.yaml` (n_basements=0). Together
the two gates separate "the building changed" (expected) from "the model
changed" (a defect): the second test would have caught, for instance, the floor
`rank` refactor perturbing above-ground dispatch.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from simulation.run import run_baseline

pytestmark = pytest.mark.vv

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"

# Paper-track snapshots (dynamic_pool=True, return_leg=False,
# scenario_window=True) spanning small/mid/large K for EV-contention
# coverage beyond the synthetic golden-path scenarios.
SNAPSHOT_FILES = [
    "baseline_h0_K50_1_uniform_s42.json",
    "baseline_h0_K100_1_uniform_s42.json",
    "baseline_h0_K200_1_uniform_s42.json",
    "baseline_h0_K300_4_uniform_s42.json",
]

# Pre-§1.6 copies of the same four runs (no basement), replayed against the
# frozen no-basement config. Two of the four are enough to catch a shared-path
# regression at both ends of the contention range without doubling this
# module's runtime.
PRE_BASEMENT_DIR = RESULTS / "pre_basement"
PRE_BASEMENT_FILES = [
    "baseline_h0_K50_1_uniform_s42.json",
    "baseline_h0_K300_4_uniform_s42.json",
]
NOBASEMENT_CONFIG = "configs/regression_nobasement_10f.yaml"

# Run-identity metadata: must match exactly (these are just the inputs
# echoed back, so any diff here means the replay wasn't a faithful
# reproduction of the snapshot's run, not a behavior change).
METADATA_KEYS = [
    "config_path", "scenario_path", "mapping_path", "floor_source",
    "floor_profile", "floor_seed", "floor_probs", "mode", "rng_seed",
    "dynamic_pool", "return_leg", "scenario_window", "window",
]


def _load_snapshot(name: str) -> dict:
    return json.loads((RESULTS / name).read_text())


def _replay(snapshot: dict) -> dict:
    """Re-run run_baseline with the exact params the snapshot itself
    recorded, so this test tracks the snapshot's actual provenance rather
    than a second, potentially stale, hard-coded copy of those params.
    `mapping_path` is deliberately re-resolved (passed as None) rather than
    reusing the snapshot's absolute path, which may not be portable."""
    return run_baseline(
        config_path=snapshot["config_path"],
        scenario_path=snapshot["scenario_path"],
        mapping_path=None,
        rng_seed=snapshot["rng_seed"],
        dynamic_pool=snapshot["dynamic_pool"],
        return_leg=snapshot["return_leg"],
        scenario_window=snapshot["scenario_window"],
        floor_profile=snapshot["floor_profile"],
        floor_seed=snapshot["floor_seed"],
    )


def _flatten(d: dict, prefix: str = "") -> dict:
    out = {}
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(_flatten(v, key + "."))
        else:
            out[key] = v
    return out


def _canonical(value) -> str:
    """`default=str` renders NaN as the literal token `NaN` so two
    identical values compare equal despite Python's `nan != nan`."""
    return json.dumps(value, sort_keys=True, default=str)


@pytest.mark.parametrize("name", SNAPSHOT_FILES)
def test_h0_replay_matches_frozen_snapshot(name: str):
    snapshot = _load_snapshot(name)
    replay = _replay(snapshot)

    # 1. run metadata: exact match (bounded dict, safe to assert directly)
    s_meta = {k: snapshot[k] for k in METADATA_KEYS}
    r_meta = {k: replay[k] for k in METADATA_KEYS}
    assert s_meta == r_meta, f"{name}: run metadata mismatch -- {s_meta} vs {r_meta}"

    # 2. per_order event trace + model_vars time series: the actual
    # simulated behavior. Compare via canonicalized string equality only
    # (never via pytest's auto-diff on failure -- see module docstring) --
    # a bounded custom message avoids ever invoking a full string diff.
    for field in ("per_order", "model_vars"):
        matches = _canonical(snapshot[field]) == _canonical(replay[field])
        assert matches, (
            f"{name}: {field} differs from the frozen snapshot -- H0 "
            "simulated behavior changed. Do not inspect this via a raw "
            "string diff (observed to hang pytest's assertion "
            "introspection); load both sides with json.loads and diff "
            "structurally instead."
        )

    # 3. kpi_summary: superset invariant -- every key present in the
    # snapshot must survive unchanged; new additive keys are allowed (see
    # module docstring point 2).
    s_kpi = _flatten(snapshot["kpi_summary"])
    r_kpi = _flatten(replay["kpi_summary"])
    missing = sorted(set(s_kpi) - set(r_kpi))
    changed = sorted(k for k in set(s_kpi) & set(r_kpi) if s_kpi[k] != r_kpi[k])
    assert not missing and not changed, (
        f"{name}: kpi_summary regression -- missing keys={missing}, "
        f"changed keys={changed}"
    )


# ------------------------------------------------- pre-§1.6 regression path

@pytest.mark.parametrize("name", PRE_BASEMENT_FILES)
def test_nobasement_replay_matches_pre_basement_snapshot(name: str):
    """n_basements=0 must still reproduce the pre-§1.6 run bit-for-bit.

    Adding the basements changed the *building*; this gate asserts it did not
    change the *model*. It is the reason `_draw_ground_floor` deliberately
    consumes no randomness when the lobby is the only endpoint -- otherwise the
    pedestrian RNG stream would shift and this test could never pass, leaving
    the rank refactor (elevator nearest-stop, wait estimation, position series)
    unguarded against silent above-ground drift.
    """
    snapshot = json.loads((PRE_BASEMENT_DIR / name).read_text())
    replay = run_baseline(
        config_path=NOBASEMENT_CONFIG,
        scenario_path=snapshot["scenario_path"],
        mapping_path=None,
        rng_seed=snapshot["rng_seed"],
        dynamic_pool=snapshot["dynamic_pool"],
        return_leg=snapshot["return_leg"],
        scenario_window=snapshot["scenario_window"],
        floor_profile=snapshot["floor_profile"],
        floor_seed=snapshot["floor_seed"],
    )

    for field in ("per_order", "model_vars"):
        matches = _canonical(snapshot[field]) == _canonical(replay[field])
        assert matches, (
            f"pre_basement/{name}: {field} differs -- adding the basements "
            "changed behaviour on the basement-free path, which it must not. "
            "Diff structurally (json.loads), never as a raw string."
        )

    s_kpi = _flatten(snapshot["kpi_summary"])
    r_kpi = _flatten(replay["kpi_summary"])
    missing = sorted(set(s_kpi) - set(r_kpi))
    changed = sorted(
        k for k in set(s_kpi) & set(r_kpi)
        if _canonical(s_kpi[k]) != _canonical(r_kpi[k])
    )
    assert not missing and not changed, (
        f"pre_basement/{name}: kpi_summary regression -- missing={missing}, "
        f"changed={changed}"
    )
