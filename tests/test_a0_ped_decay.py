"""Step A0 — post-peak pedestrian decay (점검 결정 10).

Why the decay exists
--------------------
R8's `delivery` policy spawns background pedestrians until the run ends, with no
cutoff — clipping the tail biases the late orders (W_EV −28 %, plan §1.2). For
H0 that is harmless: runs are ~7,700 ticks. Robot modes drain far longer (K300
≈27,000 ticks with 5 robots), and holding the *lunch-peak* rate of 7.5/min for
7.5 h is both unphysical and destroys cross-mode comparability — H0 K300 would
see ~960 pedestrians and H1 K300 ~3,375, so "same scenario" would be false.

Why it cannot touch H0
----------------------
Two independent guarantees, each sufficient on its own; this module pins both:

  1. **Unreachable.** The anchor is `last order + start_after_last_order_sec`,
     and the default 7200 equals H0's `max_overrun_sec`. H0's cap is
     `last order + max_overrun_sec`, so H0 stops *at* the anchor at the latest,
     and `rate_per_sec_at` compares with a **strict** `>`.
  2. **Non-perturbing even if reached.** The decay changes the Poisson rate's
     value, never the RNG call pattern — `_spawn_pedestrians` draws
     `ped_rng.poisson(rate*dt)` exactly once per tick either way.

Guarantee 1 is what `test_h0_cap_never_reaches_the_decay_anchor` checks; it is
the one that would break first if someone lowered `start_after_last_order_sec`
or raised H0's `max_overrun_sec`.
"""

from __future__ import annotations

import copy
import json

import pytest

from simulation.config_params import PedDecay
from simulation.model import ROOT, BuildingHandoffModel, HandoffMode
from simulation.space import load_config

pytestmark = pytest.mark.vv

BASELINE_CONFIG = "configs/baseline_10f.yaml"
# Both K levels of the frozen snapshot set, at the ends of the contention range.
SCENARIOS = ["data/data1/K50_1.json", "data/data1/K300_4.json"]


def _model(scenario: str, cfg: dict) -> BuildingHandoffModel:
    return BuildingHandoffModel(
        mode=HandoffMode.H0_DIRECT,
        config=cfg,
        scenario_path=scenario,
        rng_seed=42,
        dynamic_pool=True,
        return_leg=False,
        scenario_window=True,
        floor_profile="uniform",
        floor_seed=42,
    )


def _behaviour(scenario: str, cfg: dict) -> str:
    """Serialised with `default=str` so NaN compares equal to NaN — the running
    -mean model vars start as NaN and would otherwise fail every comparison
    regardless of what the model did (same trick as test_h0_frozen_snapshot)."""
    m = _model(scenario, cfg)
    m.run_to_completion()
    mv = m.datacollector.get_model_vars_dataframe()
    return json.dumps(
        {
            "per_order": sorted(m.rider_records, key=lambda r: r["ord_id"]),
            "model_vars": {k: list(v) for k, v in mv.items()},
            "ped_spawned": m.ped_spawned,
            "termination_reason": m.termination_reason,
        },
        sort_keys=True,
        default=str,
    )


# --------------------------------------------------------------------------
# Guarantee 1 — H0 cannot reach the decayed regime
# --------------------------------------------------------------------------


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_h0_cap_never_reaches_the_decay_anchor(scenario: str) -> None:
    """The structural no-touch guarantee, stated as an inequality.

    If this fails, the H0 v2.1 verification battery is no longer replaying the
    same pedestrian stream it was signed off on — fix the config, do not relax
    the test.
    """
    cfg = load_config(ROOT / BASELINE_CONFIG)
    m = _model(scenario, cfg)
    assert m.ped_decay is not None
    assert m.cap_time_sec <= m.ped_decay.start_sec
    # And in practice H0 stops far earlier than even the cap.
    m.run_to_completion()
    assert m.termination_reason == "delivery_complete"
    assert m.clock_sec < m.ped_decay.start_sec


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_h0_is_bit_identical_with_and_without_the_decay_block(scenario: str) -> None:
    """Deleting `simulation.ped_decay` changes nothing on the H0 paper track."""
    with_decay = load_config(ROOT / BASELINE_CONFIG)
    without = copy.deepcopy(with_decay)
    del without["simulation"]["ped_decay"]
    assert _behaviour(scenario, with_decay) == _behaviour(scenario, without)


def test_absent_block_disables_the_decay_entirely() -> None:
    """The frozen regression config declares no decay — it must stay flat."""
    cfg = load_config(ROOT / "configs/regression_nobasement_10f.yaml")
    assert "ped_decay" not in cfg["simulation"]
    m = BuildingHandoffModel(
        config=cfg, scenario_path=SCENARIOS[0], rng_seed=42,
        dynamic_pool=True, scenario_window=True,
    )
    assert m.ped_decay is None
    assert m._ped_rate_at(m.clock_sec) == m.ped_rate_per_sec
    assert m._ped_rate_at(1e9) == m.ped_rate_per_sec


# --------------------------------------------------------------------------
# Guarantee 2 — the rate profile itself
# --------------------------------------------------------------------------


