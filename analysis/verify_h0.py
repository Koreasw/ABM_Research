"""H0 dynamic-track results verifier — V-AUD / Stage V1 (etc/plan_h0_verification.md §2 L2).

    python -m analysis.verify_h0 results/baseline_h0_K50_1_uniform_s42.json

The dynamic (paper-track) counterpart of analysis/verify_baseline.py. That
verifier is static-only (it joins the frozen v4 mapping + travel_times files);
the paper track is the dynamic rider pool + population-density floor profile,
which has no such files, so it needs its own post-hoc gate. verify_h0 reads a
simulation/run.py results JSON (dynamic_pool run) and runs nine PASS/FAIL
checks. Exit code 0 iff every non-skipped check passes; the same checks are
meant to be embedded as the mandatory post-run gate of every experiment run.

Checks (plan §2 L2 table A1..A9):

  A1 order conservation      delivered == K, no cap termination, unique ord_ids,
                             no residual agents at end.
  A2 time-chain monotonicity ord <= ready <= dispatch <= arrival <= entered
                             < delivered < exited; every segment >= 0.
  A3 dynamic arrival formula arrival == dispatch + dist/v(recorded type);
                             horizontal_time_s == dist_m / speed(type) (σ=0);
                             entered in [arrival, arrival + tick].
  A4 dynamic lower bound     t_e2e >= (ready-ord) + rider_wait + dist/v
                             + LB_internal (graph walk / v_walk + wait-free
                             vertical up-leg + service), a strict closed-form
                             floor (continuous, never a tick above actual).
  A5 t_lobby identity        stairs: exact tick-faithful decomposition
                             (walk legs + 2 stair timers + service) reproduces
                             t_lobby to the float epsilon. elevator: the ride
                             time is unrecorded, so the residual after removing
                             the (lower-bounded) walk legs, the recorded EV
                             waits and service must clear the kinematic ride
                             floor 2*(move(1,f)+door).
  A6 elevator consistency    boards == alights, zero capacity violations, and
                             empty hall queues / cars at end (no starvation).
  A7 assignment rule replay  a faithful RiderPool replay (recorded ready /
                             exit times drive dispatch / release events)
                             reproduces every rider_type and was_fallback flag;
                             same-tick exit-vs-dispatch ambiguity is handled by
                             a sub-multiset tolerance over same-tick releases
                             (see check docstring).
  A8 window consistency      ped window == [min ORD - margin, max ORD + margin],
                             clock starts at the window start, clock_end covers
                             the full window and stays under the overrun cap.
  A9 floor-profile conformance  provenance (floor_profile, floor_seed, config)
                             alone re-derives (floor, office_id, vertical_mode)
                             for every order via rederive_profile_assignment;
                             must match exactly. Report-only GOF (observed floor
                             histogram vs K*floor_probs, chi-square p-value) is
                             printed but is NOT a gate. SKIPPED when
                             floor_source != "profile" (frozen mapping run).

  A10 basement integrity     (v2, plan_h0v2_verification.md §3 L2) the config's
                             basements are boarding levels only: no office and
                             no corridor node on any floor <= 0; no order is
                             delivered below ground (riders never use them);
                             and every EV position stays inside the declared
                             service range in floor-rank units.
  A11 EV declaration parity  the KPI elevator keys are exactly the config's
                             declared EV ids, each car balances boardings
                             against alights, and no car ever overfilled.
  A12 hall-call exclusivity  no passenger is queued at two cars (or two floors)
                             at once -- checked tick-by-tick in the model's
                             audit mode, since a results JSON has no queue
                             census. Reported here as SKIPPED with a pointer.

  A13 warm-up adequacy       (R8-c) the building was WARM when the first order
                             landed, not merely scheduled to be: head >= 600 s
                             (measured background saturation), EV busy fraction
                             at the first order >= 0.35x the delivery window,
                             at least one pedestrian present, and the recorded
                             head agrees with the declared window. SKIPPED for
                             results predating R8-b (no `warmup` block).
  A14 termination reason     (R8-c) the run stopped for its declared reason and
                             not by cap; every order delivered and every rider
                             exited; under `delivery_complete` the clock stops
                             on the tick the LAST rider leaves (+/- 1 tick).
                             SKIPPED for results predating R8-b.

Per-tick conservation invariants (free + en_route + in_building + returning ==
initial, passengers <= capacity, hall-call exclusivity, basement boarders are
pedestrians) cannot be checked from a results JSON; they are covered by the
model's `audit=True` mode (simulation/run.py --audit).

A1 / A8 ARE POLICY-DEPENDENT SINCE R8-c. Under `window_policy: delivery` the
run ends when the delivery system is done, so (a) background pedestrians are
still in the building at the end -- A1 no longer requires zero -- and (b) the
window contract is head = warmup_sec / no spawn cutoff / cap measured from the
last order, which A8 checks instead of the legacy margin arithmetic. Applying
either legacy rule to a delivery run fails every correct run.

A10 NOTE -- THE ASSERTION WAS INVERTED ON 2026-08-04. The first draft of this
gate read "no basement exists" (floor <= 0 must never appear, ev floor series
>= 1.0). Plan §1.6 then added people-only basements B1/B2, so that phrasing now
fails a correct run. What survives from it is the *rider* half: riders and
robots still never go below ground; only background pedestrians do.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from itertools import product
from pathlib import Path

from analysis.load_data import load_riders, load_scenario
from analysis.rider_arrival_model import type_priority
from simulation.agents.walker import shortest_walk_only_path
from simulation.elevator_physics import ElevatorKinematics
from simulation.floor_demand import rederive_profile_assignment
from simulation.space import add_lobby_handoff_zones, build_from_config

ROOT = Path(__file__).resolve().parent.parent

FLOAT_TOL = 1e-6            # exact-equality comparisons serialized through JSON
STAIR_NODE_1F = "lobby_direct_corridor"   # keep in sync with external_rider.py


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str
    failures: list[str] = field(default_factory=list)
    skipped: bool = False


# --------------------------------------------------------------------- loading


def _resolve(path_str: str) -> Path:
    p = Path(path_str)
    return p if p.is_absolute() else ROOT / p


def load_inputs(result: dict) -> dict:
    """Attach the scenario (rider speeds / stock) referenced by the results JSON.

    The scenario file is always the run's own input, so it is available to any
    post-hoc gate; it supplies the rider table (speed, capacity, initial stock)
    needed for the independent A3 / A4 / A7 recomputations.
    """
    scenario_path = _resolve(result["scenario_path"])
    return {
        "res": result,
        "scenario": load_scenario(scenario_path),
        "riders": load_riders(scenario_path),
    }


def _tick(res: dict) -> float:
    return float(res["config"]["simulation"].get("tick_sec", 1.0))


# --------------------------------------------------------- discretization model
# Faithful reproductions of the ABM's tick arithmetic (simulation/agents/
# walker.py walk_tick, external_rider.py timers). They repeat the exact
# floating-point accumulation the model uses, so a distance whose /speed is an
# integer (e.g. 6 m / 1.2 = 5.0) still costs the extra tick the model spends
# because 5*1.2 == 5.9999999999999996 < 6.0. Any closed-form ceil() would
# mis-count those boundary cases.


def _walk_ticks(dist_m: float, speed: float, dt: float) -> int:
    """Ticks GraphWalker.walk_tick spends covering dist_m (>= 1)."""
    progress = 0.0
    ticks = 0
    while True:
        ticks += 1
        if speed * dt >= dist_m - progress:
            return ticks
        progress += speed * dt


def _timer_ticks(duration_s: float, dt: float) -> int:
    """Ticks a countdown timer (_timer -= dt until <= 0) spends (>= 1)."""
    remaining = duration_s
    ticks = 0
    while True:
        ticks += 1
        remaining -= dt
        if remaining <= 0.0:
            return ticks


# ---------------------------------------------------------------------- checks


def check_order_conservation(inp: dict) -> CheckResult:
    """A1: delivered == K, no cap termination, unique ord_ids, no residuals."""
    res = inp["res"]
    per_order = res["per_order"]
    kpi = res["kpi_summary"]
    mv = res["model_vars"]
    fails: list[str] = []

    ord_ids = [r["ord_id"] for r in per_order]
    if len(ord_ids) != len(set(ord_ids)):
        dups = sorted({i for i in ord_ids if ord_ids.count(i) > 1})
        fails.append(f"duplicate ord_id(s): {dups}")
    expected_ids = {o.ord_id for o in inp["scenario"].orders}
    if set(ord_ids) != expected_ids:
        fails.append(
            f"ord_id set mismatch: missing={sorted(expected_ids - set(ord_ids))} "
            f"extra={sorted(set(ord_ids) - expected_ids)}"
        )
    K = inp["scenario"].K
    counts = {
        "scenario K": K,
        "per_order records": len(per_order),
        "kpi n_orders": kpi["customer"]["n_orders"],
        "kpi n_delivered": kpi["customer"]["n_delivered"],
        "kpi riders exited": kpi["rider"]["n_exited"],
        "delivered records": sum(1 for r in per_order if r["delivered_at_sec"] is not None),
    }
    if len(set(counts.values())) != 1:
        fails.append(f"count mismatch: {counts}")
    if kpi["simulation"]["terminated_by_cap"]:
        fails.append("run hit horizon + max_overrun cap (incomplete)")
    if mv["riders_in_building"] and mv["riders_in_building"][-1] != 0:
        fails.append(f"residual riders at end: {mv['riders_in_building'][-1]}")
    # R8-c: residual pedestrians are a completion criterion ONLY under the
    # drain-all policy. The delivery policy stops the clock when the delivery
    # system is done, so background pedestrians are still walking around by
    # design — demanding zero there would fail every correct run. Their count
    # is reported (and sized by kpi pedestrian.n_in_building_at_end) instead.
    policy = kpi["simulation"].get("termination_policy", "drain_all")
    residual_peds = mv["peds_active"][-1] if mv["peds_active"] else 0
    if policy == "drain_all" and residual_peds != 0:
        fails.append(f"residual pedestrians at end: {residual_peds}")

    ped_note = (
        f", residual peds={residual_peds} (expected under {policy})"
        if policy != "drain_all" else ""
    )
    return CheckResult(
        "A1 order conservation",
        not fails,
        f"K={K}, delivered={counts['kpi n_delivered']}, "
        f"exited={counts['kpi riders exited']}, unique ord_ids={len(set(ord_ids))}, "
        f"cap={kpi['simulation']['terminated_by_cap']}{ped_note}",
        fails,
    )


def check_time_chain(inp: dict, tick: float) -> CheckResult:
    """A2: ord <= ready <= dispatch <= arrival <= entered < delivered < exited."""
    res = inp["res"]
    fails: list[str] = []
    # (label, a, b, strict): b - a >= 0, or > 0 when strict
    for rec in res["per_order"]:
        oid = rec["ord_id"]
        chain = [
            ("ord->ready", rec["ord_time_abs_sec"], rec["ready_time_sec"], False),
            ("ready->dispatch", rec["ready_time_sec"], rec["dispatch_time_sec"], False),
            ("dispatch->arrival", rec["dispatch_time_sec"],
             rec["arrival_time_planned_sec"], False),
            ("arrival->entered", rec["arrival_time_planned_sec"],
             rec["entered_at_sec"], False),
            ("entered->delivered", rec["entered_at_sec"], rec["delivered_at_sec"], True),
            ("delivered->exited", rec["delivered_at_sec"], rec["exited_at_sec"], True),
        ]
        for label, a, b, strict in chain:
            if a is None or b is None:
                fails.append(f"ord {oid}: {label} has None endpoint ({a}, {b})")
                continue
            gap = b - a
            if strict:
                if gap <= FLOAT_TOL:
                    fails.append(f"ord {oid}: {label} not strictly increasing ({gap:+.3f}s)")
            elif gap < -FLOAT_TOL:
                fails.append(f"ord {oid}: {label} decreasing ({gap:+.3f}s)")

    return CheckResult(
        "A2 time-chain monotonicity",
        not fails,
        f"{len(res['per_order'])} orders: ord<=ready<=dispatch<=arrival<=entered"
        "<delivered<exited",
        fails,
    )


def check_arrival_formula(inp: dict, tick: float) -> CheckResult:
    """A3: arrival == dispatch + dist/v(type); horizontal == dist_m/speed (σ=0)."""
    res = inp["res"]
    sigma = float(res["config"]["rider_process"].get("sigma_eps", 0.0))
    speed_by_type = {r.type: r.speed_mps for r in inp["riders"]}
    fails: list[str] = []
    max_entry_lag = 0.0

    for rec in res["per_order"]:
        oid = rec["ord_id"]
        # arrival == dispatch + horizontal_time_s (identity, any sigma)
        if abs(rec["arrival_time_planned_sec"]
               - (rec["dispatch_time_sec"] + rec["horizontal_time_s"])) > FLOAT_TOL:
            fails.append(
                f"ord {oid}: arrival {rec['arrival_time_planned_sec']:.4f} != "
                f"dispatch + horizontal {rec['dispatch_time_sec'] + rec['horizontal_time_s']:.4f}"
            )
        # horizontal_time_s == dist_m / speed(type) — exact only when σ=0
        if sigma == 0.0:
            speed = speed_by_type.get(rec["rider_type"])
            if speed is None:
                fails.append(f"ord {oid}: unknown rider_type {rec['rider_type']}")
            else:
                expected = rec["dist_m"] / speed
                if abs(rec["horizontal_time_s"] - expected) > FLOAT_TOL:
                    fails.append(
                        f"ord {oid}: horizontal {rec['horizontal_time_s']:.4f} != "
                        f"dist/v {expected:.4f} ({rec['rider_type']})"
                    )
        # entered is the first tick boundary >= arrival
        lag = rec["entered_at_sec"] - rec["arrival_time_planned_sec"]
        max_entry_lag = max(max_entry_lag, lag)
        if not (-FLOAT_TOL <= lag <= tick + FLOAT_TOL):
            fails.append(
                f"ord {oid}: entered lag {lag:+.4f}s outside [0, {tick}]"
            )

    note = "σ=0 exact" if sigma == 0.0 else f"σ={sigma} (dist/v identity relaxed)"
    return CheckResult(
        "A3 dynamic arrival formula",
        not fails,
        f"max entry lag {max_entry_lag:.3f}s (tolerance {tick}s); {note}",
        fails,
    )


def _graph_and_kin(res: dict):
    cfg = res["config"]
    g = add_lobby_handoff_zones(
        build_from_config(cfg),
        n_locker_compartments=cfg["locker"]["n_compartments"],
    )
    kin = ElevatorKinematics.from_config(cfg)
    return g, kin


def _walk_dist(g, source: str, target: str) -> float:
    return shortest_walk_only_path(g, source, target)[1]


def _up_walk_lb_m(g, rec: dict) -> float:
    """Lower-bound one-way (lobby -> vertical -> office) walking distance."""
    f, office = rec["floor"], rec["office_id"]
    office_node = f"floor_{f}_office_{office}"
    if rec["vertical_mode"] == "elevator":
        ev_ids = g.graph["ev_ids"]
        leg1 = min(_walk_dist(g, "lobby_entry", f"ev_{e}_1") for e in ev_ids)
        leg2 = min(_walk_dist(g, f"ev_{e}_{f}", office_node) for e in ev_ids)
        return leg1 + leg2
    leg1 = _walk_dist(g, "lobby_entry", STAIR_NODE_1F)
    leg2 = _walk_dist(g, f"floor_{f}_corr_{g.graph['corridor_mid_pos']}", office_node)
    return leg1 + leg2


def _vertical_up_lb_s(kin: ElevatorKinematics, rec: dict, cfg: dict) -> float:
    """Wait-free vertical up-leg lower bound (elevator: move + door; stairs)."""
    f = rec["floor"]
    if rec["vertical_mode"] == "elevator":
        return kin.travel_time_sec(1, f) + kin.door_open_close_sec
    return (f - 1) * cfg["vertical"]["stair_sec_per_floor"]


def check_lower_bound(inp: dict, tick: float) -> tuple[CheckResult, dict]:
    """A4: t_e2e >= (ready-ord)+rider_wait+dist/v+LB_internal (strict floor)."""
    res = inp["res"]
    cfg = res["config"]
    g, kin = _graph_and_kin(res)
    v_walk = cfg["rider_process"]["walk_speed_mps"]
    fails: list[str] = []
    slacks: list[float] = []

    for rec in res["per_order"]:
        cook = rec["ready_time_sec"] - rec["ord_time_abs_sec"]
        walk_lb = _up_walk_lb_m(g, rec) / v_walk
        vert_lb = _vertical_up_lb_s(kin, rec, cfg)
        lb = (
            cook
            + rec["rider_wait_sec"]
            + rec["horizontal_time_s"]
            + walk_lb
            + vert_lb
            + rec["service_time_sec"]
        )
        slack = rec["t_e2e_sec"] - lb
        slacks.append(slack)
        # LB is a *continuous* closed-form floor; t_e2e is tick-quantized. The
        # wait-free elevator up-leg (move + one door cycle) can overshoot the
        # actual board->alight span by a sub-tick at the door-cycle boundary
        # (boarding is logged mid-cycle, alighting at the start of the next),
        # so a single-tick allowance keeps the bound conservative — same rule
        # as analysis/verify_baseline.py check #4.
        if slack < -tick - FLOAT_TOL:
            fails.append(
                f"ord {rec['ord_id']}: t_e2e {rec['t_e2e_sec']:.1f}s < LB "
                f"{lb:.2f}s (deficit {-slack:.2f}s, tolerance {tick}s)"
            )

    n = len(slacks)
    report = {
        "slack_min_sec": min(slacks) if slacks else None,
        "slack_mean_sec": (sum(slacks) / n) if n else None,
        "slack_max_sec": max(slacks) if slacks else None,
    }
    return (
        CheckResult(
            "A4 dynamic lower bound",
            not fails,
            f"min slack {report['slack_min_sec']:.2f}s, mean "
            f"{report['slack_mean_sec']:.2f}s over {n} orders",
            fails,
        ),
        report,
    )


def check_lobby_identity(inp: dict, tick: float) -> CheckResult:
    """A5: exact stairs decomposition; elevator residual clears the ride floor."""
    res = inp["res"]
    cfg = res["config"]
    g, kin = _graph_and_kin(res)
    v_walk = cfg["rider_process"]["walk_speed_mps"]
    sps = cfg["vertical"]["stair_sec_per_floor"]
    door = kin.door_open_close_sec
    l1_stair = _walk_dist(g, "lobby_entry", STAIR_NODE_1F)
    fails: list[str] = []
    max_stair_resid = 0.0
    min_elev_slack = math.inf

    for rec in res["per_order"]:
        f, office = rec["floor"], rec["office_id"]
        office_node = f"floor_{f}_office_{office}"
        svc_ticks = _timer_ticks(rec["service_time_sec"], tick) * tick

        if rec["vertical_mode"] == "stairs":
            l2 = _walk_dist(g, f"floor_{f}_corr_{g.graph['corridor_mid_pos']}", office_node)
            climb = _timer_ticks((f - 1) * sps, tick) * tick
            w1 = _walk_ticks(l1_stair, v_walk, tick) * tick
            w2 = _walk_ticks(l2, v_walk, tick) * tick
            # first leg (walk_to_vert) shares the creation tick: -1 tick
            recon = (w1 - tick) + climb + w2 + svc_ticks + w2 + climb + w1
            resid = abs(rec["t_lobby_sec"] - recon)
            max_stair_resid = max(max_stair_resid, resid)
            if resid > FLOAT_TOL:
                fails.append(
                    f"ord {rec['ord_id']} (stairs f{f}): t_lobby {rec['t_lobby_sec']:.1f} "
                    f"!= decomposition {recon:.1f} (resid {resid:.3f})"
                )
        else:
            # lower-bound walk time (min EV, creation-tick -1): residual is an
            # upper estimate of the unrecorded total ride time -> must clear floor
            ev_ids = g.graph["ev_ids"]
            leg1 = min(_walk_dist(g, "lobby_entry", f"ev_{e}_1") for e in ev_ids)
            leg2 = min(_walk_dist(g, f"ev_{e}_{f}", office_node) for e in ev_ids)
            w1 = _walk_ticks(leg1, v_walk, tick) * tick
            w2 = _walk_ticks(leg2, v_walk, tick) * tick
            walk_lb = (w1 - tick) + w2 + w2 + w1
            wu = rec["ev_wait_up_sec"] or 0.0
            wd = rec["ev_wait_down_sec"] or 0.0
            residual = rec["t_lobby_sec"] - walk_lb - wu - wd - svc_ticks
            ride_floor = 2.0 * (kin.travel_time_sec(1, f) + door)
            min_elev_slack = min(min_elev_slack, residual - ride_floor)
            if residual < -FLOAT_TOL:
                fails.append(
                    f"ord {rec['ord_id']} (elev f{f}): negative ride residual {residual:.2f}s"
                )
            elif residual < ride_floor - FLOAT_TOL:
                fails.append(
                    f"ord {rec['ord_id']} (elev f{f}): ride residual {residual:.2f}s < "
                    f"kinematic floor {ride_floor:.2f}s"
                )

    slack_txt = "n/a" if min_elev_slack is math.inf else f"{min_elev_slack:.2f}s"
    return CheckResult(
        "A5 t_lobby identity",
        not fails,
        f"stairs residual max {max_stair_resid:.3g}s (exact); "
        f"elevator min ride-floor slack {slack_txt}",
        fails,
    )


def _pax_on_board_at_end(mv: dict, ev_id: str) -> int:
    """Passengers still riding `ev_id` on the final tick (0 under drain-all)."""
    vals = mv.get(f"{ev_id.lower()}_pax")
    return int(vals[-1]) if vals else 0


def check_elevator_consistency(inp: dict) -> CheckResult:
    """A6: passenger conservation per car, zero capacity violations, no starvation.

    R8-c generalised the balance test. The invariant is not "boards == alights"
    but **boards - alights == passengers still on board**; under the drain-all
    policy that residual is zero and the two are the same statement, so the
    frozen results are unaffected. Under `delivery` the run stops when the last
    RIDER leaves, which can catch background pedestrians mid-ride — the old
    equality would then fail every correct run, and weakening it to an
    inequality would have stopped testing anything. The identity keeps the
    conservation claim exact under both policies.
    """
    res = inp["res"]
    kpi = res["kpi_summary"]
    mv = res["model_vars"]
    policy = kpi["simulation"].get("termination_policy", "drain_all")
    fails: list[str] = []

    residual_total = 0
    for ev_id, ev in kpi["elevator"].items():
        pax_end = _pax_on_board_at_end(mv, ev_id)
        residual_total += pax_end
        if ev["n_boardings"] - ev["n_alights"] != pax_end:
            fails.append(
                f"{ev_id}: boardings {ev['n_boardings']} - alights {ev['n_alights']} "
                f"!= passengers still on board {pax_end}"
            )
        if ev["capacity_violations"] != 0:
            fails.append(f"{ev_id}: {ev['capacity_violations']} capacity violation(s)")
        if not 0.0 <= ev["utilization"] <= 1.0:
            fails.append(f"{ev_id}: utilization {ev['utilization']} outside [0, 1]")

    # Empty cars and queues at the end are a completion criterion of the
    # drain-all policy only. Under `delivery` a leftover is a background
    # pedestrian by construction — A1 independently requires that no RIDER is
    # left in the building — so it is reported, not failed.
    ev_series = [
        f"{ev_id.lower()}_{sfx}"
        for ev_id in kpi["elevator"]
        for sfx in ("queue", "pax")
    ]
    queue_end = sum(
        (mv.get(f"{ev_id.lower()}_queue") or [0])[-1] for ev_id in kpi["elevator"]
    )
    if policy == "drain_all":
        for series in ev_series:
            vals = mv.get(series)
            if vals and vals[-1] != 0:
                fails.append(
                    f"{series} nonzero at end: {vals[-1]} (starvation / stuck car)"
                )

    boards = sum(ev["n_boardings"] for ev in kpi["elevator"].values())
    tail = (
        "cars/queues empty at end"
        if policy == "drain_all"
        else f"{residual_total} rider(s)+ped(s) aboard / {queue_end} queued at end "
             f"(background, expected under {policy})"
    )
    return CheckResult(
        "A6 elevator consistency",
        not fails,
        f"{boards} boardings, per-car conservation holds, "
        f"0 capacity violations, {tail}",
        fails,
    )


def _priority_pick(priority: list[str], stock: dict[str, int]) -> tuple[str | None, int | None]:
    """First type in cost-priority order with positive stock (type, rank)."""
    for i, t in enumerate(priority):
        if stock.get(t, 0) > 0:
            return t, i
    return None, None


def check_assignment_replay(inp: dict, tick: float) -> CheckResult:
    """A7: a faithful RiderPool replay reproduces every type + was_fallback.

    Recorded ready / dispatch / exit times drive a discrete-event replay of the
    pool. Within one tick the model's sub-phase order is: return_leg deferred
    releases (step start) -> new-ready dispatches (_dispatch_riders) -> rider
    exits, whose immediate releases (return_leg=False) can grant queued orders
    at the *same* timestamp. The JSON cannot order a same-tick dispatch among
    that tick's exits, so each dispatch is accepted if the cost-priority
    cascade selects the recorded rider_type under free + S for ANY sub-multiset
    S of the same-tick releases (S = ∅ is the pre-exit snapshot). A genuinely
    wrong assignment matches no S; the fallback flag reduces to `got`'s fixed
    index in the priority list (identical across matching S). return_leg
    releases are quantized up to the next tick boundary, mirroring
    _process_pending_releases. Global conservation (free == initial after all
    events) is enforced at the end.
    """
    res = inp["res"]
    riders = inp["riders"]
    vol_by_ord = {o.ord_id: o.vol for o in inp["scenario"].orders}
    initial = {r.type: int(r.available_number) for r in riders}
    free = dict(initial)
    speed_by_type = {r.type: r.speed_mps for r in riders}
    return_leg = bool(res.get("return_leg", False))
    fails: list[str] = []

    dispatches: list[tuple] = []
    releases: list[tuple[float, str]] = []
    for rec in res["per_order"]:
        dispatches.append(
            (rec["dispatch_time_sec"], rec["ready_time_sec"], rec["ord_id"], rec)
        )
        rel = rec["exited_at_sec"]
        if return_leg:
            # model defers by the return trip, applied at the next tick boundary
            rel += rec["dist_m"] / speed_by_type[rec["rider_type"]]
            rel = math.ceil(rel / tick - FLOAT_TOL) * tick
        releases.append((rel, rec["rider_type"]))
    # dispatches ordered by time, then ready_time (queued before new-ready),
    # then ord_id; releases consumed by time.
    dispatches.sort(key=lambda e: (e[0], e[1], e[2]))
    releases.sort(key=lambda e: e[0])

    n_fallback = 0
    ri = 0  # next unapplied release
    for time, _ready, oid, rec in dispatches:
        # releases strictly before this dispatch time are certainly applied
        while ri < len(releases) and releases[ri][0] < time - FLOAT_TOL:
            t = releases[ri][1]
            free[t] = free.get(t, 0) + 1
            ri += 1
        # same-tick releases: may or may not precede this dispatch in the model
        same_tick: dict[str, int] = {}
        j = ri
        while j < len(releases) and releases[j][0] <= time + FLOAT_TOL:
            same_tick[releases[j][1]] = same_tick.get(releases[j][1], 0) + 1
            j += 1

        eligible = [r for r in riders if r.capa >= vol_by_ord[oid]]
        priority = type_priority(eligible, rec["dist_m"])
        got = rec["rider_type"]

        # candidate stocks: free + S for every sub-multiset S of the same-tick
        # releases (S = ∅ is the pre-release snapshot). Exits within one tick
        # are unordered relative to this dispatch — the model applies them in
        # agent-iteration order, which the JSON cannot recover — so ANY subset
        # may have landed first (V4a found a CAR-before/BIKE-after interleaving
        # that the earlier pre/post two-snapshot tolerance could not express).
        # A genuinely wrong type matches no subset: whenever a higher-priority
        # type is free in `free` itself it stays free in every superset. When
        # the pick is `got`, its rank is `got`'s fixed index in the priority
        # list, identical across all matching subsets — so the fallback flag
        # needs no per-subset handling.
        matched = False
        rel_types = sorted(same_tick)
        for combo in product(*(range(same_tick[t] + 1) for t in rel_types)):
            stock = dict(free)
            for t, c in zip(rel_types, combo):
                stock[t] = stock.get(t, 0) + c
            if _priority_pick(priority, stock)[0] == got:
                matched = True
                break
        if not matched:
            if free.get(got, 0) + same_tick.get(got, 0) <= 0:
                fails.append(f"ord {oid}: dispatched {got} with no free stock in replay")
            else:
                fails.append(
                    f"ord {oid}: type {got} != cost-priority pick "
                    f"{_priority_pick(priority, free)[0]} (priority {priority}, "
                    f"no same-tick release interleaving explains it)"
                )
        else:
            got_rank = priority.index(got)
            if bool(rec["was_fallback"]) != bool(got_rank):
                fails.append(
                    f"ord {oid}: was_fallback {rec['was_fallback']} != replay "
                    f"{bool(got_rank)} (rank {got_rank})"
                )
        free[got] = free.get(got, 0) - 1  # keep accounting aligned with reality
        if rec["was_fallback"]:
            n_fallback += 1

    for rel_t, t in releases[ri:]:
        free[t] = free.get(t, 0) + 1
    if free != initial:
        fails.append(f"pool conservation broken after replay: free {free} != initial {initial}")

    n_wait = sum(1 for r in res["per_order"] if (r["rider_wait_sec"] or 0) > 0)
    return CheckResult(
        "A7 assignment rule replay",
        not fails,
        f"{len(res['per_order'])} dispatches reproduced "
        f"({n_fallback} fallback, {n_wait} queued)",
        fails,
    )


def check_window(inp: dict, tick: float) -> CheckResult:
    """A8: ped window == order span +/- margin; clock covers it under the cap.

    R8-c: the `delivery` policy has a different window contract entirely — the
    head is `warmup_sec` (not a borrowed pedestrian margin), there is NO
    pedestrian spawn cutoff (ped_end is pinned to the cap), the cap is measured
    from the LAST order, and the clock stops at the last rider exit instead of
    covering the background window. Applying the legacy arithmetic there would
    fail every correct run, so the two contracts are checked separately.
    """
    res = inp["res"]
    cfg = res["config"]
    win = res["window"]
    kpi_sim = res["kpi_summary"]["simulation"]
    fails: list[str] = []

    ord_abs = [r["ord_time_abs_sec"] for r in res["per_order"]]
    ord_min, ord_max = min(ord_abs), max(ord_abs)
    margin = float(cfg["pedestrian"].get("window_margin_sec", 3600.0))
    max_overrun = float(cfg["simulation"].get("max_overrun_sec", 3600.0))

    if kpi_sim.get("window_policy", "legacy_margin") == "delivery":
        warmup = float(kpi_sim.get("warmup_sec", cfg["simulation"].get("warmup_sec", 600.0)))
        exits = [r["exited_at_sec"] for r in res["per_order"]
                 if r["exited_at_sec"] is not None]
        last_exit = max(exits) if exits else None
        clock_end = kpi_sim["clock_end_sec"]
        if abs(win["clock_start_sec"] - (ord_min - warmup)) > FLOAT_TOL:
            fails.append(
                f"clock_start {win['clock_start_sec']} != min ORD - warmup "
                f"{ord_min - warmup}"
            )
        if abs(win["cap_time_sec"] - (ord_max + max_overrun)) > FLOAT_TOL:
            fails.append(
                f"cap {win['cap_time_sec']} != max ORD + max_overrun "
                f"{ord_max + max_overrun}"
            )
        # ped_end == cap is how "no spawn cutoff" is encoded; a ped_end below
        # the cap would silently reintroduce the late-order background bias
        if abs(win["ped_end_sec"] - win["cap_time_sec"]) > FLOAT_TOL:
            fails.append(
                f"ped_end {win['ped_end_sec']} != cap {win['cap_time_sec']} — the "
                "delivery policy must not cut the background stream short"
            )
        if abs(win["clock_start_sec"] - win["ped_start_sec"]) > FLOAT_TOL:
            fails.append(
                f"clock_start {win['clock_start_sec']} != ped_start {win['ped_start_sec']}"
            )
        if last_exit is not None and clock_end < last_exit - FLOAT_TOL:
            fails.append(f"clock_end {clock_end} < last rider exit {last_exit}")
        if clock_end > win["cap_time_sec"] + FLOAT_TOL:
            fails.append(f"clock_end {clock_end} > cap {win['cap_time_sec']} (overrun)")
        exit_txt = f"{last_exit:.0f}" if last_exit is not None else "n/a"
        return CheckResult(
            "A8 window consistency",
            not fails,
            f"delivery policy: head {warmup:.0f}s, orders "
            f"[{ord_min:.0f}, {ord_max:.0f}], clock_end {clock_end:.0f}, "
            f"last exit {exit_txt}, cap {win['cap_time_sec']:.0f}",
            fails,
        )

    if res.get("scenario_window", True):
        exp_ped_start = ord_min - margin
        exp_ped_end = ord_max + margin
        if abs(win["ped_start_sec"] - exp_ped_start) > FLOAT_TOL:
            fails.append(
                f"ped_start {win['ped_start_sec']} != min ORD - margin {exp_ped_start}"
            )
        if abs(win["ped_end_sec"] - exp_ped_end) > FLOAT_TOL:
            fails.append(
                f"ped_end {win['ped_end_sec']} != max ORD + margin {exp_ped_end}"
            )
    # clock starts at the window start, first order lies inside the window
    if abs(win["clock_start_sec"] - win["ped_start_sec"]) > FLOAT_TOL:
        fails.append(
            f"clock_start {win['clock_start_sec']} != ped_start {win['ped_start_sec']}"
        )
    if ord_min < win["ped_start_sec"] - FLOAT_TOL:
        fails.append(f"first order {ord_min} precedes ped_start {win['ped_start_sec']}")
    # cap arithmetic + full-window coverage without overrun
    if abs(win["cap_time_sec"] - (win["ped_end_sec"] + max_overrun)) > FLOAT_TOL:
        fails.append("cap_time != ped_end + max_overrun")
    clock_end = kpi_sim["clock_end_sec"]
    if clock_end < win["ped_end_sec"] - FLOAT_TOL:
        fails.append(f"clock_end {clock_end} < ped_end {win['ped_end_sec']} (window truncated)")
    if clock_end > win["cap_time_sec"] + FLOAT_TOL:
        fails.append(f"clock_end {clock_end} > cap {win['cap_time_sec']} (overrun)")

    return CheckResult(
        "A8 window consistency",
        not fails,
        f"ped window [{win['ped_start_sec']:.0f}, {win['ped_end_sec']:.0f}], "
        f"orders [{ord_min:.0f}, {ord_max:.0f}], clock_end {clock_end:.0f}, margin {margin:.0f}s",
        fails,
    )


def _gof(res: dict) -> dict | None:
    """Report-only chi-square GOF: observed floor histogram vs K*floor_probs."""
    probs = res.get("floor_probs")
    if not probs:
        return None
    n_floors = res["config"]["building"]["n_floors"]
    floors = list(range(2, n_floors + 1))
    obs = {f: 0 for f in floors}
    for rec in res["per_order"]:
        if rec["floor"] in obs:
            obs[rec["floor"]] += 1
    K = len(res["per_order"])
    observed = [obs[f] for f in floors]
    expected = [K * p for p in probs]
    try:
        from scipy.stats import chisquare

        stat, pval = chisquare(observed, f_exp=expected)
        stat, pval = float(stat), float(pval)
    except Exception:
        stat = sum(
            (o - e) ** 2 / e for o, e in zip(observed, expected) if e > 0
        )
        pval = None
    return {
        "floors": floors,
        "observed": observed,
        "expected": [round(e, 2) for e in expected],
        "chi2": round(stat, 3),
        "p_value": (round(pval, 4) if pval is not None else None),
        "dof": len(floors) - 1,
    }


def check_floor_profile(inp: dict) -> tuple[CheckResult, dict | None]:
    """A9: rederive (floor, office, mode) from provenance; must match exactly.

    SKIPPED for frozen mapping runs (floor_source != "profile"). Returns the
    report-only GOF stats alongside the gate result.
    """
    res = inp["res"]
    source = res.get("floor_source")
    if source != "profile":
        return (
            CheckResult(
                "A9 floor-profile conformance",
                True,
                f"SKIP: floor_source={source!r} (frozen mapping run, not profile track)",
                skipped=True,
            ),
            None,
        )

    profile = res["floor_profile"]
    floor_seed = res["floor_seed"]
    ord_ids = [r["ord_id"] for r in res["per_order"]]
    rederived = rederive_profile_assignment(
        res["config"], profile, floor_seed, ord_ids
    )
    fails: list[str] = []
    for rec in res["per_order"]:
        oid = rec["ord_id"]
        exp = rederived.get(oid)
        got = (rec["floor"], rec["office_id"], rec["vertical_mode"])
        if exp != got:
            fails.append(f"ord {oid}: (floor,office,mode)={got} != rederived {exp}")

    gof = _gof(res)
    gof_txt = ""
    if gof is not None:
        pv = gof["p_value"]
        gof_txt = f"; GOF chi2={gof['chi2']} p={pv} (report-only)"
    return (
        CheckResult(
            "A9 floor-profile conformance",
            not fails,
            f"profile={profile!r} floor_seed={floor_seed}: {len(ord_ids)} orders "
            f"re-derived exactly{gof_txt}",
            fails,
        ),
        gof,
    )



# ------------------------------------------------------- A10 basement integrity


def _declared_floors(res: dict) -> tuple[int, int]:
    """(n_basements, n_floors) as the run's own config declared them."""
    b = res["config"]["building"]
    return int(b.get("n_basements", 0)), int(b["n_floors"])


