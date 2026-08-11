"""V-DET determinism / two-channel variance-source verification (Stage V5d,
etc/plan_h0_verification.md §2 L6 item 1, §0.3 fact 7).

Paper track (dynamic pool + scenario window + floor_profile="uniform",
sigma_eps=0.0 per configs/baseline_10f.yaml `rider_process.sigma_eps`) is
deterministic given (rng_seed, floor_seed). Per §0.3-7 / P3, `floor_seed`
defaults to `rng_seed` when not given, so an `rng_seed` sweep with the
default wiring moves *two* independent RNG streams:

  1. pedestrian stream  -- `model.py` `self.ped_rng = default_rng(rng_seed + 1)`
                            (elevator contention: pedestrians are
                            `elevator_only: true`, competing with riders for
                            EV1/EV2 -- corridor congestion itself is NOT
                            modeled per D3, walkers are constant-speed)
  2. floor/office stream -- `floor_demand.py` `FloorDemandModel.sample`:
                            `default_rng([FLOOR_STREAM_TAG, floor_seed, ord_id])`,
                            and `floor_seed` defaults to `rng_seed`
                            (`model.py` `self.floor_seed = rng_seed if
                            floor_seed is None else int(floor_seed)`)

`vertical_mode` is drawn from a *third*, independent stream keyed off the
config-fixed `vertical.mode_seed` (42, XOR ord_id) -- untouched by either
rng_seed or floor_seed, so it is invariant across every sweep in this file
(confirmed incidentally by the exact per-order equality checks below, which
compare `(floor, office_id, vertical_mode)` triples).

Pinning `floor_seed` to a fixed value while sweeping `rng_seed` freezes
stream 2 (every order's floor/office draw is unchanged) and isolates stream
1: KPI differences under that sweep can only be explained by the pedestrian
stream. This is the CRN control described in §0.3-7.

Only `runtime_wall_sec` (a `time.perf_counter()` wall-clock reading,
`simulation/run.py` `run_baseline`) is excluded from the bit-identical
comparison -- it is the sole non-deterministic field in the `run_baseline`
result dict; every other key (`config_path`, `scenario_path`, `mapping_path`,
`floor_source/profile/seed/probs`, `mode`, `rng_seed`, `dynamic_pool`,
`return_leg`, `scenario_window`, `window`, `config`, `per_order`,
`kpi_summary`, `model_vars`) is derived purely from the deterministic model
run.

Uses `simulation.run.run_baseline` in-process (the `experiments/vv_all39.py`
pattern) on a single small scenario (K50_1) for speed -- no CLI subprocess,
no result JSON written to disk.
"""

from __future__ import annotations

import json

import pytest

from simulation.run import run_baseline

pytestmark = pytest.mark.vv

SCENARIO = "data/data1/K50_1.json"

# The only field in a run_baseline() result that is not a pure function of
# (config, scenario, rng_seed, floor_seed, ...): a time.perf_counter() wall
# clock reading (simulation/run.py run_baseline -> "runtime_wall_sec").
NONDETERMINISTIC_KEYS = {"runtime_wall_sec"}


def _run(rng_seed: int, floor_seed: int | None = None) -> dict:
    return run_baseline(
        scenario_path=SCENARIO,
        rng_seed=rng_seed,
        floor_profile="uniform",
        floor_seed=floor_seed,
    )


def _strip(result: dict) -> dict:
    return {k: v for k, v in result.items() if k not in NONDETERMINISTIC_KEYS}


def _canonical_json(result: dict) -> str:
    """Deterministic string form of a stripped result, safe for equality
    *and* inequality checks. `model_vars` contains NaN placeholders
    (running-mean series before the first delivery) and Python's `nan !=
    nan`, so a raw dict `==`/`!=` on two identical runs would falsely report
    a difference. json.dumps renders every NaN as the literal token `NaN`,
    so two identical runs serialize to identical strings and two runs that
    differ only by RNG-driven content serialize to different strings."""
    return json.dumps(_strip(result), sort_keys=True, default=str)


def _floor_assignment(result: dict) -> dict[int, tuple[int, int, str]]:
    """Per-order (floor, office_id, vertical_mode) triple, keyed by ord_id."""
    return {
        r["ord_id"]: (r["floor"], r["office_id"], r["vertical_mode"])
        for r in result["per_order"]
    }


def _t_e2e_mean(result: dict) -> float:
    return result["kpi_summary"]["customer"]["t_e2e_mean_sec"]


# --------------------------------------------------------------------- runs