def _decay(**kw) -> PedDecay:
    cfg = {
        "simulation": {
            "ped_decay": {
                "start_after_last_order_sec": kw.get("start_after", 7200.0),
                "ramp_sec": kw.get("ramp", 1800.0),
                "floor_rate_per_min": kw.get("floor_per_min", 2.0),
            }
        }
    }
    return PedDecay.from_config(
        cfg, last_order_abs_sec=kw.get("last_order", 1000.0),
        peak_rate_per_sec=kw.get("peak_per_min", 7.5) / 60.0,
    )


def test_rate_profile_is_flat_then_linear_then_flat() -> None:
    d = _decay()
    peak, floor = 7.5 / 60.0, 2.0 / 60.0
    start = 1000.0 + 7200.0
    assert d.start_sec == start
    # strictly before, and *at*, the anchor: unchanged (this equality is the
    # whole no-touch guarantee — see module docstring, guarantee 1)
    assert d.rate_per_sec_at(start - 1.0) == peak
    assert d.rate_per_sec_at(start) == peak
    # ramp: linear interpolation
    assert d.rate_per_sec_at(start + 900.0) == pytest.approx((peak + floor) / 2)
    # floor, reached at the end of the ramp and held
    assert d.rate_per_sec_at(start + 1800.0) == pytest.approx(floor)
    assert d.rate_per_sec_at(start + 1e6) == pytest.approx(floor)
    # monotone non-increasing across the whole span
    ts = [start + i * 60.0 for i in range(0, 40)]
    rates = [d.rate_per_sec_at(t) for t in ts]
    assert all(a >= b for a, b in zip(rates, rates[1:]))


def test_zero_ramp_is_a_step() -> None:
    d = _decay(ramp=0.0)
    assert d.rate_per_sec_at(d.start_sec) == pytest.approx(7.5 / 60.0)
    assert d.rate_per_sec_at(d.start_sec + 1e-9) == pytest.approx(2.0 / 60.0)


def test_no_orders_means_no_anchor() -> None:
    """Without orders there is no lunch peak to decay away from."""
    cfg = {"simulation": {"ped_decay": {"floor_rate_per_min": 2.0}}}
    assert PedDecay.from_config(
        cfg, last_order_abs_sec=None, peak_rate_per_sec=0.125
    ) is None


def test_zero_background_disables_the_decay() -> None:
    """`pedestrian.arrival_rate_per_min: 0` must stay a flat, empty stream.

    Regression pin, not a corner case: the zero-pedestrian building is the
    standard setup for `test_vv_golden_path*.py` and the extreme tests' zero
    arm. A first cut of this validator raised "decay, not a ramp-up" on those
    configs — with a peak of 0 every positive floor rate looks like a ramp-up —
    and took out 11 golden-path/extreme tests.
    """
    cfg = {"simulation": {"ped_decay": {"floor_rate_per_min": 2.0}}}
    assert PedDecay.from_config(
        cfg, last_order_abs_sec=1000.0, peak_rate_per_sec=0.0
    ) is None


@pytest.mark.parametrize(
    "kw, msg",
    [
        ({"start_after": -1.0}, "start_after_last_order_sec"),
        ({"ramp": -1.0}, "ramp_sec"),
        ({"floor_per_min": -1.0}, "floor_rate_per_min"),
        # a "decay" that raises the rate is a modelling error, not a ramp-up knob
        ({"floor_per_min": 9.0}, "decay, not a ramp-up"),
    ],
)
def test_decay_validation(kw: dict, msg: str) -> None:
    with pytest.raises(ValueError, match=msg):
        _decay(**kw)


# --------------------------------------------------------------------------
# The decay actually bites once a run is long enough (the robot-mode case)
# --------------------------------------------------------------------------


def test_decay_reduces_spawns_once_the_anchor_is_passed() -> None:
    """A positive test: with the anchor pulled in, fewer pedestrians spawn.

    H0 can never be in this regime (the tests above pin that), so the effect is
    forced by moving the anchor to the start of the run. This is what a robot
    mode's long drain will experience, and it is the only way to exercise the
    decayed branch before A1 exists.
    """
    base_cfg = load_config(ROOT / BASELINE_CONFIG)
    flat = copy.deepcopy(base_cfg)
    del flat["simulation"]["ped_decay"]

    decayed = copy.deepcopy(base_cfg)
    # anchor at t=0 after the last order would still be past the run; use a
    # negative offset so the decay covers essentially the whole run instead.
    decayed["simulation"]["ped_decay"] = {
        "start_after_last_order_sec": 0.0,
        "ramp_sec": 1.0,
        "floor_rate_per_min": 0.0,
    }
    m_flat = _model(SCENARIOS[0], flat)
    m_flat.run_to_completion()
    m_dec = _model(SCENARIOS[0], decayed)
    m_dec.run_to_completion()

    # The decayed run must spawn strictly fewer pedestrians, and with a floor of
    # 0/min it must spawn none at all after the anchor.
    assert m_dec.ped_spawned < m_flat.ped_spawned
    assert m_dec.ped_decay is not None
    assert m_dec._ped_rate_at(m_dec.ped_decay.start_sec + 10.0) == 0.0
