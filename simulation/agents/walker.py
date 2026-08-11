"""GraphWalker mixin — distance-accumulation walking on the building graph.

etc/plan_abm_baseline_h0.md §"전역 설계 결정": agents hold a path (node list +
cumulative distances) and a float `progress_m`; each tick advances
`progress_m += speed * dt` and the current node is the last one at or behind
the accumulated distance. This avoids per-node rounding of speeds like
1.2 m/s on the 1 m-resolution corridor graph, so walked distances and times
stay exact (required by the S6 strict lower-bound check).

Walk paths use walk edges only — EV edges are excluded (vertical movement is
owned by ElevatorAgent / the stair timer, never by a walking leg).
"""

from __future__ import annotations

import networkx as nx


def shortest_walk_only_path(
    g: nx.MultiDiGraph, source: str, target: str
) -> tuple[list[str], float]:
    """Shortest path using walk edges only (EV edges excluded entirely).

    Unlike simulation.space.shortest_walk_path (which treats EV edges as
    zero-cost vertical links), this restricts the search to physically
    walkable edges, so a walking leg can never silently jump floors.
    """

    def _walk_weight(u: str, v: str, edge_data: dict) -> float | None:
        best: float | None = None
        for attrs in edge_data.values():
            if attrs.get("type") == "walk":
                w = float(attrs["distance_m"])
                if best is None or w < best:
                    best = w
        return best  # None → edge ignored by networkx

    path: list[str] = nx.shortest_path(g, source=source, target=target, weight=_walk_weight)
    total = 0.0
    for u, v in zip(path[:-1], path[1:]):
        edge_data = g.get_edge_data(u, v)
        best = min(
            float(attrs["distance_m"])
            for attrs in edge_data.values()
            if attrs.get("type") == "walk"
        )
        total += best
    return path, total


class GraphWalker:
    """Mixin for agents that walk on the building graph.

    Host class must provide:
        self.model  — with .graph (networkx MultiDiGraph)
        self.node   — current node name (str)
        self.speed_mps — walking speed
    Provides:
        set_walk_target(target) / walk_tick(dt) -> bool / walked_m
    """

    node: str
    speed_mps: float

    def _init_walker(self) -> None:
        self._path: list[str] = []
        self._cumdist: list[float] = []
        self._progress_m: float = 0.0
        self._path_total_m: float = 0.0
        self.walked_m: float = 0.0

    def set_walk_target(self, target: str) -> None:
        """Plan a walk-only path from the current node to `target`."""
        if target == self.node:
            self._path = [self.node]
            self._cumdist = [0.0]
            self._progress_m = 0.0
            self._path_total_m = 0.0
            return
        path, total = shortest_walk_only_path(self.model.graph, self.node, target)
        cum = [0.0]
        for u, v in zip(path[:-1], path[1:]):
            edge_data = self.model.graph.get_edge_data(u, v)
            step = min(
                float(attrs["distance_m"])
                for attrs in edge_data.values()
                if attrs.get("type") == "walk"
            )
            cum.append(cum[-1] + step)
        self._path = path
        self._cumdist = cum
        self._progress_m = 0.0
        self._path_total_m = total

    @property
    def walk_target(self) -> str | None:
        return self._path[-1] if self._path else None

    @property
    def walk_fraction(self) -> float:
        """Progress along the current path in [0, 1] (for visualization)."""
        if self._path_total_m <= 0.0:
            return 1.0
        return min(self._progress_m / self._path_total_m, 1.0)

    def walk_tick(self, dt: float) -> bool:
        """Advance one tick along the planned path. Returns True on arrival."""
        if not self._path:
            return True
        if self._path_total_m <= 0.0:
            self.node = self._path[-1]
            self._path = []
            return True
        remaining = self._path_total_m - self._progress_m
        advance = self.speed_mps * dt
        if advance >= remaining:
            # arrive exactly: credit only the true remaining distance
            self.walked_m += remaining
            self.node = self._path[-1]
            self._path = []
            self._progress_m = self._path_total_m
            return True
        self._progress_m += advance
        self.walked_m += advance
        # current node = last node at or behind progress
        idx = 0
        for i, c in enumerate(self._cumdist):
            if c <= self._progress_m:
                idx = i
            else:
                break
        self.node = self._path[idx]
        return False
