"""Core per-agent KPIs for the H0 baseline (plan_abm_baseline_h0.md §"H0 KPI").

Final KPIs are computed from event logs (rider records, elevator boarding
logs, pedestrian done log) at end of run — the DataCollector time series is
for visualization only.
"""

from __future__ import annotations

import csv
import io

import numpy as np


def _mean(xs: list[float]) -> float | None:
    return float(np.mean(xs)) if xs else None


def _p95(xs: list[float]) -> float | None:
    return float(np.percentile(xs, 95)) if xs else None


# ------------------------------------------------------------ V-KPIWIN windows
#
# Window-dependent KPIs are those whose *denominator* is the wall-clock span of
# the run (`wall_span_sec` = clock_end - clock_start = tick_count * dt). Under
# the scenario ±1 h pedestrian window (D4) that full span carries a warm-up
# head (min ORD_TIME - 1 h .. first order) and a cool-down tail (last delivery
# .. max ORD_TIME + 1 h) in which almost no delivery work happens, so a full-
# window denominator dilutes rate KPIs. The order span [min ORD_TIME, last
# delivered] is the sub-window in which delivery demand actually exists.
#
# Full enumeration of window-sensitive KPIs in this module:
#   * elevator[ev].utilization = busy_ticks / tick_count   (denominator = full
#     window). This is the EV util reported at 93-95% (§0.3 fact 5). NEW field
#     `utilization_orderspan` restricts both numerator (busy ticks landing in
#     the order span) and denominator (order-span ticks).
#   * building.opex_running_krw is an *accumulated* cost (numerator only, not
#     normalised by wall_span). It is near window-invariant because rider dwell
#     — the only thing that accrues OPEX — lies inside the order span; NEW field
#     `opex_running_krw_orderspan` restricts the accrual to the order span and
#     demonstrates that robustness (differs only by the post-last-delivery exit
#     tail of the final riders).
# All other KPIs are per-order / per-rider / per-boarding aggregates (t_e2e,
# t_lobby, w_ev, lobby_cost, cost_per_order, sla_rate, ...) whose values do not
# depend on the measurement window at all.
#
# New fields are strictly ADDITIVE: every pre-existing field name and value is
# unchanged, so the frozen full-window KPI regression is preserved bit-for-bit.


def _order_span(customers: list) -> tuple[float, float] | None:  # noqa: ANN001
    """[min ORD_TIME, last delivery] clock-second bounds, or None if no run."""
    ord_times = [c.ord_time_sec for c in customers]
    deliveries = [c.delivered_at_sec for c in customers if c.delivered_at_sec is not None]
    if not ord_times or not deliveries:
        return None
    return min(ord_times), max(deliveries)


# ------------------------------------------------------ R8-b delivery window
#
# [min ORD_TIME, last rider EXIT] — the interval in which the delivery system
# was actually operating, and the window the paper reports (plan_h0v21_window.md
# §3). It differs from the order span only by the last riders' descent and exit
# (measured 55~91 s), so `utilization_delivery` and `utilization_orderspan`
# agree to three decimals; both are kept because they answer different
# questions ("was the system busy" vs "were deliveries outstanding") and the
# orderspan fields are frozen KPI history.
#
# The R8 `delivery` termination policy ends the run exactly at this window's
# right edge, which is why the full-window `utilization` converges to
# `utilization_delivery` minus the warm-up head under that policy.


def _delivery_span(model) -> tuple[float, float] | None:  # noqa: ANN001
    """[min ORD_TIME, last rider exit] clock-second bounds, or None."""
    first = getattr(model, "first_order_sec", None)
    if first is None:
        return None
    exits = [
        r["exited_at_sec"] for r in model.rider_records
        if r.get("exited_at_sec") is not None
    ]
    if not exits:
        return None
    return first, max(exits)


# ------------------------------------------------- A5-b: the operating window
#
# `[min ORD_TIME, the moment the delivery system went quiet]` — the last rider
# exit in H0, the last ROBOT arriving home in H1. It is the delivery window with
# its right edge extended to cover the carrier that H0 does not have, so the two
# modes get the same definition and H0's value is unchanged by construction.
#
# WHY IT EXISTS (사용자 지적 2026-08-11). Fleet utilization was reported over the
# fixed window, whose span is set by the demand data (~3,500 s in every tier —
# more orders make the lunch peak DENSER, not longer). That makes the fixed
# window a constant-size box of 5 x 3,500 robot-seconds, so once the fleet
# saturates inside it the ratio pins at a ceiling set by the window, not by the
# fleet: K200 0.735 vs K300 0.738, while the actual work grew 48 %. Over the
# operating window the same runs read 0.905 vs 0.932.
#
# It also beats the full-run denominator, which carries the 600 s warm-up head
# in which no order exists yet — an artefact of the harness, not a property of
# the system.
#
# It is a layer ③ quantity (its right edge comes from the simulation), which is
# exactly right here: fleet utilization has no cross-mode comparison to protect,
# because H0 has no fleet.


def _ops_span(model) -> tuple[float, float] | None:  # noqa: ANN001
    """[min ORD_TIME, last carrier settled] clock-second bounds, or None."""
    first = getattr(model, "first_order_sec", None)
    if first is None:
        return None
    ends = [
        r["exited_at_sec"] for r in model.rider_records
        if r.get("exited_at_sec") is not None
    ]
    ends += [
        lg["returned_at_sec"] for lg in model.robot_leg_records.values()
        if lg.get("returned_at_sec") is not None
    ]
    if not ends:
        return None
    return first, max(ends)