def basement_structure_failures(g, n_basements: int, ev_ids: list[str]) -> list[str]:  # noqa: ANN001
    """A10-1 as a pure graph predicate: basements carry boarding nodes only.

    Split out of :func:`check_basement_integrity` so it can be exercised against
    a deliberately malformed graph. The config-driven builder cannot currently
    put an office below ground, so a negative test has to corrupt the graph
    directly — and an invariant with no reachable counter-example is one nobody
    has ever seen fail.
    """
    fails: list[str] = []
    expected = sorted(["floor_center"] + ["elevator"] * len(ev_ids))
    for floor in (-i for i in range(n_basements, 0, -1)):
        kinds = sorted(
            d.get("type") for _n, d in g.nodes(data=True) if d.get("floor") == floor
        )
        if kinds != expected:
            fails.append(
                f"basement floor {floor}: node types {kinds} != expected {expected} "
                "(a basement must carry only a floor_center and one stop per EV)"
            )
    stray = sorted(
        n for n, d in g.nodes(data=True)
        if (d.get("floor") is not None and d["floor"] < 0
            and d.get("type") in {"office", "corridor", "support", "locker_compartment"})
    )
    if stray:
        fails.append(f"occupiable node(s) below ground: {stray[:10]}")
    return fails


def check_basement_integrity(inp: dict) -> CheckResult:
    """A10: basements are people-only boarding levels, and riders stay above ground.

    Three independent sub-claims (plan_h0v2_verification.md §3 L2 A10-1..A10-3),
    all derivable from the results JSON alone:

      A10-1 structure — rebuild the graph from the run's *own* config and assert
            every floor <= 0 carries exactly one floor_center plus one stop node
            per declared EV: no office, no corridor, no support node. This is
            what makes a basement a boarding level rather than an occupied
            floor, and it is checked against the config the run actually used,
            not against the repo's current default config.
      A10-2 riders — no order is delivered below ground. Basements exist to load
            the cars with background pedestrian traffic (plan §1.6); riders enter
            at the 1F lobby and serve office floors, and the robot idles at 1F.
            An order on floor <= 0 would mean the delivery path reached a level
            that has no office to deliver to.
      A10-3 EV range — every recorded car position lies within the declared
            service range, expressed in floor RANK (B2 = -1, B1 = 0, 1F = 1),
            which is the unit `ev{i}_floor` is reported in. A car outside that
            band means the shaft was wired to a floor the building does not
            declare.

    Inversion note: the pre-§1.6 draft of A10 asserted the opposite ("no floor
    <= 0 anywhere, ev floor series >= 1.0"). Implementing that text today would
    fail every correct run. The rider half is what carried over.
    """
    res = inp["res"]
    n_basements, n_floors = _declared_floors(res)
    fails: list[str] = []

    # --- A10-1 structure -----------------------------------------------------
    g = add_lobby_handoff_zones(
        build_from_config(res["config"]),
        n_locker_compartments=res["config"]["locker"]["n_compartments"],
    )
    declared_evs = list(g.graph["ev_ids"])
    fails.extend(basement_structure_failures(g, n_basements, declared_evs))

    # --- A10-2 riders --------------------------------------------------------
    below = [
        o["ord_id"] for o in res["per_order"]
        if o.get("floor") is not None and o["floor"] <= 0
    ]
    if below:
        fails.append(
            f"{len(below)} order(s) delivered below ground (ord_id {below[:10]}) — "
            "riders must not use the basements"
        )

    # --- A10-3 EV service range ---------------------------------------------
    # ev{i}_floor is in rank units: rank(B2) = -1, rank(B1) = 0, rank(1F) = 1.
    lo_rank = 1 - n_basements
    mv = res["model_vars"]
    for ev_id in res["kpi_summary"]["elevator"]:
        series = mv.get(f"{ev_id.lower()}_floor")
        if not series:
            fails.append(f"{ev_id}: no {ev_id.lower()}_floor series to range-check")
            continue
        lo, hi = min(series), max(series)
        if lo < lo_rank - FLOAT_TOL or hi > n_floors + FLOAT_TOL:
            fails.append(
                f"{ev_id}: position range [{lo}, {hi}] outside declared service "
                f"range [{lo_rank}, {n_floors}] (rank units)"
            )

    reached = [
        ev_id for ev_id in res["kpi_summary"]["elevator"]
        if (s := mv.get(f"{ev_id.lower()}_floor")) and min(s) < 1.0 - FLOAT_TOL
    ]
    detail = (
        f"{n_basements} basement level(s), riders 0 below ground, "
        f"{len(reached)}/{len(declared_evs)} car(s) actually served a basement"
    )
    if n_basements and not reached:
        # not a failure: a short run may simply never have drawn a basement trip
        detail += " (none reached — check pedestrian.ground_split if unexpected)"
    return CheckResult("A10 basement integrity", not fails, detail, fails)


