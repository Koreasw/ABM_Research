"""ElevatorAgent (framework §5.3, §6.2) — SCAN dispatch, kinematic movement.

States: IDLE / MOVING / DOORS. Hall calls are *assigned* (ControlSystemAgent
picks the EV at request time); each floor holds a FIFO deque of waiting
passengers. Car calls are the destinations of passengers on board.

SCAN policy: keep the current direction while any call (hall or car) lies
ahead; otherwise reverse; otherwise go IDLE in place (no parking floor).
Commit-to-next-stop: once MOVING, the segment target is fixed — calls that
arrive mid-flight are considered at the next decision point (documented
simplification, plan §D / 리스크 #4).

Passenger protocol (ExternalRiderAgent / PedestrianAgent / RobotAgent implement it):
    .ev_dest_floor: int          — destination floor
    .ev_wait_started_sec: float  — set when the hall call was registered
    .kind: str                   — 'rider' | 'pedestrian' | 'robot' (boarding-log split)
    .on_board(ev) / .on_alight(ev, floor)

Heterogeneous capacity (A1, design freeze R0-1·R0-2). A robot occupies roughly
four person-slots, so a car's people capacity depends on whether a robot is
aboard: 15 normally, 11 with a robot. Two rules:

    R0-1  at most ONE robot per car (robots never ride together)
    R0-2  a robot may board only a robot-shareable car, and only while
          people_aboard <= capacity_people_with_robot

Refusals are **measurement, not failure** — `robot_board_denied` counts them.
⚠️ In the v2 corpus a deny is expected to be *rare or absent*: with four cars,
ticks carrying >= 12 people are uncommon, so `robot_board_denied == 0` is NOT
evidence that the refusal path works. `tests/test_a1_robot.py` drives it with a
synthetically stuffed car, which may be the only execution of that branch.

H0 bit-identity: with no robots anywhere, `robot_aboard` is always False and
`people_aboard == len(passengers)`, so every predicate below collapses to the
pre-A1 `len(self.passengers) >= self.capacity_people`.
"""

from __future__ import annotations

from collections import deque

from mesa import Agent

from simulation.space import floor_rank


