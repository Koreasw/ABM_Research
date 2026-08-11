"""Tests for analysis.scenario_loader.load_replay / load_replay_v4."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from analysis.load_data import load_scenario, pickup_drop_distance
from analysis.scenario_loader import (
    BuildingOrder,
    BuildingOrderV4,
    DispatchOrder,
    load_dispatch_profile,
    load_dispatch_v5,
    load_replay,
    load_replay_v4,
)
from simulation.floor_demand import rederive_profile_assignment
from simulation.space import load_config
from simulation.vertical_transport import VerticalTransportModel

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "data1" / "K50_1.json"
MAPPING = ROOT / "data" / "floor_mapping" / "K50_1_floor_mapping_v4.json"
MAPPING_V5 = ROOT / "data" / "floor_mapping" / "K50_1_floor_mapping_v5.json"
CONFIG_PATH = ROOT / "configs" / "baseline_10f.yaml"
START = 11.5 * 3600.0


def test_data_present() -> None:
    if not DATA.exists():
        pytest.skip(f"data not present at {DATA}")


def test_event_count_matches_K() -> None:
    events = load_replay(DATA, start_time_sec=START, rng_seed=42)
    assert len(events) == 50
    for e in events:
        assert isinstance(e, BuildingOrder)


def test_events_anchored_to_start_time() -> None:
    events = load_replay(DATA, start_time_sec=START, rng_seed=42)
    # earliest event = start_time + min(ORD_TIME); K50_1's first ORD_TIME=7
    assert events[0].arrival_time_sec == pytest.approx(START + 7)


def test_events_sorted_by_arrival_time() -> None:
    events = load_replay(DATA, start_time_sec=START, rng_seed=42)
    times = [e.arrival_time_sec for e in events]
    assert times == sorted(times)


def test_floors_are_in_office_range() -> None:
    events = load_replay(DATA, start_time_sec=START, rng_seed=42, n_floors=5)
    floors = {e.floor for e in events}
    assert floors.issubset({2, 3, 4, 5})
    # K=50 is large enough that all 4 floors should appear with high probability
    assert len(floors) >= 3


def test_floor_assignment_reproducible_with_same_seed() -> None:
    a = load_replay(DATA, start_time_sec=START, rng_seed=42)
    b = load_replay(DATA, start_time_sec=START, rng_seed=42)
    assert [(e.floor, e.office_id) for e in a] == [(e.floor, e.office_id) for e in b]


def test_floor_assignment_changes_with_different_seed() -> None:
    a = load_replay(DATA, start_time_sec=START, rng_seed=42)
    b = load_replay(DATA, start_time_sec=START, rng_seed=43)
    assert [(e.floor, e.office_id) for e in a] != [(e.floor, e.office_id) for e in b]


def test_lead_time_passthrough() -> None:
    events = load_replay(DATA, start_time_sec=START, rng_seed=42)
    # framework §4 q05 hint ~ 38 min lower bound
    for e in events:
        assert e.lead_time_sec > 0


def test_10F_typology_widens_floor_range() -> None:
    events = load_replay(DATA, start_time_sec=START, rng_seed=42, n_floors=10)
    floors = {e.floor for e in events}
    assert floors.issubset(set(range(2, 11)))
    assert max(floors) > 5  # extends above 5F


def test_10F_profile_offices_per_floor_12() -> None:
    """10F profile (configs/baseline_10f.yaml): 12 offices/floor → office_id 0..11."""
    events = load_replay(
        DATA, start_time_sec=START, rng_seed=42, n_floors=10, offices_per_floor=12
    )
    floors = {e.floor for e in events}
    offices = {e.office_id for e in events}
    assert floors.issubset(set(range(2, 11)))
    assert offices.issubset(set(range(12)))


def test_invalid_n_floors_raises() -> None:
    with pytest.raises(ValueError):
        load_replay(DATA, n_floors=1)


def test_invalid_offices_raises() -> None:
    with pytest.raises(ValueError):
        load_replay(DATA, offices_per_floor=0)


# ---------------------------------------------------------------------------
# load_replay_v4 (etc/plan_abm_baseline_h0.md Part B)
# ---------------------------------------------------------------------------


def _v4_data_present() -> bool:
    return DATA.exists() and MAPPING.exists() and CONFIG_PATH.exists()


def test_v4_data_present() -> None:
    if not _v4_data_present():
        pytest.skip("data / mapping / config not present")


def _config() -> dict:
    return load_config(CONFIG_PATH)


def test_v4_event_count_matches_K() -> None:
    if not _v4_data_present():
        pytest.skip("data not present")
    events = load_replay_v4(DATA, MAPPING, _config(), start_time_sec=START, seed=42)
    assert len(events) == 50
    for e in events:
        assert isinstance(e, BuildingOrderV4)


def test_v4_events_sorted_by_arrival_time() -> None:
    if not _v4_data_present():
        pytest.skip("data not present")
    events = load_replay_v4(DATA, MAPPING, _config(), start_time_sec=START, seed=42)
    times = [e.arrival_time_sec for e in events]
    assert times == sorted(times)


def test_v4_floor_office_match_mapping_file() -> None:
    if not _v4_data_present():
        pytest.skip("data not present")
    mapping_raw = json.loads(MAPPING.read_text())
    floor_by_ord = {r["ord_id"]: r["floor"] for r in mapping_raw["orders"]}
    office_by_ord = {r["ord_id"]: r["office_id"] for r in mapping_raw["orders"]}
    events = load_replay_v4(DATA, MAPPING, _config(), start_time_sec=START, seed=42)
    for e in events:
        assert e.floor == floor_by_ord[e.ord_id]
        assert e.office_id == office_by_ord[e.ord_id]
    floors = {e.floor for e in events}
    assert floors.issubset(set(range(2, 11)))
    offices = {e.office_id for e in events}
    assert offices.issubset(set(range(12)))


def test_v4_vertical_mode_matches_direct_sample() -> None:
    """vertical_mode must be bit-identical to an independent sample_mode() call."""
    if not _v4_data_present():
        pytest.skip("data not present")
    config = _config()
    vt = VerticalTransportModel.from_config(config)
    events = load_replay_v4(DATA, MAPPING, config, start_time_sec=START, seed=42)
    for e in events:
        assert e.vertical_mode == vt.sample_mode(e.ord_id, e.floor)


def test_v4_horizontal_time_s_consistent_with_arrival_when_deterministic() -> None:
    """With sigma_eps=0, arrival_time = ord_time_abs + cook_time + horizontal_time_s exactly."""
    if not _v4_data_present():
        pytest.skip("data not present")
    events = load_replay_v4(
        DATA, MAPPING, _config(), start_time_sec=START, seed=42, sigma_eps=0.0
    )
    for e in events:
        reconstructed = e.ord_time_abs_sec + e.cook_time_sec + e.horizontal_time_s
        assert e.arrival_time_sec == pytest.approx(reconstructed, abs=1e-6)


def test_v4_deterministic_by_default() -> None:
    """sigma_eps defaults to 0.0 (H0 baseline decision) — two calls match exactly."""
    if not _v4_data_present():
        pytest.skip("data not present")
    config = _config()
    a = load_replay_v4(DATA, MAPPING, config, start_time_sec=START, seed=42)
    b = load_replay_v4(DATA, MAPPING, config, start_time_sec=START, seed=42)
    assert [e.arrival_time_sec for e in a] == [e.arrival_time_sec for e in b]
    assert [e.rider_type for e in a] == [e.rider_type for e in b]


def test_v4_w_R_positive() -> None:
    if not _v4_data_present():
        pytest.skip("data not present")
    events = load_replay_v4(DATA, MAPPING, _config(), start_time_sec=START, seed=42)
    for e in events:
        assert e.w_R_krw_per_h > 0


def test_v4_deadline_after_ord_time() -> None:
    if not _v4_data_present():
        pytest.skip("data not present")
    events = load_replay_v4(DATA, MAPPING, _config(), start_time_sec=START, seed=42)
    for e in events:
        assert e.deadline_abs_sec > e.ord_time_abs_sec


def test_v4_k_mismatch_raises(tmp_path: Path) -> None:
    if not _v4_data_present():
        pytest.skip("data not present")
    bad = json.loads(MAPPING.read_text())
    bad["K"] = 999
    bad_path = tmp_path / "bad_mapping.json"
    bad_path.write_text(json.dumps(bad))
    with pytest.raises(ValueError, match="K="):
        load_replay_v4(DATA, bad_path, _config(), start_time_sec=START, seed=42)


def test_v4_missing_ord_id_raises(tmp_path: Path) -> None:
    if not _v4_data_present():
        pytest.skip("data not present")
    mapping_raw = json.loads(MAPPING.read_text())
    mapping_raw["orders"] = [o for o in mapping_raw["orders"] if o["ord_id"] != 0]
    bad_path = tmp_path / "missing_ord_id_mapping.json"
    bad_path.write_text(json.dumps(mapping_raw))
    with pytest.raises(ValueError, match="missing ord_id"):
        load_replay_v4(DATA, bad_path, _config(), start_time_sec=START, seed=42)


# ---------------------------------------------------------------------------
# load_dispatch_profile (etc/demand_mapping.md 단계 2·3 profile floor demand)
# ---------------------------------------------------------------------------


def _profile_data_present() -> bool:
    return DATA.exists() and CONFIG_PATH.exists()


def test_dispatch_profile_data_present() -> None:
    if not _profile_data_present():
        pytest.skip("data / config not present")


def test_dispatch_profile_count_and_sorted() -> None:
    if not _profile_data_present():
        pytest.skip("data not present")
    events = load_dispatch_profile(DATA, _config(), start_time_sec=START)
    assert len(events) == 50
    for e in events:
        assert isinstance(e, DispatchOrder)
    ready = [e.ready_time_sec for e in events]
    assert ready == sorted(ready)


def test_dispatch_profile_ready_and_abs_times_match_raw_scenario() -> None:
    """ready/ord/deadline abs-time fields reconstruct from the raw scenario JSON."""
    if not _profile_data_present():
        pytest.skip("data not present")
    scenario = load_scenario(DATA)
    order_by_id = {o.ord_id: o for o in scenario.orders}
    events = load_dispatch_profile(DATA, _config(), start_time_sec=START)
    for e in events:
        order = order_by_id[e.ord_id]
        assert e.ready_time_sec == pytest.approx(
            START + order.ord_time_sec + order.cook_time_sec
        )
        assert e.ord_time_abs_sec == pytest.approx(START + order.ord_time_sec)
        assert e.deadline_abs_sec == pytest.approx(START + order.dlv_deadline_sec)
        assert e.ready_time_sec == pytest.approx(e.ord_time_abs_sec + e.cook_time_sec)


def test_dispatch_profile_dist_matches_dist_matrix() -> None:
    if not _profile_data_present():
        pytest.skip("data not present")
    scenario = load_scenario(DATA)
    pdd = pickup_drop_distance(DATA)  # length K, order-aligned (DIST[i][K+i])
    dist_by_ord = {o.ord_id: float(pdd[i]) for i, o in enumerate(scenario.orders)}
    events = load_dispatch_profile(DATA, _config(), start_time_sec=START)
    for e in events:
        assert e.dist_m == pytest.approx(dist_by_ord[e.ord_id])
        assert e.dist_m > 0


def test_dispatch_profile_floor_and_office_in_range() -> None:
    if not _profile_data_present():
        pytest.skip("data not present")
    events = load_dispatch_profile(DATA, _config(), start_time_sec=START)
    floors = {e.floor for e in events}
    offices = {e.office_id for e in events}
    assert floors.issubset(set(range(2, 11)))
    assert offices.issubset(set(range(12)))


def test_dispatch_profile_vertical_mode_matches_direct_sample() -> None:
    """vertical_mode must be bit-identical to an independent sample_mode() call."""
    if not _profile_data_present():
        pytest.skip("data not present")
    config = _config()
    vt = VerticalTransportModel.from_config(config)
    events = load_dispatch_profile(DATA, config, start_time_sec=START)
    for e in events:
        assert e.vertical_mode == vt.sample_mode(e.ord_id, e.floor)


def test_dispatch_profile_deterministic_repeat_calls() -> None:
    if not _profile_data_present():
        pytest.skip("data not present")
    config = _config()
    a = load_dispatch_profile(DATA, config, start_time_sec=START)
    b = load_dispatch_profile(DATA, config, start_time_sec=START)
    assert a == b


def test_dispatch_profile_floor_seed_diversity() -> None:
    if not _profile_data_present():
        pytest.skip("data not present")
    config = _config()
    a = load_dispatch_profile(DATA, config, floor_seed=1, start_time_sec=START)
    b = load_dispatch_profile(DATA, config, floor_seed=2, start_time_sec=START)
    floors_a = [e.floor for e in a]
    floors_b = [e.floor for e in b]
    assert floors_a != floors_b


def test_dispatch_profile_non_floor_fields_independent_of_floor_seed() -> None:
    """Only floor/office_id/vertical_mode may move when floor_seed changes."""
    if not _profile_data_present():
        pytest.skip("data not present")
    config = _config()
    a = load_dispatch_profile(DATA, config, floor_seed=1, start_time_sec=START)
    b = load_dispatch_profile(DATA, config, floor_seed=2, start_time_sec=START)
    by_id_a = {e.ord_id: e for e in a}
    by_id_b = {e.ord_id: e for e in b}
    assert set(by_id_a) == set(by_id_b)
    for ord_id, ea in by_id_a.items():
        eb = by_id_b[ord_id]
        assert ea.ready_time_sec == eb.ready_time_sec
        assert ea.ord_time_abs_sec == eb.ord_time_abs_sec
        assert ea.deadline_abs_sec == eb.deadline_abs_sec
        assert ea.cook_time_sec == eb.cook_time_sec
        assert ea.vol == eb.vol
        assert ea.dist_m == eb.dist_m


def test_dispatch_profile_matches_v5_except_floor_source() -> None:
    """Cross-check vs load_dispatch_v5: every field but floor/office_id/vertical_mode
    agrees, proving load_dispatch_profile only swaps the floor source."""
    if not _profile_data_present() or not MAPPING_V5.exists():
        pytest.skip("data / v5 mapping not present")
    config = _config()
    profile_events = load_dispatch_profile(DATA, config, start_time_sec=START)
    v5_events = load_dispatch_v5(DATA, MAPPING_V5, config, start_time_sec=START)
    by_id_profile = {e.ord_id: e for e in profile_events}
    by_id_v5 = {e.ord_id: e for e in v5_events}
    assert set(by_id_profile) == set(by_id_v5)
    for ord_id, ep in by_id_profile.items():
        ev = by_id_v5[ord_id]
        assert ep.ready_time_sec == ev.ready_time_sec
        assert ep.ord_time_abs_sec == ev.ord_time_abs_sec
        assert ep.deadline_abs_sec == ev.deadline_abs_sec
        assert ep.cook_time_sec == ev.cook_time_sec
        assert ep.vol == ev.vol
        assert ep.dist_m == ev.dist_m


def test_dispatch_profile_unknown_profile_raises() -> None:
    if not _profile_data_present():
        pytest.skip("data not present")
    with pytest.raises(ValueError):
        load_dispatch_profile(DATA, _config(), profile="no_such_profile", start_time_sec=START)


def test_dispatch_profile_matches_rederive_round_trip() -> None:
    """Round-trip with the Stage-1 helper: rederive_profile_assignment reconstructs
    (floor, office_id, vertical_mode) from (profile, floor_seed) alone."""
    if not _profile_data_present():
        pytest.skip("data not present")
    config = _config()
    events = load_dispatch_profile(
        DATA, config, profile="uniform", floor_seed=42, start_time_sec=START
    )
    ord_ids = [e.ord_id for e in events]
    derived = rederive_profile_assignment(config, "uniform", 42, ord_ids)
    for e in events:
        assert (e.floor, e.office_id, e.vertical_mode) == derived[e.ord_id]