# ------------------------------------------------------ A11 EV declaration parity


def check_ev_declaration(inp: dict) -> CheckResult:
    """A11: KPI elevator keys == declared EV ids, and each car balances.

    The fleet is declarative (config `ev_corridor_positions_m`/`ev_sides` size it,
    `shared_ev_ids` marks the robot-shareable cars). This gate closes the loop at
    *runtime*: the KPI schema a run emitted must name exactly the cars its config
    declared -- neither dropping one nor inventing one -- so an N-EV
    generalisation bug cannot hide behind aggregate KPIs that still look sane.

    A6 already checks the per-car passenger identity and capacity_violations == 0
    from the same fields; they are re-asserted here per declared id so that a
    *missing* car (which A6 would simply not iterate over) still fails.
    """
    res = inp["res"]
    g = build_from_config(res["config"])
    declared = list(g.graph["ev_ids"])
    reported = list(res["kpi_summary"]["elevator"])
    fails: list[str] = []

    if sorted(declared) != sorted(reported):
        fails.append(
            f"KPI elevator keys {reported} != config-declared EV ids {declared}"
        )

    mv = res["model_vars"]
    for ev_id in declared:
        ev = res["kpi_summary"]["elevator"].get(ev_id)
        if ev is None:
            fails.append(f"{ev_id}: declared in config but absent from kpi_summary")
            continue
        # same identity as A6 (see its docstring): the residual is whoever is
        # still riding when the run stops, which is 0 under the drain-all policy
        pax_end = _pax_on_board_at_end(mv, ev_id)
        if ev["n_boardings"] - ev["n_alights"] != pax_end:
            fails.append(
                f"{ev_id}: {ev['n_boardings']} boardings - {ev['n_alights']} alights "
                f"!= {pax_end} still on board"
            )
        if ev["capacity_violations"] != 0:
            fails.append(f"{ev_id}: {ev['capacity_violations']} capacity violation(s)")
        for sfx in ("queue", "floor", "pax", "util_window"):
            if f"{ev_id.lower()}_{sfx}" not in mv:
                fails.append(f"{ev_id}: model_vars is missing {ev_id.lower()}_{sfx}")

    return CheckResult(
        "A11 EV declaration parity",
        not fails,
        f"{len(declared)} declared EV(s) {declared} all reported and balanced",
        fails,
    )


