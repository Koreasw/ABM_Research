"""CustomerAgent (framework §6.2).

Position (floor, office_id), VOL, and the platform SLA target
dlv_deadline_sec (absolute simulation seconds; BaeMin's algorithmic
ETA from cook time + distance + restaurant accuracy — see §4.1.7).

This paper does NOT model customer abandonment / renege: all orders
are eventually delivered. The customer-side KPIs are:
  - L_sla_violation = 1[T_e2e > dlv_deadline_sec]
  - S_customer     = sigma(-beta * max(T_e2e - dlv_deadline_sec, 0))
                     (deadline-relative satisfaction)
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
        ord_time_sec: float,
        dlv_deadline_sec: float,
        beta: float = 0.001,
    ) -> None:
        super().__init__(model)
        self.floor = floor
        self.office_id = office_id
        self.vol = vol
        self.ord_time_sec = ord_time_sec
        self.dlv_deadline_sec = dlv_deadline_sec
        self.beta = beta
        self.delivered_at_sec: float | None = None

    @property
    def t_e2e_sec(self) -> float | None:
        if self.delivered_at_sec is None:
            return None
        return self.delivered_at_sec - self.ord_time_sec

    @property
    def sla_violation(self) -> bool | None:
        if self.delivered_at_sec is None:
            return None
        return self.delivered_at_sec > self.dlv_deadline_sec

    def step(self) -> None:
        raise NotImplementedError
