"""BuildingManagerAgent (framework §6.2, new).

Holds the active policy (H_mode, robot_count, locker_count, charging_policy).
Tracks CAPEX amortization and OPEX accumulation for NPV reporting.
The current paper uses fixed policies; adaptive selection is Future Work.

H0 baseline: CAPEX = 0 (no robot/locker). The per-tick accrual below is the
online running total of the riders' monetized dwell (w_R x T_lobby); the
exact per-order figure is recomputed from rider records in simulation.kpi
(tick quantization makes the two differ by at most one tick per rider).
"""

from __future__ import annotations

from mesa import Agent


class BuildingManagerAgent(Agent):
    def __init__(
        self,
        model,  # noqa: ANN001
        mode: str,
        robot_count: int = 0,
        locker_count: int = 0,
        # v2 (plan_h0_revision.md §1.3): the robot charges opportunistically
        # whenever it idles at the 1F lobby robot zone (waiting == charging) —
        # there is no off-peak charging trip and no basement dock (§1.6's
        # people-only basements added no robot facility).
        charging_policy: str = "opportunistic",
    ) -> None:
        super().__init__(model)
        self.mode = mode
        self.robot_count = robot_count
        self.locker_count = locker_count
        self.charging_policy = charging_policy
        self.capex_total_krw: float = 0.0
        self.opex_running_krw: float = 0.0

    def step(self) -> None:
        # `model.rider_cls` rather than a direct class name: Mesa keys
        # `agents_by_type` by the exact class, so naming `ExternalRiderAgent`
        # here would accrue zero OPEX the moment a mode swaps the rider class
        # in (A2 함정 1). H0 binds it to `ExternalRiderAgent`, so H0 is unchanged.
        dt = self.model.dt
        for rider in self.model.agents_of(self.model.rider_cls):
            self.opex_running_krw += rider.order.w_R_krw_per_h / 3600.0 * dt