# ------------------------------------------------------ A12 hall-call exclusivity


def check_hall_call_exclusivity(inp: dict) -> CheckResult:
    """A12: a passenger is never queued at two cars at once — audit-mode only.

    A results JSON records queue *lengths*, never queue membership, so the claim
    is not decidable here: two cars each reporting one waiter is indistinguishable
    from one passenger double-registered. The real gate is the tick-level assert
    in `BuildingHandoffModel._audit_invariants` (run with `--audit`), which sees
    the actual deques. This check is reported as SKIPPED rather than silently
    passing, so a report that never ran the audit cannot be mistaken for one that
    did.

    The one thing that *is* decidable post-hoc is the necessary condition below:
    total waiters across cars can never exceed the passengers that could be
    waiting, and every queue must drain by the end (A6 covers the latter).
    """
    res = inp["res"]
    mv = res["model_vars"]
    fails: list[str] = []
    for ev_id in res["kpi_summary"]["elevator"]:
        series = mv.get(f"{ev_id.lower()}_queue")
        if series and min(series) < 0:
            fails.append(f"{ev_id}: negative queue length {min(series)}")
    return CheckResult(
        "A12 hall-call exclusivity",
        not fails,
        "not decidable from a results JSON — enforced tick-by-tick by "
        "model audit=True (simulation/run.py --audit); queue lengths sane here",
        fails,
        skipped=True,
    )