@pytest.fixture(scope="module")
def run_seed42() -> dict:
    return _run(42)


@pytest.fixture(scope="module")
def run_seed42_repeat() -> dict:
    """Independent second invocation of run_baseline(seed=42) -- a fresh
    model object end to end, not a cached/reused result."""
    return _run(42)


@pytest.fixture(scope="module")
def run_seed7() -> dict:
    return _run(7)


@pytest.fixture(scope="module")
def run_seed42_fs999() -> dict:
    return _run(42, floor_seed=999)


@pytest.fixture(scope="module")
def run_seed7_fs999() -> dict:
    return _run(7, floor_seed=999)


# ---------------------------------------------------------- 1. bit-identical

def test_bit_identical_same_seed_repeat(run_seed42, run_seed42_repeat):
    """Two independent runs of the same (rng_seed, floor_seed=default) are
    bit-identical modulo the wall-clock timing field."""
    assert _canonical_json(run_seed42) == _canonical_json(run_seed42_repeat)


def test_bit_identical_exclusion_is_exactly_wall_time(run_seed42, run_seed42_repeat):
    """The only key a caller must exclude for the comparison above to be
    meaningful is runtime_wall_sec -- confirm it's present (not vacuously
    excluding nothing) and that no other key was silently dropped."""
    assert run_seed42.keys() == run_seed42_repeat.keys()
    assert set(run_seed42.keys()) >= NONDETERMINISTIC_KEYS
    assert set(run_seed42.keys()) - NONDETERMINISTIC_KEYS == set(_strip(run_seed42).keys())


# ------------------------------------------------- 2. two-channel (default)

def test_default_floor_seed_resolves_to_rng_seed(run_seed42, run_seed7):
    """P3 wiring sanity: floor_seed provenance == rng_seed when unspecified."""
    assert run_seed42["floor_seed"] == 42
    assert run_seed7["floor_seed"] == 7


def test_rng_seed_sweep_default_moves_floor_assignment(run_seed42, run_seed7):
    """Channel (a): with floor_seed left at its default (= rng_seed), an
    rng_seed change actually reassigns floor/office/mode for a nontrivial
    share of orders (floor channel is live, not merely provisioned)."""
    f42 = _floor_assignment(run_seed42)
    f7 = _floor_assignment(run_seed7)
    assert set(f42) == set(f7)  # same K, same ord_ids
    diffs = [oid for oid in f42 if f42[oid] != f7[oid]]
    assert diffs, (
        "expected at least one order's (floor, office_id, vertical_mode) to "
        "change between rng_seed=42 and rng_seed=7 under the default "
        "floor_seed=rng_seed wiring"
    )
    # majority of a 50-order scenario should move under an independent
    # categorical redraw (loose sanity bound, not a golden number)
    assert len(diffs) >= 5


def test_rng_seed_sweep_default_moves_kpi(run_seed42, run_seed7):
    """Channel (a)+(b) combined: with the default two-channel wiring, KPI
    moves under an rng_seed change (pedestrian stream AND floor stream both
    differ)."""
    assert _t_e2e_mean(run_seed42) != _t_e2e_mean(run_seed7)
    assert _canonical_json(run_seed42) != _canonical_json(run_seed7)


# ------------------------------------- 3. pinned floor_seed => single channel

def test_pinned_floor_seed_freezes_floor_assignment(run_seed42_fs999, run_seed7_fs999):
    """With floor_seed pinned to the same value, an rng_seed sweep leaves
    every order's (floor, office_id, vertical_mode) exactly unchanged --
    the floor channel is fully neutralized (reduces to the pedestrian
    channel alone)."""
    assert run_seed42_fs999["floor_seed"] == 999
    assert run_seed7_fs999["floor_seed"] == 999
    f42 = _floor_assignment(run_seed42_fs999)
    f7 = _floor_assignment(run_seed7_fs999)
    assert f42 == f7  # exact match for every order, not just the same set


def test_pinned_floor_seed_kpi_still_moves_pedestrian_channel_alone(
    run_seed42_fs999, run_seed7_fs999
):
    """Even with the floor assignment frozen bit-for-bit (previous test),
    KPI still differs under the rng_seed sweep: the pedestrian stream
    (elevator contention) is a live channel on its own, not an artifact of
    the floor channel."""
    assert _t_e2e_mean(run_seed42_fs999) != _t_e2e_mean(run_seed7_fs999)
    assert _canonical_json(run_seed42_fs999) != _canonical_json(run_seed7_fs999)
