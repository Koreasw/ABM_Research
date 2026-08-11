"""HandoffRiderAgent (Step A2) — the H1 rider, who never leaves the ground floor.

H0's rider carries the order the whole way (`external_rider.py`). H1's rider
hands it to a robot at the 1F counter and leaves, so the two share an arrival
and an exit but nothing in between:

    WALK_TO_COUNTER → WAIT_ROBOT → HANDOFF → WALK_TO_EXIT → EXITED

This is a separate class rather than a mode branch inside `ExternalRiderAgent`
because H0's file is frozen regression surface — every v2.1 gate, the golden
paths and the bit-identity snapshots run through it. A branch there would put
H1 logic on H0's execution path; a sibling class keeps H0 untouched by
construction. The cost is `model.rider_cls` (A2 함정 1), which is cheap and is
locked by `tests/test_a2_handoff.py`.

Two consequences worth stating plainly, because they shape everything downstream:

**The rider exits before the order is delivered** (A2 함정 2). In H0 one rider
record held the whole order timeline; here the rider's record ends at the
handoff and the robot's leg finishes the story. `model.robot_leg_records` holds
the second half, keyed by `ord_id`, and the two are joined on that key. Every H0
field is preserved and the ones that cannot apply are `None` — additive, so
existing consumers keep working unchanged.

**T_lobby means something different in H1.** The H0 quantity spans the whole
building visit; here it spans arrival → handoff → exit, which is short and, more
importantly, *diverges under saturation* because it includes the wait for a
free robot. `T_building_order` (A3) is the quantity actually comparable with
H0's `T_lobby`, and the paper must use that one.

The handoff duration is drawn here, not in the robot: R0-3 keys the ``'hoff'``
stream by `ord_id`, so one stream has one owner (구현 로그 §A2-4). The robot only
receives the value through `notify_rider_ready(duration)`.
"""

from __future__ import annotations

import numpy as np
from mesa import Agent

from simulation.agents.robot import COUNTER_NODE, RobotState
from simulation.agents.walker import GraphWalker


def draw_handoff_sec(tag: int, rng_seed: int, ord_id: int,
                     mean_sec: float, sd_sec: float) -> float:
    """R0-3: ``N(mean, sd^2)`` truncated at 0, from the 3-word ``'hoff'`` stream.

    A fresh `Generator` per `ord_id` (the same shape as the floor-assignment
    stream in `floor_demand.py`) is what makes the draw independent of dispatch
    order: a robot shortage reorders *when* orders are handed over, and a shared
    sequential generator would then shift every subsequent order's draw and
    destroy the CRN pairing between modes.

    Truncation is `max(x, 0)`, not resampling — resampling would consume a
    variable number of words per order and break that same property. At
    ``N(60, 15²)`` the clipped mass is ~3e-5, so the distinction is theoretical
    for the corpus but the reproducibility property is not.
    """
    rng = np.random.default_rng([tag, rng_seed, int(ord_id)])
    return max(float(rng.normal(mean_sec, sd_sec)), 0.0)