# ------------------------------------------------------- R8-c gates A13 / A14

# A13-2 threshold. Measured 2026-08-05 (n=80: K100_1 + K300_4 x warm-up head
# {0,300,600,900} x 10 seeds, delivery policy, `scratchpad/a13_threshold.csv`):
#
#   head    ratio = util_at_first_order / utilization_delivery
#     0     mean 0.000   min 0.000   max 0.000    <- every one of 20 runs
#   300     mean 0.732   min 0.498
#   600     mean 0.859   min 0.628
#   900     mean 0.851   min 0.554
#
# A cold building scores EXACTLY zero (no pedestrians, no EV movement), so the
# two populations are separated by the whole interval (0.000, 0.554]. The
# threshold sits at 0.35 — 4σ below the head=600 mean, which keeps the gate from
# firing on an unlucky seed, while still catching the failure it exists for
# (warm-up skipped, or the pedestrian stream switched off). The plan's first
# draft said 0.6, derived from 8-SEED MEANS; single-seed spread (σ ≈ 0.13) makes
# that a false-FAIL generator — the head=900 minimum is 0.554.
WARMUP_RATIO_FLOOR = 0.35
WARMUP_MIN_HEAD_SEC = 600.0   # measured background saturation time (plan §1.1)


def check_warmup_adequacy(inp: dict) -> CheckResult:
    """A13: the building was actually warm when the first order landed.

    SKIPPED for results produced before R8-b, which carry no `warmup` block.
    That skip is deliberate and loud: a silent PASS on a missing measurement is
    exactly the trap HANDOFF_v2 §3.4 records for A12.
    """
    res = inp["res"]
    kpi_sim = res["kpi_summary"]["simulation"]
    warmup = kpi_sim.get("warmup")
    if warmup is None:
        return CheckResult(
            "A13 warm-up adequacy", True,
            "SKIPPED — results predate R8-b (no kpi_summary.simulation.warmup); "
            "re-run the scenario to gate this",
            skipped=True,
        )
    fails: list[str] = []
    evs = res["kpi_summary"]["elevator"]

    # A13-3 (structural) first: a snapshot that disagrees with the declared
    # window makes the empirical test meaningless, so check it before using it.
    win = res["window"]
    ord_abs = [r["ord_time_abs_sec"] for r in res["per_order"]]
    head_expected = min(ord_abs) - win["clock_start_sec"] if ord_abs else None
    if head_expected is not None and abs(warmup["head_sec"] - head_expected) > FLOAT_TOL:
        fails.append(
            f"warmup.head_sec {warmup['head_sec']} != min ORD - clock_start "
            f"{head_expected}"
        )

    # A13-1 (config): the head must cover the measured saturation time.
    if warmup["head_sec"] < WARMUP_MIN_HEAD_SEC - FLOAT_TOL:
        fails.append(
            f"warm-up head {warmup['head_sec']:.0f}s < {WARMUP_MIN_HEAD_SEC:.0f}s "
            "(background traffic needs 300~600 s to saturate, plan §1.1)"
        )

    # A13-2 (empirical): was it actually busy, or merely scheduled to be?
    #
    # Only applicable when the config declares a background stream. With
    # `arrival_rate_per_min == 0` there is nothing to warm the building WITH, so
    # a zero busy fraction is the correct outcome, not a defect — that is the
    # deliberate design of the golden-path fixtures and of the zero-pedestrian
    # extreme case. The structural and head-length arms above stay live either
    # way, so this is a narrowing of scope, not a blanket skip.
    ped_rate = float(res["config"]["pedestrian"].get("arrival_rate_per_min", 0.0))
    util_delivery = [
        e["utilization_delivery"] for e in evs.values()
        if e.get("utilization_delivery") is not None
    ]
    ratio = None
    if ped_rate > 0:
        if util_delivery:
            mean_delivery = sum(util_delivery) / len(util_delivery)
            if mean_delivery > 0:
                ratio = warmup["util_at_first_order"] / mean_delivery
                if ratio < WARMUP_RATIO_FLOOR:
                    fails.append(
                        f"EV busy fraction at the first order is "
                        f"{warmup['util_at_first_order']:.3f}, only {ratio:.2f}x the "
                        f"delivery-window {mean_delivery:.3f} (floor "
                        f"{WARMUP_RATIO_FLOOR}) — the building was cold"
                    )
        if warmup["peds_at_first_order"] <= 0:
            fails.append(
                "no pedestrian was in the building when the first order landed "
                f"(background stream declares {ped_rate}/min)"
            )

    ratio_txt = f"{ratio:.2f}" if ratio is not None else "n/a"
    empirical = (
        f"EV busy at first order {warmup['util_at_first_order']:.3f} "
        f"({ratio_txt}x delivery window, floor {WARMUP_RATIO_FLOOR}), "
        f"peds {warmup['peds_at_first_order']} "
        f"(waiting {warmup['peds_waiting_at_first_order']}), "
        f"{warmup['ped_boardings_per_min']:.1f} boardings/min"
        if ped_rate > 0
        else "empirical arms N/A — no background stream (arrival_rate_per_min == 0)"
    )
    return CheckResult(
        "A13 warm-up adequacy",
        not fails,
        f"head {warmup['head_sec']:.0f}s, {empirical}",
        fails,
    )


