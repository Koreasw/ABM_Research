"""PedestrianAgent — background EV congestion generator (framework §5.6, §6.2).

Not a dependent variable; exists to endogenize EV wait times.
Peak profiles: commute (08-10), lunch (11:30-13:30), commute (17:30-19:00).
"""

from __future__ import annotations

from mesa import Agent


class PedestrianAgent(Agent):
    def __init__(
        self,
        model,  # noqa: ANN001
        from_floor: int,
        to_floor: int,
        speed_mps: float = 1.2,
    ) -> None:
        super().__init__(model)
        self.from_floor = from_floor
        self.to_floor = to_floor
        self.speed_mps = speed_mps

    def step(self) -> None:
        raise NotImplementedError
