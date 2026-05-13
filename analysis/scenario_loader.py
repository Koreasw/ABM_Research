"""Replay loader — turn a K=50 scenario into BuildingOrder events (framework §4.2).

ORD_TIME is anchored to the lunch-peak start (default 11:30 = 41,400 s).
COOK_TIME / VOL / lead_time are passed through unchanged from the data.
Floor and office_id are assigned uniform-random with fixed seed.

In a 5F office building, customers reside in floors 2..n_floors (1F is the
lobby, B1F hosts charging / cafe). Floor assignment uses the scenario seed
so the same scenario + seed yields identical building placements across runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from analysis.load_data import load_scenario


@dataclass(frozen=True)
class BuildingOrder:
    arrival_time_sec: float   # external order time anchored to start_time_sec
    cook_time_sec: float
    vol: int
    lead_time_sec: float
    floor: int                # 2..n_floors (1F is lobby)
    office_id: int            # 0..offices_per_floor-1
    ord_id: int


def load_replay(
    scenario_path: str | Path,
    start_time_sec: float = 11.5 * 3600.0,
    rng_seed: int = 42,
    n_floors: int = 5,
    offices_per_floor: int = 10,
) -> list[BuildingOrder]:
    """Convert one scenario into a lunch-peak BuildingOrder sequence.

    Parameters
    ----------
    scenario_path : path to a BaeMin scenario JSON.
    start_time_sec : simulation second at which the first lunch-peak event
                     is anchored (default 11:30 = 41,400 s).
    rng_seed : seed for floor / office_id assignment.
    n_floors : total floors above ground (1F lobby + 2..n_floors offices).
    offices_per_floor : number of offices per office floor.

    Returns
    -------
    list[BuildingOrder] sorted by arrival_time_sec.
    """
    if n_floors < 2:
        raise ValueError(f"n_floors must be >= 2 (need at least one office floor), got {n_floors}")
    if offices_per_floor < 1:
        raise ValueError(f"offices_per_floor must be >= 1, got {offices_per_floor}")

    scenario = load_scenario(scenario_path)
    rng = np.random.default_rng(rng_seed)

    customer_floors = np.arange(2, n_floors + 1)
    floors = rng.choice(customer_floors, size=scenario.K, replace=True)
    offices = rng.integers(0, offices_per_floor, size=scenario.K)

    events = []
    for i, order in enumerate(scenario.orders):
        events.append(
            BuildingOrder(
                arrival_time_sec=start_time_sec + order.ord_time_sec,
                cook_time_sec=order.cook_time_sec,
                vol=order.vol,
                lead_time_sec=order.dlv_deadline_sec - order.ord_time_sec,
                floor=int(floors[i]),
                office_id=int(offices[i]),
                ord_id=order.ord_id,
            )
        )
    events.sort(key=lambda e: e.arrival_time_sec)
    return events
