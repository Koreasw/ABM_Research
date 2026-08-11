"""Step A3 — KPI additions, the 3-layer measurement window, runner plumbing.

The load-bearing test in this module is `test_fixed_window_is_mode_invariant`.
Everything else guards a field; that one guards the *argument*: the paper claims
a two-sided externality (robots congest the shared cars, the dedicated cars may
improve), and the claim is only readable if H0 and H1 measured pedestrian
occupancy over the same interval. They do not run for the same length of time —
H1 keeps working long after the last order — so any window whose right edge is
produced by the simulation (last delivery, last exit, run end) silently gives
the two modes different intervals and dilutes H1's numbers toward zero. Layer ①
takes both edges from the scenario file instead, where no simulation decision
can reach them.

The other thing pinned here is what is deliberately NOT reported: an empty
dedicated-car set yields `None`, not 0.0 (결정 13), and an H0 summary carries no
`robot` block at all rather than a block of zeros (T0a precedent).
"""

from __future__ import annotations

import copy

import pytest

from simulation.kpi import _fixed_window, summarize
from simulation.model import ROOT, BuildingHandoffModel, HandoffMode
from simulation.run import run_baseline
from simulation.space import load_config

pytestmark = pytest.mark.vv

SCENARIO = "data/data1/K50_1.json"
CONFIG = ROOT / "configs/baseline_10f.yaml"


def _model(mode: HandoffMode, **kw):  # noqa: ANN001
    params = {
        "mode": mode,
        "config": load_config(CONFIG),
        "scenario_path": SCENARIO,
        "rng_seed": 42,
        "dynamic_pool": True,
        "scenario_window": True,
        "floor_profile": "uniform",
        "floor_seed": 42,
    }
    params.update(kw)
    return BuildingHandoffModel(**params)


def _run(mode: HandoffMode, **kw):  # noqa: ANN001
    m = _model(mode, **kw)
    m.run_to_completion()
    return m


@pytest.fixture(scope="module")
def hr_model():
    return _run(HandoffMode.H1_SYNC)


@pytest.fixture(scope="module")
def h0_model():
    return _run(HandoffMode.H0_DIRECT)


# ------------------------------------------------------ layer ①: fixed window


def test_fixed_window_matches_its_definition(hr_model) -> None:
    ord_times = [c.ord_time_sec for c in hr_model.customer_by_ord_id.values()]
    assert _fixed_window(hr_model) == (min(ord_times), max(ord_times))


def test_fixed_window_is_mode_invariant(h0_model, hr_model) -> None:
    """Same scenario, same seed, different mode -> byte-identical window.

    And the windows that are NOT mode-invariant must genuinely differ here, or
    the test would pass vacuously on a corpus where every window happens to
    coincide.
    """
    s0 = summarize(h0_model)["simulation"]
    s1 = summarize(hr_model)["simulation"]
    assert s0["fixed_window_sec"] == s1["fixed_window_sec"]
    assert s0["wall_span_fixed_sec"] == s1["wall_span_fixed_sec"]
    assert s0["delivery_window_sec"] != s1["delivery_window_sec"], (
        "the mode-dependent window no longer moves between modes — the "
        "mode-invariant one is then untested"
    )


def test_fixed_window_utilization_recomputes(hr_model) -> None:
    """`utilization_fixed` equals a hand recompute from the tick snapshots."""
    s = summarize(hr_model)
    lo, hi = s["simulation"]["fixed_window_sec"]
    dt, start = hr_model.dt, hr_model.clock_start_sec
    f0 = int(round((lo - start) / dt))
    f1 = int(round((hi - start) / dt))
    for i, ev in enumerate(hr_model.elevators):
        cum = hr_model._ev_busy_cum[i]
        expected = (cum[f1] - cum[f0]) / (f1 - f0)
        assert s["elevator"][ev.ev_id]["utilization_fixed"] == pytest.approx(expected)


