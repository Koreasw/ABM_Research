"""BuildingManagerAgent (framework §6.2, new).

Holds the active policy (H_mode, robot_count, locker_count, charging_policy).
Tracks CAPEX amortization and OPEX accumulation for NPV reporting.
The current paper uses fixed policies; adaptive selection is Future Work.
"""

from __future__ import annotations

from mesa import Agent


class BuildingManagerAgent(Agent):
    def __init__(
        self,
        model,  # noqa: ANN001
        mode: str,
        robot_count: int,
        locker_count: int,
        charging_policy: str = "off_peak",
    ) -> None:
        super().__init__(model)
        self.mode = mode
        self.robot_count = robot_count
        self.locker_count = locker_count
        self.charging_policy = charging_policy
        self.capex_total_krw: float = 0.0
        self.opex_running_krw: float = 0.0

    def step(self) -> None:
        raise NotImplementedError
