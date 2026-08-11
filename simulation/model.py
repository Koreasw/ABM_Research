"""BuildingHandoffModel — Mesa Model with 4-mode dispatcher (framework §6).

Handoff mode H in {H0 direct, H1 sync, H2 queued, H3 locker} is set at
construction and drives the ControlSystemAgent routing. This baseline stage
implements H0 (rider direct delivery) only; H1~H3 raise NotImplementedError
at construction (extension point, etc/plan_abm_baseline_h0.md).

Tick order (framework §6.3):
  clock += dt → ① inject riders ② spawn pedestrians ③ Customer ④ Pedestrian
  ⑤ ControlSystem ⑥ ExternalRider ⑦ Elevator ⑧ BuildingManager ⑨ collect
  → termination check.

Time: `clock_sec` (absolute sim seconds, anchored at lunch-peak 41,400 s) is
the single source of truth; Mesa's auto-incremented `Model.steps` is not used
for timing. dt = simulation.tick_sec (1.0 s).
"""

from __future__ import annotations

import heapq
import threading
from collections import deque
from enum import Enum
from pathlib import Path

import numpy as np
from mesa import DataCollector, Model

from analysis.rider_arrival_model import (
    _sample_lognormal_unbiased,
    compute_w_R_krw_per_h,
)
from analysis.scenario_loader import (
    BuildingOrderV5,
    load_dispatch_profile,
    load_dispatch_v5,
    load_replay_v4,
)
from simulation.agents.building_manager import BuildingManagerAgent
from simulation.agents.control_system import ControlSystemAgent
from simulation.agents.customer import CustomerAgent
from simulation.agents.elevator import ElevatorAgent
from simulation.agents.external_rider import ExternalRiderAgent
from simulation.agents.handoff_rider import HandoffRiderAgent
from simulation.agents.pedestrian import PedestrianAgent
from simulation.agents.robot import HOME_NODE as ROBOT_HOME_NODE
from simulation.agents.robot import REPORT_BUCKETS, RobotAgent, RobotState
from simulation.config_params import HandoffParams, PedDecay, RobotParams
from simulation.elevator_physics import ElevatorKinematics
from simulation.floor_demand import FloorDemandModel
from simulation.rider_pool import RiderPool
from simulation.space import (
    add_lobby_handoff_zones,
    build_from_config,
    floor_rank,
    load_config,
)
from simulation.vertical_transport import VerticalTransportModel

ROOT = Path(__file__).resolve().parent.parent

# rider FSM states grouped by activity, for the live state-decomposition
# series (riders_walking + ... + riders_in_service == riders_in_building)
#
# A2: the H1 rider's states are folded into the same five buckets so the
# identity keeps closing in both modes without the series changing shape —
# `walk_to_counter` is walking, `wait_robot` is a wait (of a different kind, but
# the decomposition is about where the dwell sits, and A3 reports the robot wait
# separately), and `handoff` is this mode's service. H1 never uses the stairs or
# the EV as a rider, so those two series are simply flat at 0.
_WALK_STATES = frozenset(
    {"walk_to_vert", "walk_to_office", "walk_back", "walk_to_exit",
     "walk_to_counter"}
)
_WAIT_STATES = frozenset({"wait_ev_up", "wait_ev_down", "wait_robot"})
_RIDE_STATES = frozenset({"riding_up", "riding_down"})
_STAIR_STATES = frozenset({"climb_stairs", "descend_stairs"})
_SERVICE_STATES = frozenset({"service", "handoff"})


class HandoffMode(str, Enum):
    H0_DIRECT = "h0_direct"
    H1_SYNC = "h1_sync"
    H2_QUEUED = "h2_queued"
    H3_LOCKER = "h3_locker"


# Modes in which a robot fleet carries the order. They share one property that
# the window code has to know about (A0, 점검 결정 11): the robot fleet is the
# server, so the post-peak drain is far longer than H0's and needs its own
# safety cap (`simulation.max_overrun_sec_robot`). Keeping the set here rather
# than testing `!= H0_DIRECT` means H2/H3 inherit it without a second edit.
ROBOT_MODES = frozenset(
    {HandoffMode.H1_SYNC, HandoffMode.H2_QUEUED, HandoffMode.H3_LOCKER}
)