def test_fixed_window_boardings_are_a_subset_of_all_boardings(hr_model) -> None:
    s = summarize(hr_model)
    for ev in hr_model.elevators:
        blk = s["elevator"][ev.ev_id]
        n_fixed = sum(blk["n_boardings_by_kind_fixed"].values())
        assert 0 < n_fixed <= blk["n_boardings"]


def test_windows_contract_is_declared(hr_model) -> None:
    """The 3 layers are stated in the artefact, not only in the plan document."""
    w = summarize(hr_model)["simulation"]["windows"]
    assert set(w) == {"layer1_fixed", "layer2_orderset", "layer3_mode_internal"}
    assert "ORD_TIME" in w["layer1_fixed"]


# ------------------------------------- layer ①: per-car primary, group derived


def test_group_waits_are_derived_from_the_per_car_record(hr_model) -> None:
    s = summarize(hr_model)
    bu = s["building"]
    for group, ids in (("dedicated", bu["dedicated_ev_ids"]),
                       ("shared", bu["shared_ev_ids"])):
        n = sum(
            s["elevator"][i]["n_boardings_by_kind_fixed"]["pedestrian"] for i in ids
        )
        assert bu[f"ped_ev_wait_fixed_{group}_n"] == n


def test_robots_board_only_shared_cars(hr_model) -> None:
    s = summarize(hr_model)
    for ev in hr_model.elevators:
        n_robot = s["elevator"][ev.ev_id]["n_boardings_by_kind_fixed"]["robot"]
        if ev.shared_with_robot:
            assert n_robot > 0
        else:
            assert n_robot == 0


def test_dedicated_group_is_none_when_every_car_is_shared() -> None:
    """결정 13: an empty set has no mean — the field is None, never 0.0.

    Also the first exercise of the injected-config path (A3 item 6): before it
    existed, varying one config key meant driving the model by hand.
    """
    cfg = copy.deepcopy(load_config(CONFIG))
    cfg["building"]["shared_ev_ids"] = ["EV1", "EV2", "EV3", "EV4"]
    m = _run(HandoffMode.H1_SYNC, config=cfg)
    bu = summarize(m)["building"]
    assert bu["dedicated_ev_ids"] == []
    assert bu["ped_ev_wait_fixed_dedicated_mean_sec"] is None
    assert bu["ped_ev_wait_fixed_dedicated_p95_sec"] is None
    assert bu["ped_ev_wait_fixed_dedicated_n"] is None
    assert bu["ped_ev_wait_fixed_shared_n"] > 0


# --------------------------------------------- layer ②: T_building_order


def test_t_building_order_is_the_food_clock(hr_model) -> None:
    """Courier walks in with it -> customer receives it, in both modes."""
    s = summarize(hr_model)
    rec = {r["ord_id"]: r for r in hr_model.rider_records}
    expected = [
        c.delivered_at_sec - rec[o]["entered_at_sec"]
        for o, c in hr_model.customer_by_ord_id.items()
        if c.delivered_at_sec is not None and o in rec
    ]
    assert s["customer"]["n_building_order"] == len(expected)
    assert s["customer"]["t_building_order_mean_sec"] == pytest.approx(
        sum(expected) / len(expected)
    )


def test_t_building_order_exists_in_both_modes(h0_model, hr_model) -> None:
    """The comparison the paper makes has to be defined on both sides."""
    for m in (h0_model, hr_model):
        assert summarize(m)["customer"]["t_building_order_mean_sec"] is not None


def test_post_handoff_split_is_h1_only(h0_model, hr_model) -> None:
    """H0 has no handoff, so its post-handoff leg is absent, not zero."""
    assert summarize(h0_model)["customer"]["t_order_post_handoff_mean_sec"] is None
    h1 = summarize(hr_model)["customer"]
    assert 0 < h1["t_order_post_handoff_mean_sec"] < h1["t_building_order_mean_sec"]


def test_h1_courier_dwell_is_not_the_order_dwell(hr_model) -> None:
    """The trap this KPI exists to close: in H1 the two are different amounts.

    If someone ever makes `t_lobby` mean the same thing in both modes again,
    this fails and points at the reason it was split.
    """
    s = summarize(hr_model)
    assert s["rider"]["t_lobby_mean_sec"] < s["customer"]["t_building_order_mean_sec"]


