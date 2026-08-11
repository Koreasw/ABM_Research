"""V-HR — H1 (robot relay) results verifier: gates B1..B11.

    .venv/bin/python -m analysis.verify_hr results/baseline_hr_K50_1_uniform_s42.json

Sibling of `analysis/verify_h0.py`, and deliberately a separate module rather
than a mode branch inside it: H0's A-gates encode "the courier carries the order
to the door", which is false in every H1 run, so half of them would have to be
disabled and the other half rewritten. What IS shared — the tick arithmetic, the
graph/kinematics helpers, the `CheckResult` shape, the floor-profile
re-derivation — is imported, so there is exactly one implementation of each.

WHAT THE GATES JUDGE, AND WHAT THEY DELIBERATELY DO NOT
-------------------------------------------------------
The corpus is expected to saturate: five robots are a K50-sized fleet, and at
K200/K300 the queue diverges by design (HANDOFF_phase_a §3.6). Saturation must
therefore never be a gate — it is reported as `robot_queue_wait_p95`,
`T_building_order_p95` and `drain_span_sec` in the report-only block. What the
gates judge is conservation, chain consistency, kinematic feasibility, dispatch
order, window provenance and end state — properties that must hold whether the
fleet is over- or under-sized.

Two more things are information, not gates, and for the same reason:
`n_charge_events == 0` and `soc_min > soc_low_pct` are the EXPECTED corpus
result (§3.5) — a 1.3 kWh battery against a ~6-10 Wh delivery. Gating on them
would encode "the threshold must fire", which is the opposite of the finding.

GATE MAP (the numbering follows the plan; there is no B6 — `phase_A_robot_h1.md`
§2 and `plan_hr_extension.md` R2b both jump B5 → B7, inherited from the H0
A-gate map where A6 is an H0-only elevator-consistency check):

  B1  conservation           orders = handoffs = deliveries = returns
  B2  order chain            courier stamps + robot leg stamps, joined on
                             the documented one-tick handoff lag
  B3  robot conservation     shared cars only · no basement · 2 boardings/trip ·
                             no people-capacity violation while a robot rides
  B4  robot kinematics       every leg ≥ its wait-free physical lower bound
  B5  courier decomposition  t_lobby = walk + robot wait + handoff + walk (exact)
  B7  FCFS replay            an earlier arrival is never assigned later
  B8  measurement windows    the fixed window is the scenario's, not the run's
  B9  floor-profile GOF      (floor, office) re-derived from provenance
  B10 battery conservation   0 ≤ SOC ≤ 100 · trips drain · home charges ·
                             a low-SOC return resumes only above soc_resume_pct
  B11 end state              every robot parked at home, delivered == K strictly

CONDITIONAL SKIP (결정 13). With a four-shared-car configuration the dedicated
set is empty, so B3's "a robot never boards a dedicated car" is vacuously true.
A vacuous PASS is worse than no result — it reads as evidence. The sub-check is
skipped and said to be skipped, exactly as A12 does in the H0 verifier.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from analysis.verify_h0 import (
    FLOAT_TOL,
    CheckResult,
    _gof,
    _graph_and_kin,
    _resolve,
    _tick,
    _timer_ticks,
    _walk_dist,
    _walk_ticks,
    load_inputs,
)
from simulation.agents.robot import COUNTER_NODE, HOME_NODE, RobotState
from simulation.floor_demand import rederive_profile_assignment

# The two states a settled robot may be in. Imported rather than retyped: a new
# at-home state added to the enum has no mechanical link to a hand-written
# tuple, so B11 would start failing every run that legitimately ends in it.
PARKED_STATES = (RobotState.IDLE.value, RobotState.CHARGING_BLOCKED.value)


def _legs(res: dict) -> dict[int, dict]:
    """`ord_id -> leg`. Callers must ALSO length-check against the raw list.

    Keying by `ord_id` silently collapses a duplicate leg, so this dict alone
    cannot see a double-published trip — `check_conservation` compares its size
    against `len(res["robot_legs"])` for exactly that reason.
    """
    return {int(lg["ord_id"]): lg for lg in res.get("robot_legs", [])}


def _fleet(res: dict) -> list[dict]:
    return res.get("robot_fleet", [])


def _shared_ids(res: dict) -> set[str]:
    return set(res["config"]["building"]["shared_ev_ids"])


def _dedicated_ids(res: dict) -> list[str]:
    """Cars a robot may NOT board, from the config's DECLARED fleet.

    Read from `config.building.ev_ids`, not from the KPI block's keys: a KPI
    schema regression that dropped the dedicated cars would make the dedicated
    set look empty, and B3 would then announce the 결정 13 skip and pass
    vacuously on a run where a robot really did board a people-only car.
    """
    return [e for e in _declared_ev_ids(res) if e not in _shared_ids(res)]


def _declared_ev_ids(res: dict) -> list[str]:
    """`EV1..EVn` from the config's declared fleet size (`space.py:170`)."""
    b = res["config"]["building"]
    n = len(b.get("ev_sides") or b.get("ev_corridor_positions_m") or [])
    return [f"EV{i + 1}" for i in range(n)]


# ------------------------------------------------------------------ B1 / B2