# ------------------------------------------------- A3 layer ①: the fixed window
#
# 측정 창 (결정 14, 근거는 결정 #31로 정정 / HANDOFF_phase_a §3.7). The single
# common window of the original plan — `[first order, last delivery]` — is the
# same *definition* in every mode but not the same *interval*: H0 K300 spans
# ~5,100 s while H1 K300 spans ~27,000 s. Comparing resource occupancy across
# modes over intervals of different length confounds a robot effect with a
# window effect, so layer ① takes both edges from the scenario file, where no
# simulation decision can reach them.
#
# 🔴 2026-08-11 (결정 #31) — two things the original rationale got wrong:
#   * The drain is NOT quiet. Delivery lags order placement by ~20 min, so the
#     backlog peaks just AFTER the last order: measured pedestrian EV wait is
#     HIGHER in the drain than in the demand window (K300_4 shared cars, H0:
#     29.84 s in-window vs 39.28 s in the drain).
#   * Pedestrian EV wait is not the paper's headline anyway — it moves by
#     ±1-6 s where the primary quantities move by hundreds of seconds, and its
#     sign favours H1 under load. It is kept as a VALIDITY GUARD (if pedestrians
#     avoided the shared cars, the robot would inherit an artificially free
#     shaft and its benefit would be overstated). The externality that does bite
#     is on the robot side: its own EV wait (~60-75 s per delivery, on
#     `T_building_order`'s critical path) and `robot_board_denied`.
#
#   layer ① fixed window `[min ORD_TIME, max ORD_TIME]` — cross-mode resource
#           occupancy (pedestrian EV wait per car, EV utilization, mean
#           occupancy). Defined purely by the scenario file, so it is
#           bit-identical across modes, fleets and seeds. NOT fleet
#           utilization — see `_ops_span` and 결정 #31.
#   layer ② no window at all — per-order / per-rider quantities (T_e2e,
#           T_building_order, T_lobby, SLA). Already the case; `windows` in the
#           simulation block states it so a reader cannot assume otherwise.
#   layer ③ mode-internal diagnostics — `utilization_delivery`,
#           `utilization_orderspan`. Kept — they are frozen KPI history and they
#           answer "was the system busy while deliveries were outstanding" — but
#           they are NOT to be compared across modes.
#
# The traffic outside the fixed window is not discarded: `drain_*` reports it,
# because "robot delivery defers peak load past the peak" is itself a finding.


def _fixed_window(model) -> tuple[float, float] | None:  # noqa: ANN001
    """[min ORD_TIME, max ORD_TIME] — the mode-invariant window (layer ①).

    Both edges come from the scenario's order times, which no simulation
    decision can move, so H0 and H1 runs of the same scenario measure resource
    occupancy over the identical interval.
    """
    ord_times = [c.ord_time_sec for c in model.customer_by_ord_id.values()]
    if not ord_times:
        return None
    return min(ord_times), max(ord_times)


def _tick_index(clock_start_sec: float, dt: float, t: float, n_ticks: int) -> int:
    """Nearest tick index for absolute clock time `t`, clamped to [0, n_ticks].

    Cumulative snapshots are indexed so that index j is the state at clock time
    clock_start_sec + j*dt (index 0 = window start, index n_ticks = window end).
    """
    j = int(round((t - clock_start_sec) / dt))
    return max(0, min(n_ticks, j))


