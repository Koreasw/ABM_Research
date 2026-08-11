"""Elevator kinematics — T1 (etc/plan_travel_time_functions.md §3.1).

Triangular/trapezoidal velocity-profile travel time between floors, given
uniform acceleration/deceleration and a capped max speed. Serves both the
uncongested precompute layer (analysis/travel_time_v4.py) and the ABM's
ElevatorAgent (simulation/agents/elevator.py).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ElevatorKinematics:
    accel_mps2: float = 1.0
    max_speed_mps: float = 2.5
    floor_height_m: float = 4.0
    door_open_close_sec: float = 4.0

    def floor_height_between(self, from_floor: int, to_floor: int) -> float:
        """Absolute vertical distance (m) between two floor labels.

        Floor 1 is ground (height 0); floor f>=1 sits at (f-1)*h and basement
        f<=-1 at f*h, so B1 is one storey below 1F and B2 two (plan §1.6 —
        labels skip 0, hence this is not a plain label difference).
        """
        return abs(self._height_m(to_floor) - self._height_m(from_floor))

    def _height_m(self, floor: int) -> float:
        """Height (m) of a floor label above ground: 1F=0, 2F=+h, B1=-h."""
        if floor == 0:
            raise ValueError("floor 0 does not exist")
        rank = floor if floor >= 1 else floor + 1
        return (rank - 1) * self.floor_height_m

    def move_time_sec(self, distance_m: float) -> float:
        """Pure travel time (s) for the given vertical distance, no wait/door."""
        if distance_m <= 0:
            return 0.0
        a = self.accel_mps2
        v = self.max_speed_mps
        d_ramp = v * v / a
        if distance_m < d_ramp:
            return 2.0 * math.sqrt(distance_m / a)
        return 2.0 * v / a + (distance_m - d_ramp) / v

    def travel_time_sec(self, from_floor: int, to_floor: int) -> float:
        """Pure move time (s) between two floors (no wait/door), 0 if same floor."""
        if from_floor == to_floor:
            return 0.0
        return self.move_time_sec(self.floor_height_between(from_floor, to_floor))

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> ElevatorKinematics:
        elevator = config["elevator"]
        floor_height_m = config["building"]["floor_height_m"]
        return cls(
            accel_mps2=elevator["accel_mps2"],
            max_speed_mps=elevator["max_speed_mps"],
            floor_height_m=floor_height_m,
            door_open_close_sec=elevator["door_open_close_sec"],
        )