def check_conservation(inp: dict) -> CheckResult:
    """B1: every order is handed over exactly once and delivered exactly once.

    In H0 one record carried the whole order, so conservation was a statement
    about one list. Here it is a statement about the JOIN: the courier half and
    the robot half must cover the same order set with no order in only one of
    them (A2 함정 2 — the courier leaves before the delivery, so a dropped leg
    record would silently look like a delivered order with no delivery).

    The order set comes from the SCENARIO FILE, not from the artefact's own
    counters. Checking `len(per_order) == kpi.n_orders` is self-consistency: a
    dispatcher bug that drops an order drops it from both sides and from the
    counter, and the gate stays green. `verify_h0`'s A1 compares against
    `inp["scenario"]` for exactly this reason, and this gate now does too.
    """
    res = inp["res"]
    per_order = res["per_order"]
    legs = _legs(res)
    kpi = res["kpi_summary"]
    k = kpi["customer"]["n_orders"]
    fails: list[str] = []

    scenario = inp.get("scenario")
    if scenario is None:
        fails.append("scenario file unavailable — conservation could only be "
                     "checked against the artefact's own counters")
    else:
        if k != scenario.K:
            fails.append(f"artefact K={k} != scenario K={scenario.K}")
        scen_ids = {int(o.ord_id) for o in scenario.orders}
        got_ids = {int(r["ord_id"]) for r in per_order}
        if got_ids != scen_ids:
            fails.append(f"courier records cover {len(got_ids)} of "
                         f"{len(scen_ids)} scenario orders "
                         f"(missing={sorted(scen_ids - got_ids)[:10]})")

    ord_ids = [r["ord_id"] for r in per_order]
    if len(ord_ids) != len(set(ord_ids)):
        fails.append(f"duplicate ord_ids in per_order ({len(ord_ids)} rows)")
    # `_legs` is keyed by ord_id, so a double-published leg would vanish into
    # the dict — the size comparison is the only thing that can see it
    if len(res.get("robot_legs", [])) != len(legs):
        fails.append(f"{len(res.get('robot_legs', []))} robot_legs rows collapse "
                     f"to {len(legs)} ord_ids — a trip was published twice")
    if len(ord_ids) != k:
        fails.append(f"{len(ord_ids)} courier records for K={k}")
    if set(ord_ids) != set(legs):
        missing = sorted(set(ord_ids) - set(legs))
        extra = sorted(set(legs) - set(ord_ids))
        fails.append(f"courier/robot join mismatch: missing legs={missing[:10]} "
                     f"legs without courier={extra[:10]}")
    if kpi["customer"]["n_delivered"] != k:
        fails.append(f"delivered {kpi['customer']['n_delivered']} != K={k}")

    n_handoff = sum(1 for r in per_order if r.get("handoff_started_sec") is not None)
    if n_handoff != len(per_order):
        fails.append(f"{len(per_order) - n_handoff} couriers exited without a handoff")
    for oid, lg in sorted(legs.items()):
        for key in ("assigned_at_sec", "handoff_started_sec", "handoff_ended_sec",
                    "delivered_at_sec", "returned_at_sec"):
            if lg.get(key) is None:
                fails.append(f"ord {oid}: leg missing {key}")
    if res["kpi_summary"]["rider"]["n_exited"] != k:
        fails.append(f"{res['kpi_summary']['rider']['n_exited']} couriers exited, K={k}")

    return CheckResult(
        "B1 conservation (orders = handoffs = deliveries)",
        not fails,
        f"K={k}: {len(ord_ids)} couriers, {len(legs)} robot legs, "
        f"{n_handoff} handoffs, delivered={kpi['customer']['n_delivered']}",
        fails,
    )


def check_courier_chain(inp: dict, tick: float) -> CheckResult:
    """B2: BOTH halves of the order timeline are monotone and agree with each other.

    `entered < handoff_end <= exited` is the plan's wording for the courier; the
    counter arrival is checked too, reconstructed as `handoff_started -
    robot_wait`, because a negative robot wait is the one way that chain can be
    inconsistent without any single stamp being out of order.

    The robot's half is checked here as well. In H0 one record held the whole
    timeline, so ordering it was one gate's job; H1 split it in two and only the
    courier's half was originally pinned — a leg whose handoff ended before it
    started, or whose delivery preceded its handoff, passed every gate. The two
    halves are also joined: the robot enters HANDOFF exactly ONE TICK after the
    courier does, because robots step before riders (`model.step`, A4 trap 2).
    That tick is a load-bearing consequence of the step order, so it is asserted
    rather than assumed.
    """
    res = inp["res"]
    legs = _legs(res)
    fails: list[str] = []
    max_wait = 0.0

    for oid, lg in sorted(legs.items()):
        chain = [("assigned", lg.get("assigned_at_sec")),
                 ("handoff start", lg.get("handoff_started_sec")),
                 ("handoff end", lg.get("handoff_ended_sec")),
                 ("delivered", lg.get("delivered_at_sec")),
                 ("returned", lg.get("returned_at_sec"))]
        if any(v is None for _, v in chain):
            continue                        # B1 owns missing stamps
        for (n_a, v_a), (n_b, v_b) in zip(chain, chain[1:], strict=False):
            if v_a > v_b + FLOAT_TOL:
                fails.append(f"ord {oid}: leg {n_a} {v_a} after {n_b} {v_b}")

    for rec in res["per_order"]:
        oid = rec["ord_id"]
        lg = legs.get(oid)
        if (lg is not None and rec.get("handoff_started_sec") is not None
                and lg.get("handoff_started_sec") is not None):
            lag = lg["handoff_started_sec"] - rec["handoff_started_sec"]
            if abs(lag - tick) > FLOAT_TOL:
                fails.append(
                    f"ord {oid}: robot began the handoff {lag}s after the courier, "
                    f"expected exactly one tick ({tick}s) — robots step before "
                    f"riders (A4 trap 2)"
                )
        entered, exited = rec["entered_at_sec"], rec["exited_at_sec"]
        hs, he = rec["handoff_started_sec"], rec["handoff_ended_sec"]
        if None in (hs, he):
            fails.append(f"ord {oid}: handoff stamps missing ({hs}, {he})")
            continue
        at_counter = hs - (rec["robot_wait_sec"] or 0.0)
        if not (entered <= at_counter + FLOAT_TOL):
            fails.append(f"ord {oid}: reached the counter {at_counter} before "
                         f"entering {entered}")
        if not (at_counter <= hs + FLOAT_TOL):
            fails.append(f"ord {oid}: negative robot wait ({rec['robot_wait_sec']})")
        if not (hs < he):
            fails.append(f"ord {oid}: handoff start {hs} !< end {he}")
        if not (he <= exited + FLOAT_TOL):
            fails.append(f"ord {oid}: handoff end {he} > exit {exited}")
        if not (entered < he):
            fails.append(f"ord {oid}: entered {entered} !< handoff end {he}")
        # the handoff itself must be the drawn duration, tick-quantized
        drawn = rec.get("handoff_sec")
        if drawn is None:
            fails.append(f"ord {oid}: no handoff_sec recorded")
        else:
            expected = _timer_ticks(drawn, tick) * tick
            if abs((he - hs) - expected) > FLOAT_TOL:
                fails.append(f"ord {oid}: handoff lasted {he - hs} != "
                             f"tt({drawn:.3f}) = {expected}")
        max_wait = max(max_wait, rec["robot_wait_sec"] or 0.0)

    return CheckResult(
        "B2 order chain (courier + robot halves, joined)",
        not fails,
        f"{len(res['per_order'])} couriers / {len(legs)} legs, "
        f"max robot wait {max_wait:.1f}s",
        fails,
    )


