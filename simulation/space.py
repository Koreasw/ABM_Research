"""Building space — networkx graph of floors, corridors, elevators, lobby zones.

Framework §5.1-5.4. Baseline 5F (B1F + 1F + 2-5F), extended 10F under E3.
Corridors discretized at 1 m for congestion modeling.
Lobby zone (1F) hosts handoff_counter / queue_zone / locker_bank /
robot_pickup_zone / direct_corridor.
"""

from __future__ import annotations

import networkx as nx


def build_building_graph(n_floors: int = 5, corridor_len_m: float = 100.0) -> nx.Graph:
    """Construct the building network graph with floor/corridor/EV/lobby nodes."""
    raise NotImplementedError


def add_lobby_handoff_zones(g: nx.Graph, locker_compartments: int = 8) -> nx.Graph:
    """Add lobby_entry, handoff_counter, queue_zone, locker_bank, robot_pickup_zone."""
    raise NotImplementedError
