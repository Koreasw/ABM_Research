"""Tests for analysis.travel_time_v4 (T3, etc/plan_travel_time_functions.md §7/§8)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from analysis.travel_time_v4 import compute_travel_times, main
from simulation.space import load_config
from simulation.vertical_transport import VerticalTransportModel

ROOT = Path(__file__).resolve().parent.parent
SCENARIO = ROOT / "data" / "data1" / "K50_1.json"
DISTANCES = ROOT / "data" / "floor_mapping" / "K50_1_movement_distances_v4.json"
CONFIG_PATH = ROOT / "configs" / "baseline_10f.yaml"

# §3.4 reference table (floor_height_m=4.0)
REFERENCE_BY_FLOOR = {
    2: (28.00, 16.5, 0.151),
    3: (29.70, 33.0, 0.621),
    4: (31.30, 49.5, 0.939),
    5: (32.90, 66.0, 0.993),
    6: (34.50, 82.5, 0.999),
    7: (36.10, 99.0, 1.000),
    8: (37.70, 115.5, 1.000),
    9: (39.30, 132.0, 1.000),
    10: (40.90, 148.5, 1.000),
}


def _data_present() -> bool:
    return SCENARIO.exists() and DISTANCES.exists() and CONFIG_PATH.exists()


def test_data_present() -> None:
    if not _data_present():
        pytest.skip("scenario / movement_distances / config not present")


def _result() -> dict:
    config = load_config(CONFIG_PATH)
    return compute_travel_times(SCENARIO, DISTANCES, config)


def test_order_count_matches_K() -> None:
    if not _data_present():
        pytest.skip("data not present")
    result = _result()
    assert result["K"] == 50
    assert len(result["orders"]) == 50


def test_reference_table_wiring() -> None:
    """Each order's vertical block must match the §3.4 table for its floor."""
    if not _data_present():
        pytest.skip("data not present")
    result = _result()
    for rec in result["orders"]:
        t_elev, t_stair, p_elev = REFERENCE_BY_FLOOR[rec["floor"]]
        assert rec["vertical"]["t_elevator_s"] == pytest.approx(t_elev, abs=0.01)
        assert rec["vertical"]["t_stairs_s"] == pytest.approx(t_stair, abs=0.01)
        assert rec["vertical"]["p_elevator"] == pytest.approx(p_elev, abs=0.001)


def test_vertical_total_time_is_entrance_plus_mode_time() -> None:
    if not _data_present():
        pytest.skip("data not present")
    result = _result()
    for rec in result["orders"]:
        v = rec["vertical"]
        expected = v["entrance_walk_s"] + v["mode_time_s"]
        assert v["total_time_s"] == pytest.approx(expected, abs=0.02)


def test_total_time_decomposition() -> None:
    if not _data_present():
        pytest.skip("data not present")
    result = _result()
    for rec in result["orders"]:
        for rider_type, t in rec["total_time_s"].items():
            expected = (
                rec["horizontal_time_s"][rider_type]
                + rec["vertical"]["total_time_s"]
                + rec["in_floor_time_s"]
            )
            assert t == pytest.approx(expected, abs=0.02)


def test_bike_horizontal_median_matches_anchor() -> None:
    """§2 validation anchor: BIKE horizontal_time_s median ~= 421.3 s."""
    if not _data_present():
        pytest.skip("data not present")
    result = _result()
    bike_horiz = sorted(o["horizontal_time_s"]["BIKE"] for o in result["orders"])
    n = len(bike_horiz)
    median = bike_horiz[n // 2] if n % 2 else (bike_horiz[n // 2 - 1] + bike_horiz[n // 2]) / 2
    assert median == pytest.approx(421.3, abs=5.0)


def test_stair_sample_count_near_expected() -> None:
    """§8: K50_1 floor dist weighted by (1-P_f) -> stair sample expected ~7/50."""
    if not _data_present():
        pytest.skip("data not present")
    result = _result()
    n_stairs = sum(1 for o in result["orders"] if o["vertical"]["mode"] == "stairs")
    assert 2 <= n_stairs <= 14


def test_mode_matches_direct_vertical_transport_call() -> None:
    """Self-consistency: CLI-sampled mode == calling VerticalTransportModel directly."""
    if not _data_present():
        pytest.skip("data not present")
    config = load_config(CONFIG_PATH)
    vt = VerticalTransportModel.from_config(config)
    result = compute_travel_times(SCENARIO, DISTANCES, config)
    for rec in result["orders"]:
        assert rec["vertical"]["mode"] == vt.sample_mode(rec["ord_id"], rec["floor"])


def test_reexecution_bit_identical() -> None:
    if not _data_present():
        pytest.skip("data not present")
    config = load_config(CONFIG_PATH)
    r1 = compute_travel_times(SCENARIO, DISTANCES, config)
    r2 = compute_travel_times(SCENARIO, DISTANCES, config)
    r1.pop("generated_at_utc")
    r2.pop("generated_at_utc")
    assert r1 == r2


def test_traceability_metadata_present() -> None:
    if not _data_present():
        pytest.skip("data not present")
    result = _result()
    assert result["source_file"]
    assert result["floor_mapping_file"]
    assert result["movement_distances_file"]
    assert "rng_convention" in result
    assert result["parameters"]["mode_seed"] == 42


def test_cli_writes_output_file(tmp_path: Path) -> None:
    if not _data_present():
        pytest.skip("data not present")
    out_path = tmp_path / "K50_1_travel_times_v4_test.json"
    main(
        [
            str(SCENARIO),
            "--distances",
            str(DISTANCES),
            "--config",
            str(CONFIG_PATH),
            "--out",
            str(out_path),
        ]
    )
    assert out_path.exists()
    written = json.loads(out_path.read_text())
    assert written["K"] == 50
    assert len(written["orders"]) == 50


def test_k_mismatch_raises(tmp_path: Path) -> None:
    if not _data_present():
        pytest.skip("data not present")
    bad = json.loads(DISTANCES.read_text())
    bad["K"] = 999
    bad_path = tmp_path / "bad_movement_distances.json"
    bad_path.write_text(json.dumps(bad))
    config = load_config(CONFIG_PATH)
    with pytest.raises(ValueError, match="K mismatch"):
        compute_travel_times(SCENARIO, bad_path, config)