# ------------------------------------------------------------------ B3


def check_robot_conservation(inp: dict) -> CheckResult:
    """B3: robots use only the shared cars, never the basement, twice per trip.

    The end-state half of the plan's B3 wording lives in B11 instead, so that
    "where did the fleet stop" is judged in exactly one place — B3 is about what
    happened during the run.
    """
    res = inp["res"]
    legs = _legs(res)
    shared = _shared_ids(res)
    dedicated = _dedicated_ids(res)
    kpi_ev = res["kpi_summary"]["elevator"]
    fails: list[str] = []
    notes: list[str] = []

    n_board = 0
    for oid, lg in sorted(legs.items()):
        for tag in ("up", "down"):
            ev_id = lg.get(f"ev_id_{tag}")
            # the car and the wait are recorded by the same event (`on_board`),
            # so one without the other is a broken boarding, not a boarding with
            # a missing field — checked together for that reason
            wait = lg.get(f"ev_wait_{tag}_sec")
            if ev_id is None or wait is None:
                fails.append(f"ord {oid}: incomplete {tag} boarding "
                             f"(car={ev_id!r}, wait={wait!r})")
                continue
            n_board += 1
            if dedicated and ev_id not in shared:
                fails.append(f"ord {oid}: robot boarded DEDICATED car {ev_id} ({tag})")
        floor = lg.get("floor")
        if floor is None:
            fails.append(f"ord {oid}: leg has no delivery floor")
        elif floor < 1:
            fails.append(f"ord {oid}: robot delivered to basement floor {floor}")

    expected_boardings = 2 * len(legs)
    if n_board != expected_boardings:
        fails.append(f"{n_board} robot boardings for {len(legs)} trips "
                     f"(expected {expected_boardings} = 2 per trip)")

    # a robot aboard reduces the car's people capacity to 11; the model counts
    # every breach itself, so the gate reads its counter rather than
    # re-deriving occupancy from a time series it would have to trust anyway
    for ev_id, blk in kpi_ev.items():
        if blk["capacity_violations"]:
            fails.append(f"{ev_id}: {blk['capacity_violations']} capacity violations")

    if not dedicated:
        notes.append("SKIP dedicated-car sub-check: every car is robot-shareable "
                     "(결정 13) so 'no robot on a dedicated car' is vacuous")
    denied = res["kpi_summary"].get("robot", {}).get("n_board_denied")
    detail = (f"{len(legs)} trips x 2 boardings, shared={sorted(shared)}, "
              f"dedicated={dedicated or 'none'}, board_denied={denied} (report-only)")
    if notes:
        detail += " | " + " | ".join(notes)
    return CheckResult("B3 robot conservation", not fails, detail, fails)


# ------------------------------------------------------------------ B4


def _leg_bounds(g, kin, cfg: dict, lg: dict, tick: float) -> tuple[float, float]:  # noqa: ANN001
    """(up, down) wait-free lower bounds in seconds for one robot leg.

    Every term is either a distance walked at the robot's own speed, a timer the
    robot must run, or a wait the run itself recorded — nothing here is fitted.
    The lift term is the free-run time, so the slack a real leg shows is exactly
    the time the car spent serving somebody else.
    """
    v = cfg["robot"]["speed_mps"]
    drop = cfg["robot"]["service_time_drop_sec"]
    floor = lg["floor"]
    office = f"floor_{floor}_office_{lg['office_id']}"
    up_ev, down_ev = lg["ev_id_up"], lg["ev_id_down"]
    door = _timer_ticks(kin.door_open_close_sec, tick) * tick

    up = (
        _walk_ticks(_walk_dist(g, COUNTER_NODE, f"ev_{up_ev}_1"), v, tick) * tick
        + lg["ev_wait_up_sec"]
        + door
        + _timer_ticks(kin.travel_time_sec(1, floor), tick) * tick
        + _walk_ticks(_walk_dist(g, f"ev_{up_ev}_{floor}", office), v, tick) * tick
        + _timer_ticks(drop, tick) * tick
    )
    down = (
        _walk_ticks(_walk_dist(g, office, f"ev_{down_ev}_{floor}"), v, tick) * tick
        + lg["ev_wait_down_sec"]
        + door
        + _timer_ticks(kin.travel_time_sec(floor, 1), tick) * tick
        + _walk_ticks(_walk_dist(g, f"ev_{down_ev}_1", HOME_NODE), v, tick) * tick
    )
    return up, down


