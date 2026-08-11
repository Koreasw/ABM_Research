"""Step A0 — the Phase A infrastructure must not perturb H0.

A0 is the only Phase A step that edits code H0 actually executes (A1's robot
agent is never constructed in H0). Three things landed:

  1. `robot:` / `handoff:` config blocks got a validated reader
     (simulation/config_params.py) — 점검 결정 12.
  2. `simulation.max_overrun_sec_robot` — a robot-mode-only safety cap so H0's
     calibrated 7200 is untouched — 점검 결정 11.
  3. `simulation.ped_decay` — post-peak decay of the background stream, so a
     long robot drain does not run at lunch-peak intensity forever — 점검 결정 10.

This module gates (1) and (2); `test_a0_ped_decay.py` gates (3). Between them
they discharge Phase A 완료 기준 #9 ("config 소비 회귀 테스트"): the claim that
H0 does not read these blocks becomes *proved*, which is what licenses
`test_h0_frozen_snapshot.py` to exclude `config` from its comparison.

Bit-identity is asserted on `per_order` + `model_vars` — the same pair that
module uses, and for the same reason: they are the simulated behaviour, while
`kpi_summary` is a derived view and `runtime_wall_sec` is a wall clock.
"""

from __future__ import annotations

import copy
import json

import pytest

from simulation.config_params import (
    DEFAULT_HANDOFF_RNG_TAG,
    BatteryParams,
    HandoffParams,
    PedDecay,
    RobotParams,
)
from simulation.model import ROOT, BuildingHandoffModel, HandoffMode
from simulation.space import load_config

pytestmark = pytest.mark.vv

SCENARIO = "data/data1/K50_1.json"
BASELINE_CONFIG = "configs/baseline_10f.yaml"


def _model(config_overrides: dict | None = None) -> BuildingHandoffModel:
    """A paper-track H0 model, optionally with dotted-path config overrides.

    Drives `BuildingHandoffModel` directly rather than `run_baseline`, which
    takes a config *path* and would need a temp YAML per parametrisation. The
    kwargs mirror run.py's paper-track call exactly.
    """
    cfg = copy.deepcopy(load_config(ROOT / BASELINE_CONFIG))
    for dotted, value in (config_overrides or {}).items():
        node = cfg
        *parents, leaf = dotted.split(".")
        for p in parents:
            node = node[p]
        node[leaf] = value
    return BuildingHandoffModel(
        mode=HandoffMode.H0_DIRECT,
        config=cfg,
        scenario_path=SCENARIO,
        rng_seed=42,
        dynamic_pool=True,
        return_leg=False,
        scenario_window=True,
        floor_profile="uniform",
        floor_seed=42,
    )


def _behaviour(config_overrides: dict | None = None) -> str:
    """(per-order records, per-tick model vars) — the simulated behaviour.

    Same pair `test_h0_frozen_snapshot.py` compares, and for the same reason:
    `kpi_summary` is a derived view and `runtime_wall_sec` is a wall clock.

    Serialised with `default=str` for the same reason that module does it: the
    running-mean model vars start as NaN, and `nan != nan` would make every
    comparison here fail no matter what the model did.
    """
    m = _model(config_overrides)
    m.run_to_completion()
    mv = m.datacollector.get_model_vars_dataframe()
    return json.dumps(
        {
            "per_order": sorted(m.rider_records, key=lambda r: r["ord_id"]),
            "model_vars": {k: list(v) for k, v in mv.items()},
        },
        sort_keys=True,
        default=str,
    )


# --------------------------------------------------------------------------
# 완료 기준 #9 — H0 does not consume the Phase A blocks
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "override",
    [
        pytest.param({"robot.n_robots": 99}, id="robot.n_robots"),
        pytest.param({"robot.speed_mps": 7.5}, id="robot.speed_mps"),
        pytest.param({"robot.capa": 3}, id="robot.capa"),
        pytest.param({"robot.service_time_drop_sec": 999.0}, id="robot.drop_sec"),
        pytest.param({"handoff.service_mean_sec": 1.0}, id="handoff.mean"),
        pytest.param({"handoff.service_sd_sec": 0.0}, id="handoff.sd"),
        pytest.param(
            {"simulation.max_overrun_sec_robot": 1.0}, id="max_overrun_robot"
        ),
    ],
)
def test_h0_ignores_phase_a_config_blocks(override: dict) -> None:
    """Mutating a Phase A knob must not move a single H0 number.

    `max_overrun_sec_robot` is in here on purpose: at 1.0 s it would truncate
    the run instantly *if* H0 ever read it, so this parametrisation is a real
    trap for the mode branch, not a formality.
    """
    assert _behaviour() == _behaviour(override)


def test_h0_battery_block_is_inert() -> None:
    """The whole battery sub-block, replaced wholesale, changes nothing in H0."""
    mutated = _behaviour(
        {
            "robot.battery": {
                "capacity_wh": 1.0,
                "wh_per_m": 99.0,
                "wh_per_min_idle": 99.0,
                "charge_wh_per_min": 0.001,
                "soc_low_pct": 90.0,
                "soc_resume_pct": 95.0,
                "soc_init_pct": 91.0,
            }
        }
    )
    assert _behaviour() == mutated


def test_h0_still_uses_its_own_max_overrun() -> None:
    """H0 reads `max_overrun_sec`, never the robot key — cap arithmetic proves it."""
    cfg = load_config(ROOT / BASELINE_CONFIG)
    m = _model()
    last_order = max(o.ord_time_abs_sec for o in m.orders)
    assert m.max_overrun_sec == cfg["simulation"]["max_overrun_sec"]
    assert m.cap_time_sec == pytest.approx(last_order + 7200.0)
    # ...and the robot key is present and different, so the assertion above is
    # not vacuous.
    assert cfg["simulation"]["max_overrun_sec_robot"] != 7200


