"""ExternalRiderAgent (framework §6.2, new).

Arrives at lobby_entry at t_rider_arrival (from rider_arrival_model.py).
Mode-dependent process branch (H0..H3). Building dwell time T_lobby is
monetized as w_R * T_lobby.
"""

from __future__ import annotations

from mesa import Agent


class ExternalRiderAgent(Agent):
    def __init__(
        self,
        model,  # noqa: ANN001
        arrival_time_sec: float,
        rider_type: str,           # BIKE / WALK / CAR
        w_R_krw_per_h: float,
        vol_carried: int,
        deadline_sec: float,
        tau_patience_sec: float = 300.0,
    ) -> None:
        super().__init__(model)
        self.arrival_time_sec = arrival_time_sec
        self.rider_type = rider_type
        self.w_R_krw_per_h = w_R_krw_per_h
        self.vol_carried = vol_carried
        self.deadline_sec = deadline_sec
        self.tau_patience_sec = tau_patience_sec
        self.entered_at_sec: float | None = None
        self.exited_at_sec: float | None = None

    @property
    def t_lobby_sec(self) -> float:
        if self.entered_at_sec is None or self.exited_at_sec is None:
            return 0.0
        return self.exited_at_sec - self.entered_at_sec

    def step(self) -> None:
        raise NotImplementedError