def check_robot_kinematics(inp: dict, tick: float) -> tuple[CheckResult, dict]:
    """B4: no leg beats physics. Returns the slack report alongside the verdict.

    A strict lower bound, not an identity, and for the same reason H0's A4 is:
    a car can stop for other passengers on the way, which only ever makes a leg
    longer. Zero slack is therefore the interesting value — it means the robot
    rode alone — and negative slack means the robot moved faster than the
    building allows.
    """
    res = inp["res"]
    cfg = res["config"]
    g, kin = _graph_and_kin(res)
    fails: list[str] = []
    slacks_up: list[float] = []
    slacks_dn: list[float] = []
    n_unusable = 0

    for oid, lg in sorted(_legs(res).items()):
        # A leg missing a stamp, missing a car, or claiming a basement floor is
        # already a B1/B3 failure. Skipping it here keeps each defect reported
        # once, by the gate that owns it — and, just as importantly, keeps this
        # gate from crashing on a malformed artefact. A verifier that raises
        # instead of reporting is useless precisely when it is needed.
        if (lg.get("ev_id_up") is None or lg.get("ev_id_down") is None
                or lg.get("floor") is None or lg["floor"] < 1
                or any(lg.get(k) is None for k in
                       ("handoff_ended_sec", "delivered_at_sec", "returned_at_sec",
                        "ev_wait_up_sec", "ev_wait_down_sec"))):
            n_unusable += 1
            continue
        lb_up, lb_dn = _leg_bounds(g, kin, cfg, lg, tick)
        obs_up = lg["delivered_at_sec"] - lg["handoff_ended_sec"]
        obs_dn = lg["returned_at_sec"] - lg["delivered_at_sec"]
        s_up, s_dn = obs_up - lb_up, obs_dn - lb_dn
        slacks_up.append(s_up)
        slacks_dn.append(s_dn)
        if s_up < -FLOAT_TOL:
            fails.append(f"ord {oid}: up leg {obs_up:.1f}s < lower bound {lb_up:.1f}s "
                         f"(slack {s_up:+.3f})")
        if s_dn < -FLOAT_TOL:
            fails.append(f"ord {oid}: down leg {obs_dn:.1f}s < lower bound {lb_dn:.1f}s "
                         f"(slack {s_dn:+.3f})")

    report = {
        "n_legs": len(slacks_up),
        "min_slack_up_sec": min(slacks_up, default=None),
        "min_slack_down_sec": min(slacks_dn, default=None),
        "mean_slack_up_sec": (sum(slacks_up) / len(slacks_up)) if slacks_up else None,
        "mean_slack_down_sec": (sum(slacks_dn) / len(slacks_dn)) if slacks_dn else None,
    }
    report["n_unusable"] = n_unusable
    if not slacks_up:
        # 결정 13's rule applied to this gate: a PASS with nothing judged reads
        # as evidence that physics was checked. Report SKIP instead.
        return CheckResult(
            "B4 robot kinematics (lower bound)", True,
            f"SKIP: no usable leg ({n_unusable} unusable — reported by B1/B3)",
            skipped=True,
        ), report
    detail = (f"{report['n_legs']} legs; min slack up/down "
              f"{report['min_slack_up_sec']}/{report['min_slack_down_sec']}s")
    if n_unusable:
        detail += f"; {n_unusable} leg(s) unusable (reported by B1/B3)"
    return CheckResult("B4 robot kinematics (lower bound)", not fails, detail, fails), report


# ------------------------------------------------------------------ B5


def check_courier_decomposition(inp: dict, tick: float) -> CheckResult:
    """B5: the H1 courier's dwell is EXACTLY walk + robot wait + handoff + walk.

    Exact, not bounded: the H1 courier never touches the vertical system, so
    there is nothing left for a queue to hide in. That is what makes this the
    sharpest gate in the module — any mis-accounting anywhere in the courier's
    four states shows up here as a whole-second residual.

    The leading walk costs `w - 1` ticks because the courier's constructor plans
    it, so its first walking tick is the tick it entered (A4 tick grammar); the
    trailing walk is planned inside the courier's own step and costs the full
    `w`.
    """
    res = inp["res"]
    cfg = res["config"]
    g, _ = _graph_and_kin(res)
    v = cfg["rider_process"]["walk_speed_mps"]
    w_cc = _walk_ticks(_walk_dist(g, "lobby_entry", COUNTER_NODE), v, tick)
    fails: list[str] = []
    max_resid = 0.0

    n_unusable = 0
    for rec in res["per_order"]:
        # a record missing a stamp is B1/B2's to report; skipping it here keeps
        # the identity from raising and discarding the other couriers' verdicts
        if any(rec.get(k) is None for k in
               ("t_lobby_sec", "handoff_started_sec", "handoff_ended_sec")):
            n_unusable += 1
            continue
        recon = ((w_cc - 1) * tick
                 + (rec["robot_wait_sec"] or 0.0)
                 + (rec["handoff_ended_sec"] - rec["handoff_started_sec"])
                 + w_cc * tick)
        resid = abs(rec["t_lobby_sec"] - recon)
        max_resid = max(max_resid, resid)
        if resid > FLOAT_TOL:
            fails.append(f"ord {rec['ord_id']}: t_lobby {rec['t_lobby_sec']:.1f} != "
                         f"decomposition {recon:.1f} (resid {resid:.3f})")

    n_judged = len(res["per_order"]) - n_unusable
    if not n_judged:
        return CheckResult(
            "B5 courier decomposition (exact identity)", True,
            f"SKIP: no usable courier record ({n_unusable} unusable — "
            f"reported by B1/B2)", skipped=True,
        )
    detail = (f"walk {w_cc} ticks each way; max residual {max_resid:.6f}s over "
              f"{n_judged} couriers")
    if n_unusable:
        detail += f"; {n_unusable} unusable (reported by B1/B2)"
    return CheckResult("B5 courier decomposition (exact identity)", not fails,
                       detail, fails)


# ------------------------------------------------------------------ B7


