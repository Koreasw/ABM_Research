"""Vertical transport time model — T2 (etc/plan_travel_time_functions.md §3.2-3.5).

Stairs vs elevator binary logit mode choice (McFadden), given per-floor
elevator time (kinematics + wait + door) and stair climb time. Shared by
the uncongested precompute layer (analysis/travel_time_v4.py) and the
ABM's ExternalRiderAgent (simulation/agents/external_rider.py).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from simulation.elevator_physics import ElevatorKinematics


@dataclass(frozen=True)
class VerticalTransportModel:
    kin: ElevatorKinematics
    ev_wait_sec: float = 20.0
    stair_sec_per_floor: float = 16.5
    beta_per_sec: float = 0.15
    mode_seed: int = 42
    walk_speed_mps: float = 1.2
    entrance_m: float = 4.0

    def t_elevator_s(self, floor: int, include_wait: bool = True) -> float:
        """Elevator time (s) from 1F to `floor`: wait (optional) + move + door.

        include_wait=False yields the strict, wait-free lower bound used by
        the ABM's endogenous-wait validation (see plan §V check #4).
        """
        wait = self.ev_wait_sec if include_wait else 0.0
        return wait + self.kin.travel_time_sec(1, floor) + self.kin.door_open_close_sec

    def t_stairs_s(self, floor: int) -> float:
        """Stair climb time (s) from 1F to `floor`."""
        return (floor - 1) * self.stair_sec_per_floor

    def p_elevator(self, floor: int) -> float:
        """P(elevator | floor) — binary logit, T_elev includes wait (§3.3)."""
        t_elev = self.t_elevator_s(floor, include_wait=True)
        t_stair = self.t_stairs_s(floor)
        return 1.0 / (1.0 + math.exp(-self.beta_per_sec * (t_stair - t_elev)))

    def expected_vertical_time(self, floor: int) -> float:
        """E[T](floor) = P*T_elev + (1-P)*T_stair (T_elev includes wait)."""
        p = self.p_elevator(floor)
        t_elev = self.t_elevator_s(floor, include_wait=True)
        t_stair = self.t_stairs_s(floor)
        return p * t_elev + (1.0 - p) * t_stair

    def sample_mode(self, ord_id: int, floor: int) -> str:
        """Sample 'elevator' or 'stairs' per the RNG convention (§3.3).

        RNG: numpy.random.default_rng(uint64(mode_seed) XOR uint64(ord_id)),
        one uniform draw. Reproducible per-order regardless of row order.
        """
        rng = np.random.default_rng(np.uint64(self.mode_seed) ^ np.uint64(ord_id))
        u = rng.random()
        return "elevator" if u < self.p_elevator(floor) else "stairs"

    def entrance_walk_s(self) -> float:
        """Lobby-entrance walk time (s): entrance_m / walk_speed_mps."""
        return self.entrance_m / self.walk_speed_mps

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> VerticalTransportModel:
        v = config["vertical"]
        entrance_m = config.get("building", {}).get("entrance_m", 4.0)
        return cls(
            kin=ElevatorKinematics.from_config(config),
            ev_wait_sec=v["ev_wait_sec"],
            stair_sec_per_floor=v["stair_sec_per_floor"],
            beta_per_sec=v["mode_choice_beta_per_sec"],
            mode_seed=v["mode_seed"],
            walk_speed_mps=v["walk_speed_mps"],
            entrance_m=entrance_m,
        )
