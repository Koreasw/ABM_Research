"""RobotAgent (framework §6.2) — H1 relay carrier. Implemented in Step A1.

The robot is an *elevator passenger* first and a delivery agent second: it
reuses `GraphWalker` for movement and the duck-typed passenger protocol from
`elevator.py`, so nothing about vertical transport is re-implemented here.

Two things it may never do, enforced in three places each (FSM below, the
boarding rule in `ElevatorAgent.can_board`, the audit asserts in
`model._audit_invariants`, and post-hoc gate B3):

    * ride a people-only car (EV1·EV2) — only `shared_with_robot` cars
    * enter a basement — B1/B2 are people-only levels (결정 #18, A10-2)

State machine (결정 4, 착수 전 점검 §4.2)
----------------------------------------
8 states plus two orthogonal attributes, rather than the 12-state chain the
original plan sketched. The chain was not a *partition*: "moving to the
customer" contains "waiting at the EV" and "riding", so per-state dwell times
double-count and the B4/B5 identities cannot close. It also had no state for
the handoff itself — H1's defining act — nor for a robot that reaches the
counter before the rider.

    IDLE ──assign──▶ MOVING(to_counter) ──arrive──▶ WAIT_RIDER
      ▲                                                  │ start_handoff()
      │                                                  ▼
      │                                              HANDOFF (N(60,15²))
      │                                                  │
      │        ┌───────────────────────────────────────┘
      │        ▼
      │   MOVING(to_ev_up) ─▶ WAIT_EV(up) ─▶ RIDING(up) ─▶ MOVING(to_office)
      │                                                          │
      │                                                          ▼
      │                                                        DROP (30 s)
      │                                                          │
      │   MOVING(to_home) ◀─ RIDING(down) ◀─ WAIT_EV(down) ◀─ MOVING(to_ev_down)
      │        │
      └────────┴──(SOC < low)──▶ CHARGING_BLOCKED ──(SOC ≥ resume)──▶ IDLE

`leg` distinguishes the five MOVING legs and `direction` the two WAIT_EV/RIDING
pairs, so the states stay mutually exclusive while the reporting layer can
still aggregate them into the seven buckets the paper figure uses.

`CHARGING_BLOCKED` vs charging while `IDLE`: both charge; only the former
refuses dispatch. Without that distinction 결정 #26's "recover to 40 %, then go
back to work" cannot be expressed at all.

Battery (결정 #26 — this *reverses* design freeze R0-5 "충전 비활성")
--------------------------------------------------------------------
Drain is `wh_per_m` per metre actually walked plus `wh_per_min_idle` for every
non-walking second — including riding, handoff and drop, which are stationary
for the drive train (결정 5). Charging runs whenever the robot sits on the home
node, which is also the dock (결정 #19 merged waiting and charging into the 1F
lobby zone), so "go home" and "go charge" are the same trip and are separated
only by `return_reason`.

⚠️ **The low-SOC threshold is not expected to fire in the corpus.** At 1,300 Wh
one delivery costs ~9–10 Wh, so a lunch-peak run ends at 43–90 % SOC. That is a
finding, not a defect: charging is not a binding constraint at this horizon.
The paths that *do* exercise the branch are `tests/test_a1_robot.py` and the
Phase E `soc_init_pct` sweep — never assume corpus coverage of it.
"""

from __future__ import annotations

from enum import Enum

from mesa import Agent

from simulation.agents.walker import GraphWalker
from simulation.config_params import RobotParams

HOME_NODE = "lobby_robot_pickup_zone"
COUNTER_NODE = "lobby_handoff_counter"


class RobotState(str, Enum):
    IDLE = "idle"                          # at home, dispatchable, trickle-charging
    MOVING = "moving"                      # see `leg`
    WAIT_RIDER = "wait_rider"              # at counter, rider not there yet
    HANDOFF = "handoff"                    # N(60, 15²) 0-truncated
    WAIT_EV = "wait_ev"                    # hall call registered; see `direction`
    RIDING = "riding"                      # aboard a shared car
    DROP = "drop"                          # 30 s at the office door
    CHARGING_BLOCKED = "charging_blocked"  # at home, NOT dispatchable


class RobotLeg(str, Enum):
    TO_COUNTER = "to_counter"
    TO_EV_UP = "to_ev_up"
    TO_OFFICE = "to_office"
    TO_EV_DOWN = "to_ev_down"
    TO_HOME = "to_home"


