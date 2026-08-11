"""H0 baseline verification CLI — S6 (etc/plan_abm_baseline_h0.md Part E).

    python -m analysis.verify_baseline results/baseline_h0_K50_1.json

Six PASS/FAIL checks against a simulation/run.py results JSON:
  1. order conservation   K == delivered == exited riders, no ord_id dups
  2. arrival times        entered_at == closed-form t_arrival (±1 tick, σ=0),
                          recomputed from the raw scenario JSON (independent
                          of analysis.scenario_loader)
  3. floor & mode join    (floor, office_id) == floor_mapping_v4;
                          vertical_mode == travel_times_v4, all K orders
  4. strict lower bound   T_e2e >= LB_strict = COOK + horizontal
                          + graph-measured walk / 1.2 (lobby 4 m entrance leg
                          included in the graph distance)
                          + vertical (elevator: include_wait=False; stairs
                          exact) + service_time.
                          ⚠ travel_times_v4 totals embed the exogenous 20 s
                          EV wait — comparing against them is a false-positive
                          trap (plan §주의점 #2), so that delta is REPORT-ONLY
                          (congestion overhead indicator, printed below the
                          table, never a PASS/FAIL input).
  5. complete delivery    no undelivered orders, no residual agents
  6. internal consistency T_lobby > 0, W_EV >= 0, boards == alights,
                          zero capacity violations, record arithmetic

Exit code 0 iff every check passes.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from analysis.load_data import load_scenario
from simulation.space import add_lobby_handoff_zones, build_from_config, shortest_walk_path
from simulation.vertical_transport import VerticalTransportModel

ROOT = Path(__file__).resolve().parent.parent

FLOAT_TOL = 1e-6           # exact-equality comparisons serialized through JSON
STAIR_NODE_1F = "lobby_direct_corridor"   # keep in sync with external_rider.py


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str
    failures: list[str] = field(default_factory=list)


# --------------------------------------------------------------------- loading


def _resolve(path_str: str, override: str | None) -> Path:
    """Resolve a path stored in the results JSON, honoring a CLI override."""
    if override is not None:
        p = Path(override)
    else:
        p = Path(path_str)
    if not p.is_absolute():
        p = ROOT / p
    return p


def load_inputs(results_path: Path, args: argparse.Namespace) -> dict:
    res = json.loads(results_path.read_text())
    scenario_path = _resolve(res["scenario_path"], args.scenario)
    mapping_path = _resolve(res["mapping_path"], args.mapping)
    if args.travel_times is not None:
        tt_path = _resolve(args.travel_times, None)
    else:
        tt_path = mapping_path.with_name(
            mapping_path.name.replace("_floor_mapping_v4", "_travel_times_v4")
        )
    return {
        "res": res,
        "scenario": load_scenario(scenario_path),
        "mapping": json.loads(mapping_path.read_text()),
        "travel_times": json.loads(tt_path.read_text()),
    }


# ---------------------------------------------------------------------- checks


def check_order_conservation(inp: dict) -> CheckResult:
    """#1: K == deliveries == exited riders; ord_id unique and matches data."""
    res, scenario = inp["res"], inp["scenario"]
    per_order = res["per_order"]
    kpi = res["kpi_summary"]
    fails: list[str] = []

    ord_ids = [r["ord_id"] for r in per_order]
    if len(ord_ids) != len(set(ord_ids)):
        dups = sorted({i for i in ord_ids if ord_ids.count(i) > 1})
        fails.append(f"duplicate ord_id(s): {dups}")
    expected_ids = {o.ord_id for o in scenario.orders}
    if set(ord_ids) != expected_ids:
        fails.append(
            f"ord_id set mismatch: missing={sorted(expected_ids - set(ord_ids))} "
            f"extra={sorted(set(ord_ids) - expected_ids)}"
        )
    counts = {
        "scenario K": scenario.K,
        "per_order records": len(per_order),
        "kpi n_orders": kpi["customer"]["n_orders"],
        "kpi n_delivered": kpi["customer"]["n_delivered"],
        "kpi riders exited": kpi["rider"]["n_exited"],
        "delivered records": sum(1 for r in per_order if r["delivered_at_sec"] is not None),
    }
    if len(set(counts.values())) != 1:
        fails.append(f"count mismatch: {counts}")

    return CheckResult(
        "1 order conservation",
        not fails,
        f"K={scenario.K}, delivered={counts['kpi n_delivered']}, "
        f"exited={counts['kpi riders exited']}, unique ord_ids={len(set(ord_ids))}",
        fails,
    )