def _robot_block(model, fspan_ticks: int, f0: int, f1: int,  # noqa: ANN001
                 ospan_ticks: int, p0: int, p1: int) -> dict:
    """Fleet KPIs: utilization, the 7-bucket time split, battery, EV contention.

    ⚠️ `utilization_ops_mean` is the fleet-load figure to quote (A5-b). The
    fixed-window one is kept — it was the A3 headline and the frozen field — but
    it stops discriminating above ρ≈2: its denominator is the demand window,
    whose length does not grow with K, so once the fleet saturates inside it the
    ratio pins (K200 0.735 / K300 0.738 while the work grew 48 %). Quoting it
    for a fleet-sizing comparison reads as "more load did not make the fleet
    busier", which is false. See `_ops_span`.

    The bucket split is a layer ③ diagnostic (see the window note above) and is
    therefore full-run.

    ⚠️ On this corpus `n_charge_events == 0` is the EXPECTED result, not a
    missing measurement: a delivery costs ~9–10 Wh out of 1,300 Wh, so a lunch
    peak ends at 43–90 % SOC (§3.5). The battery fields are here to make that
    statement measurable — and to fire in the Phase E `soc_init` sweep, which is
    the only place in the study where the threshold is reachable.
    """
    robots = model.robots
    n = len(robots)
    busy_cum = getattr(model, "_robot_busy_cum", None)
    bucket_ticks = getattr(model, "_robot_bucket_ticks", None)
    ticks = model.tick_count

    util_fixed_by_robot = {}
    util_ops_by_robot = {}
    for i, rb in enumerate(robots):
        u = uo = None
        if busy_cum is not None:
            cum = busy_cum[i]
            if fspan_ticks > 0:
                u = (cum[f1] - cum[f0]) / fspan_ticks
            if ospan_ticks > 0:
                uo = (cum[p1] - cum[p0]) / ospan_ticks
        util_fixed_by_robot[str(rb.unique_id)] = u
        util_ops_by_robot[str(rb.unique_id)] = uo
    utils = [u for u in util_fixed_by_robot.values() if u is not None]
    utils_ops = [u for u in util_ops_by_robot.values() if u is not None]

    # fleet-time share per reporting bucket: total bucket ticks / total fleet
    # ticks. Sums to 1 by construction (report_bucket is a total function on the
    # state space and raises on an unmapped state), which is what makes the
    # paper figure's stacked bar honest.
    bucket_share = None
    if bucket_ticks is not None and ticks and n:
        totals: dict[str, int] = {}
        for d in bucket_ticks:
            for k, v in d.items():
                totals[k] = totals.get(k, 0) + v
        denom = float(ticks * n)
        bucket_share = {k: v / denom for k, v in totals.items()}

    legs = list(model.robot_leg_records.values())
    ev_up = [lg["ev_wait_up_sec"] for lg in legs if lg.get("ev_wait_up_sec") is not None]
    ev_dn = [
        lg["ev_wait_down_sec"] for lg in legs if lg.get("ev_wait_down_sec") is not None
    ]

    # A3 item 4: the robot counterpart of the H0 staleness figure (52.95 % /
    # ≤28.81 s harm). None when the evsel instrumentation was not requested —
    # an absent measurement, not a zero.
    stale_ratio = None
    n_calls = None
    if model.evsel_events is not None:
        calls = [e for e in model.evsel_events if e["kind"] == "robot"]
        n_calls = len(calls)
        if calls:
            stale_ratio = sum(1 for e in calls if e["stale"]) / len(calls)

    soc_end = [rb.soc_pct for rb in robots]

    # F3: what the cap cut off. A robot still holding an order at the end has an
    # unpublished leg; whether its ORDER was served is a separate question, so
    # the two are counted separately (see the fields below).
    inflight = [rb for rb in robots if rb.order is not None]
    n_inflight = len(inflight)
    n_assigned_undelivered = sum(
        1 for rb in inflight
        if model.customer_by_ord_id[rb.order.ord_id].delivered_at_sec is None
    )
    return {
        "n_robots": n,
        "trips_completed": sum(rb.trips_completed for rb in robots),
        "trips_by_robot": {str(rb.unique_id): rb.trips_completed for rb in robots},
        "n_leg_records": len(legs),
        # the fleet-load figure to quote (A5-b) — see the docstring
        "utilization_ops_mean": _mean(utils_ops),
        "utilization_ops_by_robot": util_ops_by_robot,
        "utilization_fixed_mean": _mean(utils),
        "utilization_fixed_by_robot": util_fixed_by_robot,
        "utilization_full_mean": (
            _mean([
                busy_cum[i][-1] / ticks for i in range(n)
            ]) if busy_cum is not None and ticks else None
        ),
        "bucket_share": bucket_share,
        # --- battery (§3.5) ---------------------------------------------------
        "soc_min_pct": min((rb.soc_min_pct for rb in robots), default=None),
        "soc_end_pct_min": min(soc_end, default=None),
        "soc_end_pct_mean": _mean(soc_end),
        "n_charge_events": sum(rb.charge_events for rb in robots),
        "charge_blocked_sec": sum(rb.charge_blocked_sec for rb in robots),
        "distance_traveled_m": sum(rb.distance_traveled_m for rb in robots),
        # --- elevator contention ---------------------------------------------
        "ev_wait_up_mean_sec": _mean(ev_up),
        "ev_wait_up_p95_sec": _p95(ev_up),
        "ev_wait_down_mean_sec": _mean(ev_dn),
        "ev_wait_down_p95_sec": _p95(ev_dn),
        "n_board_denied": sum(
            getattr(ev, "robot_board_denied", 0) for ev in model.elevators
        ),
        "evsel_stale_ratio": stale_ratio,
        "n_evsel_calls": n_calls,
        # --- saturation (§3.6) + cap censoring (F3) ---------------------------
        # A run stopped by `max_overrun_sec_robot` leaves work in mid-air, and
        # before F3 nothing in the summary said so: an unfinished leg is never
        # written to `robot_leg_records` (only `_finish_trip` publishes), and
        # `n_requests_unserved_at_end` counted the FCFS queue alone — so an order
        # that had been dispatched but not completed was invisible on both
        # sides. Phase D's small-fleet sweep is exactly where that happens.
        #   * `n_trips_inflight_at_end` — trips with no leg record, i.e. the
        #     censored work. 0 under any normal termination (the run only ends
        #     when every carrier has settled), so it is a cap detector.
        #   * `n_requests_unserved_at_end` — now queue + dispatched-but-not-
        #     delivered. The two sets are disjoint (a queued rider has no robot
        #     yet), and a robot still walking home from a COMPLETED delivery is
        #     counted in `n_trips_inflight_at_end` but NOT here: its order was
        #     served. Unchanged (0) in every non-cap run.
        "n_trips_inflight_at_end": n_inflight,
        "n_requests_queued_at_end": len(model.control.robot_requests),
        "n_requests_unserved_at_end": (
            len(model.control.robot_requests) + n_assigned_undelivered
        ),
    }