# --------------------------------------------------------------------------
# The readers themselves
# --------------------------------------------------------------------------


def test_baseline_config_declares_the_reviewed_values() -> None:
    """The values the plan review settled on are actually in the YAML."""
    cfg = load_config(ROOT / BASELINE_CONFIG)
    rp = RobotParams.from_config(cfg)
    assert rp.n_robots == 5          # 점검 결정 1 (구 3)
    assert rp.speed_mps == 1.0
    assert rp.capa == 100            # 코퍼스 max VOL
    assert rp.battery.capacity_wh == 1300.0
    assert rp.battery.wh_per_m == 0.14
    assert rp.battery.wh_per_min_idle == 1.0
    assert rp.battery.soc_low_pct == 20.0
    assert rp.battery.soc_resume_pct == 40.0

    hp = HandoffParams.from_config(cfg)
    assert (hp.service_mean_sec, hp.service_sd_sec) == (60.0, 15.0)   # R0-3
    assert hp.rng_stream_tag == DEFAULT_HANDOFF_RNG_TAG               # 'hoff'


def test_charge_rate_matches_the_20_to_80_pct_hour_spec() -> None:
    """13.0 Wh/min is not a free parameter — it is 20→80 % in one hour."""
    b = RobotParams.from_config(load_config(ROOT / BASELINE_CONFIG)).battery
    wh_20_to_80 = b.wh_for_soc_pct(80.0) - b.wh_for_soc_pct(20.0)
    assert wh_20_to_80 / b.charge_wh_per_min == pytest.approx(60.0, rel=0.01)
    # and the recovery leg the policy actually uses: 20 % -> 40 % = 20 min
    wh_20_to_40 = b.wh_for_soc_pct(40.0) - b.wh_for_soc_pct(20.0)
    assert wh_20_to_40 / b.charge_wh_per_min == pytest.approx(20.0, rel=0.01)


def test_missing_blocks_fall_back_to_pre_a0_defaults() -> None:
    """The frozen regression config carries neither block — it must still load.

    This is the contract that keeps
    `test_nobasement_replay_matches_pre_basement_snapshot` green.
    """
    cfg = load_config(ROOT / "configs/regression_nobasement_10f.yaml")
    assert "handoff" not in cfg
    assert "battery" not in cfg["robot"]
    rp = RobotParams.from_config(cfg)
    assert rp.battery.capacity_wh == 1300.0        # defaulted, not crashed
    assert HandoffParams.from_config(cfg).service_mean_sec == 60.0
    assert RobotParams.from_config({}).n_robots == 5


@pytest.mark.parametrize(
    "block, msg",
    [
        ({"capacity_wh": 0.0}, "capacity_wh"),
        ({"charge_wh_per_min": 0.0}, "charge_wh_per_min"),
        ({"wh_per_m": -1.0}, "drain rates"),
        # resume must be strictly above the cut-off, else the robot leaves the
        # dock and immediately re-triggers -> charge/dispatch loop
        ({"soc_low_pct": 40.0, "soc_resume_pct": 40.0}, "soc_low_pct"),
        ({"soc_low_pct": 50.0, "soc_resume_pct": 30.0}, "soc_low_pct"),
        ({"soc_init_pct": 0.0}, "soc_init_pct"),
        ({"soc_init_pct": 101.0}, "soc_init_pct"),
    ],
)
def test_battery_validation_rejects_incoherent_blocks(block: dict, msg: str) -> None:
    with pytest.raises(ValueError, match=msg):
        BatteryParams.from_block(block)


@pytest.mark.parametrize(
    "cfg, msg",
    [
        ({"robot": {"n_robots": 0}}, "n_robots"),
        ({"robot": {"n_robots": 2.5}}, "n_robots"),
        ({"robot": {"capa": 0}}, "capa"),
        ({"robot": {"speed_mps": 0.0}}, "speed_mps"),
    ],
)
def test_robot_validation_rejects_incoherent_blocks(cfg: dict, msg: str) -> None:
    with pytest.raises(ValueError, match=msg):
        RobotParams.from_config(cfg)


def test_handoff_rng_tag_must_be_an_int() -> None:
    with pytest.raises(ValueError, match="rng_stream_tag"):
        HandoffParams.from_config({"handoff": {"rng_stream_tag": "hoff"}})


# --------------------------------------------------------------------------
# The robot-mode cap branch (unreachable until A2 lifts the mode gate)
# --------------------------------------------------------------------------


def test_robot_mode_set_is_complete_and_only_h1_is_open() -> None:
    """The gate is lifted one mode at a time; the *set* must not drift.

    `ROBOT_MODES` drives A0's separate robot overrun cap, so it has to keep
    listing every mode with a fleet — including the two that are still refused
    at construction. A2 opened H1_SYNC; H2/H3 stay closed until their agents
    exist, because an open gate there would silently run them as H1.
    """
    from simulation.model import ROBOT_MODES

    assert ROBOT_MODES == {
        HandoffMode.H1_SYNC, HandoffMode.H2_QUEUED, HandoffMode.H3_LOCKER
    }
    assert HandoffMode.H0_DIRECT not in ROBOT_MODES
    for mode in (HandoffMode.H2_QUEUED, HandoffMode.H3_LOCKER):
        with pytest.raises(NotImplementedError):
            BuildingHandoffModel(mode=mode, scenario_path=SCENARIO)
    # H1 is open and carries a fleet (A2)
    m = BuildingHandoffModel(mode=HandoffMode.H1_SYNC, scenario_path=SCENARIO)
    assert len(m.robots) == m.n_robots > 0