def check_arrival_times(inp: dict, tick: float) -> CheckResult:
    """#2: entered_at == closed-form t_arrival (±1 tick), recomputed from raw data.

    t_arrival = start + ORD_TIME + COOK_TIME + DIST[i][K+i] / speed(rider_type),
    with the recorded rider_type (its sampling is covered by the RNG convention,
    check #3 covers the mode leg). σ=0, so the form is exact; riders are
    injected on the first tick boundary >= t_arrival, hence the ±1 tick band.
    """
    res, scenario = inp["res"], inp["scenario"]
    start = res["config"]["simulation"]["lunch_peak_start_sec"]
    speed_by_type = {r.type: r.speed_mps for r in scenario.riders}
    row_by_ord = {o.ord_id: i for i, o in enumerate(scenario.orders)}
    order_by_id = {o.ord_id: o for o in scenario.orders}
    fails: list[str] = []
    max_entry_lag = 0.0

    for rec in res["per_order"]:
        oid = rec["ord_id"]
        o = order_by_id[oid]
        i = row_by_ord[oid]
        dist_m = float(scenario.dist[i, scenario.K + i])
        horizontal = dist_m / speed_by_type[rec["rider_type"]]
        t_arrival = start + o.ord_time_sec + o.cook_time_sec + horizontal

        if abs(rec["horizontal_time_s"] - horizontal) > FLOAT_TOL:
            fails.append(
                f"ord {oid}: horizontal_time_s {rec['horizontal_time_s']:.4f} "
                f"!= DIST/speed {horizontal:.4f}"
            )
        if abs(rec["arrival_time_planned_sec"] - t_arrival) > FLOAT_TOL:
            fails.append(
                f"ord {oid}: arrival_time_planned {rec['arrival_time_planned_sec']:.4f} "
                f"!= closed-form {t_arrival:.4f}"
            )
        lag = rec["entered_at_sec"] - t_arrival
        max_entry_lag = max(max_entry_lag, lag)
        if not (-FLOAT_TOL <= lag <= tick + FLOAT_TOL):
            fails.append(
                f"ord {oid}: entered_at {rec['entered_at_sec']} vs closed-form "
                f"{t_arrival:.4f} (lag {lag:+.4f}s, tolerance ±{tick}s)"
            )
        if abs(rec["ord_time_abs_sec"] - (start + o.ord_time_sec)) > FLOAT_TOL:
            fails.append(f"ord {oid}: ord_time_abs_sec != start + ORD_TIME")
        if abs(rec["cook_time_sec"] - o.cook_time_sec) > FLOAT_TOL:
            fails.append(f"ord {oid}: cook_time_sec != data COOK_TIME")
        if abs(rec["deadline_abs_sec"] - (start + o.dlv_deadline_sec)) > FLOAT_TOL:
            fails.append(f"ord {oid}: deadline_abs_sec != start + DLV_DEADLINE")

    return CheckResult(
        "2 arrival times (closed form)",
        not fails,
        f"max entry lag {max_entry_lag:.3f}s (tick quantization, tolerance {tick}s)",
        fails,
    )