def summarize(model) -> dict:  # noqa: ANN001
    records = model.rider_records
    customers = list(model.customer_by_ord_id.values())

    # V-KPIWIN: order-span sub-window [min ORD_TIME, last delivery] and its tick
    # index bounds within the full-window cumulative snapshots (see helpers).
    span = _order_span(customers)
    n_ticks = model.tick_count
    if span is not None:
        j0 = _tick_index(model.clock_start_sec, model.dt, span[0], n_ticks)
        j1 = _tick_index(model.clock_start_sec, model.dt, span[1], n_ticks)
    else:
        j0 = j1 = 0
    span_ticks = j1 - j0

    # R8-b delivery sub-window [min ORD_TIME, last rider exit] (see above)
    dspan = _delivery_span(model)
    if dspan is not None:
        d0 = _tick_index(model.clock_start_sec, model.dt, dspan[0], n_ticks)
        d1 = _tick_index(model.clock_start_sec, model.dt, dspan[1], n_ticks)
    else:
        d0 = d1 = 0
    dspan_ticks = d1 - d0

    # A3 layer ①: the mode-invariant fixed window (see _fixed_window).
    fspan = _fixed_window(model)
    if fspan is not None:
        f0 = _tick_index(model.clock_start_sec, model.dt, fspan[0], n_ticks)
        f1 = _tick_index(model.clock_start_sec, model.dt, fspan[1], n_ticks)
    else:
        f0 = f1 = 0
    fspan_ticks = f1 - f0

    # A5-b: the operating window (see _ops_span) — the denominator for fleet
    # utilization, and the only one of the four that neither truncates the work
    # nor pads the clock with a warm-up the system could not have used.
    ospan = _ops_span(model)
    if ospan is not None:
        p0 = _tick_index(model.clock_start_sec, model.dt, ospan[0], n_ticks)
        p1 = _tick_index(model.clock_start_sec, model.dt, ospan[1], n_ticks)
    else:
        p0 = p1 = 0
    ospan_ticks = p1 - p0

    # --- Customer ----------------------------------------------------------
    t_e2e = [c.t_e2e_sec for c in customers if c.t_e2e_sec is not None]
    n_delivered = len(t_e2e)
    n_sla_violations = sum(1 for c in customers if c.sla_violation)
    # A3 layer ②: `T_building_order` — how long the FOOD was inside the
    # building, from the courier walking in with it to the customer receiving
    # it. This is the quantity that means the same thing in every mode, and the
    # one the paper compares: H0's `t_lobby` happens to equal it because the
    # courier stays with the order to the door, but H1's `t_lobby` is only the
    # courier's own dwell (arrival → handoff → exit) and diverges under
    # saturation for a reason that has nothing to do with the customer.
    # `t_order_post_handoff_sec` splits off the robot's half (handoff start →
    # delivery) and is None in H0, where no handoff exists.
    rec_by_ord = {r["ord_id"]: r for r in records}
    t_building_order: list[float] = []
    t_post_handoff: list[float] = []
    for ord_id, c in model.customer_by_ord_id.items():
        rec = rec_by_ord.get(ord_id)
        if rec is None or c.delivered_at_sec is None:
            continue          # order never delivered, or courier still inside
        t_building_order.append(c.delivered_at_sec - rec["entered_at_sec"])
        hstart = rec.get("handoff_started_sec")
        if hstart is not None:
            t_post_handoff.append(c.delivered_at_sec - hstart)
    customer = {
        "n_orders": model.K,
        "n_delivered": n_delivered,
        "t_e2e_mean_sec": _mean(t_e2e),
        "t_e2e_p95_sec": _p95(t_e2e),
        "sla_violation_rate": (n_sla_violations / n_delivered) if n_delivered else None,
        "n_sla_violations": n_sla_violations,
        "t_building_order_mean_sec": _mean(t_building_order),
        "t_building_order_p95_sec": _p95(t_building_order),
        "n_building_order": len(t_building_order),
        "t_order_post_handoff_mean_sec": _mean(t_post_handoff),
        "t_order_post_handoff_p95_sec": _p95(t_post_handoff),
    }

    # --- Rider ---------------------------------------------------------------
    t_lobby = [r["t_lobby_sec"] for r in records]
    lobby_cost = sum(r["w_R_krw_per_h"] / 3600.0 * r["t_lobby_sec"] for r in records)
    ev_waits_up = [r["ev_wait_up_sec"] for r in records if r["ev_wait_up_sec"] is not None]
    ev_waits_down = [
        r["ev_wait_down_sec"] for r in records if r["ev_wait_down_sec"] is not None
    ]
    # A3: the courier's wait for a free robot — the saturation signal (§3.6).
    # None-valued in H0 records, so the lists are empty there and the fields
    # read `None` rather than a fabricated zero.
    robot_waits = [
        r["robot_wait_sec"] for r in records
        if r.get("robot_wait_sec") is not None
    ]
    handoffs = [r["handoff_sec"] for r in records if r.get("handoff_sec") is not None]
    rider = {
        "n_exited": len(records),
        "t_lobby_mean_sec": _mean(t_lobby),
        "t_lobby_p95_sec": _p95(t_lobby),
        "lobby_cost_total_krw": round(lobby_cost, 1),
        "ev_wait_up_mean_sec": _mean(ev_waits_up),
        "ev_wait_down_mean_sec": _mean(ev_waits_down),
        "n_by_mode": {
            # A3 (이월 §A2-⑤-5): the H1 courier never uses the vertical system,
            # so both counters are structurally 0 and the pair is meaningless —
            # `handoff` is where its riders land. Kept as a fixed three-key dict
            # rather than a mode branch so the schema is the same in both modes
            # and a table can be built without asking which mode produced it.
            m: sum(1 for r in records if r["vertical_mode"] == m)
            for m in ("elevator", "stairs", "handoff")
        },
        "robot_wait_mean_sec": _mean(robot_waits),
        "robot_wait_p95_sec": _p95(robot_waits),
        "handoff_mean_sec": _mean(handoffs),
        "n_handoffs": len(handoffs),
    }

    # --- Elevator ------------------------------------------------------------
    ev_busy_cum = getattr(model, "_ev_busy_cum", None)
    ev_pax_cum = getattr(model, "_ev_pax_cum", None)
    elevators = {}
    # raw per-car fixed-window waits, kept so the dedicated/shared groups below
    # can be aggregated from observations rather than from per-car means (a mean
    # of means would silently weight a car with 3 boardings like one with 300)
    fixed_waits_by_ev: dict[str, dict[str, list[float]]] = {}
    # F2 (Fable 5 리뷰 2026-08-11): the per-car split carries a `robot` key iff
    # a fleet exists, which is what the T0a comment below always promised ("H1
    # adds it when robots exist") and what `analysis/vv_balance.py` already
    # filters on. In H0 the key set is unchanged, so the frozen schema is intact.
    person_kinds = ("rider", "pedestrian")
    full_kinds = (*person_kinds, "robot") if model.robots else person_kinds
    for ev_idx, ev in enumerate(model.elevators):
        # F2: personhood rule (A3 item 5) — `w_ev_mean_sec`/`w_ev_p95_sec` are
        # "the wait a PERSON experienced at this car", so a robot boarding is
        # excluded exactly as it is from `building.w_ev_mean_all_sec`. Before the
        # fix these two fields averaged robots into the people's wait while the
        # by-kind split next to them dropped robots entirely — the same car
        # reported 221 boardings, a by-kind sum of 167 and a 16 %-contaminated
        # mean (H1 K50_1 seed 42, EV3: 29.46 s pooled vs 25.37 s for people).
        # Filtered in boarding order so H0, where the filter is a no-op, stays
        # bit-identical.
        waits = [b["wait_sec"] for b in ev.boarding_log if b["kind"] != "robot"]
        # V-KPIWIN: busy fraction over the order span only (numerator = busy
        # ticks landing in the span, denominator = span ticks). None when the
        # span is empty or the cumulative history is unavailable (older models).
        util_orderspan = None
        if ev_busy_cum is not None and span_ticks > 0:
            cum = ev_busy_cum[ev_idx]
            util_orderspan = (cum[j1] - cum[j0]) / span_ticks
        # R8-b: same, over the delivery window, plus the mean number of people
        # on board there — `utilization` is time-not-parked, not load.
        util_delivery = None
        mean_pax_delivery = None
        if dspan_ticks > 0:
            if ev_busy_cum is not None:
                cum = ev_busy_cum[ev_idx]
                util_delivery = (cum[d1] - cum[d0]) / dspan_ticks
            if ev_pax_cum is not None:
                pcum = ev_pax_cum[ev_idx]
                mean_pax_delivery = (pcum[d1] - pcum[d0]) / dspan_ticks
        # T0a (2026-08-06): per-car split by boarding kind. `n_boardings` and
        # `w_ev_*` pool riders and pedestrians, so a car's person-load and the
        # *pedestrian* wait it produces cannot be read per car — precisely the
        # two quantities the robot modes need per car, because robots use only
        # the shared cars (`building.shared_ev_ids`, EV3/EV4) and the paper's
        # claim is a two-sided externality (shared cars degrade, dedicated cars
        # may improve). Recorded here for H0 so the H1 comparison has a
        # pre-robot baseline; Phase A Step A3 would otherwise have to
        # reconstruct it after the fact. `robot` is *not* a key in H0 — H0 has no
        # robot boardings and inventing an always-zero key would make the H0
        # schema lie about what it measured; H1 adds it when robots exist
        # (F2 — before the fix it never did, so 54 of EV3's 221 boardings were
        # invisible in every H1 summary).
        # Strictly additive: every pre-existing field above is untouched, which
        # is what tests/test_h0_frozen_snapshot.py's superset invariant checks.
        waits_by_kind: dict[str, list[float]] = {k: [] for k in full_kinds}
        for b in ev.boarding_log:
            if b["kind"] in waits_by_kind:
                waits_by_kind[b["kind"]].append(b["wait_sec"])
        # A3 layer ①: the same split restricted to the fixed window, and this
        # is the PRIMARY record for the externality claim — `ev_id` is the unit
        # of truth, the dedicated/shared groups below are derived from it.
        # `robot` is an unconditional key here (unlike the full-window split
        # above, which adds it only when a fleet exists so the frozen H0 schema
        # is preserved) because in H1 the robot boardings ARE the mechanism
        # under study; this dict is fixed-key so H0 reports an honest empty
        # `robot` entry (n=0, wait None) inside a field that did not exist
        # before A3 and therefore has no frozen H0 form to protect.
        # A boarding is placed in the window by `t_board_sec`, the moment the
        # car actually took the passenger: the alternative (wait start) would
        # let a queue that formed inside the window but boarded after it count
        # its whole wait against the window, which is exactly the dilution the
        # window exists to prevent.
        fixed_by_kind: dict[str, list[float]] = {
            "rider": [], "pedestrian": [], "robot": []
        }
        if fspan is not None:
            for b in ev.boarding_log:
                if b["kind"] in fixed_by_kind and fspan[0] <= b["t_board_sec"] <= fspan[1]:
                    fixed_by_kind[b["kind"]].append(b["wait_sec"])
        fixed_waits_by_ev[ev.ev_id] = fixed_by_kind
        util_fixed = None
        mean_pax_fixed = None
        if fspan_ticks > 0:
            if ev_busy_cum is not None:
                cum = ev_busy_cum[ev_idx]
                util_fixed = (cum[f1] - cum[f0]) / fspan_ticks
            if ev_pax_cum is not None:
                pcum = ev_pax_cum[ev_idx]
                mean_pax_fixed = (pcum[f1] - pcum[f0]) / fspan_ticks
        elevators[ev.ev_id] = {
            "utilization": ev.busy_ticks / model.tick_count if model.tick_count else 0.0,
            "utilization_orderspan": util_orderspan,
            "utilization_delivery": util_delivery,
            "mean_passengers_delivery": mean_pax_delivery,
            "n_boardings": len(ev.boarding_log),
            "n_alights": ev.alight_count,
            "w_ev_mean_sec": _mean(waits),
            "w_ev_p95_sec": _p95(waits),
            "capacity_violations": ev.capacity_violations,
            "shared_with_robot": ev.shared_with_robot,
            "n_boardings_by_kind": {k: len(v) for k, v in waits_by_kind.items()},
            "w_ev_mean_by_kind_sec": {k: _mean(v) for k, v in waits_by_kind.items()},
            "w_ev_p95_by_kind_sec": {k: _p95(v) for k, v in waits_by_kind.items()},
            # --- A3 fixed-window (layer ①) fields --------------------------
            "utilization_ops": (
                (ev_busy_cum[ev_idx][p1] - ev_busy_cum[ev_idx][p0]) / ospan_ticks
                if ev_busy_cum is not None and ospan_ticks > 0 else None
            ),
            "utilization_fixed": util_fixed,
            "mean_passengers_fixed": mean_pax_fixed,
            "n_boardings_by_kind_fixed": {k: len(v) for k, v in fixed_by_kind.items()},
            "w_ev_mean_by_kind_fixed_sec": {
                k: _mean(v) for k, v in fixed_by_kind.items()
            },
            "w_ev_p95_by_kind_fixed_sec": {
                k: _p95(v) for k, v in fixed_by_kind.items()
            },
            "robot_board_denied": getattr(ev, "robot_board_denied", 0),
        }
    # A3 item 5: `w_ev_mean_all_sec` is "the mean wait a PERSON experienced at a
    # car". A robot boarding is not a person and must not average into it, or
    # the H0→H1 comparison of that field would move for a reason that has
    # nothing to do with how people were served. H0 has no robot boardings, so
    # the filter is a no-op there and the frozen value is unchanged; robots get
    # their own field below.
    all_waits = [
        b["wait_sec"]
        for ev in model.elevators
        for b in ev.boarding_log
        if b["kind"] != "robot"
    ]
    rider_waits = [
        b["wait_sec"]
        for ev in model.elevators
        for b in ev.boarding_log
        if b["kind"] == "rider"
    ]
    robot_ev_waits = [
        b["wait_sec"]
        for ev in model.elevators
        for b in ev.boarding_log
        if b["kind"] == "robot"
    ]

    # --- Pedestrian ------------------------------------------------------------
    ped_waits = [
        p["ev_wait_sec"] for p in model.ped_done_log if p["ev_wait_sec"] is not None
    ]
    pedestrian = {
        "n_spawned": model.ped_spawned,
        "n_completed": len(model.ped_done_log),
        "ev_wait_mean_sec": _mean(ped_waits),
        # R8-b: pedestrians still inside when the run stopped. Zero under the
        # drain-all policy by construction; under `delivery` these are censored
        # (they never reach ped_done_log), so `ev_wait_mean_sec` is very
        # slightly biased low — the count is recorded to size that bias.
        "n_in_building_at_end": model.ped_spawned - len(model.ped_done_log),
    }

    # --- Building --------------------------------------------------------------
    # V-KPIWIN: OPEX accrued within the order span only. Near-identical to the
    # full-window total (rider dwell lies inside the span); the small gap is the
    # last riders' exit dwell after the final delivery.
    opex_cum = getattr(model, "_opex_cum", None)
    opex_orderspan = (
        round(opex_cum[j1] - opex_cum[j0], 1)
        if opex_cum is not None and span is not None
        else None
    )
    opex_delivery = (
        round(opex_cum[d1] - opex_cum[d0], 1)
        if opex_cum is not None and dspan is not None
        else None
    )
    # A3 item 2 (결정 13): the dedicated/shared split is DERIVED from the
    # per-`ev_id` record, which is the primary one. With a four-shared-car
    # configuration the dedicated set is empty, and an empty set has no mean —
    # so the group fields are `None`, never 0.0. Reporting 0.0 would read as
    # "dedicated cars had no wait", i.e. the strongest possible version of the
    # very claim under test, produced by a configuration in which the claim is
    # not even defined.
    ded_ids = [ev.ev_id for ev in model.elevators if not ev.shared_with_robot]
    shr_ids = [ev.ev_id for ev in model.elevators if ev.shared_with_robot]

    def _group(ids: list[str], kind: str) -> dict[str, float | int | None]:
        if not ids:
            return {"mean_sec": None, "p95_sec": None, "n": None}
        xs = [w for i in ids for w in fixed_waits_by_ev[i][kind]]
        return {"mean_sec": _mean(xs), "p95_sec": _p95(xs), "n": len(xs)}

    ped_ded = _group(ded_ids, "pedestrian")
    ped_shr = _group(shr_ids, "pedestrian")

    # A3: the drain — everything that happened after the last order was placed,
    # i.e. outside the fixed window. Not a leftover but a result: a robot fleet
    # too small for the load pushes delivery work past the demand peak, and the
    # size of that push is the observable. `drain_span_sec` is measured to the
    # last delivery (the last thing the delivery system did), not to the run's
    # end, which is set by the termination policy rather than by the workload.
    deliveries = [
        c.delivered_at_sec for c in customers if c.delivered_at_sec is not None
    ]
    # F5 — `drain_span_sec` is a LENGTH, so its convention is:
    #     None  the run delivered nothing at all (nothing to measure)
    #     0.0   deliveries exist but none landed after the fixed window — the
    #           drain is empty, which is a real answer and not a missing one
    #     > 0   clock seconds from the last order to the last delivery
    # Without the 0.0 floor a capped run reports a NEGATIVE span (measured
    # -54.0 s with `max_overrun_sec_robot=10` on K50_1 s42, `drain_deliveries=0`),
    # which reads as "the drain ran backwards" and breaks any downstream sum.
    # Note the floor hides no information: `drain_deliveries == 0` says the drain
    # was empty, and `terminated_by_cap` says why.
    if fspan is not None:
        w_end = fspan[1]
        drain_span = max(0.0, max(deliveries) - w_end) if deliveries else None
        drain_deliveries = sum(1 for t in deliveries if t > w_end)
        drain_boardings = sum(
            1 for ev in model.elevators for b in ev.boarding_log
            if b["t_board_sec"] > w_end
        )
        drain_robot_trips = sum(
            1 for lg in model.robot_leg_records.values()
            if lg.get("delivered_at_sec") is not None
            and lg["delivered_at_sec"] > w_end
        )
    else:
        drain_span = None
        drain_deliveries = drain_boardings = drain_robot_trips = 0

    building = {
        "capex_total_krw": model.manager.capex_total_krw,      # H0: 0
        "opex_running_krw": round(model.manager.opex_running_krw, 1),
        "opex_running_krw_orderspan": opex_orderspan,
        "opex_running_krw_delivery": opex_delivery,
        "cost_per_order_krw": round(lobby_cost / model.K, 1) if model.K else None,
        "w_ev_mean_all_sec": _mean(all_waits),
        "w_ev_mean_riders_sec": _mean(rider_waits),
        # --- A3: robot EV load + fixed-window pedestrian groups (layer ①) ---
        "w_ev_mean_robots_sec": _mean(robot_ev_waits),
        "w_ev_p95_robots_sec": _p95(robot_ev_waits),
        "ped_ev_wait_fixed_dedicated_mean_sec": ped_ded["mean_sec"],
        "ped_ev_wait_fixed_dedicated_p95_sec": ped_ded["p95_sec"],
        "ped_ev_wait_fixed_dedicated_n": ped_ded["n"],
        "ped_ev_wait_fixed_shared_mean_sec": ped_shr["mean_sec"],
        "ped_ev_wait_fixed_shared_p95_sec": ped_shr["p95_sec"],
        "ped_ev_wait_fixed_shared_n": ped_shr["n"],
        "dedicated_ev_ids": ded_ids,
        "shared_ev_ids": shr_ids,
        # --- A3: drain (outside the fixed window) ---------------------------
        "drain_span_sec": drain_span,
        "drain_deliveries": drain_deliveries,
        "drain_ev_boardings": drain_boardings,
        "drain_robot_trips": drain_robot_trips,
    }

    out = {
        "customer": customer,
        "rider": rider,
        "elevator": elevators,
        "pedestrian": pedestrian,
        "building": building,
        "simulation": {
            "ticks": model.tick_count,
            "clock_end_sec": model.clock_sec,
            "wall_span_sec": model.clock_sec - model.clock_start_sec,
            "terminated_by_cap": model.terminated_by_cap,
            "scenario_window": model.scenario_window,
            "clock_start_sec": model.clock_start_sec,
            "ped_window_sec": [model.ped_start_sec, model.ped_end_sec],
            # V-KPIWIN: order-span sub-window used by *_orderspan KPIs.
            "orderspan_window_sec": list(span) if span is not None else None,
            "wall_span_orderspan_sec": (span[1] - span[0]) if span is not None else None,
            # --- R8-b: window/termination provenance + delivery sub-window ----
            "window_policy": getattr(model, "window_policy", "legacy_margin"),
            "warmup_sec": getattr(model, "warmup_sec", None),
            "termination_policy": getattr(model, "termination_policy", "drain_all"),
            "termination_reason": getattr(model, "termination_reason", None),
            "delivery_window_sec": list(dspan) if dspan is not None else None,
            "wall_span_delivery_sec": (
                (dspan[1] - dspan[0]) if dspan is not None else None
            ),
            # state of the building when the first order landed (A13 input)
            "warmup": getattr(model, "_warmup_snapshot", None),
            # --- A3: the fixed window and the 3-layer contract ---------------
            "fixed_window_sec": list(fspan) if fspan is not None else None,
            "wall_span_fixed_sec": (fspan[1] - fspan[0]) if fspan is not None else None,
            # A5-b: [first order, last carrier settled] — the fleet-utilization
            # denominator. Equals the delivery window in H0 by construction.
            "ops_window_sec": list(ospan) if ospan is not None else None,
            "wall_span_ops_sec": (ospan[1] - ospan[0]) if ospan is not None else None,
            # Machine-readable statement of which window each family of KPIs was
            # measured over (결정 14). A reader — or Phase D's aggregation — must
            # not have to infer it from a field name suffix.
            "windows": {
                "layer1_fixed": "[min ORD_TIME, max ORD_TIME]; mode-invariant; "
                                "fields suffixed _fixed + building.ped_ev_wait_fixed_*",
                "layer2_orderset": "no window; per-order/per-rider aggregates "
                                   "(t_e2e, t_building_order, t_lobby, SLA)",
                "layer3_mode_internal": "utilization_ops (fleet load — QUOTE THIS "
                                        "for fleet sizing), utilization_delivery, "
                                        "utilization_orderspan — diagnostic within "
                                        "one mode, never across",
            },
        },
    }
    # --- Robot (H1+) ---------------------------------------------------------
    # Emitted only when a fleet exists, following the T0a precedent: an
    # always-zero robot block in an H0 summary would make the H0 schema claim it
    # measured something it structurally cannot have.
    if model.robots:
        out["robot"] = _robot_block(model, fspan_ticks, f0, f1, ospan_ticks, p0, p1)
    return out


