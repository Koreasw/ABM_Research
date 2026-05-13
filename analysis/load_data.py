"""Data loader for BaeMin scenarios (framework §2.3 official schema).

ORDERS row: [ORD_ID, ORD_TIME, SHOP_LAT, SHOP_LON, DLV_LAT, DLV_LON,
             COOK_TIME, VOL, DLV_DEADLINE]
RIDERS row: [type, speed_mps, capa, var_cost, fixed_cost,
             service_time_sec, available_number]
DIST: (K*2) x (K*2) road-network distance in meters.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Order:
    ord_id: int
    ord_time_sec: float
    shop_lat: float
    shop_lon: float
    dlv_lat: float
    dlv_lon: float
    cook_time_sec: float
    vol: int
    dlv_deadline_sec: float


@dataclass(frozen=True)
class Rider:
    type: str            # BIKE / WALK / CAR
    speed_mps: float
    capa: int
    var_cost: float
    fixed_cost: float
    service_time_sec: float
    available_number: int


def load_orders(scenario_path: Path) -> list[Order]:
    """Parse ORDERS array of a scenario JSON into Order dataclasses."""
    raise NotImplementedError


def load_riders(scenario_path: Path) -> list[Rider]:
    """Parse RIDERS array into Rider dataclasses."""
    raise NotImplementedError


def load_dist(scenario_path: Path) -> list[list[float]]:
    """Return DIST matrix as nested list (K*2 x K*2)."""
    raise NotImplementedError


def pickup_drop_distance(scenario_path: Path) -> list[float]:
    """For each order i, return DIST[i][K+i] (pickup -> drop, meters)."""
    raise NotImplementedError