def check_floor_and_mode(inp: dict) -> CheckResult:
    """#3: floor/office == floor_mapping_v4; vertical_mode == travel_times_v4."""
    res = inp["res"]
    map_by_ord = {r["ord_id"]: r for r in inp["mapping"]["orders"]}
    tt_by_ord = {r["ord_id"]: r for r in inp["travel_times"]["orders"]}
    fails: list[str] = []

    for rec in res["per_order"]:
        oid = rec["ord_id"]
        m = map_by_ord.get(oid)
        t = tt_by_ord.get(oid)
        if m is None or t is None:
            fails.append(f"ord {oid}: missing from mapping/travel_times")
            continue
        if (rec["floor"], rec["office_id"]) != (m["floor"], m["office_id"]):
            fails.append(
                f"ord {oid}: (floor, office)=({rec['floor']},{rec['office_id']}) "
                f"!= mapping ({m['floor']},{m['office_id']})"
            )
        if rec["vertical_mode"] != t["vertical"]["mode"]:
            fails.append(
                f"ord {oid}: mode {rec['vertical_mode']} != "
                f"travel_times {t['vertical']['mode']}"
            )

    n_stairs = sum(1 for r in res["per_order"] if r["vertical_mode"] == "stairs")
    return CheckResult(
        "3 floor & mode join",
        not fails,
        f"all {len(res['per_order'])} orders match v4 mapping + mode "
        f"(stairs {n_stairs}/{len(res['per_order'])})",
        fails,
    )


def _strict_lower_bound(rec: dict, g, vt: VerticalTransportModel, walk_speed: float) -> float:
    """LB_strict for one order (plan Part E check #4).

    COOK + horizontal + one-way graph walk / walk_speed + up-leg vertical
    + service. The graph distance from lobby_entry already contains the 4 m
    entrance leg (space.add_lobby_handoff_zones), so entrance_walk_s is not
    added again. Elevator vertical uses include_wait=False (wait is endogenous
    in the ABM, >= 0); the +door 4 s is valid because boarding happens at the
    start of a door cycle (elevator._open_doors), so board->alight always
    spans a full door cycle plus the (subadditive) kinematic move.
    """
    f, office = rec["floor"], rec["office_id"]
    office_node = f"floor_{f}_office_{office}"

    if rec["vertical_mode"] == "elevator":
        # ev edges cost 0 in shortest_walk_path -> walk_m is the one-way
        # walking distance via the cheapest declared EV (the ABM may use any)
        _, walk_m = shortest_walk_path(g, "lobby_entry", office_node)
        vert = vt.t_elevator_s(f, include_wait=False)
    else:
        _, leg1 = shortest_walk_path(g, "lobby_entry", STAIR_NODE_1F)
        mid = g.graph["corridor_mid_pos"]
        _, leg2 = shortest_walk_path(g, f"floor_{f}_corr_{mid}", office_node)
        walk_m = leg1 + leg2
        vert = vt.t_stairs_s(f)

    return (
        rec["cook_time_sec"]
        + rec["horizontal_time_s"]
        + walk_m / walk_speed
        + vert
        + rec["service_time_sec"]
    )


def check_strict_lower_bound(inp: dict, tick: float) -> tuple[CheckResult, dict]:
    """#4: T_e2e >= LB_strict (±1 tick). Returns report-only stats too."""
    res = inp["res"]
    cfg = res["config"]
    g = add_lobby_handoff_zones(
        build_from_config(cfg),
        n_locker_compartments=cfg["locker"]["n_compartments"],
    )
    vt = VerticalTransportModel.from_config(cfg)
    walk_speed = cfg["rider_process"]["walk_speed_mps"]
    tt_by_ord = {r["ord_id"]: r for r in inp["travel_times"]["orders"]}
    fails: list[str] = []
    slacks: list[float] = []
    naive_deltas: list[float] = []

    for rec in res["per_order"]:
        lb = _strict_lower_bound(rec, g, vt, walk_speed)
        slack = rec["t_e2e_sec"] - lb
        slacks.append(slack)
        if slack < -tick - FLOAT_TOL:
            fails.append(
                f"ord {rec['ord_id']}: T_e2e {rec['t_e2e_sec']:.1f}s < "
                f"LB_strict {lb:.2f}s (deficit {-slack:.2f}s)"
            )
        # report-only: naive precompute total (20 s exogenous wait, v4-anchor
        # haversine horizontal) — congestion overhead indicator, never a gate
        t = tt_by_ord.get(rec["ord_id"])
        if t is not None:
            naive = (
                rec["cook_time_sec"]
                + t["total_time_s"][rec["rider_type"]]
                + rec["service_time_sec"]
            )
            naive_deltas.append(rec["t_e2e_sec"] - naive)

    n = len(slacks)
    report = {
        "slack_min_sec": min(slacks) if slacks else None,
        "slack_mean_sec": sum(slacks) / n if n else None,
        "slack_max_sec": max(slacks) if slacks else None,
        "vs_travel_times_v4_mean_sec": (
            sum(naive_deltas) / len(naive_deltas) if naive_deltas else None
        ),
        "vs_travel_times_v4_min_sec": min(naive_deltas) if naive_deltas else None,
    }
    return (
        CheckResult(
            "4 strict lower bound",
            not fails,
            f"min slack {report['slack_min_sec']:.2f}s, "
            f"mean {report['slack_mean_sec']:.2f}s over {n} orders",
            fails,
        ),
        report,
    )