# --------------------------------------------------------------- KPI report
# Downloadable end-of-run KPI table (S7.1): flatten summarize() into
# (section, metric, value) rows, render as Markdown / CSV. Pure functions of
# the summary dict so they are unit-testable without a Solara server.

_SECTION_ORDER = [
    ("simulation", "Simulation"),
    ("customer", "Customer"),
    ("rider", "Rider"),
    # A3: absent from an H0 summary; `summary.get(key, {})` below renders it as
    # no rows rather than as a section of n/a
    ("robot", "Robot"),
    ("elevator", "Elevator"),
    ("pedestrian", "Pedestrian"),
    ("building", "Building"),
]


# F8: ratio-valued metrics render to THREE decimals, everything else to two.
# The module docstring's own example is why: the reason `utilization_ops` exists
# is that the fixed-window ratio pins at K200 0.735 vs K300 0.738 — a contrast
# two decimals rounds into a single "0.74" and deletes from the report. Seconds,
# counts, costs and percentages keep two decimals; widening every float would
# add three digits of false precision to a 41,407.00 s clock reading.
# Matched on the metric name (including the dotted sub-key, so `bucket_share.*`
# and `utilization_ops_by_robot.*` are covered) because the value alone cannot
# say whether a 0.735 is a ratio or a number of seconds.
_RATIO_METRIC_TOKENS = ("util", "bucket_share", "_ratio", "_rate")