# ------------------------------------------------------------- robot block


def test_h0_summary_has_no_robot_block(h0_model) -> None:
    """T0a precedent: no fabricated always-zero section in the H0 schema."""
    assert "robot" not in summarize(h0_model)


def test_robot_block_conserves_trips(hr_model) -> None:
    ro = summarize(hr_model)["robot"]
    assert ro["n_robots"] == len(hr_model.robots)
    assert ro["trips_completed"] == ro["n_leg_records"] == hr_model.K
    assert sum(ro["trips_by_robot"].values()) == ro["trips_completed"]
    assert ro["n_requests_unserved_at_end"] == 0


def test_bucket_shares_partition_fleet_time(hr_model) -> None:
    """The 7 buckets are a partition, so their shares sum to exactly 1."""
    ro = summarize(hr_model)["robot"]
    assert set(ro["bucket_share"]) == {
        "wait", "meet_rider", "handoff", "deliver_up", "drop", "return", "charge",
    }
    assert sum(ro["bucket_share"].values()) == pytest.approx(1.0)
    assert ro["bucket_share"]["handoff"] > 0


def test_ops_window_ends_when_the_last_carrier_settles(h0_model, hr_model) -> None:
    """A5-b: [first order, last carrier home]; in H0 that IS the delivery window.

    One definition covering both modes, rather than a robot-only window bolted
    on beside the H0 one — which is what keeps the H0 value unchanged and makes
    the two modes' fleet denominators comparable in kind.
    """
    s0 = summarize(h0_model)["simulation"]
    assert s0["ops_window_sec"] == s0["delivery_window_sec"]

    s1 = summarize(hr_model)["simulation"]
    last_home = max(lg["returned_at_sec"] for lg in hr_model.robot_leg_records.values())
    last_exit = max(r["exited_at_sec"] for r in hr_model.rider_records)
    assert s1["ops_window_sec"] == [hr_model.first_order_sec, max(last_home, last_exit)]
    # in H1 the robot outlives the courier, so the two windows must differ
    assert s1["ops_window_sec"][1] > s1["delivery_window_sec"][1]


def test_ops_utilization_beats_the_fixed_window_as_a_load_measure(hr_model) -> None:
    """Why the field exists: the fixed window's denominator does not grow with K.

    Asserted structurally rather than by pinning the K200/K300 pair: the fixed
    window is a strict sub-interval of the operating window and the fleet works
    outside it, so the fixed-window ratio is measuring a box the work overflows.
    """
    s = summarize(hr_model)
    sim, ro = s["simulation"], s["robot"]
    lo_f, hi_f = sim["fixed_window_sec"]
    lo_o, hi_o = sim["ops_window_sec"]
    assert lo_o == lo_f and hi_o > hi_f          # same start, strictly later end
    assert ro["utilization_ops_mean"] > ro["utilization_fixed_mean"]
    # and the full-run figure sits between them: it shares the ops end but pads
    # the denominator with the warm-up head, which no robot could have used
    assert ro["utilization_fixed_mean"] < ro["utilization_full_mean"]
    assert ro["utilization_full_mean"] < ro["utilization_ops_mean"]


def test_ops_utilization_recomputes(hr_model) -> None:
    s = summarize(hr_model)
    lo, hi = s["simulation"]["ops_window_sec"]
    p0 = int(round((lo - hr_model.clock_start_sec) / hr_model.dt))
    p1 = int(round((hi - hr_model.clock_start_sec) / hr_model.dt))
    for i, rb in enumerate(hr_model.robots):
        cum = hr_model._robot_busy_cum[i]
        assert s["robot"]["utilization_ops_by_robot"][str(rb.unique_id)] == pytest.approx(
            (cum[p1] - cum[p0]) / (p1 - p0)
        )


