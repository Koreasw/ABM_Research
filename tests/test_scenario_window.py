"""scenario_window mode — demand-driven pedestrian window + warm-up start.

2026-07-09 사용자 확정: 보행자 혼잡은 데이터 ORD_TIME의 전후 1시간
([min ORD − margin, max ORD + margin])에 적용하고, 시뮬레이션 clock은 윈도우
시작(첫 주문 1시간 전)에서 출발한다. scenario_window=False(기본값)는 기존
lunch-peak horizon 윈도우를 그대로 재현해야 한다 (동결 회귀 경로).

R8 (etc/plan_h0v21_window.md): `configs/baseline_10f.yaml`은 이제
`window_policy: delivery`를 선언한다. 이 파일이 검사하는 **legacy_margin 계약은
동결 회귀 경로의 계약**이므로, 그 테스트들은 `LEGACY_CFG`(정책만 되돌린 사본)에
고정한다 — baseline config를 따라가게 두면 검사 대상이 통째로 바뀌어 버린다.
delivery 계약 쪽은 `tests/test_termination_policy.py`가 담당한다.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from simulation.model import ROOT, BuildingHandoffModel
from simulation.space import load_config

CFG = load_config(ROOT / "configs" / "baseline_10f.yaml")
MARGIN = CFG["pedestrian"]["window_margin_sec"]
START = CFG["simulation"]["lunch_peak_start_sec"]
HORIZON = CFG["simulation"]["horizon_sec"]
OVERRUN = CFG["simulation"]["max_overrun_sec"]

# 정책만 R8 이전으로 되돌린 사본 — 나머지 상수는 baseline과 공유한다
LEGACY_CFG = copy.deepcopy(CFG)
LEGACY_CFG["simulation"]["window_policy"] = "legacy_margin"


def _ord_span(model) -> tuple[float, float]:
    ts = [o.ord_time_abs_sec for o in model.orders]
    return min(ts), max(ts)


def test_legacy_window_unchanged():
    # scenario_window 미지정 -> legacy_margin 정책에서는 False (R8 이전 기본값)
    m = BuildingHandoffModel(config=LEGACY_CFG, rng_seed=42)
    assert m.scenario_window is False
    assert m.window_policy == "legacy_margin"
    assert m.termination_policy == "drain_all"
    assert m.clock_start_sec == START
    assert m.clock_sec == START
    assert m.ped_start_sec == START
    assert m.ped_end_sec == START + HORIZON
    assert m.cap_time_sec == START + HORIZON + OVERRUN


def test_window_bounds_derived_from_orders():
    m = BuildingHandoffModel(
        config=LEGACY_CFG, rng_seed=42, dynamic_pool=True, scenario_window=True
    )
    t_min, t_max = _ord_span(m)
    assert m.ped_start_sec == pytest.approx(t_min - MARGIN)
    assert m.ped_end_sec == pytest.approx(t_max + MARGIN)
    assert m.clock_start_sec == m.ped_start_sec
    assert m.clock_sec == m.clock_start_sec
    assert m.cap_time_sec == pytest.approx(m.ped_end_sec + OVERRUN)
    # warm-up: clock starts a full margin before the first order
    assert t_min - m.clock_sec == pytest.approx(MARGIN)


def test_window_applies_to_static_path_too():
    m = BuildingHandoffModel(config=LEGACY_CFG, rng_seed=42, scenario_window=True)
    t_min, t_max = _ord_span(m)
    assert m.ped_start_sec == pytest.approx(t_min - MARGIN)
    assert m.ped_end_sec == pytest.approx(t_max + MARGIN)


def test_explicit_legacy_window_rejected_under_delivery():
    """명시적 모순은 조용히 덮지 않는다 (R8-f). 기본값(None)은 정책이 정한다."""
    with pytest.raises(ValueError, match="scenario_window=False"):
        BuildingHandoffModel(config=CFG, rng_seed=42, scenario_window=False)
    m = BuildingHandoffModel(config=CFG, rng_seed=42)
    assert m.window_policy == "delivery" and m.scenario_window is True


@pytest.fixture(scope="module")
def window_run():
    m = BuildingHandoffModel(
        config=CFG, rng_seed=42, dynamic_pool=True, scenario_window=True
    )
    m.run_to_completion()
    return m


def test_window_run_completes_all_orders(window_run):
    m = window_run
    assert m.terminated_by_cap is False
    assert all(c.delivered_at_sec is not None for c in m.customer_by_ord_id.values())
    assert len(m.rider_records) == m.K
    assert m.rider_pool.free == m.rider_pool.initial  # pool fully restored


def test_pedestrians_cover_warmup_and_cooldown(window_run):
    m = window_run
    t_min, t_max = _ord_span(m)
    spawned = [p["spawned_at_sec"] for p in m.ped_done_log]
    assert any(t < t_min for t in spawned), "no pedestrians during warm-up hour"
    assert any(t > t_max for t in spawned), "no pedestrians during cool-down hour"
    assert min(spawned) >= m.ped_start_sec
    assert max(spawned) <= m.ped_end_sec


def test_first_riders_meet_congested_building(window_run):
    """Warm-up purpose: EVs must already be moving before the first order."""
    m = window_run
    t_min, _ = _ord_span(m)
    warmup_boards = [
        b for ev in m.elevators for b in ev.boarding_log if b["t_board_sec"] < t_min
    ]
    assert len(warmup_boards) > 0


def test_window_kpi_span(window_run):
    from simulation.kpi import summarize

    m = window_run
    s = summarize(m)
    sim = s["simulation"]
    assert sim["scenario_window"] is True
    assert sim["clock_start_sec"] == pytest.approx(m.clock_start_sec)
    assert sim["wall_span_sec"] == pytest.approx(m.clock_sec - m.clock_start_sec)
    # R8: "the run spans at least the ped window" was a drain-all property —
    # under `delivery` the clock stops at the last rider exit, which is EARLIER
    # than ped_end (pinned to the cap) by design. Assert the live contract.
    if m.termination_policy == "drain_all":
        assert m.clock_sec >= m.ped_end_sec
    else:
        last_exit = max(r["exited_at_sec"] for r in m.rider_records)
        assert m.clock_sec == pytest.approx(last_exit)
        assert m.clock_sec < m.ped_end_sec


def test_cli_resolve_mapping_convention(tmp_path):
    from simulation.run import resolve_mapping

    p = resolve_mapping("data/data1/K300_4.json", None, "v5")
    assert p == ROOT / "data" / "floor_mapping" / "K300_4_floor_mapping_v5.json"
    p4 = resolve_mapping("data/data1/K50_1.json", None, "v4")
    assert p4.name == "K50_1_floor_mapping_v4.json"
    explicit = tmp_path / "custom.json"
    assert resolve_mapping("data/data1/K50_1.json", explicit, "v5") == explicit


def test_cli_dynamic_window_smoke(tmp_path):
    """run.py default paper track is the profile path (uniform), not v5.

    Contract update (etc/plan_demand_mapping_profile.md Stage 4): the default
    track now draws floors from the population-density profile, so provenance
    is floor_source=profile / mapping_path=None.
    """
    import json as _json

    from simulation import run as run_mod

    out = tmp_path / "res.json"
    run_mod.main(["--out", str(out)])
    res = _json.loads(out.read_text())
    assert res["dynamic_pool"] is True
    assert res["scenario_window"] is True
    assert res["floor_source"] == "profile"
    assert res["floor_profile"] == "uniform"
    assert res["floor_seed"] == res["rng_seed"]  # default: floor_seed = rng_seed
    assert res["mapping_path"] is None
    assert res["floor_probs"] is not None
    assert res["floor_probs"] == pytest.approx([1 / 9] * 9)
    assert res["kpi_summary"]["customer"]["n_delivered"] == res["kpi_summary"]["customer"]["n_orders"]
    assert res["window"]["ped_start_sec"] < res["window"]["ped_end_sec"]


def test_cli_frozen_v5_smoke(tmp_path):
    """--mapping-version v5 reproduces the frozen distance-band provenance."""
    import json as _json

    from analysis.map_floor_v5 import generate
    from simulation import run as run_mod

    v5_path = ROOT / "data" / "floor_mapping" / "K50_1_floor_mapping_v5.json"
    if not v5_path.exists():
        generate("data/data1/K50_1.json", quiet=True)

    out = tmp_path / "res.json"
    run_mod.main(["--mapping-version", "v5", "--out", str(out)])
    res = _json.loads(out.read_text())
    assert res["dynamic_pool"] is True
    assert res["scenario_window"] is True
    assert res["floor_source"] == "mapping"
    assert res["floor_profile"] is None
    assert res["mapping_path"].endswith("K50_1_floor_mapping_v5.json")
    assert res["kpi_summary"]["customer"]["n_delivered"] == res["kpi_summary"]["customer"]["n_orders"]


def test_cli_profile_mapping_mutually_exclusive(tmp_path):
    """profile flags and frozen distance-band flags cannot be combined."""
    from simulation import run as run_mod

    out = tmp_path / "res.json"
    with pytest.raises(SystemExit):
        run_mod.main(["--mapping-version", "v5",
                      "--floor-profile", "bottom_heavy", "--out", str(out)])
    with pytest.raises(SystemExit):
        run_mod.main(["--static", "--floor-seed", "7", "--out", str(out)])
