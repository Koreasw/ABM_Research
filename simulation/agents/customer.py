"""CustomerAgent (framework §6.2).

Position (floor, office), VOL, abandon threshold tau_abandon (lead-time q05
~ 38 min lower bound), price sensitivity beta_p.
"""

from __future__ import annotations

from mesa import Agent


class CustomerAgent(Agent):
    def __init__(
        self,
        model,  # noqa: ANN001
        floor: int,
        office_id: int,
        vol: int,
        tau_abandon_sec: float = 2280.0,
        beta_p: float = 0.0,
    ) -> None:
        super().__init__(model)
        self.floor = floor
        self.office_id = office_id
        self.vol = vol
        self.tau_abandon_sec = tau_abandon_sec
        self.beta_p = beta_p

    def step(self) -> None:
        raise NotImplementedError