def check_fcfs(inp: dict) -> CheckResult:
    """B7: a courier who entered earlier is never assigned a robot later.

    Judged between TIE GROUPS, not between adjacent rows. Couriers entering
    within one tick are ordered by the arrival heap, whose sequence number the
    artefact does not carry, so a pair inside a group cannot be judged — but
    skipping such a pair in an adjacent-only scan silently breaks the chain:
    `A(t=100) B(t=100) C(t=200)` compares only B↔C, so A may be assigned long
    after C and nothing notices. Same-tick arrivals are the norm under
    saturation (K200_1 has several groups), so that hole is not hypothetical.

    Comparing `max(assigned)` of one group against `min(assigned)` of the next
    restores the full order: every cross-group pair is covered by the extremes,
    and no within-group pair is judged.
    """
    res = inp["res"]
    legs = _legs(res)
    rows = [
        (r["entered_at_sec"], r["ord_id"], legs[r["ord_id"]]["assigned_at_sec"])
        for r in res["per_order"]
        if r["ord_id"] in legs
        and r.get("entered_at_sec") is not None
        and legs[r["ord_id"]].get("assigned_at_sec") is not None
    ]
    if not rows:
        return CheckResult(
            "B7 FCFS dispatch replay", True,
            "SKIP: no order has both an entry time and an assignment "
            "(nothing to put in order)", skipped=True,
        )
    rows.sort(key=lambda t: (t[0], t[1]))

    groups: list[tuple[float, list[tuple[float, int, float]]]] = []
    for row in rows:
        if groups and groups[-1][0] == row[0]:
            groups[-1][1].append(row)
        else:
            groups.append((row[0], [row]))

    fails: list[str] = []
    n_ties = sum(len(g) for _, g in groups if len(g) > 1)
    # ragged pairwise walk over the groups (n-1 pairs), so strict=False
    for (e_i, g_i), (e_j, g_j) in zip(groups, groups[1:], strict=False):
        latest = max(g_i, key=lambda t: t[2])
        earliest = min(g_j, key=lambda t: t[2])
        if latest[2] > earliest[2] + FLOAT_TOL:
            fails.append(
                f"ord {latest[1]} entered {e_i} but was assigned {latest[2]}, "
                f"after ord {earliest[1]} (entered {e_j}, assigned {earliest[2]})"
            )
    return CheckResult(
        "B7 FCFS dispatch replay",
        not fails,
        f"{len(rows)} orders in {len(groups)} arrival-tick groups; "
        f"{n_ties} same-tick arrivals not ordered among themselves "
        f"(heap sequence not in the artefact)",
        fails,
    )


# ------------------------------------------------------------------ B8


def check_windows(inp: dict, tick: float) -> CheckResult:
    """B8: the 3-layer window contract (결정 14).

    The load-bearing assertion is that layer ①'s window is recomputed from the
    ORDER TIMES and matches — i.e. that both of its edges come from the scenario
    file. That is what makes it identical across modes: an H0 and an H1 run of
    the same scenario cannot disagree about when the orders were placed, so if
    the recompute matches here it matches there. A window whose edge came from
    the simulation (last delivery, last exit, run end) would pass no such test.
    """
    res = inp["res"]
    sim = res["kpi_summary"]["simulation"]
    fails: list[str] = []

    ord_times = [r["ord_time_abs_sec"] for r in res["per_order"]]
    expected = [min(ord_times), max(ord_times)]
    got = sim.get("fixed_window_sec")
    if got != expected:
        fails.append(f"fixed window {got} != [min,max] ORD_TIME {expected}")
    if sim.get("wall_span_fixed_sec") != expected[1] - expected[0]:
        fails.append(f"wall_span_fixed {sim.get('wall_span_fixed_sec')} != "
                     f"{expected[1] - expected[0]}")
    if got and not (sim["clock_start_sec"] <= got[0] and got[1] <= sim["clock_end_sec"]):
        fails.append(f"fixed window {got} not inside the run "
                     f"[{sim['clock_start_sec']}, {sim['clock_end_sec']}]")

    windows = sim.get("windows") or {}
    for layer in ("layer1_fixed", "layer2_orderset", "layer3_mode_internal"):
        if layer not in windows:
            fails.append(f"window contract missing {layer}")

    # A5-b: the operating window is what the fleet-load figure is divided by, so
    # a wrong edge silently rescales every utilization number in the study. It
    # starts with the demand and ends when the last carrier settles — which in a
    # robot mode is strictly after the last courier left.
    ops = sim.get("ops_window_sec")
    if not ops:
        fails.append("no ops_window_sec (fleet utilization has no denominator)")
    else:
        if got and ops[0] != got[0]:
            fails.append(f"ops window starts {ops[0]}, fixed window starts {got[0]}")
        last_home = max((lg["returned_at_sec"] for lg in _legs(res).values()
                         if lg.get("returned_at_sec") is not None), default=None)
        last_exit = max((r["exited_at_sec"] for r in res["per_order"]
                         if r.get("exited_at_sec") is not None), default=None)
        if (last_home is not None and last_exit is not None
                and ops[1] != max(last_home, last_exit)):
            fails.append(f"ops window ends {ops[1]} != last carrier settled "
                         f"{max(last_home, last_exit)}")
        # (`ops[1] >= delivery[1]` is not asserted: `_ops_span`'s end is a max
        # over a SUPERSET of `_delivery_span`'s, so it holds by construction and
        # a check would be unreachable. The real content is the equality above.)

    # layer ① must actually have been measured, and it must be a sub-window:
    # a fixed-window count above the full-run count would mean the restriction
    # ran on the wrong axis
    for ev_id, blk in res["kpi_summary"]["elevator"].items():
        if blk.get("utilization_fixed") is None:
            fails.append(f"{ev_id}: no fixed-window utilization")
        n_fixed = sum((blk.get("n_boardings_by_kind_fixed") or {}).values())
        if n_fixed > blk["n_boardings"]:
            fails.append(f"{ev_id}: {n_fixed} fixed-window boardings > "
                         f"{blk['n_boardings']} total")

    span = expected[1] - expected[0]
    return CheckResult(
        "B8 measurement windows (3 layers)",
        not fails,
        f"fixed window {got} (span {span:.0f}s) re-derived from ORD_TIME; "
        f"delivery window span {sim.get('wall_span_delivery_sec')}s is layer ③",
        fails,
    )


