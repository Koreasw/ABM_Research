"""ExternalRiderAgent (framework §6.2, new) — H0 direct-delivery FSM.

Arrives at lobby_entry at t_rider_arrival (BuildingOrderV4.arrival_time_sec,
synthesized by analysis.scenario_loader.load_replay_v4). Carries one order to
floor/office from the v4 mapping, using the pre-sampled vertical mode
(elevator vs stairs — the same logit draw as the precompute layer), drops it
(service_time from RIDERS data, per type), descends by the same mode
(rider_process.descend_same_mode), and exits. Building dwell T_lobby is
monetized as w_R * T_lobby (BuildingManagerAgent).

H0 FSM:
  WALK_TO_VERT → [CLIMB_STAIRS | WAIT_EV_UP → RIDING_UP] → WALK_TO_OFFICE
  → SERVICE → WALK_BACK → [DESCEND_STAIRS | WAIT_EV_DOWN → RIDING_DOWN]
  → WALK_TO_EXIT → EXITED (record + remove)

Stairs are off-graph timers (plan §"전역 설계 결정"): access points are
lobby_direct_corridor (1F) and the corridor midpoint floor_{f}_corr_{mid}
(floor f; mid = model.stair_corr_pos, derived from the corridor length).
"""

from __future__ import annotations

from mesa import Agent

from simulation.agents.walker import GraphWalker

STAIR_NODE_1F = "lobby_direct_corridor"


