"""PedestrianAgent — background EV congestion generator (framework §5.6, §6.2).

Not a dependent variable; exists to endogenize EV wait times. H0 baseline
uses a constant lunch-peak Poisson stream (plan_abm_baseline_h0.md): 'down'
trips (office floor → ground-side endpoint) and 'up' trips (endpoint → office
floor), all via elevator (pedestrian.elevator_only: true).

The ground-side endpoint is the lobby (1F) or a basement (B1/B2) drawn per
trip from pedestrian.ground_split (plan_h0_revision.md §1.6) — occupants
riding down to parking are what lengthens the rides and loads the cars. Only
the lobby has walk-in zones; a basement trip starts/ends at that level's
floor_center, since basements carry no offices or corridor.

FSM: WALK_TO_EV → WAIT_EV → RIDING → WALK_OFF → done (remove).
"""

from __future__ import annotations

from mesa import Agent

from simulation.agents.walker import GraphWalker
from simulation.space import floor_label


class PedestrianAgent(Agent, GraphWalker):
    WALK_TO_EV = "walk_to_ev"
    WAIT_EV = "wait_ev"
    RIDING = "riding"
    WALK_OFF = "walk_off"

    kind = "pedestrian"

    def __init__(
        self,
        model,  # noqa: ANN001
        from_floor: int,
        to_floor: int,
        speed_mps: float = 1.2,
    ) -> None:
        super().__init__(model)
        self.from_floor = from_floor
        self.to_floor = to_floor
        self.speed_mps = speed_mps
        self._init_walker()

        self.ev_dest_floor = to_floor
        self.ev_wait_started_sec: float = 0.0
        self.ev_wait_sec: float | None = None
        self.spawned_at_sec: float = model.clock_sec
        self._ev = None

        # spawn point and EV choice
        self.node = self._ground_node(from_floor)
        self._ev = model.control.choose_elevator(from_floor, to_floor)
        self.state = self.WALK_TO_EV
        self.set_walk_target(f"ev_{self._ev.ev_id}_{floor_label(from_floor)}")

    # --------------------------------------------------- passenger protocol

    def on_board(self, ev) -> None:  # noqa: ANN001
        self.ev_wait_sec = self.model.clock_sec - self.ev_wait_started_sec
        self.state = self.RIDING

    def on_alight(self, ev, floor: int) -> None:  # noqa: ANN001
        self.node = f"ev_{ev.ev_id}_{floor_label(floor)}"
        self.state = self.WALK_OFF
        self.set_walk_target(self._ground_node(floor))

    @staticmethod
    def _ground_node(floor: int) -> str:
        """Where a pedestrian enters/leaves the graph on `floor`.

        1F has the lobby zones; every other level (office floors and the
        basements alike) is entered at its floor_center hub.
        """
        return "lobby_entry" if floor == 1 else f"floor_{floor_label(floor)}_center"

    # ------------------------------------------------------------------ step

    def step(self) -> None:
        if self.state == self.WALK_TO_EV:
            if self.walk_tick(self.model.dt):
                self.state = self.WAIT_EV
                self.ev_wait_started_sec = self.model.clock_sec
                self._ev.register_hall_call(self.from_floor, self)
        elif self.state == self.WALK_OFF:
            if self.walk_tick(self.model.dt):
                self.model.ped_done_log.append(
                    {
                        "spawned_at_sec": self.spawned_at_sec,
                        "from_floor": self.from_floor,
                        "to_floor": self.to_floor,
                        "ev_wait_sec": self.ev_wait_sec,
                        "done_at_sec": self.model.clock_sec,
                    }
                )
                self.remove()
        # WAIT_EV / RIDING: elevator drives the transitions