# ------------------------------------------------------------------ B9


def check_floor_profile_hr(inp: dict) -> tuple[CheckResult, dict | None]:
    """B9: (floor, office) re-derived from provenance; mode must be 'handoff'.

    H0's A9 also re-derives `vertical_mode`, which cannot be done here: the H1
    courier never uses the vertical system, so the pre-sampled mode stays on the
    order unconsumed (`handoff_rider.py`). Asserting that every record says
    `handoff` is the H1 form of the same claim — the courier took no lift and no
    stairs — and it is stronger than silently dropping the field.
    """
    res = inp["res"]
    source = res.get("floor_source")
    fails: list[str] = []

    # The "courier took no lift and no stairs" claim is checked FIRST and
    # unconditionally: it is an H1 invariant that has nothing to do with floor
    # provenance, and folding it into the profile-only branch meant every
    # frozen-mapping HR run silently stopped asserting it.
    for rec in res["per_order"]:
        if rec.get("vertical_mode") != "handoff":
            fails.append(f"ord {rec['ord_id']}: vertical_mode="
                         f"{rec.get('vertical_mode')!r}, but an H1 courier never "
                         f"uses the vertical system")

    if source != "profile":
        return (
            CheckResult(
                "B9 floor-profile conformance", not fails,
                f"floor re-derivation SKIPPED: floor_source={source!r} (frozen "
                f"mapping run); vertical_mode=='handoff' still checked on "
                f"{len(res['per_order'])} couriers",
                fails, skipped=not fails,
            ),
            None,
        )
    rederived = rederive_profile_assignment(
        res["config"], res["floor_profile"], res["floor_seed"],
        [r["ord_id"] for r in res["per_order"]],
    )
    for rec in res["per_order"]:
        oid = rec["ord_id"]
        exp = rederived.get(oid)
        if exp is None:
            fails.append(f"ord {oid}: not re-derivable")
            continue
        if (rec["floor"], rec["office_id"]) != exp[:2]:
            fails.append(f"ord {oid}: (floor,office)={(rec['floor'], rec['office_id'])}"
                         f" != re-derived {exp[:2]}")
    gof = _gof(res)
    gof_txt = f"; GOF chi2={gof['chi2']} p={gof['p_value']} (report-only)" if gof else ""
    return (
        CheckResult("B9 floor-profile conformance", not fails,
                    f"profile={res['floor_profile']!r} floor_seed={res['floor_seed']}: "
                    f"{len(res['per_order'])} orders re-derived{gof_txt}", fails),
        gof,
    )


# ------------------------------------------------------------------ B10


def check_battery(inp: dict) -> CheckResult:
    """B10: SOC stays in range, trips cost energy, the dock repays it.

    Three gated claims and two information rows. Gated: SOC never leaves
    [0, 100]; a trip always ends below where it started (there is no charging
    away from the dock); and a robot that parked BECAUSE of low SOC does not
    take another order until it is back above `soc_resume_pct`.

    Information only (§3.5): `n_charge_events` and the SOC floor. On this corpus
    both say "the threshold never came close", which is the finding, not a
    failure — gating on them would demand that a 1.3 kWh battery run flat.
    """
    res = inp["res"]
    bat = res["config"]["robot"]["battery"]
    resume = bat["soc_resume_pct"]
    fails: list[str] = []

    # A missing SOC is reported AND excluded from every later comparison. The
    # first version only reported it, then compared it anyway — one None stamp
    # raised a TypeError that `_guard` turned into a crash, discarding the other
    # 49 legs' verdicts. Reporting a defect must never cost the report.
    def _ok(label: str, v: float | None) -> bool:
        if v is None:
            fails.append(f"{label}: missing SOC")
            return False
        if not (0.0 - FLOAT_TOL <= v <= 100.0 + FLOAT_TOL):
            fails.append(f"{label}: SOC {v} outside [0, 100]")
            return False
        return True

    by_robot: dict[int, list[dict]] = {}
    for oid, lg in sorted(_legs(res).items()):
        a_ok = _ok(f"ord {oid} assign", lg.get("soc_pct_at_assign"))
        r_ok = _ok(f"ord {oid} return", lg.get("soc_pct_at_return"))
        if a_ok and r_ok and lg["soc_pct_at_return"] >= lg["soc_pct_at_assign"] + FLOAT_TOL:
            fails.append(f"ord {oid}: SOC rose during the trip "
                         f"({lg['soc_pct_at_assign']:.2f} -> {lg['soc_pct_at_return']:.2f})")
        if a_ok and r_ok and lg.get("assigned_at_sec") is not None:
            by_robot.setdefault(lg.get("robot_id"), []).append(lg)

    n_blocked_returns = 0
    for rid, rlegs in sorted(by_robot.items(), key=lambda kv: str(kv[0])):
        rlegs.sort(key=lambda x: x["assigned_at_sec"])
        for prev, nxt in zip(rlegs, rlegs[1:], strict=False):  # ragged by design
            # the robot zone is a net charger (13 Wh/min in, 1 Wh/min idle out),
            # so a robot cannot start a trip below where the last one left it
            if nxt["soc_pct_at_assign"] < prev["soc_pct_at_return"] - FLOAT_TOL:
                fails.append(f"robot {rid}: SOC fell while parked "
                             f"({prev['soc_pct_at_return']:.2f} -> "
                             f"{nxt['soc_pct_at_assign']:.2f})")
            if prev.get("return_reason") == "low_soc":
                n_blocked_returns += 1
                if nxt["soc_pct_at_assign"] < resume - FLOAT_TOL:
                    fails.append(
                        f"robot {rid}: dispatched at SOC {nxt['soc_pct_at_assign']:.2f}% "
                        f"after a low-SOC return, below soc_resume_pct={resume}"
                    )

    for rb in _fleet(res):
        rid = rb.get("robot_id")
        end_ok = _ok(f"robot {rid} end", rb.get("soc_pct"))
        min_ok = _ok(f"robot {rid} min", rb.get("soc_min_pct"))
        if end_ok and min_ok and rb["soc_min_pct"] > rb["soc_pct"] + FLOAT_TOL:
            fails.append(f"robot {rid}: recorded minimum "
                         f"{rb['soc_min_pct']:.2f} above final {rb['soc_pct']:.2f}")

    n_charge = sum(rb.get("charge_events") or 0 for rb in _fleet(res))
    soc_floor = min((rb["soc_min_pct"] for rb in _fleet(res)
                     if rb.get("soc_min_pct") is not None), default=None)
    return CheckResult(
        "B10 battery conservation",
        not fails,
        f"report-only: charge_events={n_charge}, fleet SOC floor="
        f"{soc_floor if soc_floor is None else round(soc_floor, 2)}% vs "
        f"soc_low_pct={bat['soc_low_pct']} (0 events is the EXPECTED corpus "
        f"result, §3.5); {n_blocked_returns} low-SOC returns judged",
        fails,
    )