class ExternalRiderAgent(Agent, GraphWalker):
    WALK_TO_VERT = "walk_to_vert"
    CLIMB_STAIRS = "climb_stairs"
    WAIT_EV_UP = "wait_ev_up"
    RIDING_UP = "riding_up"
    WALK_TO_OFFICE = "walk_to_office"
    SERVICE = "service"
    WALK_BACK = "walk_back"
    DESCEND_STAIRS = "descend_stairs"
    WAIT_EV_DOWN = "wait_ev_down"
    RIDING_DOWN = "riding_down"
    WALK_TO_EXIT = "walk_to_exit"
    EXITED = "exited"

    kind = "rider"

    def __init__(
        self,
        model,  # noqa: ANN001
        order,  # BuildingOrderV4
        service_time_sec: float,
    ) -> None:
        super().__init__(model)
        self.order = order
        self.service_time_sec = service_time_sec
        self.speed_mps = model.rider_walk_speed_mps

        self.node = "lobby_entry"
        self._init_walker()
        self.entered_at_sec: float = model.clock_sec
        self.exited_at_sec: float | None = None
        self.mode_used: str = order.vertical_mode
        self.ev_wait_up_sec: float | None = None
        self.ev_wait_down_sec: float | None = None
        self.ev_wait_started_sec: float = 0.0
        self.ev_dest_floor: int = order.floor
        self._timer: float = 0.0
        self._ev = None

        self.state = self.WALK_TO_VERT
        if self.mode_used == "elevator":
            self._ev = model.control.choose_elevator(1, order.floor)
            self.set_walk_target(f"ev_{self._ev.ev_id}_1")
        else:
            self.set_walk_target(STAIR_NODE_1F)

    # ------------------------------------------------------------ properties

    @property
    def t_lobby_sec(self) -> float | None:
        if self.exited_at_sec is None:
            return None
        return self.exited_at_sec - self.entered_at_sec

    # --------------------------------------------------- passenger protocol

    def on_board(self, ev) -> None:  # noqa: ANN001
        wait = self.model.clock_sec - self.ev_wait_started_sec
        if self.state == self.WAIT_EV_UP:
            self.ev_wait_up_sec = wait
            self.state = self.RIDING_UP
        else:
            self.ev_wait_down_sec = wait
            self.state = self.RIDING_DOWN

    def on_alight(self, ev, floor: int) -> None:  # noqa: ANN001
        self.node = f"ev_{ev.ev_id}_{floor}"
        if self.state == self.RIDING_UP:
            self.state = self.WALK_TO_OFFICE
            self.set_walk_target(
                f"floor_{self.order.floor}_office_{self.order.office_id}"
            )
        else:
            self.state = self.WALK_TO_EXIT
            self.set_walk_target("lobby_entry")

    # ------------------------------------------------------------------ step

    def step(self) -> None:
        dt = self.model.dt
        f = self.order.floor

        if self.state == self.WALK_TO_VERT:
            if self.walk_tick(dt):
                if self.mode_used == "elevator":
                    self.state = self.WAIT_EV_UP
                    self.ev_dest_floor = f
                    self.ev_wait_started_sec = self.model.clock_sec
                    self._ev.register_hall_call(1, self)
                else:
                    self.state = self.CLIMB_STAIRS
                    self._timer = (f - 1) * self.model.stair_sec_per_floor

        elif self.state == self.CLIMB_STAIRS:
            self._timer -= dt
            if self._timer <= 0.0:
                self.node = f"floor_{f}_corr_{self.model.stair_corr_pos}"
                self.state = self.WALK_TO_OFFICE
                self.set_walk_target(f"floor_{f}_office_{self.order.office_id}")

        elif self.state == self.WALK_TO_OFFICE:
            if self.walk_tick(dt):
                self.state = self.SERVICE
                self._timer = self.service_time_sec

        elif self.state == self.SERVICE:
            self._timer -= dt
            if self._timer <= 0.0:
                customer = self.model.customer_by_ord_id[self.order.ord_id]
                customer.delivered_at_sec = self.model.clock_sec
                self.state = self.WALK_BACK
                if self.mode_used == "elevator":
                    self._ev = self.model.control.choose_elevator(f, 1)
                    self.set_walk_target(f"ev_{self._ev.ev_id}_{f}")
                else:
                    self.set_walk_target(
                        f"floor_{f}_corr_{self.model.stair_corr_pos}"
                    )

        elif self.state == self.WALK_BACK:
            if self.walk_tick(dt):
                if self.mode_used == "elevator":
                    self.state = self.WAIT_EV_DOWN
                    self.ev_dest_floor = 1
                    self.ev_wait_started_sec = self.model.clock_sec
                    self._ev.register_hall_call(f, self)
                else:
                    self.state = self.DESCEND_STAIRS
                    self._timer = (f - 1) * self.model.stair_sec_per_floor

        elif self.state == self.DESCEND_STAIRS:
            self._timer -= dt
            if self._timer <= 0.0:
                self.node = STAIR_NODE_1F
                self.state = self.WALK_TO_EXIT
                self.set_walk_target("lobby_entry")

        elif self.state == self.WALK_TO_EXIT:
            if self.walk_tick(dt):
                self._finalize()

        # WAIT_EV_UP / WAIT_EV_DOWN / RIDING_*: elevator drives transitions

    # -------------------------------------------------------------- internal

    def _finalize(self) -> None:
        self.exited_at_sec = self.model.clock_sec
        self.state = self.EXITED
        o = self.order
        customer = self.model.customer_by_ord_id[o.ord_id]
        self.model.rider_records.append(
            {
                "ord_id": o.ord_id,
                "floor": o.floor,
                "office_id": o.office_id,
                "rider_type": o.rider_type,
                "vertical_mode": self.mode_used,
                "arrival_time_planned_sec": o.arrival_time_sec,
                "entered_at_sec": self.entered_at_sec,
                "exited_at_sec": self.exited_at_sec,
                "t_lobby_sec": self.t_lobby_sec,
                "ev_wait_up_sec": self.ev_wait_up_sec,
                "ev_wait_down_sec": self.ev_wait_down_sec,
                "walked_m": round(self.walked_m, 2),
                "service_time_sec": self.service_time_sec,
                "w_R_krw_per_h": o.w_R_krw_per_h,
                "ord_time_abs_sec": o.ord_time_abs_sec,
                "cook_time_sec": o.cook_time_sec,
                "horizontal_time_s": o.horizontal_time_s,
                "deadline_abs_sec": o.deadline_abs_sec,
                "delivered_at_sec": customer.delivered_at_sec,
                "t_e2e_sec": customer.t_e2e_sec,
                "sla_violation": customer.sla_violation,
                # dynamic-pool provenance (None on the static replay path)
                "ready_time_sec": getattr(o, "ready_time_sec", None),
                "dispatch_time_sec": getattr(o, "dispatch_time_sec", None),
                "rider_wait_sec": getattr(o, "rider_wait_sec", None),
                "was_fallback": getattr(o, "was_fallback", None),
                "dist_m": getattr(o, "dist_m", None),
            }
        )
        # dynamic pool: return this rider to the pool (no-op on static path)
        self.model.on_rider_exit(o)
        self.remove()
