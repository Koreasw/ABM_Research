"""RobotAgent (framework §6.2)."""

from __future__ import annotations

from enum import Enum

from mesa import Agent


class RobotState(str, Enum):
    IDLE = "idle"
    MOVING = "moving"
    DELIVERING = "delivering"
    CHARGING = "charging"
    RETURNING = "returning"


class RobotAgent(Agent):
    def __init__(
        self,
        model,  # noqa: ANN001
        capa: int = 100,
        soc: float = 100.0,
        soc_low_threshold: float = 20.0,
        speed_mps: float = 1.0,
    ) -> None:
        super().__init__(model)
        self.capa = capa
        self.soc = soc
        self.soc_low_threshold = soc_low_threshold
        self.speed_mps = speed_mps
        self.state: RobotState = RobotState.IDLE
        self.carrying_vol: int = 0
        self.distance_traveled_m: float = 0.0

    def step(self) -> None:
        raise NotImplementedError