def test_robot_utilization_recomputes_and_excludes_idle(hr_model) -> None:
    s = summarize(hr_model)
    ro = s["robot"]
    lo, hi = s["simulation"]["fixed_window_sec"]
    f0 = int(round((lo - hr_model.clock_start_sec) / hr_model.dt))
    f1 = int(round((hi - hr_model.clock_start_sec) / hr_model.dt))
    for i, rb in enumerate(hr_model.robots):
        cum = hr_model._robot_busy_cum[i]
        expected = (cum[f1] - cum[f0]) / (f1 - f0)
        assert ro["utilization_fixed_by_robot"][str(rb.unique_id)] == pytest.approx(
            expected
        )
    # idle time is excluded, so utilization is strictly below 1 on this corpus
    assert 0 < ro["utilization_fixed_mean"] < 1
    assert ro["bucket_share"]["wait"] == pytest.approx(
        1 - ro["utilization_full_mean"] - ro["bucket_share"]["charge"]
    )


def test_battery_fields_report_a_non_firing_threshold(hr_model) -> None:
    """§3.5: on this corpus `n_charge_events == 0` is the EXPECTED result.

    Asserted as an information row, not as a success criterion — if a future
    parameter set does fire the threshold the fields must still be coherent.
    """
    ro = summarize(hr_model)["robot"]
    assert 0.0 <= ro["soc_min_pct"] <= 100.0
    assert ro["soc_min_pct"] <= ro["soc_end_pct_min"] <= ro["soc_end_pct_mean"]
    assert ro["n_charge_events"] == 0
    assert ro["charge_blocked_sec"] == 0.0
    assert ro["distance_traveled_m"] > 0


def test_robot_ev_contention_is_recorded(hr_model) -> None:
    s = summarize(hr_model)
    ro = s["robot"]
    assert ro["ev_wait_up_mean_sec"] > 0
    assert ro["ev_wait_down_mean_sec"] > 0
    assert ro["n_board_denied"] == sum(
        ev.robot_board_denied for ev in hr_model.elevators
    )


def test_per_car_by_kind_split_accounts_for_every_boarding(hr_model) -> None:
    """F2 — a car's by-kind counts must add up to its boardings, robots included.

    Before the fix `n_boardings_by_kind` silently dropped robot boardings (EV3:
    221 boardings, by-kind sum 167), so the shared cars' extra load — the very
    mechanism the paper studies — was invisible in the per-car record.
    """
    s = summarize(hr_model)
    total_robot = 0
    for ev in hr_model.elevators:
        blk = s["elevator"][ev.ev_id]
        assert set(blk["n_boardings_by_kind"]) == {"rider", "pedestrian", "robot"}
        assert sum(blk["n_boardings_by_kind"].values()) == blk["n_boardings"]
        n_robot = sum(1 for b in ev.boarding_log if b["kind"] == "robot")
        assert blk["n_boardings_by_kind"]["robot"] == n_robot
        if n_robot:
            assert blk["w_ev_mean_by_kind_sec"]["robot"] == pytest.approx(
                sum(b["wait_sec"] for b in ev.boarding_log if b["kind"] == "robot")
                / n_robot
            )
        total_robot += n_robot
    assert total_robot > 0, "no robot boardings — the regression would be vacuous"


def test_per_car_pooled_wait_is_a_person_quantity(hr_model) -> None:
    """F2 — `w_ev_mean_sec`/`w_ev_p95_sec` follow the same personhood rule as
    `building.w_ev_mean_all_sec` (A3 item 5). Averaging robot boardings into a
    car's mean moved EV3 from 25.37 s (people) to 29.46 s (pooled), a 16 %
    contamination of a field the H0→H1 comparison reads as a people KPI.
    """
    s = summarize(hr_model)
    for ev in hr_model.elevators:
        blk = s["elevator"][ev.ev_id]
        people = [b["wait_sec"] for b in ev.boarding_log if b["kind"] != "robot"]
        assert blk["w_ev_mean_sec"] == pytest.approx(sum(people) / len(people))
        # and it must differ from the robot-polluted pooled figure on the cars
        # robots actually use, or the fix is untested
        if ev.shared_with_robot:
            pooled = [b["wait_sec"] for b in ev.boarding_log]
            assert blk["w_ev_mean_sec"] != pytest.approx(sum(pooled) / len(pooled))


