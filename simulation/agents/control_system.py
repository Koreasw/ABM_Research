"""ControlSystemAgent — central dispatcher (framework §6.2).

Mode-aware routing:
  H0: guide the external rider (and pedestrians) to the min-expected-wait EV;
      no robot involvement — `step()` is a no-op.
  H1: dispatch nearest idle robot to handoff_counter when rider arrives
  H2: rider joins queue; assign next idle robot
  H3: notify idle robot when rider docks the locker
H1~H3 branches are the future extension point (plan_abm_baseline_h0.md);
only H0 is implemented in this baseline.

EV choice heuristic (plan §C3, TBD 확정): estimated wait =
    |position_floor − rank(from_floor)| × adjacent-floor travel time
  + door_time × pending stop count
  + remaining door timer if currently in a door cycle.
Ties go to the lower ev_id (EV1).
"""

from __future__ import annotations

from collections import deque

from mesa import Agent

from simulation.agents.elevator import ElevatorAgent
from simulation.space import floor_rank


class ControlSystemAgent(Agent):
    def __init__(self, model, policy: str = "min_wait") -> None:  # noqa: ANN001
        super().__init__(model)
        self.policy = policy
        self.order_queue: deque = deque()
        self.dispatch_count: int = 0
        # H1 robot dispatch (A2). `robot_requests` is the FCFS line of riders
        # who have entered the building and want a robot; `_robot_by_ord_id`
        # lets the rider find the robot that was assigned to its order without
        # either side holding a reference to the other before assignment.
        self.robot_requests: deque = deque()
        self._robot_by_ord_id: dict[int, object] = {}
        self.robot_dispatch_count: int = 0

    def choose_elevator(
        self, from_floor: int, to_floor: int, candidates=None  # noqa: ANN001
    ) -> ElevatorAgent:
        """Pick the EV with the smallest estimated wait for a hall call.

        `candidates` restricts the pool without changing the heuristic — the
        robot passes the robot-shareable cars (A1). Deliberately the *same*
        cost function and the same lower-`ev_id` tie-break, so the tie-break
        skew W5c measured for people applies to robots too and is observable
        in A7 rather than hidden behind a second policy.

        Default `None` means "all cars", which is the pre-A1 call exactly —
        H0 keeps its bit-identical dispatch.
        """
        pool = self.model.elevators if candidates is None else candidates
        evs = sorted(pool, key=lambda e: e.ev_id)
        if not evs:
            raise ValueError(
                "choose_elevator got an empty candidate set — a robot mode with "
                "no robot-shareable car is a config error (building.shared_ev_ids)"
            )
        best = min(evs, key=lambda ev: self._estimate_wait(ev, from_floor))
        self.dispatch_count += 1
        return best

    def _estimate_wait(self, ev: ElevatorAgent, from_floor: int) -> float:
        per_floor_sec = self.model.kin.travel_time_sec(1, 2)
        # position_floor is already in rank units; from_floor is a label, so it
        # must be converted before subtracting (plan §1.6 — a B1 hall call would
        # otherwise read one storey too far from every car).
        est = abs(ev.position_floor - floor_rank(from_floor)) * per_floor_sec
        est += ev.door_open_close_sec * ev.pending_stop_count()
        if ev.state == ElevatorAgent.DOORS:
            est += max(ev._door_timer, 0.0)
        return est

    # -------------------------------------------------------- robot dispatch

    def request_robot(self, rider) -> None:  # noqa: ANN001
        """Join the FCFS line. Called by the rider when it enters the building."""
        self.robot_requests.append(rider)

    def robot_for(self, ord_id: int):  # noqa: ANN001
        """The robot assigned to this order, or None if none has been yet."""
        return self._robot_by_ord_id.get(ord_id)

    def release_robot(self, ord_id: int) -> None:
        """Drop the order→robot link once the trip is finished."""
        self._robot_by_ord_id.pop(ord_id, None)

    def _dispatch_robots(self) -> None:
        """FCFS: oldest waiting rider gets the lowest-id available robot.

        "Nearest idle robot" and "first-come-first-served" are the same rule
        here and that is not a coincidence — 결정 #19 merged waiting and charging
        into the single 1F robot zone, so every dispatchable robot sits on the
        same node and the distance term is constant. Should a future variant
        park robots on different floors, this is the one place that has to grow
        a distance key; the FCFS order of `robot_requests` stays correct either
        way.

        `CHARGING_BLOCKED` robots are deliberately not candidates — that is the
        entire reason the state exists (3.1). Ordering by `unique_id` rather
        than by list position keeps the assignment reproducible under CRN.
        """
        if not self.robot_requests:
            return
        idle = sorted(
            (r for r in self.model.robots if r.is_available),
            key=lambda r: r.unique_id,
        )
        if not idle:
            return
        for robot in idle:
            if not self.robot_requests:
                break
            rider = self.robot_requests.popleft()
            order = rider.order
            robot.assign(order)
            self._robot_by_ord_id[order.ord_id] = robot
            self.robot_dispatch_count += 1

    def step(self) -> None:
        # Keyed on "is there a fleet", not on the mode enum: `model` imports
        # this module, so importing `ROBOT_MODES` back would be circular, and an
        # empty fleet is the precise condition anyway. H0 builds no robots, so
        # this is a single falsy check and the H0 path stays bit-identical.
        #
        # Dispatch has NO tick lag: `_inject_riders` runs at the top of
        # `model.step`, before this, so a rider that entered the building this
        # tick joins the line and is assigned a robot in the same tick. (The
        # one-tick lag in H1 is elsewhere — the handoff start, because robots
        # step before riders. A4's hand chain needs both facts, so neither is
        # left to be inferred.)
        if self.model.robots:
            self._dispatch_robots()
