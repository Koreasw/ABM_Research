"""Tests for analysis.load_data — schema-correct parsing of BaeMin JSON."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from analysis.load_data import (
    Order,
    Rider,
    Scenario,
    load_dist,
    load_orders,
    load_riders,
    load_scenario,
    pickup_drop_distance,
)

DATA_ROOT = Path(__file__).resolve().parent.parent / "data" / "data1"
K50_1 = DATA_ROOT / "K50_1.json"


@pytest.fixture(scope="module")
def scenario() -> Scenario:
    return load_scenario(K50_1)


def test_data_present() -> None:
    if not K50_1.exists():
        pytest.skip(f"data not present at {K50_1}")


def test_scenario_meta(scenario: Scenario) -> None:
    assert scenario.name == "TEST_K50_1"
    assert scenario.K == 50
    assert len(scenario.orders) == 50
    assert len(scenario.riders) == 3


def test_orders_field_types(scenario: Scenario) -> None:
    first = scenario.orders[0]
    assert isinstance(first, Order)
    assert first.ord_id == 0
    assert first.ord_time_sec >= 0
    assert 5 <= first.vol <= 100
    assert first.cook_time_sec >= 0
    assert first.dlv_deadline_sec > first.ord_time_sec


def test_riders_have_bike_walk_car(scenario: Scenario) -> None:
    types = {r.type for r in scenario.riders}
    assert types == {"BIKE", "WALK", "CAR"}


def test_riders_field_ranges(scenario: Scenario) -> None:
    for r in scenario.riders:
        assert isinstance(r, Rider)
        assert r.speed_mps > 0
        assert r.capa > 0
        assert r.available_number > 0


def test_dist_is_2K_square(scenario: Scenario) -> None:
    K = scenario.K
    assert scenario.dist.shape == (2 * K, 2 * K)
    # diagonal (self -> self) should be 0
    assert np.allclose(np.diag(scenario.dist), 0.0)


def test_individual_loaders_match_scenario(scenario: Scenario) -> None:
    assert load_orders(K50_1) == scenario.orders
    assert load_riders(K50_1) == scenario.riders
    assert np.array_equal(load_dist(K50_1), scenario.dist)


def test_pickup_drop_distance_matches_DIST_lookup(scenario: Scenario) -> None:
    pdd = pickup_drop_distance(K50_1)
    assert pdd.shape == (scenario.K,)
    # spot-check first order
    assert pdd[0] == scenario.dist[0, scenario.K]
    # all positive (pickup and drop are different nodes)
    assert (pdd > 0).all()


def test_bad_path_raises() -> None:
    with pytest.raises(FileNotFoundError):
        load_scenario("/nonexistent/path.json")