def test_h0_per_car_split_has_no_robot_key(h0_model) -> None:
    """F2 must not fabricate an always-zero robot key in the frozen H0 schema."""
    s = summarize(h0_model)
    for blk in s["elevator"].values():
        assert set(blk["n_boardings_by_kind"]) == {"rider", "pedestrian"}
        assert sum(blk["n_boardings_by_kind"].values()) == blk["n_boardings"]


def test_people_ev_wait_excludes_robot_boardings(hr_model) -> None:
    """`w_ev_mean_all_sec` is a per-PERSON quantity in every mode (A3 item 5)."""
    s = summarize(hr_model)
    people = [
        b["wait_sec"] for ev in hr_model.elevators for b in ev.boarding_log
        if b["kind"] != "robot"
    ]
    assert s["building"]["w_ev_mean_all_sec"] == pytest.approx(
        sum(people) / len(people)
    )
    assert s["building"]["w_ev_mean_robots_sec"] is not None


# ------------------------------------------------------------------- drain


@pytest.fixture(scope="module")
def capped_model():
    """An H1 run stopped by the safety cap, with work still in mid-air.

    `max_overrun_sec_robot=10` ends K50_1 ten seconds after its last order, so
    robots are mid-trip and the FCFS queue is non-empty — the state Phase D's
    small-fleet sweep produces and the one F3/F5 are about. Reached by config
    injection so no scenario file or fixture run has to be invented for it.
    """
    cfg = copy.deepcopy(load_config(CONFIG))
    cfg["simulation"]["max_overrun_sec_robot"] = 10
    return _run(HandoffMode.H1_SYNC, config=cfg)


def test_cap_termination_reports_the_work_it_cut_off(capped_model) -> None:
    """F3 — a capped run must SAY that it censored trips, not silently drop them.

    An unfinished leg never reaches `robot_leg_records` (only `_finish_trip`
    publishes one), so before F3 the whole busiest tail of a capped run was
    invisible: `n_leg_records` was short of `n_delivered` and no field said why.
    """
    s = summarize(capped_model)
    ro, cu = s["robot"], s["customer"]
    assert s["simulation"]["terminated_by_cap"] is True
    inflight = [rb for rb in capped_model.robots if rb.order is not None]
    assert ro["n_trips_inflight_at_end"] == len(inflight) > 0
    # the censoring is real: those trips have no leg record
    assert ro["n_leg_records"] == ro["trips_completed"] < cu["n_delivered"]


def test_unserved_count_includes_dispatched_but_undelivered_orders(capped_model) -> None:
    """F3 — `n_requests_unserved_at_end` counted the FCFS queue only, so an
    order that had already been handed to a robot was counted nowhere."""
    s = summarize(capped_model)
    ro = s["robot"]
    queued = len(capped_model.control.robot_requests)
    assigned_undelivered = sum(
        1 for rb in capped_model.robots
        if rb.order is not None
        and capped_model.customer_by_ord_id[rb.order.ord_id].delivered_at_sec is None
    )
    assert assigned_undelivered > 0, "no censored order — the regression is vacuous"
    assert ro["n_requests_queued_at_end"] == queued
    assert ro["n_requests_unserved_at_end"] == queued + assigned_undelivered
    # a robot walking home from a COMPLETED delivery is in-flight but NOT unserved
    assert ro["n_trips_inflight_at_end"] >= assigned_undelivered


def test_drain_span_is_never_negative(capped_model) -> None:
    """F5 — a length has a floor of 0. This run's raw difference is negative."""
    s = summarize(capped_model)
    bu = s["building"]
    deliveries = [
        c.delivered_at_sec for c in capped_model.customer_by_ord_id.values()
        if c.delivered_at_sec is not None
    ]
    w_end = s["simulation"]["fixed_window_sec"][1]
    assert max(deliveries) < w_end, (
        "the last delivery no longer precedes the last order — this run stopped "
        "exercising the negative branch and the guard is untested"
    )
    assert bu["drain_deliveries"] == 0
    assert bu["drain_span_sec"] == 0.0