def check_termination_reason(inp: dict) -> CheckResult:
    """A14: the run stopped for the declared reason, at the right instant.

    The distinctive claim of the `delivery` policy is that the clock stops on
    the tick the LAST rider leaves the building. That is checkable to the tick
    and is what separates "terminated correctly" from "terminated because some
    unrelated condition happened to be true".
    """
    res = inp["res"]
    kpi = res["kpi_summary"]
    kpi_sim = kpi["simulation"]
    if "termination_reason" not in kpi_sim:
        return CheckResult(
            "A14 termination reason", True,
            "SKIPPED — results predate R8-b (no termination_reason recorded)",
            skipped=True,
        )
    fails: list[str] = []
    reason = kpi_sim["termination_reason"]
    policy = kpi_sim.get("termination_policy", "drain_all")
    tick = _tick(res)

    if reason == "cap":
        fails.append("terminated by cap — the run is incomplete")
    elif reason != policy:
        fails.append(f"termination_reason {reason!r} != declared policy {policy!r}")

    if kpi["customer"]["n_delivered"] != kpi["customer"]["n_orders"]:
        fails.append(
            f"stopped with {kpi['customer']['n_orders'] - kpi['customer']['n_delivered']}"
            " order(s) undelivered"
        )
    exits = [r["exited_at_sec"] for r in res["per_order"] if r["exited_at_sec"] is not None]
    if len(exits) != len(res["per_order"]):
        fails.append(f"{len(res['per_order']) - len(exits)} rider(s) never exited")

    clock_end = kpi_sim["clock_end_sec"]
    if reason == "delivery_complete" and exits:
        last_exit = max(exits)
        if abs(clock_end - last_exit) > tick + FLOAT_TOL:
            fails.append(
                f"clock_end {clock_end} is {clock_end - last_exit:.0f}s past the last "
                f"rider exit {last_exit} — delivery_complete must stop on that tick"
            )
    return CheckResult(
        "A14 termination reason",
        not fails,
        f"reason={reason} (policy {policy}), delivered "
        f"{kpi['customer']['n_delivered']}/{kpi['customer']['n_orders']}, "
        f"clock_end {clock_end:.0f}"
        + (f", last exit {max(exits):.0f}" if exits else ""),
        fails,
    )