class ElevatorAgent(Agent):
    IDLE = "idle"
    MOVING = "moving"
    DOORS = "doors"

    def __init__(
        self,
        model,  # noqa: ANN001
        ev_id: str,                      # EV1·EV2 people-only / EV3·EV4 shared
        shared_with_robot: bool = False,
        capacity_people: int = 15,
        door_open_close_sec: float = 4.0,
        capacity_people_with_robot: int = 11,
    ) -> None:
        super().__init__(model)
        self.ev_id = ev_id
        self.shared_with_robot = shared_with_robot
        self.capacity_people = capacity_people
        # A1 (R0-2): people limit while a robot rides. Only ever consulted when
        # a robot is actually aboard, so H0 never reads it.
        self.capacity_people_with_robot = capacity_people_with_robot
        self.door_open_close_sec = door_open_close_sec

        self.state: str = self.IDLE
        self.current_floor: int = 1        # floor *label* (-1 = B1, 1..N above)
        # Interpolated vertical position while MOVING (viz/KPI), in floor-RANK
        # units, not labels: labels skip 0 so they cannot be interpolated across
        # ground level (plan §1.6). Above ground rank == label, so every value
        # this field took before basements existed is unchanged.
        self.position_floor: float = 1.0
        self.direction: int = 0            # +1 up / -1 down / 0 uncommitted
        self.hall_calls: dict[int, deque] = {}
        self.car_calls: set[int] = set()
        self.passengers: list = []

        self._move_from: int = 1
        self._move_to: int = 1
        self._move_eta: float = 0.0
        self._move_total: float = 1.0
        self._door_timer: float = 0.0

        self.busy_ticks: int = 0
        self.boarding_log: list[dict] = []   # {kind, wait_sec, floor, t_board_sec}
        self.alight_count: int = 0           # S6 check #6: boards == alights
        self.capacity_violations: int = 0    # S6 check #6 — must stay 0
        # A1: door cycles at which a direction-compatible robot was at the head
        # of the queue but could not board (car full of people, or another robot
        # already aboard). Measurement, not failure — see module docstring.
        self.robot_board_denied: int = 0

    # ------------------------------------------------------------------ calls

    def register_hall_call(self, floor: int, passenger) -> None:  # noqa: ANN001
        """Queue a passenger waiting at `floor` for this EV (FIFO per floor)."""
        self.hall_calls.setdefault(floor, deque()).append(passenger)
        # V-EVSEL: pure-observation hook (None when off -> bit-identical)
        if self.model.evsel_events is not None:
            self.model._evsel_on_register(self, floor, passenger)

    def pending_stop_count(self) -> int:
        hall_floors = {f for f, q in self.hall_calls.items() if q}
        return len(self.car_calls | hall_floors)

    def queue_length(self) -> int:
        return sum(len(q) for q in self.hall_calls.values())

    @property
    def passenger_count(self) -> int:
        return len(self.passengers)

    # --------------------------------------------------- heterogeneous capacity

    @property
    def robot_aboard(self) -> bool:
        return any(p.kind == "robot" for p in self.passengers)

    @property
    def people_aboard(self) -> int:
        return sum(1 for p in self.passengers if p.kind != "robot")

    def _people_limit(self, *, with_robot: bool) -> int:
        return self.capacity_people_with_robot if with_robot else self.capacity_people

    def can_board(self, p) -> bool:  # noqa: ANN001
        """May `p` board right now, ignoring direction (the caller checks that)?

        For a person this is the pre-A1 rule with the limit lowered while a
        robot rides. For a robot it is R0-1 + R0-2 plus the hard restriction
        that people-only cars (EV1·EV2) never take one — the defensive half of
        gate B3, enforced here rather than only asserted afterwards.
        """
        if p.kind == "robot":
            if not self.shared_with_robot:
                return False
            if self.robot_aboard:                      # R0-1: one robot per car
                return False
            return self.people_aboard <= self.capacity_people_with_robot
        return self.people_aboard < self._people_limit(with_robot=self.robot_aboard)

    def _capacity_violated(self) -> bool:
        """Post-boarding invariant (feeds `capacity_violations`, must stay 0)."""
        n_robots = sum(1 for p in self.passengers if p.kind == "robot")
        if n_robots > 1:
            return True
        return self.people_aboard > self._people_limit(with_robot=n_robots == 1)

    # ------------------------------------------------------------------- step

    def step(self) -> None:
        dt = self.model.dt
        if self.state == self.DOORS:
            self.busy_ticks += 1
            self._door_timer -= dt
            if self._door_timer <= 0.0:
                self._decide_next()
        elif self.state == self.MOVING:
            self.busy_ticks += 1
            self._move_eta -= dt
            frac = 1.0 - max(self._move_eta, 0.0) / self._move_total
            r_from, r_to = floor_rank(self._move_from), floor_rank(self._move_to)
            self.position_floor = r_from + (r_to - r_from) * frac
            if self._move_eta <= 0.0:
                self.current_floor = self._move_to
                self.position_floor = float(floor_rank(self._move_to))
                self._open_doors()
        else:  # IDLE
            if self._candidate_floors():
                self.busy_ticks += 1
                if self.current_floor in self._candidate_floors():
                    self._open_doors()
                else:
                    self._decide_next()

    # -------------------------------------------------------------- internals

    def _candidate_floors(self) -> set[int]:
        return self.car_calls | {f for f, q in self.hall_calls.items() if q}

    def _open_doors(self) -> None:
        """One door cycle at current_floor: alight, then board (FIFO,
        direction-compatible, capacity-capped)."""
        self.state = self.DOORS
        self._door_timer = self.door_open_close_sec
        floor = self.current_floor

        # 1) alight
        for p in [p for p in self.passengers if p.ev_dest_floor == floor]:
            self.passengers.remove(p)
            self.alight_count += 1
            p.on_alight(self, floor)
        self.car_calls.discard(floor)

        # 2) service direction for boarding: keep the committed direction only
        #    if something still lies ahead; otherwise let the first boarder set it
        direction = self.direction
        if direction != 0:
            ahead_calls = any((c - floor) * direction > 0 for c in self._candidate_floors())
            ahead_pax = any((p.ev_dest_floor - floor) * direction > 0 for p in self.passengers)
            if not ahead_calls and not ahead_pax:
                direction = 0

        # 3) board FIFO from this floor's queue
        queue = self.hall_calls.get(floor)
        if queue:
            still_waiting: deque = deque()
            while queue:
                p = queue.popleft()
                p_dir = 1 if p.ev_dest_floor > floor else -1
                if direction == 0:
                    direction = p_dir
                if p_dir != direction:
                    still_waiting.append(p)
                    continue
                if not self.can_board(p):
                    # Split from the direction test so a robot turned away for
                    # *occupancy* is counted, while one merely facing the wrong
                    # way is not — the deny metric must mean "the car was full",
                    # not "the car was going the other way".
                    if p.kind == "robot":
                        self.robot_board_denied += 1
                    still_waiting.append(p)
                    continue
                self.passengers.append(p)
                if self._capacity_violated():
                    self.capacity_violations += 1
                self.car_calls.add(p.ev_dest_floor)
                self.boarding_log.append(
                    {
                        "kind": p.kind,
                        "wait_sec": self.model.clock_sec - p.ev_wait_started_sec,
                        "floor": floor,
                        "t_board_sec": self.model.clock_sec,
                    }
                )
                # V-EVSEL: backfill realized wait (None when off -> bit-identical)
                if self.model.evsel_events is not None:
                    self.model._evsel_on_board(p)
                p.on_board(self)
            if still_waiting:
                self.hall_calls[floor] = still_waiting
            else:
                del self.hall_calls[floor]
        self.direction = direction

    def _decide_next(self) -> None:
        """SCAN target selection after a door cycle (or from IDLE)."""
        floor = self.current_floor
        candidates = self._candidate_floors()
        candidates.discard(floor)

        if not candidates:
            if self.hall_calls.get(floor):
                # waiters here couldn't board last cycle (direction mismatch,
                # and that direction is now exhausted): reopen uncommitted
                self.direction = 0
                self._open_doors()
                return
            self.state = self.IDLE
            self.direction = 0
            return

        # Distance is measured in floor RANK (storeys), never in labels: with
        # basements the label gap across ground level is one too wide, which
        # would mis-rank a basement stop against an above-ground one (plan
        # §1.6). Direction tests below stay on labels — rank is monotone in the
        # label, so the sign of the comparison is identical.
        here = floor_rank(floor)
        if self.direction != 0:
            ahead = [c for c in candidates if (c - floor) * self.direction > 0]
            if not ahead:
                self.direction = -self.direction
                ahead = [c for c in candidates if (c - floor) * self.direction > 0]
            next_stop = min(ahead, key=lambda c: abs(floor_rank(c) - here))
        else:
            next_stop = min(candidates, key=lambda c: abs(floor_rank(c) - here))
            self.direction = 1 if next_stop > floor else -1

        self._move_from = floor
        self._move_to = next_stop
        self._move_total = max(
            self.model.kin.travel_time_sec(floor, next_stop), self.model.dt
        )
        self._move_eta = self._move_total
        self.state = self.MOVING