def _is_ratio_metric(metric: str) -> bool:
    return any(tok in metric for tok in _RATIO_METRIC_TOKENS)


def _fmt(v, metric: str = "") -> str:  # noqa: ANN001
    if v is None:
        return "n/a"
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, float):
        return f"{v:.3f}" if _is_ratio_metric(metric) else f"{v:.2f}"
    return str(v)


def summary_to_rows(summary: dict) -> list[tuple[str, str, str]]:
    """Flatten the nested summarize() dict into (section, metric, value) rows."""
    rows: list[tuple[str, str, str]] = []
    for key, label in _SECTION_ORDER:
        block = summary.get(key, {})
        if key == "elevator":  # nested one level deeper: per EV id
            for ev_id, ev_block in block.items():
                for metric, value in ev_block.items():
                    if isinstance(value, dict):  # T0a: *_by_kind splits
                        for sub, sub_v in value.items():
                            name = f"{metric}.{sub}"
                            rows.append((f"{label} {ev_id}", name, _fmt(sub_v, name)))
                        continue
                    rows.append((f"{label} {ev_id}", metric, _fmt(value, metric)))
            continue
        for metric, value in block.items():
            if isinstance(value, dict):  # e.g. rider.n_by_mode
                for sub, sub_v in value.items():
                    name = f"{metric}.{sub}"
                    rows.append((label, name, _fmt(sub_v, name)))
            else:
                rows.append((label, metric, _fmt(value, metric)))
    return rows


