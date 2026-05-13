"""LockerAgent (framework §6.2, new). M compartments, dock/pickup time stochastic."""

from __future__ import annotations

from dataclasses import dataclass

from mesa import Agent


@dataclass
class Compartment:
    occupied_by_order_id: int | None = None
    occupied_since_sec: float | None = None


class LockerAgent(Agent):
    def __init__(
        self,
        model,  # noqa: ANN001
        n_compartments: int = 8,
        v_max: int = 100,
        storage_limit_sec: float = 1800.0,    # 30 min
        dock_mean_sec: float = 20.0,
        dock_sd_sec: float = 5.0,
        pickup_mean_sec: float = 15.0,
        pickup_sd_sec: float = 4.0,
    ) -> None:
        super().__init__(model)
        self.v_max = v_max
        self.storage_limit_sec = storage_limit_sec
        self.dock_mean_sec = dock_mean_sec
        self.dock_sd_sec = dock_sd_sec
        self.pickup_mean_sec = pickup_mean_sec
        self.pickup_sd_sec = pickup_sd_sec
        self.compartments: list[Compartment] = [Compartment() for _ in range(n_compartments)]

    def try_dock(self, order_id: int, vol: int, now_sec: float) -> int | None:
        """Return index of newly-occupied compartment, or None if full / vol > v_max."""
        raise NotImplementedError

    def pickup(self, order_id: int) -> None:
        raise NotImplementedError

    @property
    def occupancy(self) -> float:
        n = len(self.compartments)
        occ = sum(1 for c in self.compartments if c.occupied_by_order_id is not None)
        return occ / n if n > 0 else 0.0
