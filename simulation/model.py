"""BuildingHandoffModel — Mesa Model with 4-mode dispatcher (framework §6).

Handoff mode H in {H0 direct, H1 sync, H2 queued, H3 locker} is set at
construction and drives the ControlSystemAgent routing.
"""

from __future__ import annotations

from enum import Enum

from mesa import Model


class HandoffMode(str, Enum):
    H0_DIRECT = "h0_direct"
    H1_SYNC = "h1_sync"
    H2_QUEUED = "h2_queued"
    H3_LOCKER = "h3_locker"


class BuildingHandoffModel(Model):
    def __init__(
        self,
        mode: HandoffMode,
        n_floors: int = 5,
        n_robots: int = 3,
        n_locker_compartments: int = 8,
        locker_vmax: int = 100,
        rng_seed: int = 42,
        config: dict | None = None,
    ) -> None:
        super().__init__()
        self.mode = mode
        self.n_floors = n_floors
        self.n_robots = n_robots
        self.n_locker_compartments = n_locker_compartments
        self.locker_vmax = locker_vmax
        self.config = config or {}
        # TODO: build space (§5), schedule, agents, datacollector

    def step(self) -> None:
        raise NotImplementedError