# ------------------------------------------------------------------ B11


def check_end_state(inp: dict) -> CheckResult:
    """B11: the run ended because the work ended, with the fleet parked at home.

    `IDLE ∨ CHARGING_BLOCKED` — not `IDLE` alone. Dropping the second state is
    the mistake §3.2 warns about: a robot that came home low would never satisfy
    the condition and the run would not terminate at all, so a gate written that
    way would fail exactly the runs the charging model exists to produce.

    A cap termination is NOT a gate failure here — it is a failed RUN. The
    distinction matters because the corpus is expected to saturate: the response
    is to raise `max_overrun_sec_robot` and re-run, not to declare the model
    broken (점검 §10.1-B).
    """
    res = inp["res"]
    sim = res["kpi_summary"]["simulation"]
    kpi = res["kpi_summary"]
    fails: list[str] = []

    # The expected reason is the run's own termination POLICY, not the literal
    # "delivery_complete": a config on the legacy `drain_all` policy ends with
    # reason "drain_all" and is perfectly healthy. verify_h0's A14 compares
    # reason against policy for the same reason; hard-coding the string made
    # B11 fail every non-`delivery` HR run.
    policy = sim.get("termination_policy", "drain_all")
    reason = sim.get("termination_reason")
    expected = "delivery_complete" if policy == "delivery" else policy
    if reason != expected:
        cap_note = ("; a cap termination is a failed RUN — raise "
                    "max_overrun_sec_robot and re-run"
                    if sim.get("terminated_by_cap") else "")
        fails.append(f"termination_reason={reason!r} (policy={policy!r} expects "
                     f"{expected!r}{cap_note})")
    if sim.get("terminated_by_cap"):
        fails.append("run hit the overrun cap")
    if kpi["customer"]["n_delivered"] != kpi["customer"]["n_orders"]:
        fails.append(f"delivered {kpi['customer']['n_delivered']} != "
                     f"K={kpi['customer']['n_orders']}")

    # An absent or short fleet block would make every claim below vacuously
    # true — the same trap 결정 13 names. The declared size is the config's.
    # (NOT compared against `config.robot.n_robots`: `run_baseline(n_robots=)`
    # overrides it by design for Phase D's sizing sweep, so a mismatch there is
    # the intended behaviour, not a defect.)
    fleet = _fleet(res)
    reported_n = kpi.get("robot", {}).get("n_robots")
    if not fleet:
        fails.append("no `robot_fleet` in the artefact — 'every robot parked at "
                     "home' cannot be judged")
    elif reported_n is not None and len(fleet) != reported_n:
        fails.append(f"{len(fleet)} robot_fleet rows but kpi.robot.n_robots="
                     f"{reported_n}")

    for rb in fleet:
        rid = rb.get("robot_id")
        if rb.get("state") not in PARKED_STATES:
            fails.append(f"robot {rid} ended in state {rb.get('state')!r}, "
                         f"not one of {PARKED_STATES}")
        if rb.get("node") != HOME_NODE:
            fails.append(f"robot {rid} ended at {rb.get('node')!r}, not the "
                         f"robot zone")
    unserved = kpi.get("robot", {}).get("n_requests_unserved_at_end")
    if unserved:
        # F3: the field now covers BOTH halves of "not served" — riders still in
        # the FCFS queue and orders a robot was carrying when the run stopped.
        # In a completed run both are 0, so the gate's threshold is unchanged.
        fails.append(f"{unserved} robot requests unserved at the end (queued or "
                     f"dispatched but undelivered)")

    states = sorted({rb["state"] for rb in _fleet(res)})
    return CheckResult(
        "B11 end state",
        not fails,
        f"{reason}; {len(_fleet(res))} robots parked ({', '.join(states) or 'none'}), "
        f"delivered={kpi['customer']['n_delivered']}/{kpi['customer']['n_orders']}",
        fails,
    )


# ------------------------------------------------------------------------ core


def _saturation_report(res: dict) -> dict:
    """The numbers that replace a saturation gate (§3.6). Never judged."""
    kpi = res["kpi_summary"]
    return {
        "robot_queue_wait_p95_sec": kpi["rider"].get("robot_wait_p95_sec"),
        "t_building_order_p95_sec": kpi["customer"].get("t_building_order_p95_sec"),
        "drain_span_sec": kpi["building"].get("drain_span_sec"),
        "drain_deliveries": kpi["building"].get("drain_deliveries"),
        "robot_utilization_fixed": kpi.get("robot", {}).get("utilization_fixed_mean"),
        "robot_board_denied": kpi.get("robot", {}).get("n_board_denied"),
    }


