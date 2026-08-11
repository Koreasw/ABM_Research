"""Tests for VerticalTransportModel (T2, etc/plan_travel_time_functions.md §3.2-3.5)."""

from __future__ import annotations

import pytest

from simulation.elevator_physics import ElevatorKinematics
from simulation.vertical_transport import VerticalTransportModel

# §3.4 reference table (floor_height_m=4.0, T_wait=20.0, door=4.0, beta=0.15)
REFERENCE_TABLE = [
    (2, 28.00, 16.5, 0.151, 18.24),
    (3, 29.70, 33.0, 0.621, 30.95),
    (4, 31.30, 49.5, 0.939, 32.41),
    (5, 32.90, 66.0, 0.993, 33.13),
    (6, 34.50, 82.5, 0.999, 34.54),
    (7, 36.10, 99.0, 1.000, 36.11),
    (8, 37.70, 115.5, 1.000, 37.70),
    (9, 39.30, 132.0, 1.000, 39.30),
    (10, 40.90, 148.5, 1.000, 40.90),
]


def _model() -> VerticalTransportModel:
    kin = ElevatorKinematics(
        accel_mps2=1.0, max_speed_mps=2.5, floor_height_m=4.0, door_open_close_sec=4.0
    )
    return VerticalTransportModel(
        kin=kin,
        ev_wait_sec=20.0,
        stair_sec_per_floor=16.5,
        beta_per_sec=0.15,
        mode_seed=42,
        walk_speed_mps=1.2,
        entrance_m=4.0,
    )


@pytest.mark.parametrize("f,t_elev,t_stair,p_elev,e_t", REFERENCE_TABLE)
def test_reference_table(f: int, t_elev: float, t_stair: float, p_elev: float, e_t: float) -> None:
    m = _model()
    assert m.t_elevator_s(f, include_wait=True) == pytest.approx(t_elev, abs=0.01)
    assert m.t_stairs_s(f) == pytest.approx(t_stair, abs=0.01)
    assert m.p_elevator(f) == pytest.approx(p_elev, abs=0.001)
    assert m.expected_vertical_time(f) == pytest.approx(e_t, abs=0.02)


def test_include_wait_false_strict_lower_bound() -> None:
    m = _model()
    with_wait = m.t_elevator_s(4, include_wait=True)
    without_wait = m.t_elevator_s(4, include_wait=False)
    assert without_wait == pytest.approx(with_wait - 20.0)
    assert without_wait < with_wait


def test_monotonic_increasing_in_floor() -> None:
    m = _model()
    floors = list(range(2, 11))
    t_elevs = [m.t_elevator_s(f) for f in floors]
    t_stairs = [m.t_stairs_s(f) for f in floors]
    p_elevs = [m.p_elevator(f) for f in floors]
    e_ts = [m.expected_vertical_time(f) for f in floors]
    for series in (t_elevs, t_stairs, p_elevs, e_ts):
        assert all(a <= b + 1e-9 for a, b in zip(series, series[1:]))


def test_logit_crossover_sanity() -> None:
    m = _model()
    assert m.p_elevator(2) < 0.5
    assert m.p_elevator(3) > 0.5
    assert m.p_elevator(9) > 0.9
    assert m.p_elevator(10) > 0.9


def test_sample_mode_seed_reproducible() -> None:
    m = _model()
    r1 = m.sample_mode(ord_id=7, floor=4)
    r2 = m.sample_mode(ord_id=7, floor=4)
    assert r1 == r2
    assert r1 in ("elevator", "stairs")


def test_sample_mode_independent_of_call_order() -> None:
    m = _model()
    # Calling for other ord_ids first must not perturb ord_id=7's draw.
    _ = [m.sample_mode(ord_id=i, floor=4) for i in range(20)]
    a = m.sample_mode(ord_id=7, floor=4)
    b = m.sample_mode(ord_id=7, floor=4)
    assert a == b


def test_sample_mode_distribution_matches_p_elevator() -> None:
    m = _model()
    # High floor -> near-certain elevator; low floor -> mostly stairs.
    high_floor_modes = [m.sample_mode(ord_id=i, floor=10) for i in range(200)]
    assert high_floor_modes.count("elevator") / len(high_floor_modes) > 0.95

    low_floor_modes = [m.sample_mode(ord_id=1000 + i, floor=2) for i in range(200)]
    assert low_floor_modes.count("stairs") / len(low_floor_modes) > 0.7


def test_entrance_walk_s() -> None:
    m = _model()
    assert m.entrance_walk_s() == pytest.approx(4.0 / 1.2, abs=1e-6)
    assert m.entrance_walk_s() == pytest.approx(3.33, abs=0.01)


def test_from_config() -> None:
    config = {
        "building": {"floor_height_m": 4.0, "entrance_m": 4.0},
        "elevator": {"accel_mps2": 1.0, "max_speed_mps": 2.5, "door_open_close_sec": 4.0},
        "vertical": {
            "ev_wait_sec": 20.0,
            "stair_sec_per_floor": 16.5,
            "mode_choice_beta_per_sec": 0.15,
            "mode_seed": 42,
            "walk_speed_mps": 1.2,
        },
    }
    m = VerticalTransportModel.from_config(config)
    assert m.ev_wait_sec == 20.0
    assert m.stair_sec_per_floor == 16.5
    assert m.beta_per_sec == 0.15
    assert m.mode_seed == 42
    assert m.walk_speed_mps == 1.2
    assert m.entrance_m == 4.0
    assert m.t_elevator_s(4) == pytest.approx(31.30, abs=0.01)


def test_from_config_default_entrance_m() -> None:
    config = {
        "building": {"floor_height_m": 4.0},
        "elevator": {"accel_mps2": 1.0, "max_speed_mps": 2.5, "door_open_close_sec": 4.0},
        "vertical": {
            "ev_wait_sec": 20.0,
            "stair_sec_per_floor": 16.5,
            "mode_choice_beta_per_sec": 0.15,
            "mode_seed": 42,
            "walk_speed_mps": 1.2,
        },
    }
    m = VerticalTransportModel.from_config(config)
    assert m.entrance_m == 4.0
