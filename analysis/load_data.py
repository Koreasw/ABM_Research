"""Data loader for BaeMin scenarios (framework §2.3 official schema).

JSON top-level keys: name, K, RIDERS, ORDERS, DIST.

ORDERS row: [ORD_ID, ORD_TIME, SHOP_LAT, SHOP_LON, DLV_LAT, DLV_LON,
             COOK_TIME, VOL, DLV_DEADLINE]
RIDERS row: [type, speed_mps, capa, var_cost, fixed_cost,
             service_time_sec, available_number]
DIST: (2K x 2K) road-network distance in meters.
      Indices 0..K-1 = pickup nodes, K..2K-1 = drop nodes.
      For order i, pickup-drop distance = DIST[i][K+i].
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np


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

    @classmethod
    def from_row(cls, row: list) -> Order:
        return cls(
            ord_id=int(row[0]),
            ord_time_sec=float(row[1]),
            shop_lat=float(row[2]),
            shop_lon=float(row[3]),
            dlv_lat=float(row[4]),
            dlv_lon=float(row[5]),
            cook_time_sec=float(row[6]),
            vol=int(row[7]),
            dlv_deadline_sec=float(row[8]),
        )


@dataclass(frozen=True)
class Rider:
    type: str            # BIKE / WALK / CAR
    speed_mps: float
    capa: int
    var_cost: float
    fixed_cost: float
    service_time_sec: float
    available_number: int

    @classmethod
    def from_row(cls, row: list) -> Rider:
        return cls(
            type=str(row[0]),
            speed_mps=float(row[1]),
            capa=int(row[2]),
            var_cost=float(row[3]),
            fixed_cost=float(row[4]),
            service_time_sec=float(row[5]),
            available_number=int(row[6]),
        )


@dataclass(frozen=True)
class Scenario:
    name: str
    K: int
    orders: list[Order]
    riders: list[Rider]
    dist: np.ndarray  # shape (2K, 2K), dtype float

    def __post_init__(self) -> None:
        expected = 2 * self.K
        if self.dist.shape != (expected, expected):
            raise ValueError(
                f"DIST shape {self.dist.shape} does not match 2K x 2K "
                f"with K={self.K} (expected ({expected}, {expected}))"
            )
        if len(self.orders) != self.K:
            raise ValueError(
                f"ORDERS count {len(self.orders)} does not match K={self.K}"
            )


def load_scenario(scenario_path: str | Path) -> Scenario:
    """Load a full scenario JSON into a Scenario dataclass."""
    path = Path(scenario_path)
    with path.open("r") as f:
        raw = json.load(f)
    orders = [Order.from_row(r) for r in raw["ORDERS"]]
    riders = [Rider.from_row(r) for r in raw["RIDERS"]]
    dist = np.asarray(raw["DIST"], dtype=float)
    return Scenario(
        name=str(raw["name"]),
        K=int(raw["K"]),
        orders=orders,
        riders=riders,
        dist=dist,
    )


def load_orders(scenario_path: str | Path) -> list[Order]:
    return load_scenario(scenario_path).orders


def load_riders(scenario_path: str | Path) -> list[Rider]:
    return load_scenario(scenario_path).riders


def load_dist(scenario_path: str | Path) -> np.ndarray:
    return load_scenario(scenario_path).dist


def pickup_drop_distance(scenario_path: str | Path) -> np.ndarray:
    """For each order i, return DIST[i][K+i] (pickup -> drop, meters)."""
    s = load_scenario(scenario_path)
    idx = np.arange(s.K)
    return s.dist[idx, idx + s.K]