# Reporting buckets (paper figure / KPI). The execution FSM stays fine-grained
# so the kinematic identities close; this is the only place they are merged.
REPORT_BUCKETS: dict[str, tuple] = {
    "wait": ((RobotState.IDLE, None),),
    "meet_rider": ((RobotState.MOVING, RobotLeg.TO_COUNTER),
                   (RobotState.WAIT_RIDER, None)),
    "handoff": ((RobotState.HANDOFF, None),),
    "deliver_up": ((RobotState.MOVING, RobotLeg.TO_EV_UP),
                   (RobotState.WAIT_EV, 1), (RobotState.RIDING, 1),
                   (RobotState.MOVING, RobotLeg.TO_OFFICE)),
    "drop": ((RobotState.DROP, None),),
    "return": ((RobotState.MOVING, RobotLeg.TO_EV_DOWN),
               (RobotState.WAIT_EV, -1), (RobotState.RIDING, -1),
               (RobotState.MOVING, RobotLeg.TO_HOME)),
    "charge": ((RobotState.CHARGING_BLOCKED, None),),
}


class RobotAgent(Agent, GraphWalker):
    kind = "robot"

    def __init__(self, model, params: RobotParams | None = None) -> None:  # noqa: ANN001
        super().__init__(model)
        # Parameters come from the config block A0 wired up. Falling back to
        # `model.robot_params` (rather than re-declaring defaults here) is what
        # keeps a single source of truth: a second set of defaults in this
        # signature is exactly the drift V21-DOC hunts for.
        self.params: RobotParams = params or model.robot_params
        self.battery = self.params.battery
        self.speed_mps: float = self.params.speed_mps
        self.capa: int = self.params.capa

        self.node: str = HOME_NODE
        self._init_walker()

        self.state: RobotState = RobotState.IDLE
        self.leg: RobotLeg | None = None
        self.direction: int = 0            # +1 up / -1 down, for WAIT_EV/RIDING
        self.return_reason: str = "idle"   # 'idle' | 'low_soc'

        # passenger protocol (elevator.py)
        self.ev_dest_floor: int = 1
        self.ev_wait_started_sec: float = 0.0

        self.soc_wh: float = self.battery.wh_for_soc_pct(self.battery.soc_init_pct)
        self.distance_traveled_m: float = 0.0
        self.charge_events: int = 0
        self.charge_blocked_sec: float = 0.0
        self.soc_min_pct: float = self.soc_pct

        self.order = None                  # set by dispatch (A2)
        self.carrying_vol: int = 0
        self.trips_completed: int = 0
        self._timer: float = 0.0
        self._ev = None
        self._rider_ready: bool = False
        self._handoff_sec: float = 0.0
        self._pending_dest_floor: int = 1
        # A2 함정 2 — the rider exits before the delivery, so the second half of
        # every order timeline lives on the robot and is published to
        # `model.robot_leg_records` at trip end, joined back on `ord_id`.
        self._leg: dict = {}

    # ------------------------------------------------------------------ battery

    @property
    def soc_pct(self) -> float:
        return 100.0 * self.soc_wh / self.battery.capacity_wh

    @property
    def is_charging(self) -> bool:
        """Charging is a property of *being docked*, not a state (결정 #19).

        `IDLE` and `CHARGING_BLOCKED` differ in dispatchability, not in whether
        current flows, so this is deliberately not part of `RobotState`.
        """
        return self.node == HOME_NODE and self.state in (
            RobotState.IDLE, RobotState.CHARGING_BLOCKED
        )

    @property
    def is_available(self) -> bool:
        """Dispatchable? `CHARGING_BLOCKED` is the whole point of the flag."""
        return self.state == RobotState.IDLE

    def _account_energy(self, walked_m: float, dt: float) -> None:
        """Drain for this tick, then charge if docked.

        Walking bills distance; everything else bills time, including riding
        and the handoff/drop timers — the drive train is stationary but the
        robot is powered (결정 5). Over a long drain the time term is the larger
        of the two (~55 % of total), which is why `wh_per_min_idle` is a Phase E
        sensitivity target rather than a rounding detail.
        """
        if walked_m > 0.0:
            self.soc_wh -= walked_m * self.battery.wh_per_m
        else:
            self.soc_wh -= dt * self.battery.wh_per_sec_idle
        if self.is_charging:
            self.soc_wh += dt * self.battery.charge_wh_per_sec
        self.soc_wh = min(max(self.soc_wh, 0.0), self.battery.capacity_wh)
        self.soc_min_pct = min(self.soc_min_pct, self.soc_pct)

    # -------------------------------------------------------- dispatch (A2 API)

    def assign(self, order) -> None:  # noqa: ANN001
        """Accept an order and head for the counter. Called by the dispatcher."""
        if not self.is_available:
            raise ValueError(
                f"robot {self.unique_id} is not dispatchable (state={self.state})"
            )
        if order.floor < 1:
            raise ValueError(
                f"robot delivery to floor {order.floor}: robots never enter a "
                f"basement (결정 #18 / gate B3)"
            )
        self.order = order
        self.carrying_vol = 0          # loaded at handoff, not at dispatch
        self.return_reason = "idle"
        self._rider_ready = False
        self._leg = {
            "ord_id": order.ord_id,
            "robot_id": self.unique_id,
            "floor": order.floor,
            "office_id": order.office_id,
            "assigned_at_sec": self.model.clock_sec,
            "handoff_started_sec": None,
            "handoff_ended_sec": None,
            "ev_wait_up_sec": None,
            "ev_wait_down_sec": None,
            "ev_id_up": None,
            "ev_id_down": None,
            "delivered_at_sec": None,
            "returned_at_sec": None,
            "soc_pct_at_assign": self.soc_pct,
            # A5/B10: filled at `_finish_trip`. Without it the gate cannot tell
            # a robot that parked to charge from one that parked because it had
            # nothing to do — and "no dispatch while CHARGING_BLOCKED" is a
            # statement about exactly that difference.
            "return_reason": None,
        }
        self._enter_moving(RobotLeg.TO_COUNTER, COUNTER_NODE)

    def notify_rider_ready(self, duration_sec: float) -> None:
        """Rider is at the counter with the food; hand over for `duration_sec`.

        The caller owns the duration because R0-3 draws it from the dedicated
        `'hoff'` stream keyed by `ord_id`, and that draw belongs with the rider
        (A2), not here — one stream, one owner.

        The transition itself happens on the robot's **next** tick, not inside
        this call. That one-tick lag is a real consequence of the tick order
        (the rider steps before the robot), so it is left visible and is carried
        into the A4 golden-path hand calculation rather than papered over.
        """
        if self.state is not RobotState.WAIT_RIDER:
            raise ValueError(
                f"rider signalled while robot is {self.state}, not WAIT_RIDER"
            )
        self._rider_ready = True
        self._handoff_sec = max(duration_sec, 0.0)

    def _begin_handoff(self) -> None:
        self.carrying_vol = int(getattr(self.order, "vol", 0) or 0)
        self.state = RobotState.HANDOFF
        self.leg = None
        self._timer = self._handoff_sec
        self._rider_ready = False
        self._leg["handoff_started_sec"] = self.model.clock_sec

    # --------------------------------------------------- passenger protocol

    def on_board(self, ev) -> None:  # noqa: ANN001
        wait = self.model.clock_sec - self.ev_wait_started_sec
        # `direction` is still the WAIT_EV direction at this point — it is only
        # cleared when the next MOVING leg starts.
        key = "ev_wait_up_sec" if self.direction > 0 else "ev_wait_down_sec"
        if self._leg:
            self._leg[key] = wait
            # A5/B3: which car actually carried the robot. The gate "a robot
            # never boards a dedicated car" needs the car identity per boarding,
            # and a per-EV counter cannot supply it — the counter says a robot
            # boarded EV1, not which trip did, so a violation could not be
            # traced back to an order.
            self._leg["ev_id_up" if self.direction > 0 else "ev_id_down"] = ev.ev_id
        self.state = RobotState.RIDING
        self._ev = ev

    def on_alight(self, ev, floor: int) -> None:  # noqa: ANN001
        self.node = f"ev_{ev.ev_id}_{floor}"
        if self.direction > 0:
            self._enter_moving(
                RobotLeg.TO_OFFICE,
                f"floor_{self.order.floor}_office_{self.order.office_id}",
            )
        else:
            self._enter_moving(RobotLeg.TO_HOME, HOME_NODE)

    # -------------------------------------------------------------- internals

    def _enter_moving(self, leg: RobotLeg, target: str) -> None:
        self.state = RobotState.MOVING
        self.leg = leg
        self.direction = 0
        self.set_walk_target(target)

    def _shared_cars(self) -> list:
        cars = [ev for ev in self.model.elevators if ev.shared_with_robot]
        if not cars:
            raise ValueError(
                "no robot-shareable elevator: building.shared_ev_ids is empty, "
                "so a robot mode cannot run (check the config, not this agent)"
            )
        return cars

    def _depart_for_ev(self, from_floor: int, to_floor: int, leg: RobotLeg) -> None:
        """Pick the car, then walk to its landing — in that order, once.

        Mirrors the rider exactly (`external_rider.py`): the car is chosen
        *before* the walk and the hall call goes to that same car on arrival.
        This is the designated-dispatch simplification whose cost W5d measures
        (H0: stale 52.95 %, harm ≤ 28.81 s mean); re-choosing on arrival would
        quietly make the robot smarter than the rider and break the comparison.
        Restricting the pool to shareable cars is the only difference.
        """
        self._ev = self.model.control.choose_elevator(
            from_floor, to_floor, candidates=self._shared_cars()
        )
        self._pending_dest_floor = to_floor
        self._enter_moving(leg, f"ev_{self._ev.ev_id}_{from_floor}")

    def _register_call(self, from_floor: int) -> None:
        """Arrived at the landing → queue on the car chosen before the walk."""
        to_floor = self._pending_dest_floor
        self.direction = 1 if to_floor > from_floor else -1
        self.state = RobotState.WAIT_EV
        self.leg = None
        self.ev_dest_floor = to_floor
        self.ev_wait_started_sec = self.model.clock_sec
        self._ev.register_hall_call(from_floor, self)

    def _finish_trip(self) -> None:
        """Arrived home: publish the leg record, then idle or block to charge."""
        if self._leg:
            self._leg["returned_at_sec"] = self.model.clock_sec
            self._leg["soc_pct_at_return"] = self.soc_pct
            self._leg["return_reason"] = self.return_reason
            # A2 함정 2: this is the half of the order timeline the rider could
            # not record. Keyed by ord_id so kpi.py can join the two halves.
            self.model.robot_leg_records[self._leg["ord_id"]] = self._leg
            self.model.control.release_robot(self._leg["ord_id"])
            self._leg = {}
        self.order = None
        self.carrying_vol = 0
        self.trips_completed += 1
        self.leg = None
        self.direction = 0
        if self.return_reason == "low_soc":
            self.state = RobotState.CHARGING_BLOCKED
            self.charge_events += 1
        else:
            self.state = RobotState.IDLE

    # ------------------------------------------------------------------ step

    def step(self) -> None:
        dt = self.model.dt
        walked_before = self.walked_m

        if self.state is RobotState.MOVING:
            arrived = self.walk_tick(dt)
            if arrived:
                self._on_arrive()

        elif self.state is RobotState.WAIT_RIDER:
            # Waiting for the rider is its own state, not an invisible gap
            # inside "moving to the customer" — A4's second golden-path case
            # (2 orders, 1 robot) measures exactly this dwell.
            if self._rider_ready:
                self._begin_handoff()

        elif self.state is RobotState.HANDOFF:
            self._timer -= dt
            if self._timer <= 0.0:
                # A5: the OBSERVED end tick. A2 filled this in `_finish_trip` as
                # `started + handoff_sec`, which is the nominal duration and can
                # land between ticks — the only stamp in the record that was not
                # a clock reading, and B4 compares it against tick-quantized
                # segments. Recording it where the transition happens makes the
                # whole leg one consistent clock.
                self._leg["handoff_ended_sec"] = self.model.clock_sec
                self._depart_for_ev(1, self.order.floor, RobotLeg.TO_EV_UP)

        elif self.state is RobotState.DROP:
            self._timer -= dt
            if self._timer <= 0.0:
                customer = self.model.customer_by_ord_id[self.order.ord_id]
                if customer.delivered_at_sec is None:
                    customer.delivered_at_sec = self.model.clock_sec
                self._leg["delivered_at_sec"] = customer.delivered_at_sec
                # 결정 5: the low-SOC decision is taken at DROP completion, so a
                # robot never abandons food mid-delivery to go charge.
                if self.soc_pct < self.battery.soc_low_pct:
                    self.return_reason = "low_soc"
                self._depart_for_ev(self.order.floor, 1, RobotLeg.TO_EV_DOWN)

        elif self.state is RobotState.CHARGING_BLOCKED:
            self.charge_blocked_sec += dt
            if self.soc_pct >= self.battery.soc_resume_pct:
                self.state = RobotState.IDLE
                self.return_reason = "idle"

        # WAIT_EV / RIDING / IDLE advance through the elevator or the dispatcher.
        self._account_energy(self.walked_m - walked_before, dt)
        self.distance_traveled_m = self.walked_m

    def _on_arrive(self) -> None:
        leg = self.leg
        if leg is RobotLeg.TO_COUNTER:
            self.state = RobotState.WAIT_RIDER
            self.leg = None
        elif leg is RobotLeg.TO_EV_UP:
            self._register_call(1)
        elif leg is RobotLeg.TO_OFFICE:
            self.state = RobotState.DROP
            self.leg = None
            self._timer = self.params.service_time_drop_sec
        elif leg is RobotLeg.TO_EV_DOWN:
            self._register_call(self.order.floor)
        elif leg is RobotLeg.TO_HOME:
            self._finish_trip()

    # ------------------------------------------------------------- reporting

    @property
    def report_bucket(self) -> str:
        key = self.leg if self.state is RobotState.MOVING else (
            self.direction if self.state in (RobotState.WAIT_EV, RobotState.RIDING)
            else None
        )
        for bucket, members in REPORT_BUCKETS.items():
            if (self.state, key) in members:
                return bucket
        raise ValueError(  # a new state must be given a bucket, not silently dropped
            f"robot state {self.state} / key {key!r} maps to no report bucket"
        )