class HandoffRiderAgent(Agent, GraphWalker):
    WALK_TO_COUNTER = "walk_to_counter"
    WAIT_ROBOT = "wait_robot"
    HANDOFF = "handoff"
    WALK_TO_EXIT = "walk_to_exit"
    EXITED = "exited"

    kind = "rider"

    def __init__(
        self,
        model,  # noqa: ANN001
        order,  # BuildingOrderV4 / V5
        service_time_sec: float,
    ) -> None:
        super().__init__(model)
        self.order = order
        # Kept for record parity with H0 even though the H1 rider never performs
        # it: the office service is the robot's DROP now. Recording it as the
        # counterfactual keeps the two modes' rider records the same shape.
        self.service_time_sec = service_time_sec
        self.speed_mps = model.rider_walk_speed_mps

        self.node = "lobby_entry"
        self._init_walker()
        self.entered_at_sec: float = model.clock_sec
        self.exited_at_sec: float | None = None
        # H1 riders do not use the vertical system at all; the pre-sampled
        # vertical mode stays on the order for the H0/H1 paired comparison but
        # is deliberately not consumed here.
        self.mode_used: str = "handoff"
        self.robot = None
        self.arrived_at_counter_sec: float | None = None
        self.handoff_started_sec: float | None = None
        self.handoff_ended_sec: float | None = None
        self.handoff_sec: float = draw_handoff_sec(
            model.handoff_params.rng_stream_tag,
            model.rng_seed,
            order.ord_id,
            model.handoff_params.service_mean_sec,
            model.handoff_params.service_sd_sec,
        )
        self._timer: float = 0.0

        self.state = self.WALK_TO_COUNTER
        self.set_walk_target(COUNTER_NODE)
        # Requesting on arrival at the *building*, not at the counter, is what
        # lets the robot walk its 5 m to the counter while the rider walks
        # theirs — and it makes the FCFS order the arrival order (A2-4).
        model.control.request_robot(self)

    # ------------------------------------------------------------ properties

    @property
    def t_lobby_sec(self) -> float | None:
        """Building dwell. NOT comparable with H0's — see the module docstring."""
        if self.exited_at_sec is None:
            return None
        return self.exited_at_sec - self.entered_at_sec

    @property
    def robot_wait_sec(self) -> float | None:
        """Counter dwell waiting for a robot — the saturation signal (§3.6)."""
        if self.handoff_started_sec is None or self.arrived_at_counter_sec is None:
            return None
        return self.handoff_started_sec - self.arrived_at_counter_sec

    # ------------------------------------------------------------------ step

    def step(self) -> None:
        dt = self.model.dt

        if self.state == self.WALK_TO_COUNTER:
            if self.walk_tick(dt):
                self.state = self.WAIT_ROBOT
                self.arrived_at_counter_sec = self.model.clock_sec

        elif self.state == self.WAIT_ROBOT:
            robot = self.model.control.robot_for(self.order.ord_id)
            # Both parties must actually be at the counter. The robot may have
            # been assigned several ticks ago and still be walking over.
            if (
                robot is not None
                and robot.state is RobotState.WAIT_RIDER
                and robot.node == COUNTER_NODE
            ):
                self.robot = robot
                self.handoff_started_sec = self.model.clock_sec
                # The robot transitions on its NEXT tick (it steps after the
                # rider), so its handoff ends one tick after the rider's. That
                # lag is a genuine consequence of the tick order and is carried
                # into the A4 hand calculation rather than hidden.
                robot.notify_rider_ready(self.handoff_sec)
                self.state = self.HANDOFF
                self._timer = self.handoff_sec

        elif self.state == self.HANDOFF:
            self._timer -= dt
            if self._timer <= 0.0:
                self.handoff_ended_sec = self.model.clock_sec
                self.state = self.WALK_TO_EXIT
                self.set_walk_target("lobby_entry")

        elif self.state == self.WALK_TO_EXIT:
            if self.walk_tick(dt):
                self._finalize()

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
                # H1 riders never ride: None, not 0.0 — a zero would average
                # into the EV-wait KPIs as a real observation.
                "ev_wait_up_sec": None,
                "ev_wait_down_sec": None,
                "walked_m": round(self.walked_m, 2),
                "service_time_sec": self.service_time_sec,
                "w_R_krw_per_h": o.w_R_krw_per_h,
                "ord_time_abs_sec": o.ord_time_abs_sec,
                "cook_time_sec": o.cook_time_sec,
                "horizontal_time_s": o.horizontal_time_s,
                "deadline_abs_sec": o.deadline_abs_sec,
                # ⚠️ The rider leaves BEFORE the delivery: these are the state at
                # exit, so they are usually None here. The delivered/T_e2e/SLA
                # truth for H1 comes from the customer joined on `ord_id`, never
                # from this row (A2 함정 2).
                "delivered_at_sec": customer.delivered_at_sec,
                "t_e2e_sec": customer.t_e2e_sec,
                "sla_violation": customer.sla_violation,
                # H1 additions (None in H0 records — additive convention)
                "handoff_started_sec": self.handoff_started_sec,
                "handoff_ended_sec": self.handoff_ended_sec,
                "handoff_sec": self.handoff_sec,
                "robot_wait_sec": self.robot_wait_sec,
                "robot_id": None if self.robot is None else self.robot.unique_id,
                # dynamic-pool provenance (None on the static replay path)
                "ready_time_sec": getattr(o, "ready_time_sec", None),
                "dispatch_time_sec": getattr(o, "dispatch_time_sec", None),
                "rider_wait_sec": getattr(o, "rider_wait_sec", None),
                "was_fallback": getattr(o, "was_fallback", None),
                "dist_m": getattr(o, "dist_m", None),
            }
        )
        self.model.on_rider_exit(o)
        self.remove()