def summary_to_markdown(summary: dict, meta: dict | None = None) -> str:
    """KPI report as a Markdown document (one table per section)."""
    lines = ["# H0 Baseline — KPI Report", ""]
    for k, v in (meta or {}).items():
        lines.append(f"- **{k}**: {v}")
    if meta:
        lines.append("")
    rows = summary_to_rows(summary)
    current = None
    for i, (section, metric, value) in enumerate(rows):
        if section != current:
            lines += [f"## {section}", "", "| metric | value |", "|---|---|"]
            current = section
        lines.append(f"| {metric} | {value} |")
        if i + 1 < len(rows) and rows[i + 1][0] != section:
            lines.append("")
    lines.append("")
    return "\n".join(lines)


def summary_to_csv(summary: dict, meta: dict | None = None) -> str:
    """KPI report as flat CSV: section,metric,value (meta rows prefixed).

    F4: written by the `csv` module, not by string joining. Every summary
    contains values with commas in them — `simulation.ped_window_sec` is
    `[41400.0, 72000.0]`, `building.shared_ev_ids` is `['EV3', 'EV4']`, the
    `windows` contract rows are prose — so the hand-joined version emitted 4-
    and 5-column rows into a 3-column file on EVERY run, and any reader that
    split on commas mis-parsed them. Quoting is the whole fix; the column
    layout, the row order and the meta prefix are unchanged.
    """
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["section", "metric", "value"])
    for k, v in (meta or {}).items():
        w.writerow(["meta", k, v])
    w.writerows(summary_to_rows(summary))
    return buf.getvalue()
