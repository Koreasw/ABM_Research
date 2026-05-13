"""Tests for analysis.scenario_loader.load_replay."""

from __future__ import annotations

from pathlib import Path

import pytest

from analysis.scenario_loader import BuildingOrder, load_replay

DATA = Path(__file__).resolve().parent.parent / "data" / "data1" / "K50_1.json"
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


def test_invalid_n_floors_raises() -> None:
    with pytest.raises(ValueError):
        load_replay(DATA, n_floors=1)


def test_invalid_offices_raises() -> None:
    with pytest.raises(ValueError):
        load_replay(DATA, offices_per_floor=0)
