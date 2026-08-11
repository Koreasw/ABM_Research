"""Tests for ElevatorAgent kinematics (framework §5.3, plan_travel_time_functions.md §3.1/§3.4)."""

from __future__ import annotations

import math

import pytest

from simulation.elevator_physics import ElevatorKinematics

# §3.4 reference table (floor_height_m=4.0, ground floor = 1).
# f, dH(m), t_move(s), T_elev(s) with T_wait=20.0, door=4.0
REFERENCE_TABLE_H4 = [
    (2, 4, 4.00, 28.00),
    (3, 8, 5.70, 29.70),
    (4, 12, 7.30, 31.30),
    (5, 16, 8.90, 32.90),
    (6, 20, 10.50, 34.50),
    (7, 24, 12.10, 36.10),
    (8, 28, 13.70, 37.70),
    (9, 32, 15.30, 39.30),
    (10, 36, 16.90, 40.90),
]

T_WAIT_SEC = 20.0


def _kin_h4() -> ElevatorKinematics:
    return ElevatorKinematics(
        accel_mps2=1.0, max_speed_mps=2.5, floor_height_m=4.0, door_open_close_sec=4.0
    )


@pytest.mark.parametrize("f,dh,t_move,t_elev", REFERENCE_TABLE_H4)
def test_reference_table_h4(f: int, dh: float, t_move: float, t_elev: float) -> None:
    kin = _kin_h4()
    assert kin.floor_height_between(1, f) == pytest.approx(dh)
    assert kin.move_time_sec(dh) == pytest.approx(t_move, abs=0.01)
    assert kin.travel_time_sec(1, f) == pytest.approx(t_move, abs=0.01)
    # T_elev = T_wait + t_move + door (assembled externally; kinematics owns move only)
    assembled = T_WAIT_SEC + kin.travel_time_sec(1, f) + kin.door_open_close_sec
    assert assembled == pytest.approx(t_elev, abs=0.01)


def test_triangular_case_3_6m_legacy_correction() -> None:
    """1F->2F at floor_height=3.6m: correct value is 7.79s (move+door, no wait),
    correcting the legacy no-deceleration miscalc of 6.68s (see plan §3.1 note)."""
    kin = ElevatorKinematics(floor_height_m=3.6)
    move = kin.travel_time_sec(1, 2)
    assert move == pytest.approx(2.0 * math.sqrt(3.6 / 1.0), abs=1e-6)
    assert move + kin.door_open_close_sec == pytest.approx(7.79, abs=0.01)


@pytest.mark.parametrize(
    "dh,expected_move_plus_door",
    [
        (7.2, 9.38),
        (10.8, 10.82),
        (14.4, 12.26),
        (21.6, 15.14),
    ],
)
def test_trapezoidal_cases_3_6m_building(dh: float, expected_move_plus_door: float) -> None:
    kin = ElevatorKinematics(floor_height_m=3.6)
    assert kin.move_time_sec(dh) + kin.door_open_close_sec == pytest.approx(
        expected_move_plus_door, abs=0.01
    )


def test_d_ramp_boundary() -> None:
    kin = _kin_h4()
    d_ramp = kin.max_speed_mps**2 / kin.accel_mps2
    assert d_ramp == pytest.approx(6.25)
    # just below d_ramp: triangular formula
    below = kin.move_time_sec(d_ramp - 0.01)
    assert below == pytest.approx(2.0 * math.sqrt((d_ramp - 0.01) / kin.accel_mps2))
    # just above d_ramp: trapezoidal formula
    above = kin.move_time_sec(d_ramp + 0.01)
    expected = 2.0 * kin.max_speed_mps / kin.accel_mps2 + 0.01 / kin.max_speed_mps
    assert above == pytest.approx(expected)


def test_same_floor_zero() -> None:
    kin = _kin_h4()
    assert kin.travel_time_sec(3, 3) == 0.0
    assert kin.move_time_sec(0.0) == 0.0


def test_symmetry() -> None:
    kin = _kin_h4()
    assert kin.travel_time_sec(2, 5) == pytest.approx(kin.travel_time_sec(5, 2))


def test_floor_height_label_difference() -> None:
    """Above ground the height is a plain label difference over floors 1..n."""
    kin = _kin_h4()
    assert kin.floor_height_between(1, 2) == pytest.approx(4.0)
    assert kin.floor_height_between(1, 10) == pytest.approx(36.0)
    assert kin.floor_height_between(7, 3) == pytest.approx(16.0)


def test_floor_height_across_ground_level() -> None:
    """§1.6 basements: labels skip 0, so B1 is ONE storey below 1F, not two.

    This is the arithmetic the whole rank convention exists to protect: a naive
    abs(label difference) would put B1 8 m below 1F and B2 12 m, inflating every
    basement ride.
    """
    kin = _kin_h4()
    assert kin.floor_height_between(1, -1) == pytest.approx(4.0)
    assert kin.floor_height_between(1, -2) == pytest.approx(8.0)
    assert kin.floor_height_between(-1, -2) == pytest.approx(4.0)
    assert kin.floor_height_between(10, -2) == pytest.approx(44.0)   # 11 storeys
    assert kin.floor_height_between(-2, 10) == pytest.approx(44.0)   # symmetric
    assert kin.travel_time_sec(-1, -1) == 0.0
    with pytest.raises(ValueError):
        kin.floor_height_between(0, 5)


def test_from_config() -> None:
    config = {
        "elevator": {"accel_mps2": 1.0, "max_speed_mps": 2.5, "door_open_close_sec": 4.0},
        "building": {"floor_height_m": 4.0},
    }
    kin = ElevatorKinematics.from_config(config)
    assert kin.accel_mps2 == 1.0
    assert kin.max_speed_mps == 2.5
    assert kin.floor_height_m == 4.0
    assert kin.door_open_close_sec == 4.0
