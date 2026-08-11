"""Replay loader — turn a K=50 scenario into BuildingOrder events (framework §4.2).

ORD_TIME is anchored to the lunch-peak start (default 11:30 = 41,400 s).
COOK_TIME / VOL / lead_time are passed through unchanged from the data.
Floor and office_id are assigned uniform-random with fixed seed.

Customers reside in floors 2..n_floors (1F is the lobby; v2 building has no
basement — plan_h0_revision.md §1.3). Floor assignment uses the scenario seed
so the same scenario + seed yields identical building placements across runs.

`load_replay` (above) is preserved unchanged for regression. `load_replay_v4`
(below) is the H0 baseline ABM's actual data source (etc/plan_abm_baseline_h0.md
Part B): it supersedes the uniform-random floor/office assignment with the
v4 floor-mapping join and adds the deterministic vertical-mode sample needed
by the ABM's ExternalRiderAgent.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from analysis.load_data import load_scenario, pickup_drop_distance
from analysis.rider_arrival_model import sample_rider_arrivals
from simulation.floor_demand import FloorDemandModel
from simulation.vertical_transport import VerticalTransportModel


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


@dataclass(frozen=True)
class BuildingOrderV4:
    """One order's H0 baseline replay record (etc/plan_abm_baseline_h0.md Part B).

    All time fields are absolute simulation seconds (anchored to start_time_sec).
    floor/office_id come from the v4 floor-mapping join (NOT uniform-random).
    vertical_mode is the pre-sampled elevator/stairs choice — calling
    VerticalTransportModel.sample_mode(ord_id, floor) directly reproduces it
    bit-for-bit (same RNG convention, no ABM-side re-derivation needed).

    horizontal_time_s is the *courier road-distance* travel-time component
    (DIST[i][K+i] / speed(rider_type), the same quantity that produced
    arrival_time_sec via analysis.rider_arrival_model.sample_rider_arrivals).
    This is deliberately distinct from analysis.travel_time_v4's
    horizontal_time_s (which uses the v4-anchor haversine reconstruction,
    horizontal_m) — see the implementation log for why the two must not be
    conflated when building the S6 strict lower bound.
    """

    ord_id: int
    arrival_time_sec: float      # rider building-lobby arrival (deterministic if sigma_eps=0)
    ord_time_abs_sec: float      # start + ORD_TIME (T_e2e anchor)
    deadline_abs_sec: float      # start + DLV_DEADLINE
    cook_time_sec: float
    vol: int
    floor: int                  # 2..10, from v4 floor mapping
    office_id: int              # 0..11, from v4 floor mapping
    rider_type: str              # BIKE / WALK / CAR
    w_R_krw_per_h: float
    vertical_mode: str           # 'elevator' | 'stairs'
    horizontal_time_s: float     # DIST[i][K+i] / speed(rider_type), noise-free component


def load_replay_v4(
    scenario_path: str | Path,
    mapping_path: str | Path,
    config: dict[str, Any],
    start_time_sec: float = 41400.0,
    seed: int = 42,
    sigma_eps: float = 0.0,
    throughput_per_rider_h: float = 50.0,
) -> list[BuildingOrderV4]:
    """Build the H0 baseline replay timeline from a scenario + its v4 floor mapping.

    Parameters
    ----------
    scenario_path : path to a BaeMin scenario JSON (e.g. data/data1/K50_1.json).
    mapping_path  : path to the matching {scenario}_floor_mapping_v4.json.
    config        : parsed baseline_10f.yaml (must contain a `vertical:` block).
    start_time_sec : lunch-peak anchor (default 41,400 s = 11:30).
    seed          : RNG seed for rider-type/noise sampling (passed through to
                    analysis.rider_arrival_model.sample_rider_arrivals).
    sigma_eps     : arrival-time noise. Default 0.0 (deterministic, per the
                    H0 baseline's interview-confirmed decision); 0.15 is the
                    calibrated value reserved for a future sensitivity stage.
    throughput_per_rider_h : passed through to the w_R wage calibration.

    Returns
    -------
    list[BuildingOrderV4] sorted by arrival_time_sec.

    Raises
    ------
    ValueError if the mapping's K doesn't match the scenario's K, or any
    scenario ord_id is absent from the mapping.
    """
    scenario = load_scenario(scenario_path)
    order_by_id = {o.ord_id: o for o in scenario.orders}

    mapping_raw = json.loads(Path(mapping_path).read_text())
    if mapping_raw["K"] != scenario.K:
        raise ValueError(
            f"floor mapping K={mapping_raw['K']} does not match scenario K={scenario.K}"
        )
    floor_by_ord: dict[int, int] = {}
    office_by_ord: dict[int, int] = {}
    for rec in mapping_raw["orders"]:
        floor_by_ord[rec["ord_id"]] = rec["floor"]
        office_by_ord[rec["ord_id"]] = rec["office_id"]
    missing = [ord_id for ord_id in order_by_id if ord_id not in floor_by_ord]
    if missing:
        raise ValueError(f"floor mapping missing ord_id(s): {sorted(missing)}")

    # Reuse sample_rider_arrivals verbatim — no RNG re-derivation here, so the
    # type/eps consumption order (type vector first, then eps vector) is
    # inherited automatically rather than re-encoded (plan §"주의점" #1).
    rider_events = sample_rider_arrivals(
        scenario_path,
        seed=seed,
        sigma_eps=sigma_eps,
        start_time_sec=start_time_sec,
        throughput_per_rider_h=throughput_per_rider_h,
    )

    vt = VerticalTransportModel.from_config(config)

    events: list[BuildingOrderV4] = []
    for re in rider_events:
        order = order_by_id[re.order_id]
        floor = floor_by_ord[re.order_id]
        horizontal_time_s = (
            re.t_arrival_sec - start_time_sec - order.ord_time_sec - order.cook_time_sec
        )
        events.append(
            BuildingOrderV4(
                ord_id=re.order_id,
                arrival_time_sec=re.t_arrival_sec,
                ord_time_abs_sec=start_time_sec + order.ord_time_sec,
                deadline_abs_sec=re.deadline_sec,
                cook_time_sec=order.cook_time_sec,
                vol=re.vol,
                floor=floor,
                office_id=office_by_ord[re.order_id],
                rider_type=re.rider_type,
                w_R_krw_per_h=re.time_cost_per_sec * 3600.0,
                vertical_mode=vt.sample_mode(re.order_id, floor),
                horizontal_time_s=horizontal_time_s,
            )
        )
    events.sort(key=lambda e: e.arrival_time_sec)
    return events


# --------------------------------------------------------------------------
# v5 dynamic-pool dispatch timeline (etc/plan_rider_pool_dynamic.md Part B)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class BuildingOrderV5(BuildingOrderV4):
    """BuildingOrderV4 + dynamic-pool dispatch provenance.

    Assembled at runtime by BuildingHandoffModel when the pool grants a rider
    (NOT at load time). Subclassing keeps ExternalRiderAgent's contract
    unchanged — the FSM reads only V4 fields.
    """

    ready_time_sec: float        # start + ORD_TIME + COOK (dispatch request)
    dispatch_time_sec: float     # when the pool actually granted a rider
    rider_wait_sec: float        # dispatch - ready (>0 iff queued for stock)
    was_fallback: bool           # cost-optimal type exhausted, pricier used
    dist_m: float                # shop->drop road distance


@dataclass(frozen=True)
class DispatchOrder:
    """One order's dispatch request record for the dynamic rider-pool path.

    Deliberately carries NO rider_type / arrival_time: those are decided at
    runtime by simulation.rider_pool.RiderPool when the order becomes ready
    (food cooked), because they depend on the time-varying pool state.
    Everything type-independent (floor mapping join, vertical mode) is still
    precomputed here, so the v4 RNG conventions for floor/mode survive.
    """

    ord_id: int
    ready_time_sec: float        # start + ORD_TIME + COOK_TIME (dispatch request)
    ord_time_abs_sec: float      # start + ORD_TIME (T_e2e anchor)
    deadline_abs_sec: float      # start + DLV_DEADLINE
    cook_time_sec: float
    vol: int
    dist_m: float                # DIST[i][K+i] shop->drop road distance
    floor: int                   # from v4 floor mapping
    office_id: int               # from v4 floor mapping
    vertical_mode: str           # 'elevator' | 'stairs' (ord_id-keyed, type-free)


def load_dispatch_v5(
    scenario_path: str | Path,
    mapping_path: str | Path,
    config: dict[str, Any],
    start_time_sec: float = 41400.0,
) -> list[DispatchOrder]:
    """Build the dynamic-pool dispatch timeline from a scenario + v4 mapping.

    Returns DispatchOrder records sorted by ready_time_sec. The floor-mapping
    join duplicates load_replay_v4's block on purpose: v4 is the frozen
    regression path and must not be refactored (plan §주의점 1).

    Raises ValueError on K mismatch or missing ord_id, same as v4.
    """
    scenario = load_scenario(scenario_path)
    order_by_id = {o.ord_id: o for o in scenario.orders}

    mapping_raw = json.loads(Path(mapping_path).read_text())
    if mapping_raw["K"] != scenario.K:
        raise ValueError(
            f"floor mapping K={mapping_raw['K']} does not match scenario K={scenario.K}"
        )
    floor_by_ord: dict[int, int] = {}
    office_by_ord: dict[int, int] = {}
    for rec in mapping_raw["orders"]:
        floor_by_ord[rec["ord_id"]] = rec["floor"]
        office_by_ord[rec["ord_id"]] = rec["office_id"]
    missing = [ord_id for ord_id in order_by_id if ord_id not in floor_by_ord]
    if missing:
        raise ValueError(f"floor mapping missing ord_id(s): {sorted(missing)}")

    pdd_m = pickup_drop_distance(scenario_path)  # length K, order-aligned
    vt = VerticalTransportModel.from_config(config)

    events: list[DispatchOrder] = []
    for i, order in enumerate(scenario.orders):
        floor = floor_by_ord[order.ord_id]
        events.append(
            DispatchOrder(
                ord_id=order.ord_id,
                ready_time_sec=start_time_sec + order.ord_time_sec + order.cook_time_sec,
                ord_time_abs_sec=start_time_sec + order.ord_time_sec,
                deadline_abs_sec=start_time_sec + order.dlv_deadline_sec,
                cook_time_sec=order.cook_time_sec,
                vol=order.vol,
                dist_m=float(pdd_m[i]),
                floor=floor,
                office_id=office_by_ord[order.ord_id],
                vertical_mode=vt.sample_mode(order.ord_id, floor),
            )
        )
    events.sort(key=lambda e: e.ready_time_sec)
    return events


# --------------------------------------------------------------------------
# profile floor demand dispatch timeline (etc/demand_mapping.md 단계 2·3)
# --------------------------------------------------------------------------


def load_dispatch_profile(
    scenario_path: str | Path,
    config: dict[str, Any],
    profile: str | None = None,
    floor_seed: int = 42,
    start_time_sec: float = 41400.0,
) -> list[DispatchOrder]:
    """Build the dispatch timeline with floor/office from the profile demand model.

    Same DispatchOrder record shape and field semantics as load_dispatch_v5,
    minus the floor-mapping-file join: floor and office_id instead come from
    an independent categorical draw over a building population-density
    profile (simulation.floor_demand.FloorDemandModel, per
    etc/demand_mapping.md 단계 2·3 — 2D-independent of the scenario's
    distance data). Every (floor, office_id, vertical_mode) assignment is
    reproducible from (profile, floor_seed) alone via
    simulation.floor_demand.rederive_profile_assignment, with no mapping
    file needed. load_dispatch_v5 remains the frozen mapping-file path and
    is untouched by this function.

    Parameters
    ----------
    scenario_path : path to a BaeMin scenario JSON (e.g. data/data1/K50_1.json).
    config        : parsed baseline_10f.yaml (must contain `demand:` and
                    `vertical:` blocks).
    profile       : demand.floor_profiles key; None uses demand.default_profile.
    floor_seed    : seed for the profile floor/office draw (independent of
                    the mode_seed / rng_seed streams; see floor_demand.py's
                    module docstring for the stream-family separation).
    start_time_sec : lunch-peak anchor (default 41,400 s = 11:30).

    Returns
    -------
    list[DispatchOrder] sorted by ready_time_sec.

    Raises
    ------
    ValueError if `profile` (or demand.default_profile when profile=None)
    is not a key of config["demand"]["floor_profiles"].
    """
    scenario = load_scenario(scenario_path)
    pdd_m = pickup_drop_distance(scenario_path)  # length K, order-aligned

    fd = FloorDemandModel.from_config(config, profile, floor_seed=floor_seed)
    vt = VerticalTransportModel.from_config(config)

    events: list[DispatchOrder] = []
    for i, order in enumerate(scenario.orders):
        floor, office_id = fd.sample(order.ord_id)
        events.append(
            DispatchOrder(
                ord_id=order.ord_id,
                ready_time_sec=start_time_sec + order.ord_time_sec + order.cook_time_sec,
                ord_time_abs_sec=start_time_sec + order.ord_time_sec,
                deadline_abs_sec=start_time_sec + order.dlv_deadline_sec,
                cook_time_sec=order.cook_time_sec,
                vol=order.vol,
                dist_m=float(pdd_m[i]),
                floor=floor,
                office_id=office_id,
                vertical_mode=vt.sample_mode(order.ord_id, floor),
            )
        )
    events.sort(key=lambda e: e.ready_time_sec)
    return events