def check_complete_delivery(inp: dict) -> CheckResult:
    """#5: every order delivered, no residual agents, no cap termination."""
    res = inp["res"]
    kpi = res["kpi_summary"]
    mv = res["model_vars"]
    fails: list[str] = []

    undelivered = [r["ord_id"] for r in res["per_order"] if r["delivered_at_sec"] is None]
    if undelivered:
        fails.append(f"undelivered ord_id(s): {undelivered}")
    if kpi["customer"]["n_delivered"] != kpi["customer"]["n_orders"]:
        fails.append(
            f"n_delivered {kpi['customer']['n_delivered']} != K {kpi['customer']['n_orders']}"
        )
    if kpi["simulation"]["terminated_by_cap"]:
        fails.append("run hit horizon + max_overrun cap (incomplete)")
    if mv["riders_in_building"][-1] != 0:
        fails.append(f"residual riders at end: {mv['riders_in_building'][-1]}")
    if mv["peds_active"][-1] != 0:
        fails.append(f"residual pedestrians at end: {mv['peds_active'][-1]}")

    return CheckResult(
        "5 complete delivery",
        not fails,
        f"delivered {kpi['customer']['n_delivered']}/{kpi['customer']['n_orders']}, "
        f"clock end {kpi['simulation']['clock_end_sec']:.0f}s, residual agents 0",
        fails,
    )


