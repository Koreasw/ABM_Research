"""ElevatorAgent (framework §5.3, §6.2).

Physics: accel 1.0 m/s^2, max speed 2.5 m/s, door open/close 4 s.
EV1-3 are people-only; EV4 is shared (robot capacity reduces people slots).
Social acceptance alpha governs people's avoidance of EV4 with robot inside.
"""

from __future__ import annotations

from mesa import Agent


class ElevatorAgent(Agent):
    def __init__(
        self,
        model,  # noqa: ANN001
        ev_id: str,                      # EV1 / EV2 / EV3 / EV4
        shared_with_robot: bool = False,
        capacity_people: int = 10,
        accel_mps2: float = 1.0,
        max_speed_mps: float = 2.5,
        door_open_close_sec: float = 4.0,
        social_acceptance_alpha: float = 0.1,
    ) -> None:
        super().__init__(model)
        self.ev_id = ev_id
        self.shared_with_robot = shared_with_robot
        self.capacity_people = capacity_people
        self.accel_mps2 = accel_mps2
        self.max_speed_mps = max_speed_mps
        self.door_open_close_sec = door_open_close_sec
        self.social_acceptance_alpha = social_acceptance_alpha
        self.current_floor: int = 1
        self.passenger_count: int = 0

    def step(self) -> None:
        raise NotImplementedError