def test_drain_accounts_for_everything_outside_the_window(hr_model) -> None:
    s = summarize(hr_model)
    bu, cu = s["building"], s["customer"]
    hi = s["simulation"]["fixed_window_sec"][1]
    inside = sum(
        1 for c in hr_model.customer_by_ord_id.values()
        if c.delivered_at_sec is not None and c.delivered_at_sec <= hi
    )
    assert inside + bu["drain_deliveries"] == cu["n_delivered"]
    assert bu["drain_span_sec"] > 0
    assert bu["drain_robot_trips"] == bu["drain_deliveries"]


# -------------------------------------------------------------- evsel pool


def test_robot_evsel_reevaluates_only_the_cars_a_robot_may_use() -> None:
    """A robot cannot choose a dedicated car, so it cannot be stale against one.

    Counting EV1 as "the better choice it missed" would inflate the robot stale
    ratio with a counterfactual the dispatch policy forbids.
    """
    m = _run(HandoffMode.H1_SYNC, evsel=True)
    shared = {ev.ev_id for ev in m.elevators if ev.shared_with_robot}
    robot_events = [e for e in m.evsel_events if e["kind"] == "robot"]
    ped_events = [e for e in m.evsel_events if e["kind"] == "pedestrian"]
    assert robot_events and ped_events
    for e in robot_events:
        assert e["n_candidates"] == len(shared)
        assert e["chosen_ev"] in shared
        assert e["reeval_best_ev"] in shared
    for e in ped_events:
        assert e["n_candidates"] == len(m.elevators)
    ro = summarize(m)["robot"]
    assert ro["n_evsel_calls"] == len(robot_events)
    assert 0.0 <= ro["evsel_stale_ratio"] <= 1.0


def test_evsel_ratio_is_none_when_instrumentation_is_off(hr_model) -> None:
    ro = summarize(hr_model)["robot"]
    assert ro["evsel_stale_ratio"] is None and ro["n_evsel_calls"] is None


# ------------------------------------------------------------ runner plumbing


def test_injected_config_matches_reading_it_from_disk() -> None:
    """The new path must be a pure substitution, not a second config semantics."""
    kw = {
        "scenario_path": SCENARIO, "rng_seed": 42,
        "floor_profile": "uniform", "mode": "hr",
    }
    from_disk = run_baseline(**kw)
    injected = run_baseline(config=load_config(CONFIG), **kw)
    assert injected["config_injected"] is True
    assert from_disk["config_injected"] is False
    assert injected["kpi_summary"] == from_disk["kpi_summary"]
    assert injected["per_order"] == from_disk["per_order"]


def test_fleet_size_override_reaches_the_model() -> None:
    """Phase D's sizing sweep needs this without writing a config file per cell."""
    res = run_baseline(
        scenario_path=SCENARIO, rng_seed=42, floor_profile="uniform", mode="hr",
        n_robots=2,
    )
    assert res["kpi_summary"]["robot"]["n_robots"] == 2
    # a smaller fleet cannot serve the same load as fast: the courier's wait for
    # a robot is the mechanism, so it must move in the obvious direction
    base = run_baseline(
        scenario_path=SCENARIO, rng_seed=42, floor_profile="uniform", mode="hr"
    )
    assert (res["kpi_summary"]["rider"]["robot_wait_p95_sec"]
            > base["kpi_summary"]["rider"]["robot_wait_p95_sec"])


def test_kpi_report_renders_the_robot_section(hr_model) -> None:
    """The downloadable report must not silently drop a whole new section."""
    from simulation.kpi import summary_to_csv, summary_to_markdown

    s = summarize(hr_model)
    assert "## Robot" in summary_to_markdown(s)
    assert "Robot,n_robots,5" in summary_to_csv(s)


def test_h0_report_has_no_robot_section(h0_model) -> None:
    from simulation.kpi import summary_to_markdown

    assert "## Robot" not in summary_to_markdown(summarize(h0_model))