def check_internal_consistency(inp: dict, tick: float) -> CheckResult:
    """#6: T_lobby > 0, W_EV >= 0, boards == alights, zero capacity violations,
    per-record arithmetic (t_lobby/t_e2e/sla derived fields)."""
    res, scenario = inp["res"], inp["scenario"]
    kpi = res["kpi_summary"]
    service_by_type = {r.type: r.service_time_sec for r in scenario.riders}
    fails: list[str] = []

    for rec in res["per_order"]:
        oid = rec["ord_id"]
        if not rec["t_lobby_sec"] > 0:
            fails.append(f"ord {oid}: t_lobby {rec['t_lobby_sec']} <= 0")
        if abs(rec["t_lobby_sec"] - (rec["exited_at_sec"] - rec["entered_at_sec"])) > FLOAT_TOL:
            fails.append(f"ord {oid}: t_lobby != exited - entered")
        if abs(rec["t_e2e_sec"] - (rec["delivered_at_sec"] - rec["ord_time_abs_sec"])) > FLOAT_TOL:
            fails.append(f"ord {oid}: t_e2e != delivered - ord_time")
        if rec["sla_violation"] != (rec["delivered_at_sec"] > rec["deadline_abs_sec"]):
            fails.append(f"ord {oid}: sla_violation flag inconsistent with deadline")
        if abs(rec["service_time_sec"] - service_by_type[rec["rider_type"]]) > FLOAT_TOL:
            fails.append(f"ord {oid}: service_time != RIDERS data for {rec['rider_type']}")
        if not rec["walked_m"] > 0:
            fails.append(f"ord {oid}: walked_m {rec['walked_m']} <= 0")

        waits = (rec["ev_wait_up_sec"], rec["ev_wait_down_sec"])
        if rec["vertical_mode"] == "elevator":
            if any(w is None or w < 0 for w in waits):
                fails.append(f"ord {oid}: elevator rider has invalid EV waits {waits}")
        else:
            if waits != (None, None):
                fails.append(f"ord {oid}: stairs rider has EV waits {waits}")

    for ev_id, ev in kpi["elevator"].items():
        if ev["n_boardings"] != ev["n_alights"]:
            fails.append(
                f"{ev_id}: boardings {ev['n_boardings']} != alights {ev['n_alights']}"
            )
        if ev["capacity_violations"] != 0:
            fails.append(f"{ev_id}: {ev['capacity_violations']} capacity violation(s)")
        if ev["w_ev_mean_sec"] is not None and ev["w_ev_mean_sec"] < 0:
            fails.append(f"{ev_id}: negative mean W_EV")
        if not 0.0 <= ev["utilization"] <= 1.0:
            fails.append(f"{ev_id}: utilization {ev['utilization']} outside [0, 1]")
    if kpi["pedestrian"]["n_spawned"] != kpi["pedestrian"]["n_completed"]:
        fails.append(
            f"pedestrians spawned {kpi['pedestrian']['n_spawned']} != "
            f"completed {kpi['pedestrian']['n_completed']}"
        )

    boards = sum(ev["n_boardings"] for ev in kpi["elevator"].values())
    return CheckResult(
        "6 internal consistency",
        not fails,
        f"{boards} boardings == alights, 0 capacity violations, "
        f"{len(res['per_order'])} records arithmetically consistent",
        fails,
    )


# ------------------------------------------------------------------------ CLI


def run_checks(inp: dict) -> tuple[list[CheckResult], dict]:
    tick = inp["res"]["config"]["simulation"].get("tick_sec", 1.0)
    lb_result, lb_report = check_strict_lower_bound(inp, tick)
    results = [
        check_order_conservation(inp),
        check_arrival_times(inp, tick),
        check_floor_and_mode(inp),
        lb_result,
        check_complete_delivery(inp),
        check_internal_consistency(inp, tick),
    ]
    return results, lb_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="H0 baseline results verifier (S6)")
    parser.add_argument("results", help="results JSON from simulation.run")
    parser.add_argument("--scenario", default=None, help="override scenario JSON path")
    parser.add_argument("--mapping", default=None, help="override floor_mapping_v4 path")
    parser.add_argument("--travel-times", default=None, help="override travel_times_v4 path")
    args = parser.parse_args(argv)

    results_path = Path(args.results)
    if not results_path.is_absolute():
        results_path = ROOT / results_path
    inp = load_inputs(results_path, args)
    results, lb_report = run_checks(inp)

    width = max(len(r.name) for r in results)
    print(f"verify_baseline: {results_path}")
    print("-" * (width + 60))
    for r in results:
        print(f"[{'PASS' if r.passed else 'FAIL'}] {r.name:<{width}}  {r.detail}")
        for f in r.failures[:20]:
            print(f"         - {f}")
        if len(r.failures) > 20:
            print(f"         ... and {len(r.failures) - 20} more")
    print("-" * (width + 60))
    print(
        "report-only (never a gate): congestion overhead vs uncongested "
        "travel_times_v4 totals\n"
        f"  T_e2e - (COOK + total_time_s[type] + service): "
        f"mean {lb_report['vs_travel_times_v4_mean_sec']:+.1f}s, "
        f"min {lb_report['vs_travel_times_v4_min_sec']:+.1f}s "
        "(negative min would NOT be a violation: v4 totals embed the 20 s "
        "exogenous EV wait and haversine horizontal)"
    )

    n_fail = sum(1 for r in results if not r.passed)
    print(f"{len(results) - n_fail}/{len(results)} checks passed")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