class BuildingHandoffModel(Model):
    def __init__(
        self,
        mode: HandoffMode = HandoffMode.H0_DIRECT,
        config: dict | None = None,
        scenario_path: str | Path = "data/data1/K50_1.json",
        mapping_path: str | Path | None = None,
        rng_seed: int = 42,
        # dynamic rider pool (etc/plan_rider_pool_dynamic.md):
        dynamic_pool: bool = False,
        return_leg: bool = False,
        # demand-driven simulation window (2026-07-09 사용자 확정):
        # pedestrian congestion spans [min ORD_TIME - margin, max ORD_TIME +
        # margin] (margin = pedestrian.window_margin_sec, default 1 h) and the
        # clock starts at the window start (warm-up hour before the first
        # order). False = legacy lunch-peak horizon window (frozen tests).
        #
        # R8: this flag belongs to the `legacy_margin` policy. `window_policy:
        # delivery` always derives the window from the order data, so the flag
        # does not apply there. None (the default) lets the policy decide —
        # False under legacy_margin, which is the pre-R8 default. An EXPLICIT
        # False against a delivery config is a contradiction and is refused
        # rather than silently overridden.
        scenario_window: bool | None = None,
        # H1~H3 construction args preserved for the extension stage.
        # A0: `n_robots=None` means "take it from the config" (`robot.n_robots`,
        # baseline 5). An explicit int still wins — that is how the Phase D
        # fleet sweep {5,7,9} will drive it without editing YAML per arm.
        n_robots: int | None = None,
        n_locker_compartments: int = 8,
        locker_vmax: int = 100,
        # profile-based floor demand (etc/demand_mapping.md 단계 2·3): floor/
        # office come from a population-density profile instead of a mapping
        # file. Mutually exclusive with mapping_path; requires dynamic_pool.
        floor_profile: str | None = None,
        floor_seed: int | None = None,
        # V-AUD tick-level conservation audit (etc/plan_h0_verification.md §2 L2).
        # Default OFF: when False the audit hook is never entered, so behavior
        # and RNG consumption are bit-for-bit identical to a non-audited run.
        audit: bool = False,
        # V-EVSEL EV-selection staleness log (etc/plan_h0_verification.md §2 L5-3).
        # Default OFF: when False the hooks are never entered and `evsel_events`
        # is None, so results and RNG consumption are bit-for-bit identical. The
        # instrumentation is pure observation (reads EV state only, no mutation,
        # no RNG), so ON is also non-perturbing — it only records.
        evsel: bool = False,
    ) -> None:
        super().__init__(rng=rng_seed)
        # A2 lifted the gate for H1 only. H2 (queue + balk) and H3 (locker) stay
        # closed: their agents do not exist yet, and a silent fallthrough would
        # run them as H1 and quietly produce publishable-looking numbers.
        if mode not in (HandoffMode.H0_DIRECT, HandoffMode.H1_SYNC):
            raise NotImplementedError(
                f"mode {mode} is a future extension; implemented modes are "
                f"H0_DIRECT (baseline) and H1_SYNC (Phase A)"
            )
        # profile-mode guards (etc/demand_mapping.md) — raised before any heavy
        # work, keeping the parameter space unambiguous and the frozen v4/v5
        # mapping paths unreachable from profile mode.
        if floor_profile is not None and mapping_path is not None:
            raise ValueError(
                "floor_profile and mapping_path are mutually exclusive — "
                "profile mode does not use mapping files"
            )
        if floor_profile is not None and not dynamic_pool:
            raise ValueError(
                "floor_profile requires dynamic_pool=True; static replay is the "
                "frozen v4 regression path"
            )
        if floor_seed is not None and floor_profile is None:
            raise ValueError(
                "floor_seed only applies to profile mode (set floor_profile)"
            )
        self.mode = mode
        self.audit = audit
        # V-EVSEL: hall-call registration/board events (None when OFF -> hooks
        # short-circuit, keeping runs bit-identical). `_evsel_pending` maps a
        # waiting passenger to its open registration event so the board hook can
        # backfill the realized wait.
        self.evsel = evsel
        self.evsel_events: list[dict] | None = [] if evsel else None
        self._evsel_pending: dict = {}
        self.n_locker_compartments = n_locker_compartments
        self.locker_vmax = locker_vmax
        self.rng_seed = rng_seed

        self.config = config or load_config(ROOT / "configs" / "baseline_10f.yaml")
        cfg = self.config
        # A0 (점검 결정 12): the robot/handoff blocks get a single validated
        # reader instead of three ad-hoc cfg.get() chains in A1/A2. Both blocks
        # are optional with pre-A0 defaults, because
        # configs/regression_nobasement_10f.yaml carries neither and its replay
        # is a frozen gate. H0 never touches either — test_a0_config_wiring.py
        # proves it by mutating them and asserting bit-identical output.
        self.robot_params = RobotParams.from_config(cfg)
        self.handoff_params = HandoffParams.from_config(cfg)
        self.n_robots = (
            self.robot_params.n_robots if n_robots is None else n_robots
        )
        # A2 함정 1 — Mesa keys `agents_by_type` by the EXACT class, so a lookup
        # naming one rider class silently returns [] once a mode swaps in the
        # other. Every rider lookup in the code base goes through this attribute
        # instead of naming a class directly (11 sites: model.py 6 ·
        # visualize.py 4 · building_manager.py 1). In H0 this is
        # `ExternalRiderAgent`, so H0 stays bit-identical and the
        # `checklist_visual_h0v2.md` signature keeps holding.
        self.rider_cls: type = (
            HandoffRiderAgent if mode in ROBOT_MODES else ExternalRiderAgent
        )
        self.n_floors: int = cfg["building"]["n_floors"]
        self.n_basements: int = cfg["building"].get("n_basements", 0)
        self.office_floors: list[int] = list(range(2, self.n_floors + 1))
        # People-only levels B1..Bn, bottom-up (plan §1.6). Empty when the
        # config declares none, which restores the pre-§1.6 building exactly.
        self.basement_floors: list[int] = [
            -i for i in range(self.n_basements, 0, -1)
        ]

        sim_cfg = cfg["simulation"]
        self.start_time_sec: float = sim_cfg["lunch_peak_start_sec"]
        self.horizon_sec: float = sim_cfg["horizon_sec"]
        self.dt: float = sim_cfg.get("tick_sec", 1.0)
        # A0 (점검 결정 11): robot modes drain far longer than H0 (K300 ~4.9 h
        # vs H0 ~2.1 h), so they take their own cap. H0's value is read by the
        # untouched key — the whole H0 v2.1 battery is calibrated on 7200, and
        # `ped_decay`'s no-touch guarantee is anchored to it too. Falls back to
        # `max_overrun_sec` so a config that never declares the robot key still
        # works (e.g. the frozen regression config).
        if mode in ROBOT_MODES:
            self.max_overrun_sec: float = sim_cfg.get(
                "max_overrun_sec_robot", sim_cfg.get("max_overrun_sec", 3600.0)
            )
        else:
            self.max_overrun_sec = sim_cfg.get("max_overrun_sec", 3600.0)
        # R8 window/termination policy (etc/plan_h0v21_window.md §2.1). The
        # default `legacy_margin` reproduces the pre-R8 model bit-for-bit, so a
        # config that never mentions the key cannot change behaviour — that is
        # what keeps the frozen regression path (HANDOFF_v2 §3.6) valid.
        self.window_policy: str = sim_cfg.get("window_policy", "legacy_margin")
        if self.window_policy not in ("legacy_margin", "delivery"):
            raise ValueError(
                "simulation.window_policy must be 'legacy_margin' or 'delivery', "
                f"got {self.window_policy!r}"
            )
        self.warmup_sec: float = float(sim_cfg.get("warmup_sec", 600.0))
        # 'drain_all' | 'delivery_complete' — decided with the window below
        self.termination_policy: str = "drain_all"
        # 'drain_all' | 'delivery_complete' | 'cap' | None (still running)
        self.termination_reason: str | None = None
        # clock_sec is re-anchored to clock_start_sec after orders are loaded
        # (scenario_window mode starts one margin before the first order)
        self.clock_sec: float = self.start_time_sec
        self.tick_count: int = 0
        self.terminated_by_cap: bool = False

        # --- space & time layers -------------------------------------------
        self.graph = add_lobby_handoff_zones(
            build_from_config(cfg),
            n_locker_compartments=cfg["locker"]["n_compartments"],
        )
        self.kin = ElevatorKinematics.from_config(cfg)
        self.vt = VerticalTransportModel.from_config(cfg)
        self.stair_sec_per_floor: float = cfg["vertical"]["stair_sec_per_floor"]
        self.rider_walk_speed_mps: float = cfg["rider_process"]["walk_speed_mps"]
        # off-graph stair access point on office floors: the corridor midpoint
        # (v2: derived from the graph, not hardcoded — plan_h0_revision.md §1.1)
        self.stair_corr_pos: int = self.graph.graph["corridor_mid_pos"]

        # --- replay timeline & customers -----------------------------------
        scenario_path = Path(scenario_path)
        if not scenario_path.is_absolute():
            scenario_path = ROOT / scenario_path
        if floor_profile is None:
            if mapping_path is None:
                # v4 mapping naming convention: {scenario stem}_floor_mapping_v4.json
                mapping_path = (
                    ROOT / "data" / "floor_mapping"
                    / f"{scenario_path.stem}_floor_mapping_v4.json"
                )
            mapping_path = Path(mapping_path)
            if not mapping_path.is_absolute():
                mapping_path = ROOT / mapping_path
        else:
            mapping_path = None  # profile mode: no mapping file
        self.scenario_path = scenario_path
        self.mapping_path = mapping_path

        # profile-based floor demand (etc/demand_mapping.md 단계 2·3): floor/
        # office_id are an independent categorical draw over a building
        # population-density profile, not a mapping-file join. floor_seed
        # defaults to rng_seed (framework §7.1 floor-assignment seed
        # diversification) but can be pinned independently for CRN contrasts.
        self.floor_profile = floor_profile
        if floor_profile is not None:
            self.floor_seed: int | None = (
                rng_seed if floor_seed is None else int(floor_seed)
            )
            self.floor_demand: FloorDemandModel | None = (
                FloorDemandModel.from_config(
                    cfg, floor_profile, floor_seed=self.floor_seed
                )
            )
        else:
            self.floor_seed = None
            self.floor_demand = None

        # --- rider supply: static replay vs dynamic pool ---------------------
        # static (dynamic_pool=False, frozen regression path): rider type &
        # arrival are pre-determined at load time by load_replay_v4.
        # dynamic: load_dispatch_v5 gives type-free dispatch requests; the
        # RiderPool decides type at ready-time via cost-priority cascade
        # (etc/rider_type_assignment_inventory.md §5), riders return to the
        # pool on building exit (+ optional return leg).
        self.dynamic_pool = dynamic_pool
        self.return_leg = return_leg
        self.sigma_eps: float = cfg["rider_process"].get("sigma_eps", 0.0)

        from analysis.load_data import load_riders

        riders_table = load_riders(scenario_path)
        self.rider_by_type = {r.type: r for r in riders_table}
        self.service_time_by_type: dict[str, float] = {
            r.type: r.service_time_sec for r in riders_table
        }

        if dynamic_pool:
            if floor_profile is not None:
                # profile mode: floors from the population-density draw, no
                # mapping file (etc/demand_mapping.md 단계 2·3). Same
                # DispatchOrder records as v5, so everything downstream
                # (pool, arrivals, customers, collector) is untouched.
                orders = load_dispatch_profile(
                    scenario_path, cfg,
                    profile=floor_profile,
                    floor_seed=self.floor_seed,
                    start_time_sec=self.start_time_sec,
                )
            else:
                orders = load_dispatch_v5(
                    scenario_path, mapping_path, cfg,
                    start_time_sec=self.start_time_sec,
                )
            self.rider_pool: RiderPool | None = RiderPool(riders_table)
            self.dispatch_events: deque = deque(orders)  # ready_time-sorted
            # (arrival_time, seq, BuildingOrderV5) — dispatched, en route
            self.pending_arrivals: list[tuple] = []
            # (release_time, rider_type) — return_leg deferred pool returns
            self.pending_releases: list[tuple] = []
            self._dispatch_seq = 0
            self.rider_events: deque = deque()  # unused in dynamic mode
        else:
            # rng_seed (constructor arg, SolaraViz-adjustable) drives
            # rider-type/ε sampling and the pedestrian stream; mode choice
            # stays on the separate vertical.mode_seed XOR ord_id convention
            orders = load_replay_v4(
                scenario_path,
                mapping_path,
                cfg,
                start_time_sec=self.start_time_sec,
                seed=rng_seed,
                sigma_eps=self.sigma_eps,
            )
            self.rider_pool = None
            self.dispatch_events = deque()
            self.pending_arrivals = []
            self.pending_releases = []
            self._dispatch_seq = 0
            self.rider_events = deque(orders)  # already sorted by arrival

        self.orders = orders
        self.K = len(orders)
        self._service_fallback_sec: float = cfg["rider_process"].get(
            "service_time_sec", 120.0
        )

        # --- simulation window ------------------------------------------------
        # Two policies (R8, etc/plan_h0v21_window.md §2.1):
        #
        # legacy_margin (default, frozen path). scenario_window=True: the
        #   pedestrian stream covers the data's order span ±margin and the clock
        #   starts one margin before the first order (warm-up, so first riders
        #   meet a congested building). scenario_window=False reproduces the
        #   fixed lunch-peak window. cap = ped_end + max_overrun in both.
        #
        # delivery. The warm-up head is an explicit, measured constant
        #   (`warmup_sec`, 600 s — background traffic saturates in 300~600 s,
        #   plan §1.1) instead of a margin borrowed from the pedestrian block,
        #   and there is NO pedestrian spawn cutoff: ped_end is pinned to the cap
        #   so background traffic runs until the run ends. Clipping the tail is
        #   what biases the late orders (plan §1.2: W_EV −28 % when the
        #   background stops early), and a delivery-driven termination makes the
        #   cutoff pointless anyway — the run no longer waits for pedestrians.
        if scenario_window is None:
            scenario_window = self.window_policy == "delivery"
        elif self.window_policy == "delivery" and not scenario_window:
            raise ValueError(
                "window_policy='delivery' derives the window from the order "
                "data; it is incompatible with an explicit scenario_window=False "
                "(the fixed lunch-peak window). Use a legacy_margin config."
            )
        self.scenario_window = scenario_window
        margin = cfg["pedestrian"].get("window_margin_sec", 3600.0)
        if self.window_policy == "delivery" and orders:
            ord_abs = [o.ord_time_abs_sec for o in orders]
            self.ped_start_sec: float = min(ord_abs) - self.warmup_sec
            # The cap is a safety net, not a schedule: measured, the last rider
            # exits 2,400~3,500 s after the LAST order (cook + street + in
            # building), so `max_overrun_sec` must sit comfortably above that.
            # Delivery configs declare 7200 (plan §10-1).
            self.cap_time_sec: float = max(ord_abs) + self.max_overrun_sec
            self.ped_end_sec: float = self.cap_time_sec  # == no spawn cutoff
            self.termination_policy = "delivery_complete"
        else:
            # K == 0 degenerates to the legacy window on purpose: "every order
            # delivered" is vacuously true at tick 1, so a delivery-driven run
            # would end immediately. The background window bounds it instead.
            if scenario_window and orders:
                ord_abs = [o.ord_time_abs_sec for o in orders]
                self.ped_start_sec = min(ord_abs) - margin
                self.ped_end_sec = max(ord_abs) + margin
            else:
                self.ped_start_sec = self.start_time_sec
                self.ped_end_sec = self.start_time_sec + self.horizon_sec
            self.cap_time_sec = self.ped_end_sec + self.max_overrun_sec
        self.clock_start_sec: float = self.ped_start_sec
        self.clock_sec = self.clock_start_sec

        self.customer_by_ord_id: dict[int, CustomerAgent] = {}
        for o in orders:
            self.customer_by_ord_id[o.ord_id] = CustomerAgent(
                self,
                floor=o.floor,
                office_id=o.office_id,
                vol=o.vol,
                ord_time_sec=o.ord_time_abs_sec,
                dlv_deadline_sec=o.deadline_abs_sec,
            )

        # --- infrastructure agents -----------------------------------------
        self.control = ControlSystemAgent(self)
        self.manager = BuildingManagerAgent(self, mode=mode.value)
        # v2: the EV fleet is declared by the config/graph (ev_ids +
        # shared_ev_ids), one ElevatorAgent per declared car — no hardcoded
        # count (plan_h0_revision.md §1.2). H0 has no robots, so shared cars
        # behave identically to people-only cars here.
        cap = cfg["building"]["shared_ev_capacity_people_no_robot"]
        cap_with_robot = cfg["building"]["shared_ev_capacity_people_with_robot"]
        door = cfg["elevator"]["door_open_close_sec"]
        shared_ids = set(self.graph.graph["shared_ev_ids"])
        self.elevators: list[ElevatorAgent] = [
            ElevatorAgent(self, ev_id, shared_with_robot=ev_id in shared_ids,
                          capacity_people=cap, door_open_close_sec=door,
                          capacity_people_with_robot=cap_with_robot)
            for ev_id in self.graph.graph["ev_ids"]
        ]

        # --- robot fleet (A2) -------------------------------------------------
        # Built only in robot modes, so `self.robots` is the empty list in H0 —
        # which is also the condition `ControlSystemAgent.step` keys its dispatch
        # branch on, keeping the H0 tick free of any new work.
        self.robots: list[RobotAgent] = (
            [RobotAgent(self, self.robot_params) for _ in range(self.n_robots)]
            if mode in ROBOT_MODES
            else []
        )
        # A2 함정 2 — the H1 rider exits before the delivery, so the rest of the
        # order timeline is published here by the robot and joined on `ord_id`.
        # Always present (empty in H0) so consumers need no mode branch.
        self.robot_leg_records: dict[int, dict] = {}

        # --- pedestrian stream ----------------------------------------------
        ped_cfg = cfg["pedestrian"]
        self.ped_rate_per_sec: float = ped_cfg["arrival_rate_per_min"] / 60.0
        self.ped_down_fraction: float = ped_cfg["down_fraction"]
        self.ped_speed_mps: float = ped_cfg["speed_mps"]
        # Ground-side endpoint distribution (plan §1.6): floor label -> weight.
        # Basement entries are dropped when the building has no such floor, so
        # a ground_split block cannot conjure a level the graph lacks.
        self.ped_ground_floors, self.ped_ground_weights = self._ground_split(
            ped_cfg.get("ground_split")
        )
        self.ped_rng = np.random.default_rng(rng_seed + 1)
        self.ped_spawned: int = 0
        self.ped_done_log: list[dict] = []
        # Post-peak decay of the background stream (A0, 점검 결정 10). `None`
        # when the config omits `simulation.ped_decay` (the frozen regression
        # path) or when there are no orders to anchor it to. It cannot perturb
        # H0: the anchor is `last order + 7200` == H0's cap and the comparison
        # is strict, so H0 terminates before entering the decayed regime — and
        # even in the regime the RNG call *pattern* is unchanged, only the rate
        # value. See simulation/config_params.py::PedDecay.
        self.ped_decay: PedDecay | None = PedDecay.from_config(
            cfg,
            last_order_abs_sec=(
                max(o.ord_time_abs_sec for o in orders) if orders else None
            ),
            peak_rate_per_sec=self.ped_rate_per_sec,
        )

        # --- results & collection --------------------------------------------
        self.rider_records: list[dict] = []
        # rolling busy_ticks snapshots per EV for the windowed utilization
        # (last 60 sim-seconds); one snapshot per tick, appended in step()
        self._ev_busy_hist: list[deque] = [
            deque([ev.busy_ticks], maxlen=61) for ev in self.elevators
        ]
        # V-KPIWIN: full-length cumulative snapshots (index 0 = window start,
        # index j = state after j ticks, i.e. at clock_start_sec + j*dt) so
        # simulation.kpi can restrict the busy-tick numerator and the OPEX
        # accrual to an arbitrary sub-window (the order span). Purely additive
        # bookkeeping — never read by any existing KPI path, so audit-off runs
        # stay bit-identical.
        self._ev_busy_cum: list[list[int]] = [[ev.busy_ticks] for ev in self.elevators]
        self._opex_cum: list[float] = [self.manager.opex_running_krw]
        # R8-b: same indexing convention, running SUM of the per-tick passenger
        # count. Window-restricted mean occupancy = (cum[j1] - cum[j0]) /
        # (j1 - j0). `utilization` measures time-not-parked, NOT how full the
        # cars are; reporting both stops a reader from taking 85 % busy for
        # 85 % of capacity (plan_h0v21_window.md §3.5).
        self._ev_pax_cum: list[list[int]] = [[0] for _ in self.elevators]
        # A3: fleet-time bookkeeping, same indexing convention as _ev_busy_cum
        # (index j = state after j ticks) so kpi.py can restrict robot
        # utilization to the mode-invariant fixed window. "Busy" is defined as
        # NOT (IDLE or CHARGING_BLOCKED) — i.e. everything except sitting in the
        # robot zone available or recharging; both of those are the fleet's
        # slack, and 결정 #19 merged waiting with charging so they must count the
        # same way. The 7-bucket decomposition is a plain per-tick counter with
        # no cumulative history: it is a layer ③ mode-internal diagnostic
        # (§3.7), never compared across modes, so a window would buy nothing at
        # the cost of 7 lists per robot. All three are empty in H0.
        self._robot_busy_ticks: list[int] = [0 for _ in self.robots]
        self._robot_busy_cum: list[list[int]] = [[0] for _ in self.robots]
        self._robot_bucket_ticks: list[dict[str, int]] = [
            dict.fromkeys(REPORT_BUCKETS, 0) for _ in self.robots
        ]
        # R8-b: state of the building at the moment the FIRST order lands — the
        # evidence that the warm-up actually warmed it (A13 gate input). Filled
        # once, in step(); None until then and for an order-free run.
        self.first_order_sec: float | None = (
            min(o.ord_time_abs_sec for o in orders) if orders else None
        )
        self._warmup_snapshot: dict | None = None
        # per-EV series (ev1_queue .. ev{n}_util_window) are generated from the
        # declared fleet so the collector schema always matches the EV count
        model_reporters = {
                "clock_sec": lambda m: m.clock_sec,
                "riders_in_building": lambda m: len(m.agents_of(m.rider_cls)),
                "delivered": lambda m: sum(
                    1 for c in m.customer_by_ord_id.values()
                    if c.delivered_at_sec is not None
                ),
                "sla_violations": lambda m: sum(
                    1 for c in m.customer_by_ord_id.values() if c.sla_violation
                ),
                "peds_active": lambda m: len(m.agents_of(PedestrianAgent)),
                # --- S7.1 live-KPI series (plan 1-B) -------------------------
                "backlog": lambda m: m.backlog(),
                "sla_rate_running": lambda m: m.sla_rate_running_pct(),
                "t_e2e_running_mean": lambda m: m.t_e2e_running_mean(),
                "t_lobby_running_mean": lambda m: m.t_lobby_running_mean(),
                "riders_walking": lambda m: m.count_rider_states(_WALK_STATES),
                "riders_waiting_ev": lambda m: m.count_rider_states(_WAIT_STATES),
                "riders_riding_ev": lambda m: m.count_rider_states(_RIDE_STATES),
                "riders_on_stairs": lambda m: m.count_rider_states(_STAIR_STATES),
                "riders_in_service": lambda m: m.count_rider_states(_SERVICE_STATES),
                "opex_running_krw": lambda m: m.manager.opex_running_krw,
                "peds_waiting": lambda m: sum(
                    1 for p in m.agents_of(PedestrianAgent)
                    if p.state == PedestrianAgent.WAIT_EV
                ),
                # --- dynamic rider pool series (NaN when dynamic_pool=False) --
                "free_bike": lambda m: m.pool_free("BIKE"),
                "free_walk": lambda m: m.pool_free("WALK"),
                "free_car": lambda m: m.pool_free("CAR"),
                "dispatch_queue_len": lambda m: (
                    float(len(m.rider_pool.waiting)) if m.rider_pool else float("nan")
                ),
                "fallback_cum": lambda m: (
                    float(m.rider_pool.fallback_count) if m.rider_pool else float("nan")
                ),
                "riders_en_route": lambda m: (
                    float(len(m.pending_arrivals)) if m.dynamic_pool else float("nan")
                ),
        }
        for i, ev in enumerate(self.elevators):
            key = ev.ev_id.lower()  # EV1 -> ev1
            model_reporters[f"{key}_queue"] = (
                lambda m, i=i: m.elevators[i].queue_length()
            )
            model_reporters[f"{key}_floor"] = (
                lambda m, i=i: m.elevators[i].position_floor
            )
            model_reporters[f"{key}_pax"] = (
                lambda m, i=i: m.elevators[i].passenger_count
            )
            model_reporters[f"{key}_util_window"] = (
                lambda m, i=i: m.ev_util_window_pct(i)
            )
        self.datacollector = DataCollector(model_reporters=model_reporters)
        # Mesa's DataCollector.collect() appends to ~20 per-reporter lists in
        # a plain (non-atomic) loop, and SolaraViz's STEP button / interval
        # sliders can invoke model.step() from the foreground thread while a
        # Play run is still driving it from a background thread (both call
        # ModelController.do_step() -> model.step()). A read
        # (get_model_vars_dataframe(), called by every plot component on
        # render) that lands mid-loop sees some columns one tick ahead of
        # others -> pandas "Length of values does not match length of index".
        # A single lock serializing every collect() and every read closes
        # that window regardless of which two call sites race.
        self._datacollector_lock = threading.Lock()
        _orig_get_model_vars_dataframe = self.datacollector.get_model_vars_dataframe

        def _locked_get_model_vars_dataframe():
            with self._datacollector_lock:
                return _orig_get_model_vars_dataframe()

        self.datacollector.get_model_vars_dataframe = _locked_get_model_vars_dataframe
        self.datacollector.collect(self)

    # ------------------------------------------------------------------ util

    def agents_of(self, cls) -> list:  # noqa: ANN001
        """Live agents of a type (agents_by_type raises KeyError when absent)."""
        if cls in self.agents_by_type:
            return list(self.agents_by_type[cls])
        return []

    def service_time_for(self, rider_type: str) -> float:
        return self.service_time_by_type.get(rider_type, self._service_fallback_sec)

    def pool_free(self, rider_type: str) -> float:
        """Free riders of a type (NaN when the dynamic pool is off)."""
        if self.rider_pool is None:
            return float("nan")
        return float(self.rider_pool.free.get(rider_type, 0))

    # -------------------------------------------------- live KPI helpers (S7.1)

    def backlog(self) -> int:
        """Orders already placed (ord_time passed) but not yet delivered."""
        return sum(
            1 for c in self.customer_by_ord_id.values()
            if c.ord_time_sec <= self.clock_sec and c.delivered_at_sec is None
        )

    def sla_rate_running_pct(self) -> float:
        delivered = [
            c for c in self.customer_by_ord_id.values()
            if c.delivered_at_sec is not None
        ]
        if not delivered:
            return 0.0
        return 100.0 * sum(1 for c in delivered if c.sla_violation) / len(delivered)

    def t_e2e_running_mean(self) -> float:
        vals = [
            c.t_e2e_sec for c in self.customer_by_ord_id.values()
            if c.t_e2e_sec is not None
        ]
        return float(np.mean(vals)) if vals else float("nan")

    def t_lobby_running_mean(self) -> float:
        vals = [r["t_lobby_sec"] for r in self.rider_records]
        return float(np.mean(vals)) if vals else float("nan")

    def count_rider_states(self, states: frozenset) -> int:
        return sum(
            1 for r in self.agents_of(self.rider_cls) if r.state in states
        )

    def ev_util_window_pct(self, ev_index: int) -> float:
        """Busy fraction of the last <=60 sim-seconds (vs cumulative util)."""
        hist = self._ev_busy_hist[ev_index]
        if len(hist) < 2:
            return 0.0
        return 100.0 * (hist[-1] - hist[0]) / (len(hist) - 1)

    def _take_warmup_snapshot(self) -> None:
        """How warm the building was when the first order landed (R8-b).

        Taken once, on the tick the clock reaches the first ORD_TIME. The EV
        figure is a trailing 300 s busy fraction (or the whole head, if the
        warm-up is shorter than that), which is what `verify_h0` A13 compares
        against the delivery-window utilisation — an empty building scores ~0
        and fails the gate (etc/plan_h0v21_window.md §4).
        """
        j1 = self.tick_count
        lookback = min(300, j1)
        j0 = j1 - lookback
        if lookback <= 0:  # first order lands on the very first tick
            util = float("nan")
            boardings_per_min = float("nan")
        else:
            util = float(
                np.mean([(c[j1] - c[j0]) / lookback for c in self._ev_busy_cum])
            )
            t0 = self.clock_sec - lookback * self.dt
            boardings = sum(
                1
                for ev in self.elevators
                for b in ev.boarding_log
                if b["kind"] == "pedestrian" and b["t_board_sec"] > t0
            )
            boardings_per_min = boardings / (lookback * self.dt / 60.0)
        peds = self.agents_of(PedestrianAgent)
        self._warmup_snapshot = {
            "head_sec": self.first_order_sec - self.clock_start_sec,
            "lookback_sec": lookback * self.dt,
            "util_at_first_order": util,
            "peds_at_first_order": len(peds),
            "peds_waiting_at_first_order": sum(
                1 for p in peds if p.state == PedestrianAgent.WAIT_EV
            ),
            "ped_boardings_per_min": boardings_per_min,
        }

    # ------------------------------------------------------------------ step

    def step(self) -> None:
        self.clock_sec += self.dt
        self.tick_count += 1

        if self.dynamic_pool:
            self._process_pending_releases()  # return_leg deferred returns
            self._dispatch_riders()           # ready orders -> pool -> en route
        self._inject_riders()
        self._spawn_pedestrians()

        # framework §6.3 tick order; explicit snapshots so agents can remove()
        # themselves mid-iteration without perturbing the sweep
        for c in self.agents_of(CustomerAgent):
            c.step()
        for p in self.agents_of(PedestrianAgent):
            p.step()
        self.control.step()
        # Robots step BEFORE the riders, which is what makes A1's recorded
        # one-tick handoff lag real: the rider calls `notify_rider_ready` on its
        # own step, the robot has already stepped, so it enters HANDOFF on the
        # next tick (robot.py::notify_rider_ready, 구현 로그 §A2-2). Ordering
        # them the other way would silently delete that tick and invalidate the
        # A4 hand chain that is written against it. Elevators still step last,
        # so a hall call registered here is served within the same tick.
        # `self.robots` is empty in H0, so this is a no-op there.
        for rb in self.robots:
            rb.step()
        for r in self.agents_of(self.rider_cls):
            r.step()
        for ev in self.elevators:
            ev.step()
        self.manager.step()

        # strict=True is safe here (and only here): every one of these lists is
        # built with exactly one entry per elevator and the fleet never changes
        # size. Do NOT blanket-apply it to the zips in analysis/ — some of those
        # are deliberately ragged (`zip(spans, spans[1:])`).
        for hist, ev in zip(self._ev_busy_hist, self.elevators, strict=True):
            hist.append(ev.busy_ticks)
        # V-KPIWIN full-length snapshots (see __init__): one per tick.
        for cum, ev in zip(self._ev_busy_cum, self.elevators, strict=True):
            cum.append(ev.busy_ticks)
        for cum, ev in zip(self._ev_pax_cum, self.elevators, strict=True):
            cum.append(cum[-1] + len(ev.passengers))
        self._opex_cum.append(self.manager.opex_running_krw)
        # A3 robot fleet-time snapshot. `self.robots` is empty in H0, so this is
        # a no-op there and the frozen bit-identity holds by construction.
        for i, rb in enumerate(self.robots):
            if rb.state not in (RobotState.IDLE, RobotState.CHARGING_BLOCKED):
                self._robot_busy_ticks[i] += 1
            self._robot_busy_cum[i].append(self._robot_busy_ticks[i])
            self._robot_bucket_ticks[i][rb.report_bucket] += 1
        if (
            self._warmup_snapshot is None
            and self.first_order_sec is not None
            and self.clock_sec >= self.first_order_sec
        ):
            self._take_warmup_snapshot()
        # locked: see the comment on _datacollector_lock in __init__
        with self._datacollector_lock:
            self.datacollector.collect(self)
        if self.audit:
            self._audit_invariants()
        self._check_termination()

    def _audit_invariants(self) -> None:
        """Tick-level conservation invariants (V-AUD, audit mode only).

        Post-hoc results-JSON checks (analysis/verify_h0.py) cannot see the
        per-tick rider census, car occupancy or queue *membership*; these asserts
        fill that gap and run only when audit=True. Rider conservation: for every
        type the busy count tracked by the pool (initial - free) must equal the
        riders that are physically accounted for — en route to the building,
        inside it, or (return_leg) travelling back to the pool. Car occupancy
        must never exceed capacity.

        Two v2 invariants live here because they are undecidable from a results
        JSON (plan_h0v2_verification.md §3 L2):

          A12 hall-call exclusivity — one passenger, at most one queue slot. The
              JSON records queue lengths only, so "two cars with one waiter each"
              and "one waiter registered twice" look identical there. With four
              cars a re-registration path (dispatch, then re-dispatch) would
              silently double-count a passenger into two queues, inflating
              boardings and stranding the duplicate; the assert below is the only
              thing standing between that bug and a plausible-looking KPI.

          A10-2/3 riders stay above ground — the basements are background
              pedestrian infrastructure (plan §1.6). A rider (or, from Phase A,
              a robot) queued at or bound for a basement means the delivery path
              escaped the office floors.
        """
        # A1: the capacity rule is heterogeneous (R0-1·R0-2) — people 15 alone,
        # 11 while a robot rides, and never two robots. With no robots the three
        # asserts collapse to the pre-A1 `len(passengers) <= capacity_people`.
        for ev in self.elevators:
            n_robots = sum(1 for p in ev.passengers if p.kind == "robot")
            assert n_robots <= 1, (
                f"tick {self.tick_count}: {ev.ev_id} carries {n_robots} robots "
                f"— one robot per car (R0-1)"
            )
            assert not (n_robots and not ev.shared_with_robot), (
                f"tick {self.tick_count}: robot rode people-only {ev.ev_id} "
                f"(B3: robots use robot-shareable cars only)"
            )
            limit = (
                ev.capacity_people_with_robot if n_robots else ev.capacity_people
            )
            assert ev.people_aboard <= limit, (
                f"tick {self.tick_count}: {ev.ev_id} carries {ev.people_aboard} "
                f"people (robot aboard: {bool(n_robots)}) > capacity {limit}"
            )

        # --- A12: hall-call exclusivity across every car and floor ------------
        seen: dict[int, tuple[str, int]] = {}
        for ev in self.elevators:
            for floor, queue in ev.hall_calls.items():
                for passenger in queue:
                    prev = seen.get(id(passenger))
                    assert prev is None, (
                        f"tick {self.tick_count}: {getattr(passenger, 'kind', '?')} "
                        f"passenger is queued twice — {prev[0]}@{prev[1]} and "
                        f"{ev.ev_id}@{floor} (hall-call exclusivity, A12)"
                    )
                    seen[id(passenger)] = (ev.ev_id, floor)
                    # a queued passenger must not already be riding some car
                    assert not any(
                        passenger in other.passengers for other in self.elevators
                    ), (
                        f"tick {self.tick_count}: passenger queued at "
                        f"{ev.ev_id}@{floor} while already on board a car (A12)"
                    )

        # --- A10-2/3: no rider below ground -----------------------------------
        for ev in self.elevators:
            for floor, queue in ev.hall_calls.items():
                if floor > 0:
                    continue
                offenders = [p for p in queue if getattr(p, "kind", None) != "pedestrian"]
                assert not offenders, (
                    f"tick {self.tick_count}: non-pedestrian(s) waiting at "
                    f"{ev.ev_id} floor {floor} — basements are pedestrian-only (A10-2)"
                )
            for p in ev.passengers:
                if getattr(p, "kind", None) == "pedestrian":
                    continue
                assert p.ev_dest_floor > 0, (
                    f"tick {self.tick_count}: {getattr(p, 'kind', '?')} bound for "
                    f"floor {p.ev_dest_floor} in {ev.ev_id} — riders never go below "
                    "ground (A10-2)"
                )
        if not self.dynamic_pool or self.rider_pool is None:
            return
        in_building: dict[str, int] = {t: 0 for t in self.rider_pool.initial}
        for r in self.agents_of(self.rider_cls):
            in_building[r.order.rider_type] = in_building.get(r.order.rider_type, 0) + 1
        en_route: dict[str, int] = {t: 0 for t in self.rider_pool.initial}
        for _at, _seq, order in self.pending_arrivals:
            en_route[order.rider_type] = en_route.get(order.rider_type, 0) + 1
        returning: dict[str, int] = {t: 0 for t in self.rider_pool.initial}
        for _rel, rider_type in self.pending_releases:
            returning[rider_type] = returning.get(rider_type, 0) + 1
        for t, initial in self.rider_pool.initial.items():
            busy = initial - self.rider_pool.free[t]
            accounted = en_route[t] + in_building[t] + returning[t]
            assert busy == accounted, (
                f"tick {self.tick_count}: rider type {t} conservation broken — "
                f"busy {busy} (initial {initial} - free {self.rider_pool.free[t]}) != "
                f"en_route {en_route[t]} + in_building {in_building[t]} + "
                f"returning {returning[t]}"
            )

    # ----------------------------------------------- V-EVSEL staleness hooks

    def _evsel_on_register(self, chosen_ev, from_floor: int, passenger) -> None:  # noqa: ANN001
        """Record one EV-selection event at hall-call registration (evsel only).

        The dispatch heuristic (ControlSystemAgent.choose_elevator) picks the
        min-estimated-wait EV **when the passenger enters / finishes service**,
        then the passenger walks to that EV shaft and only *later* registers the
        hall call. This hook re-evaluates the *same* cost function
        (`_estimate_wait`, same lower-ev_id tie-break) against current EV state
        at registration time. `stale` is True when the argmin has since moved to
        a different EV, i.e. the committed choice is no longer optimal under the
        heuristic's own cost model. `reeval_best_lb_sec` is a strict physical
        lower bound on how long the re-eval-optimal EV would take to reach the
        floor (pure directional travel, ignoring door cycles and intermediate
        stops) — used later as a conservative counterfactual wait floor.

        A3: the re-evaluation pool is the pool the passenger could actually have
        chosen from, not always the whole fleet. Robots are restricted to the
        robot-shareable cars (`choose_elevator(..., candidates=)`, A1), so
        re-evaluating a robot's call against all four cars would flag "EV1 was
        better" as stale even though EV1 was never a legal option — inflating
        the robot stale ratio with counterfactuals the policy forbids. People
        keep the whole fleet, so every H0 event is produced exactly as before
        and the frozen 52.95 % anchor is untouched.
        """
        ctrl = self.control
        pool = (
            [ev for ev in self.elevators if ev.shared_with_robot]
            if getattr(passenger, "kind", None) == "robot"
            else self.elevators
        )
        evs = sorted(pool, key=lambda e: e.ev_id)
        ests = {ev.ev_id: ctrl._estimate_wait(ev, from_floor) for ev in evs}
        reeval_best = min(evs, key=lambda ev: ests[ev.ev_id])  # ties -> lower ev_id
        per_floor = self.kin.travel_time_sec(1, 2)
        # position_floor is in rank units, from_floor is a label (plan §1.6)
        lb = abs(reeval_best.position_floor - floor_rank(from_floor)) * per_floor
        order = getattr(passenger, "order", None)
        event = {
            "ord_id": getattr(order, "ord_id", None),
            "kind": getattr(passenger, "kind", None),
            "reg_clock_sec": self.clock_sec,
            "from_floor": from_floor,
            "chosen_ev": chosen_ev.ev_id,
            "reeval_best_ev": reeval_best.ev_id,
            # size of the pool the re-evaluation was allowed to consider (4 for
            # people, 2 for robots on the baseline fleet) — the reader needs it
            # to compare stale ratios across kinds, since a smaller pool has
            # fewer chances to move its argmin (A3)
            "n_candidates": len(evs),
            "stale": chosen_ev.ev_id != reeval_best.ev_id,
            "est_chosen_sec": ests[chosen_ev.ev_id],
            "est_reeval_best_sec": ests[reeval_best.ev_id],
            "reeval_best_lb_sec": lb,
            "observed_wait_sec": None,  # backfilled at board
        }
        self.evsel_events.append(event)
        self._evsel_pending[passenger] = event

    def _evsel_on_board(self, passenger) -> None:  # noqa: ANN001
        """Backfill the realized hall-call wait when the passenger boards."""
        event = self._evsel_pending.pop(passenger, None)
        if event is not None:
            event["observed_wait_sec"] = (
                self.clock_sec - passenger.ev_wait_started_sec
            )

    def _inject_riders(self) -> None:
        # `self.rider_cls`, not a literal class: both rider classes take the
        # same (model, order, service_time_sec) signature precisely so this
        # injection point stays mode-agnostic (A2 함정 1).
        if self.dynamic_pool:
            while self.pending_arrivals and self.pending_arrivals[0][0] <= self.clock_sec:
                _, _, order = heapq.heappop(self.pending_arrivals)
                self.rider_cls(
                    self, order,
                    service_time_sec=self.service_time_for(order.rider_type),
                )
            return
        while self.rider_events and self.rider_events[0].arrival_time_sec <= self.clock_sec:
            order = self.rider_events.popleft()
            self.rider_cls(
                self, order, service_time_sec=self.service_time_for(order.rider_type)
            )

    # ------------------------------------------- dynamic rider pool (v5 path)

    def _dispatch_riders(self) -> None:
        """Move ready orders (food cooked) into the pool: grant or enqueue."""
        while (
            self.dispatch_events
            and self.dispatch_events[0].ready_time_sec <= self.clock_sec
        ):
            order = self.dispatch_events.popleft()
            granted = self.rider_pool.try_dispatch(order)
            if granted is None:
                self.rider_pool.enqueue(order)  # all eligible types exhausted
            else:
                self._schedule_arrival(order, granted[0], granted[1],
                                       dispatch_time=self.clock_sec)

    def _schedule_arrival(
        self, order, rider_type: str, was_fallback: bool, dispatch_time: float
    ) -> None:  # noqa: ANN001
        """Assemble the runtime BuildingOrderV5 and put it en route."""
        rider = self.rider_by_type[rider_type]
        travel_sec = order.dist_m / rider.speed_mps
        if self.sigma_eps > 0:
            # per-order RNG stream keyed by (seed, ord_id): queue-order changes
            # must not shift other orders' noise (plan §주의점 3)
            rng = np.random.default_rng([self.rng_seed, order.ord_id])
            travel_sec *= float(
                _sample_lognormal_unbiased(rng, self.sigma_eps, 1)[0]
            )
        v5 = BuildingOrderV5(
            ord_id=order.ord_id,
            arrival_time_sec=dispatch_time + travel_sec,
            ord_time_abs_sec=order.ord_time_abs_sec,
            deadline_abs_sec=order.deadline_abs_sec,
            cook_time_sec=order.cook_time_sec,
            vol=order.vol,
            floor=order.floor,
            office_id=order.office_id,
            rider_type=rider_type,
            w_R_krw_per_h=compute_w_R_krw_per_h(rider),
            vertical_mode=order.vertical_mode,
            horizontal_time_s=travel_sec,
            ready_time_sec=order.ready_time_sec,
            dispatch_time_sec=dispatch_time,
            rider_wait_sec=dispatch_time - order.ready_time_sec,
            was_fallback=was_fallback,
            dist_m=order.dist_m,
        )
        self._dispatch_seq += 1  # heap tie-breaker (dataclasses not orderable)
        heapq.heappush(self.pending_arrivals,
                       (v5.arrival_time_sec, self._dispatch_seq, v5))

    def on_rider_exit(self, order) -> None:  # noqa: ANN001
        """ExternalRiderAgent._finalize hook: return the rider to the pool.

        Static path: no-op. return_leg=True defers the return by the
        drop->shop travel time (rider agent is already removed; the deferred
        return is a model-level event, plan §주의점 4).
        """
        if not self.dynamic_pool:
            return
        if self.return_leg:
            rider = self.rider_by_type[order.rider_type]
            release_at = self.clock_sec + order.dist_m / rider.speed_mps
            heapq.heappush(self.pending_releases, (release_at, order.rider_type))
        else:
            self._apply_release(order.rider_type)

    def _process_pending_releases(self) -> None:
        while self.pending_releases and self.pending_releases[0][0] <= self.clock_sec:
            _, rider_type = heapq.heappop(self.pending_releases)
            self._apply_release(rider_type)

    def _apply_release(self, rider_type: str) -> None:
        """Pool return + immediately dispatch any queue order it unblocks."""
        for order, granted_type, was_fallback in self.rider_pool.release(rider_type):
            self._schedule_arrival(order, granted_type, was_fallback,
                                   dispatch_time=self.clock_sec)

    def _ground_split(
        self, raw: dict | None
    ) -> tuple[list[int], list[float]]:
        """Parse pedestrian.ground_split into (floor labels, normalised weights).

        Keys are floor labels as strings ("1", "-1", "-2"); weights need not sum
        to 1. A basement weight is ignored (with its mass redistributed by the
        renormalisation) when the building declares no such basement, so config
        and geometry cannot disagree silently. Missing/empty block => lobby only,
        which is the pre-§1.6 behaviour.
        """
        if not raw:
            return [1], [1.0]
        valid = {1, *self.basement_floors}
        floors: list[int] = []
        weights: list[float] = []
        for key, weight in raw.items():
            floor = int(key)
            if floor not in valid:
                if floor < 0:
                    continue          # basement the building does not have
                raise ValueError(
                    f"pedestrian.ground_split names floor {floor}, which is not a "
                    f"ground-side endpoint (expected 1 or one of {self.basement_floors})"
                )
            if weight < 0:
                raise ValueError(f"ground_split weight for {floor} is negative: {weight}")
            floors.append(floor)
            weights.append(float(weight))
        total = sum(weights)
        if not floors or total <= 0:
            raise ValueError("pedestrian.ground_split has no positive weight")
        order = sorted(range(len(floors)), key=lambda i: floors[i])
        return [floors[i] for i in order], [weights[i] / total for i in order]

    def _draw_ground_floor(self) -> int:
        """Ground-side endpoint for one pedestrian trip (plan §1.6).

        Deliberately consumes NO randomness when the lobby is the only endpoint:
        that keeps a basement-free configuration bit-identical to the pre-§1.6
        model rather than merely statistically equivalent.
        """
        if len(self.ped_ground_floors) == 1:
            return self.ped_ground_floors[0]
        return int(self.ped_rng.choice(self.ped_ground_floors, p=self.ped_ground_weights))

    def _ped_rate_at(self, t: float) -> float:
        """Background pedestrian Poisson rate at absolute time ``t``.

        Constant (the lunch-peak rate) unless `simulation.ped_decay` is
        declared AND ``t`` is strictly past its anchor. Deliberately returns
        `self.ped_rate_per_sec` — the same float object the pre-A0 code used —
        on that path, so the Poisson draw is bit-identical, not merely equal.
        """
        if self.ped_decay is None:
            return self.ped_rate_per_sec
        return self.ped_decay.rate_per_sec_at(t)

    def _spawn_pedestrians(self) -> None:
        if self.clock_sec > self.ped_end_sec:
            return
        # One poisson() draw per tick regardless of the rate: the decay changes
        # the rate's *value*, never the RNG call pattern, which is what keeps
        # pre-decay ticks bit-identical (config_params.PedDecay, reason 2).
        n = int(self.ped_rng.poisson(self._ped_rate_at(self.clock_sec) * self.dt))
        for _ in range(n):
            down = self.ped_rng.random() < self.ped_down_fraction
            floor = int(self.ped_rng.choice(self.office_floors))
            ground = self._draw_ground_floor()
            if down:
                PedestrianAgent(self, from_floor=floor, to_floor=ground,
                                speed_mps=self.ped_speed_mps)
            else:
                PedestrianAgent(self, from_floor=ground, to_floor=floor,
                                speed_mps=self.ped_speed_mps)
            self.ped_spawned += 1

    # ------------------------------------------------------- termination (R8)

    def _pipeline_empty(self) -> bool:
        """No order is still waiting to be handed to a carrier.

        `pending_releases` (return_leg travel back to the shop) is deliberately
        NOT a blocker: that rider is already outside the building, and once every
        order is delivered there is no queued order left for the return to
        unblock (etc/plan_h0v21_window.md §2.2).
        """
        if self.rider_events:
            return False
        if self.dynamic_pool and (  # noqa: SIM103 — guard chain, not one condition
            self.dispatch_events or self.pending_arrivals or self.rider_pool.waiting
        ):
            return False
        return True

    def _delivery_complete(self) -> bool:
        return all(
            c.delivered_at_sec is not None for c in self.customer_by_ord_id.values()
        )

    def _carriers_settled(self) -> bool:
        """Mode-specific "every delivery actor is back home" (plan §2.3).

        H0 (implemented): no ExternalRiderAgent is left inside the building.

        The modes below are NOT implemented — the constructor rejects them — and
        are recorded here so the condition is written down where it will be
        needed instead of being rediscovered:

          H1 (Phase A): H0's condition AND every RobotAgent IDLE at the 1F lobby
              robot zone. R3 merged waiting and charging into that zone, so
              "home" is a single, well-defined node.
          H2 (Phase C): no per-order branch is needed. "riders all out AND robots
              all home" already covers a mixed corpus where some orders were
              carried by a rider and others by a robot — whichever carrier was
              idle for an order makes its half of the condition vacuously true.
          H3 (Phase D): as H1, plus — only if `delivered` ends up defined as
              customer PICKUP rather than locker DEPOSIT — every compartment
              empty. That definition is an open decision; the plan recommends
              DEPOSIT so T_e2e stays comparable with H0~H2 and the customer can
              stay a passive agent.
        """
        # Deliberately a guard chain rather than `return not agents_of(...)`:
        # H1~H3 append their own `if ...: return False` blocks here (see above).
        if self.agents_of(self.rider_cls):
            return False
        # H1 (A2): every robot back in the 1F robot zone and off duty. The
        # accepted states are IDLE *and* CHARGING_BLOCKED (§3.2) — requiring
        # IDLE alone would hang the run whenever the last delivery leaves a
        # robot below `soc_low_pct`, because it then charges for minutes before
        # becoming dispatchable again and nothing else is left to advance.
        return all(
            rb.node == ROBOT_HOME_NODE
            and rb.state in (RobotState.IDLE, RobotState.CHARGING_BLOCKED)
            for rb in self.robots
        )

    def _check_termination(self) -> None:
        if self.clock_sec >= self.cap_time_sec:
            self.running = False
            self.terminated_by_cap = True
            self.termination_reason = "cap"
            return
        if self.termination_policy == "drain_all":
            self._check_termination_drain_all()
        else:
            self._check_termination_delivery()

    def _check_termination_delivery(self) -> None:
        """R8: the run ends when the delivery system is done, not when the
        background happens to empty out. Pedestrians are stage furniture."""
        if not self._pipeline_empty():
            return
        if not self._delivery_complete():
            return
        if not self._carriers_settled():
            return
        self.running = False
        self.termination_reason = "delivery_complete"

    def _check_termination_drain_all(self) -> None:
        """Pre-R8 rule, kept verbatim for the frozen regression path."""
        # the congestion window must be simulated in full: pedestrians keep
        # spawning until ped_end_sec, so an "all drained" check before then is
        # a race against the Poisson stream (momentary zero ≠ done)
        if self.clock_sec < self.ped_end_sec:
            return
        if self.rider_events:
            return
        if self.dynamic_pool and (
            self.dispatch_events
            or self.pending_arrivals
            or self.pending_releases
            or self.rider_pool.waiting
        ):
            return
        if self.agents_of(self.rider_cls):
            return
        if any(c.delivered_at_sec is None for c in self.customer_by_ord_id.values()):
            return
        if self.agents_of(PedestrianAgent):
            return
        self.running = False
        self.termination_reason = "drain_all"

    # ------------------------------------------------------------- interface

    def run_to_completion(self, max_ticks: int | None = None) -> None:
        cap = max_ticks or int((self.cap_time_sec - self.clock_start_sec) / self.dt) + 1
        while self.running and self.tick_count < cap:
            self.step()