# ------------------------------------------------------------------------ core


def run_checks(result: dict) -> dict:
    """Run A1..A14; return a report dict (importable API)."""
    inp = load_inputs(result)
    tick = _tick(result)
    lb_result, lb_report = check_lower_bound(inp, tick)
    a9_result, gof = check_floor_profile(inp)
    checks = [
        check_order_conservation(inp),
        check_time_chain(inp, tick),
        check_arrival_formula(inp, tick),
        lb_result,
        check_lobby_identity(inp, tick),
        check_elevator_consistency(inp),
        check_assignment_replay(inp, tick),
        check_window(inp, tick),
        a9_result,
        check_basement_integrity(inp),
        check_ev_declaration(inp),
        check_hall_call_exclusivity(inp),
        check_warmup_adequacy(inp),
        check_termination_reason(inp),
    ]
    all_passed = all(c.passed for c in checks)
    return {
        "checks": checks,
        "all_passed": all_passed,
        "floor_source": result.get("floor_source"),
        "a4_slack": lb_report,
        "a9_gof": gof,
    }


def verify_result(path_or_dict: str | Path | dict) -> dict:
    """Verify a results JSON (path or already-parsed dict). Returns the report."""
    if isinstance(path_or_dict, dict):
        result = path_or_dict
    else:
        p = Path(path_or_dict)
        if not p.is_absolute():
            p = ROOT / p
        result = json.loads(p.read_text())
    return run_checks(result)