def _guard(name: str, fn):  # noqa: ANN001, ANN202
    """Run one gate; turn a crash into a labelled FAIL instead of a traceback.

    A verifier's whole job is to survive bad input, and bad input is exactly
    what makes a gate raise (a None stamp subtracted, a floor that has no graph
    node). Reporting the exception keeps the other nine gates' verdicts, which
    is usually what tells you what actually went wrong — but it is labelled
    `gate crashed` so a defect in the GATE is never mistaken for a defect in
    the run.
    """
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 — deliberately broad, see docstring
        return _crashed(name, exc)


def _crashed(name: str, exc: Exception) -> CheckResult:
    return CheckResult(
        name, False, f"gate crashed: {type(exc).__name__}",
        [f"gate crashed on this artefact: {type(exc).__name__}: {exc}"],
    )


def _guard_pair(name: str, fn, fallback):  # noqa: ANN001, ANN202
    """`_guard` for the two gates that also return a report alongside a verdict."""
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001
        return _crashed(name, exc), fallback


def run_checks(result: dict) -> dict:
    """Run B1..B11 on an H1 results dict; return a report (importable API)."""
    # Keyed on the KEY's presence, not its truthiness: `run.py` emits
    # `robot_legs: []` for a robot run in which no trip finished, which is
    # exactly what a cap-truncated or badly undersized fleet produces — the run
    # that most needs B11's cap diagnosis. Rejecting it as "an H0 artefact"
    # refused to look at the one case the gate exists for.
    if "robot_legs" not in result:
        raise ValueError(
            "no `robot_legs` in the results JSON — verify_hr is for robot-mode "
            "runs (`--mode hr`); use analysis.verify_h0 for H0 artefacts"
        )
    # The scenario is the independent basis for B1's order set. Loading it can
    # fail (an archived artefact whose scenario file moved), and that must cost
    # one gate's evidence, not the whole report — so it is guarded here and B1
    # says so when it is missing.
    try:
        inp = load_inputs(result)
    except Exception:  # noqa: BLE001 — see above; B1 reports the consequence
        inp = {"res": result, "scenario": None, "riders": None}
    tick = _tick(result)
    b4_result, b4_report = _guard_pair(
        "B4 robot kinematics (lower bound)",
        lambda: check_robot_kinematics(inp, tick), {},
    )
    b9_result, gof = _guard_pair(
        "B9 floor-profile conformance", lambda: check_floor_profile_hr(inp), None,
    )
    checks = [
        _guard("B1 conservation (orders = handoffs = deliveries)",
               lambda: check_conservation(inp)),
        _guard("B2 order chain (courier + robot halves, joined)",
               lambda: check_courier_chain(inp, tick)),
        _guard("B3 robot conservation", lambda: check_robot_conservation(inp)),
        b4_result,
        _guard("B5 courier decomposition (exact identity)",
               lambda: check_courier_decomposition(inp, tick)),
        _guard("B7 FCFS dispatch replay", lambda: check_fcfs(inp)),
        _guard("B8 measurement windows (3 layers)", lambda: check_windows(inp, tick)),
        b9_result,
        _guard("B10 battery conservation", lambda: check_battery(inp)),
        _guard("B11 end state", lambda: check_end_state(inp)),
    ]
    return {
        "checks": checks,
        "all_passed": all(c.passed for c in checks),
        "floor_source": result.get("floor_source"),
        "b4_slack": b4_report,
        "b9_gof": gof,
        "saturation": _saturation_report(result),
    }


def verify_result(path_or_dict: str | Path | dict) -> dict:
    result = (path_or_dict if isinstance(path_or_dict, dict)
              else json.loads(_resolve(str(path_or_dict)).read_text()))
    return run_checks(result)


# ------------------------------------------------------------------------- CLI


def _print_report(report: dict, label: str) -> None:
    checks = report["checks"]
    width = max(len(c.name) for c in checks)
    print(f"verify_hr: {label}")
    print("-" * (width + 60))
    for c in checks:
        tag = "SKIP" if c.skipped else ("PASS" if c.passed else "FAIL")
        print(f"[{tag}] {c.name:<{width}}  {c.detail}")
        for f in c.failures[:20]:
            print(f"         - {f}")
        if len(c.failures) > 20:
            print(f"         ... and {len(c.failures) - 20} more")
    print("-" * (width + 60))
    s = report["saturation"]
    print("report-only (never a gate) — saturation is a measurement, not a defect:")
    print(f"  robot queue wait p95 = {s['robot_queue_wait_p95_sec']}s | "
          f"T_building_order p95 = {s['t_building_order_p95_sec']}s")
    print(f"  drain span = {s['drain_span_sec']}s ({s['drain_deliveries']} deliveries "
          f"outside the fixed window) | robot util = {s['robot_utilization_fixed']}")
    if report["b9_gof"] is not None:
        g = report["b9_gof"]
        print(f"  floor GOF chi2={g['chi2']} p={g['p_value']} dof={g['dof']}")
    n_pass = sum(1 for c in checks if c.passed and not c.skipped)
    n_skip = sum(1 for c in checks if c.skipped)
    n_fail = sum(1 for c in checks if not c.passed)
    print(f"{n_pass} passed, {n_skip} skipped, {n_fail} failed")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="H1 robot-relay results verifier (B1..B11)")
    parser.add_argument("results", nargs="+", help="results JSON(s) from simulation.run --mode hr")
    args = parser.parse_args(argv)

    exit_code = 0
    for i, results in enumerate(args.results):
        results_path = _resolve(results)
        if i:
            print()
        # One unusable file must not cost the verdicts on the rest: with
        # `nargs="+"` a single H0 artefact in the list used to abort the whole
        # CLI before any report was printed and before any exit code was set.
        try:
            report = verify_result(results_path)
        except Exception as exc:  # noqa: BLE001
            print(f"verify_hr: {results_path}\n[FAIL] cannot verify: "
                  f"{type(exc).__name__}: {exc}")
            exit_code = 1
            continue
        _print_report(report, str(results_path))
        if not report["all_passed"]:
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
