"""Replay loader — turn a K=50 scenario into BuildingOrder events (framework §4.2).

ORD_TIME is anchored to the lunch-peak start (default 11:30 = 41,400 s).
COOK_TIME / VOL / lead_time are passed through unchanged from the data.
Floor and office_id are assigned uniform-random with fixed seed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BuildingOrder:
    arrival_time_sec: float
    cook_time_sec: float
    vol: int
    lead_time_sec: float
    floor: int
    office_id: int
    ord_id: int


def load_replay(
    scenario_path: Path,
    start_time_sec: float = 11.5 * 3600.0,
    rng_seed: int = 42,
    n_floors: int = 5,
    offices_per_floor: int = 10,
) -> list[BuildingOrder]:
    """Convert one K=50 scenario into a lunch-peak BuildingOrder sequence."""
    raise NotImplementedError
