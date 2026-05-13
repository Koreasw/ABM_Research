"""ControlSystemAgent — central dispatcher (framework §6.2).

Mode-aware routing:
  H0: external rider goes directly to customer via EV1-4
  H1: dispatch nearest idle robot to handoff_counter when rider arrives
  H2: rider joins queue; assign next idle robot
  H3: notify idle robot when rider docks the locker
"""

from __future__ import annotations

from collections import deque

from mesa import Agent


class ControlSystemAgent(Agent):
    def __init__(self, model, policy: str = "fcfs") -> None:  # noqa: ANN001
        super().__init__(model)
        self.policy = policy
        self.order_queue: deque = deque()

    def step(self) -> None:
        raise NotImplementedError
