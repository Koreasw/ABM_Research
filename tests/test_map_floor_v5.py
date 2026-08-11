"""v5 floor mapping — per-scenario demand-centroid anchor (analysis/map_floor_v5.py).

v5 changes ONLY the building anchor (fixed Seoul coord → scenario demand
centroid). Floors/offices must therefore be bit-identical to v4 for K50_1,
and the anchor must sit inside the scenario's delivery bounding box.
Regenerating the v5 artifacts is idempotent (fixed seeds, data-only).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from analysis.load_data import load_scenario
from analysis.map_floor_v5 import demand_centroid, generate

ROOT = Path(__file__).resolve().parent.parent


def test_demand_centroid_is_mean_of_dlv_coords():
    scenario = load_scenario(ROOT / "data" / "data1" / "K50_1.json")
    lat, lon = demand_centroid(scenario.orders)
    assert lat == pytest.approx(np.mean([o.dlv_lat for o in scenario.orders]))
    assert lon == pytest.approx(np.mean([o.dlv_lon for o in scenario.orders]))


def test_demand_centroid_rejects_empty():
    with pytest.raises(ValueError):
        demand_centroid([])


@pytest.fixture(scope="module")
def v5_k50(tmp_path_factory) -> dict:
    """Generate (idempotently) the real v5 artifacts for K50_1."""
    return generate("data/data1/K50_1.json", quiet=True)


def test_v5_floors_offices_identical_to_v4(v5_k50):
    """Anchor-independence of the 2D→3D rule: v5 ≡ v4 on floors/offices."""
    v4 = json.loads(
        (ROOT / "data" / "floor_mapping" / "K50_1_floor_mapping_v4.json").read_text()
    )
    v5 = json.loads((ROOT / v5_k50["fm_path"]).read_text())
    a4 = {o["ord_id"]: (o["floor"], o["office_id"]) for o in v4["orders"]}
    a5 = {o["ord_id"]: (o["floor"], o["office_id"]) for o in v5["orders"]}
    assert a4 == a5
    assert v5["floor_distribution_2_to_10"] == v4["floor_distribution_2_to_10"]


def test_v5_anchor_inside_dlv_bbox_and_recorded(v5_k50):
    scenario = load_scenario(ROOT / "data" / "data1" / "K50_1.json")
    lats = [o.dlv_lat for o in scenario.orders]
    lons = [o.dlv_lon for o in scenario.orders]
    lat, lon = v5_k50["anchor"]
    assert min(lats) <= lat <= max(lats)
    assert min(lons) <= lon <= max(lons)
    v5 = json.loads((ROOT / v5_k50["fm_path"]).read_text())
    coord = v5["parameters"]["building_coord"]
    assert coord["lat"] == pytest.approx(lat)
    assert coord["lon"] == pytest.approx(lon)
    assert "anchor_rule" in v5["parameters"]


def test_v5_horizontal_uses_scenario_anchor(v5_k50):
    """Street leg must be city-scale (shop → in-city centroid), not fixed-anchor scale."""
    mv = json.loads(
        (ROOT / "data" / "floor_mapping" / "K50_1_movement_distances_v5.json").read_text()
    )
    horiz = [o["horizontal_m"] for o in mv["orders"]]
    assert all(h > 0 for h in horiz)
    assert np.median(horiz) < 20_000.0  # within-city scale (< 20 km)


def test_v5_generates_for_non_seoul_scenario():
    """K100_1 as a second scenario: anchor is per-scenario, not global."""
    s_100 = generate("data/data1/K100_1.json", quiet=True)
    s_50 = generate("data/data1/K50_1.json", quiet=True)
    assert s_100["anchor"] != s_50["anchor"]
    assert s_100["K"] == 100
    fm = json.loads((ROOT / s_100["fm_path"]).read_text())
    assert fm["K"] == 100
    assert len(fm["orders"]) == 100
    assert sum(fm["floor_distribution_2_to_10"]) == 100