# ------------------------------------------------------------------------- CLI


def _print_report(report: dict, label: str) -> None:
    checks = report["checks"]
    width = max(len(c.name) for c in checks)
    print(f"verify_h0: {label}")
    print("-" * (width + 60))
    for c in checks:
        tag = "SKIP" if c.skipped else ("PASS" if c.passed else "FAIL")
        print(f"[{tag}] {c.name:<{width}}  {c.detail}")
        for f in c.failures[:20]:
            print(f"         - {f}")
        if len(c.failures) > 20:
            print(f"         ... and {len(c.failures) - 20} more")
    print("-" * (width + 60))
    if report["a9_gof"] is not None:
        g = report["a9_gof"]
        print(
            "report-only (never a gate): floor GOF vs K*floor_probs — "
            f"chi2={g['chi2']} p={g['p_value']} dof={g['dof']}\n"
            f"  observed={g['observed']}\n  expected={g['expected']}"
        )
    n_pass = sum(1 for c in checks if c.passed and not c.skipped)
    n_skip = sum(1 for c in checks if c.skipped)
    n_fail = sum(1 for c in checks if not c.passed)
    print(f"{n_pass} passed, {n_skip} skipped, {n_fail} failed")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="H0 dynamic-track results verifier (V-AUD)")
    parser.add_argument("results", nargs="+", help="results JSON(s) from simulation.run")
    args = parser.parse_args(argv)

    exit_code = 0
    for i, results in enumerate(args.results):
        results_path = Path(results)
        if not results_path.is_absolute():
            results_path = ROOT / results_path
        report = verify_result(results_path)
        if i:
            print()
        _print_report(report, str(results_path))
        if not report["all_passed"]:
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
