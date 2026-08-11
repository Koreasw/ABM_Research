"""Tests for analysis/verify_hr.py (B1..B18 gates).

Same contract as `test_verify_h0.py`: every gate passes on real HR runs, and
every gate has a negative case — a deliberately corrupted field that must flip
THAT gate to FAIL. A gate nobody has ever seen fail is not a gate; it is a
comment that costs CPU.

Two properties specific to this module are pinned as well:

  * the corpus SATURATES on purpose, so a K200 run — robot queue diverging to
    ~5,200 s, 148 of 200 deliveries after the last order — must still pass every
    gate. A gate that fails there would be judging fleet sizing, which is a
    result, not a defect (§3.6).
  * the dedicated-car sub-check SKIPS rather than passes when every car is
    robot-shareable (결정 13). A vacuous PASS reads as evidence.

The A7-a block at the bottom of the file (B12..B18) is stricter still about
what counts as a negative case: every corruption there is one the A5-c gate
review MEASURED the B1..B11 set passing on a real artefact — a rewritten
headline mean, an inverted SLA column, a deleted warm-up block, a car removed
from the KPI, `ready` moved an hour before its order. The gate that now owns
each of them is pinned by the test named after it.
"""

from __future__ import annotations

import copy

import pytest

from analysis.verify_h0 import ROOT
from analysis.verify_hr import main, verify_result
from simulation.run import run_baseline
from simulation.space import load_config

CONFIG = ROOT / "configs" / "baseline_10f.yaml"


def _run(stem: str = "K50_1", **kw) -> dict:
    params = {
        "scenario_path": f"data/data1/{stem}.json",
        "rng_seed": 42,
        "floor_profile": "uniform",
        "mode": "hr",
    }
    params.update(kw)
    return run_baseline(**params)


@pytest.fixture(scope="module")
def base() -> dict:
    return _run("K50_1")


@pytest.fixture(scope="module")
def saturated() -> dict:
    return _run("K200_1")


def _check(report: dict, prefix: str):
    for c in report["checks"]:
        if c.name.startswith(prefix):
            return c
    raise AssertionError(f"no check named {prefix!r}")


def _assert_gate_fails(result: dict, prefix: str, *, also: tuple[str, ...] = ()) -> None:
    """The corruption fails its own gate, and ONLY the gates named here.

    The `also` list is not a convenience — it is the point. A single corrupted
    field often trips a second gate legitimately (a negative robot wait breaks
    B2's chain AND B5's identity, because both are computed from it), and an
    earlier version of this helper simply did not look, so a change that made
    some gate fire on every artefact would have left the suite green. Naming the
    co-failures pins the ownership boundary the module is designed around:
    if a future edit widens or narrows a gate's reach, this list stops matching.
    """
    report = verify_result(result)
    c = _check(report, prefix)
    assert not c.passed, f"{prefix} did not catch the corruption"
    assert c.failures, f"{prefix} failed without saying why"
    assert not report["all_passed"]
    failed = {ch.name.split()[0] for ch in report["checks"] if not ch.passed}
    assert failed == {prefix, *also}, (
        f"expected {prefix} (+{list(also)}) to fail, got {sorted(failed)}"
    )


def _legs_by_robot(result: dict) -> list[dict]:
    """The chronological legs of some robot that made at least two trips."""
    by_robot: dict[int, list[dict]] = {}
    for lg in sorted(result["robot_legs"], key=lambda x: x["assigned_at_sec"]):
        by_robot.setdefault(lg["robot_id"], []).append(lg)
    return next(v for v in by_robot.values() if len(v) >= 2)


# ------------------------------------------------------------------- positive


def test_all_gates_pass_on_a_healthy_run(base):
    report = verify_result(base)
    assert report["all_passed"], [
        (c.name, c.failures[:3]) for c in report["checks"] if not c.passed
    ]
    assert len(report["checks"]) == 17          # B1..B5, B7..B18 (no B6)
    assert not any(c.skipped for c in report["checks"])


def test_all_gates_pass_under_saturation(saturated):
    """ρ≈2: the queue diverges, the drain is longer than the demand window.

    Everything the gates judge must still hold — and the things that must NOT
    be judged show up in the report-only block instead.
    """
    report = verify_result(saturated)
    assert report["all_passed"], [
        (c.name, c.failures[:3]) for c in report["checks"] if not c.passed
    ]
    sat = report["saturation"]
    assert sat["robot_queue_wait_p95_sec"] > 1000.0
    assert sat["drain_deliveries"] > 0.5 * saturated["kpi_summary"]["customer"]["n_orders"]


def test_b4_bound_is_tight_but_not_an_identity(base):
    """A lower bound nobody ever touches is not measuring anything.

    Zero minimum slack means some leg rode with no intermediate stop — the bound
    is reachable — while a positive mean means real legs do wait for the car to
    serve other people, which is what the slack is supposed to be.
    """
    rep = verify_result(base)["b4_slack"]
    assert rep["min_slack_up_sec"] == 0.0
    assert rep["min_slack_down_sec"] == 0.0
    assert rep["mean_slack_up_sec"] > 0.0
    assert rep["mean_slack_down_sec"] > 0.0


def test_dedicated_subcheck_skips_when_every_car_is_shared():
    """결정 13: an empty dedicated set makes the sub-check vacuous — say so."""
    cfg = copy.deepcopy(load_config(CONFIG))
    cfg["building"]["shared_ev_ids"] = ["EV1", "EV2", "EV3", "EV4"]
    res = _run("K50_1", config=cfg)
    report = verify_result(res)
    assert report["all_passed"]
    b3 = _check(report, "B3")
    assert "SKIP dedicated-car sub-check" in b3.detail


def test_h0_artefact_is_rejected_rather_than_silently_passed():
    """Running the HR gates on an H0 run must be an error, not a green report."""
    h0 = _run("K50_1", mode="h0")
    assert "robot_legs" not in h0
    with pytest.raises(ValueError, match="verify_hr is for robot-mode"):
        verify_result(h0)


def test_cli_main_exit_codes(tmp_path, base):
    import json

    good = tmp_path / "good.json"
    good.write_text(json.dumps(base))
    assert main([str(good)]) == 0

    bad = copy.deepcopy(base)
    bad["robot_fleet"][0]["node"] = "floor_5_corr_10"
    bad_path = tmp_path / "bad.json"
    bad_path.write_text(json.dumps(bad))
    assert main([str(bad_path)]) == 1


# ------------------------------------------------------------------- B1 / B2


def test_b1_negative_missing_robot_leg(base):
    bad = copy.deepcopy(base)
    bad["robot_legs"].pop()
    # B10 too, legitimately: removing a leg from the middle of a robot's
    # chronology leaves an SOC gap between the legs that remain adjacent
    _assert_gate_fails(bad, "B1", also=("B10",))


def test_b1_negative_undelivered_order(base):
    bad = copy.deepcopy(base)
    bad["kpi_summary"]["customer"]["n_delivered"] -= 1
    # B11 asserts delivered == K as well — deliberately, since "the run ended
    # because the work ended" is not the same claim as "the work is conserved".
    # B12 too: `n_delivered` is the SLA rate's denominator, and it re-derives
    # both from the per-order source.
    _assert_gate_fails(bad, "B1", also=("B11", "B12"))


def test_b1_negative_leg_without_a_return(base):
    bad = copy.deepcopy(base)
    bad["robot_legs"][0]["returned_at_sec"] = None
    _assert_gate_fails(bad, "B1")


def test_b2_negative_handoff_after_exit(base):
    bad = copy.deepcopy(base)
    bad["per_order"][0]["exited_at_sec"] = bad["per_order"][0]["handoff_ended_sec"] - 1.0
    _assert_gate_fails(bad, "B2")


def test_b2_negative_negative_robot_wait(base):
    bad = copy.deepcopy(base)
    bad["per_order"][0]["robot_wait_sec"] = -30.0
    # B5 too: its identity is computed FROM robot_wait, so a corrupted wait
    # necessarily breaks the decomposition as well
    _assert_gate_fails(bad, "B2", also=("B5",))


def test_b2_negative_handoff_duration_not_the_drawn_one(base):
    bad = copy.deepcopy(base)
    bad["per_order"][0]["handoff_ended_sec"] += 5.0
    _assert_gate_fails(bad, "B2", also=("B5",))


# ------------------------------------------------------------------------ B3


def test_b3_negative_robot_on_a_dedicated_car(base):
    bad = copy.deepcopy(base)
    bad["robot_legs"][0]["ev_id_up"] = "EV1"
    _assert_gate_fails(bad, "B3")


def test_b3_negative_robot_in_the_basement(base):
    bad = copy.deepcopy(base)
    bad["robot_legs"][0]["floor"] = -1
    # B16 owns the RANGE [2, n_floors]; B3 owns "no basement" specifically. A
    # basement floor violates both, and the overlap is deliberate — B3 names the
    # physical claim, B16 the admissible set.
    _assert_gate_fails(bad, "B3", also=("B16",))


def test_b3_negative_capacity_violation(base):
    bad = copy.deepcopy(base)
    bad["kpi_summary"]["elevator"]["EV3"]["capacity_violations"] = 2
    _assert_gate_fails(bad, "B3")


def test_b3_negative_missing_boarding(base):
    bad = copy.deepcopy(base)
    bad["robot_legs"][0]["ev_id_down"] = None
    _assert_gate_fails(bad, "B3")


# ------------------------------------------------------------------- B4 / B5


def test_b4_negative_leg_faster_than_physics(base):
    bad = copy.deepcopy(base)
    lg = bad["robot_legs"][0]
    lg["delivered_at_sec"] = lg["handoff_ended_sec"] + 1.0
    # B12 too: the delivery stamp is where every customer aggregate starts, so
    # moving it necessarily breaks the re-derivation of t_e2e and the rest
    _assert_gate_fails(bad, "B4", also=("B12",))


def test_b4_negative_instant_return(base):
    bad = copy.deepcopy(base)
    lg = bad["robot_legs"][0]
    lg["returned_at_sec"] = lg["delivered_at_sec"] + 1.0
    _assert_gate_fails(bad, "B4")


def test_b5_negative_one_second_of_unaccounted_dwell(base):
    """The identity is exact, so one second must be enough to trip it."""
    bad = copy.deepcopy(base)
    bad["per_order"][0]["t_lobby_sec"] += 1.0
    _assert_gate_fails(bad, "B5")


# ------------------------------------------------------------------------ B7


def test_b7_negative_late_arrival_served_first(base):
    bad = copy.deepcopy(base)
    legs = {lg["ord_id"]: lg for lg in bad["robot_legs"]}
    order = sorted(bad["per_order"], key=lambda r: r["entered_at_sec"])
    first, later = order[0]["ord_id"], order[-1]["ord_id"]
    legs[first]["assigned_at_sec"], legs[later]["assigned_at_sec"] = (
        legs[later]["assigned_at_sec"], legs[first]["assigned_at_sec"]
    )
    # B2 too: an assignment moved past its own handoff breaks the leg's chain
    _assert_gate_fails(bad, "B7", also=("B2",))


# ------------------------------------------------------------------------ B8


def test_b8_negative_window_edge_from_the_simulation(base):
    """The exact defect layer ① exists to prevent: a mode-dependent edge."""
    bad = copy.deepcopy(base)
    sim = bad["kpi_summary"]["simulation"]
    sim["fixed_window_sec"] = [sim["fixed_window_sec"][0], sim["clock_end_sec"]]
    _assert_gate_fails(bad, "B8")


def test_b8_negative_missing_window_contract(base):
    bad = copy.deepcopy(base)
    del bad["kpi_summary"]["simulation"]["windows"]["layer1_fixed"]
    _assert_gate_fails(bad, "B8")


def test_b8_negative_fixed_boardings_exceed_the_total(base):
    bad = copy.deepcopy(base)
    ev = bad["kpi_summary"]["elevator"]["EV3"]
    ev["n_boardings_by_kind_fixed"]["pedestrian"] = ev["n_boardings"] + 1
    _assert_gate_fails(bad, "B8")


# ------------------------------------------------------------------------ B9


def test_b9_negative_corrupted_floor(base):
    bad = copy.deepcopy(base)
    rec = bad["per_order"][0]
    rec["floor"] = 1 if rec["floor"] != 1 else 2
    _assert_gate_fails(bad, "B9")


def test_b9_negative_courier_used_the_lift(base):
    """`vertical_mode` is the H1 claim that the courier never went upstairs."""
    bad = copy.deepcopy(base)
    bad["per_order"][0]["vertical_mode"] = "elevator"
    _assert_gate_fails(bad, "B9")


# ----------------------------------------------------------------------- B10


def test_b10_negative_soc_out_of_range(base):
    bad = copy.deepcopy(base)
    bad["robot_legs"][0]["soc_pct_at_return"] = -3.0
    _assert_gate_fails(bad, "B10")


def test_b10_negative_soc_rose_during_a_trip(base):
    bad = copy.deepcopy(base)
    lg = bad["robot_legs"][0]
    lg["soc_pct_at_return"] = lg["soc_pct_at_assign"] + 1.0
    _assert_gate_fails(bad, "B10")


def test_b10_negative_dispatched_before_recharging(base):
    """The path the corpus never takes — so it is pinned synthetically.

    `n_charge_events == 0` is the expected corpus result (§3.5), which means
    this branch is dead on every real run. It is exactly the branch a future
    `soc_init` sweep will exercise for the first time, so it has to be known to
    work before that sweep interprets its output.
    """
    bad = copy.deepcopy(base)
    resume = bad["config"]["robot"]["battery"]["soc_resume_pct"]
    by_robot: dict[int, list[dict]] = {}
    for lg in sorted(bad["robot_legs"], key=lambda x: x["assigned_at_sec"]):
        by_robot.setdefault(lg["robot_id"], []).append(lg)
    pair = next(v for v in by_robot.values() if len(v) >= 2)
    pair[0]["return_reason"] = "low_soc"
    pair[0]["soc_pct_at_return"] = 15.0
    pair[1]["soc_pct_at_assign"] = resume - 5.0
    _assert_gate_fails(bad, "B10")


def test_b10_negative_soc_fell_while_parked(base):
    bad = copy.deepcopy(base)
    by_robot: dict[int, list[dict]] = {}
    for lg in sorted(bad["robot_legs"], key=lambda x: x["assigned_at_sec"]):
        by_robot.setdefault(lg["robot_id"], []).append(lg)
    pair = next(v for v in by_robot.values() if len(v) >= 2)
    pair[1]["soc_pct_at_assign"] = pair[0]["soc_pct_at_return"] - 10.0
    _assert_gate_fails(bad, "B10")


def test_b10_reports_the_non_firing_threshold_without_gating_on_it(base):
    """§3.5: zero charge events must be reported, never judged."""
    report = verify_result(base)
    b10 = _check(report, "B10")
    assert b10.passed
    assert "charge_events=0" in b10.detail
    assert "EXPECTED corpus result" in b10.detail


# ----------------------------------------------------------------------- B11


def test_b11_negative_robot_stranded_away_from_home(base):
    bad = copy.deepcopy(base)
    bad["robot_fleet"][0]["node"] = "floor_7_corr_18"
    _assert_gate_fails(bad, "B11")


def test_b11_negative_robot_still_working(base):
    bad = copy.deepcopy(base)
    bad["robot_fleet"][0]["state"] = "riding"
    _assert_gate_fails(bad, "B11")


def test_b11_negative_cap_termination_names_the_remedy(base):
    """A cap termination is a failed RUN; the report must say what to do."""
    bad = copy.deepcopy(base)
    sim = bad["kpi_summary"]["simulation"]
    sim["terminated_by_cap"] = True
    sim["termination_reason"] = "cap"
    report = verify_result(bad)
    b11 = _check(report, "B11")
    assert not b11.passed
    assert any("max_overrun_sec_robot" in f for f in b11.failures)


def test_b11_accepts_a_charging_robot_at_home(base):
    """`IDLE ∨ CHARGING_BLOCKED` — dropping the second state breaks §3.2."""
    ok = copy.deepcopy(base)
    ok["robot_fleet"][0]["state"] = "charging_blocked"
    report = verify_result(ok)
    assert _check(report, "B11").passed


def test_b11_negative_requests_left_in_the_queue(base):
    bad = copy.deepcopy(base)
    bad["kpi_summary"]["robot"]["n_requests_unserved_at_end"] = 3
    # B17 too, and from the other side: B11 says "unserved must be zero in a
    # completed run", B17 says "3 unserved cannot coexist with 0 undelivered"
    _assert_gate_fails(bad, "B11", also=("B17",))


# --------------------------------------------------- robustness of the gates


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("robot_legs", 0, "delivered_at_sec"), None),
        (("robot_legs", 0, "ev_wait_up_sec"), None),
        (("robot_legs", 0, "soc_pct_at_assign"), None),
        (("robot_legs", 0, "assigned_at_sec"), None),
        (("per_order", 0, "handoff_sec"), None),
        (("per_order", 0, "handoff_started_sec"), None),
        (("kpi_summary", "simulation", "fixed_window_sec"), None),
    ],
)
def test_a_malformed_artefact_reports_instead_of_raising(base, path, value):
    """A verifier that raises is useless exactly when it is needed.

    Each of these is a stamp a broken run could plausibly be missing. The
    requirement is not that a particular gate catches it — B1 already does —
    but that the report comes back at all, so the other gates' verdicts survive
    to say what else was wrong.
    """
    bad = copy.deepcopy(base)
    target = bad
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value

    report = verify_result(bad)          # must not raise
    assert not report["all_passed"], "a missing stamp must be reported by SOME gate"
    # No gate may crash. The first version allowed crashes as long as one gate
    # survived, which certified four real TypeErrors as acceptable behaviour —
    # a gate that raises discards its verdict on every OTHER record it holds.
    crashed = [c.name for c in report["checks"] if "gate crashed" in c.detail]
    assert not crashed, f"gates crashed instead of reporting: {crashed}"


def test_b8_negative_ops_window_ends_early(base):
    """A5-b: the fleet-load denominator. A wrong edge rescales every utilization
    number in the study, silently — so B8 owns it."""
    bad = copy.deepcopy(base)
    sim = bad["kpi_summary"]["simulation"]
    sim["ops_window_sec"] = [sim["ops_window_sec"][0], sim["delivery_window_sec"][1]]
    _assert_gate_fails(bad, "B8")


def test_b8_negative_ops_window_missing(base):
    bad = copy.deepcopy(base)
    bad["kpi_summary"]["simulation"]["ops_window_sec"] = None
    _assert_gate_fails(bad, "B8")


# =====================================================================
# A5-c — regressions for the defects the max-effort gate review found.
# Each test below FAILED (or vacuously passed) before that review.
# =====================================================================


def test_b7_catches_a_violation_that_straddles_a_same_tick_tie(base):
    """The review's headline defect: a tie broke the transitivity chain.

    B7 used to walk adjacent pairs and `continue` on same-tick arrivals, so
    `A(t=100) B(t=100) C(t=200)` compared only B↔C — and A, which entered
    first, could be assigned hours after C with the gate reporting PASS. Ties
    are the norm under saturation, so this was a live hole, not a corner case.
    """
    bad = copy.deepcopy(base)
    legs = {lg["ord_id"]: lg for lg in bad["robot_legs"]}
    rows = sorted(bad["per_order"], key=lambda r: r["entered_at_sec"])
    first, tie, later = rows[0], rows[1], rows[-1]
    tie["entered_at_sec"] = first["entered_at_sec"]      # make a tie group
    # the earliest arrival is dispatched long after the last one
    legs[first["ord_id"]]["assigned_at_sec"] = (
        legs[later["ord_id"]]["assigned_at_sec"] + 5000.0
    )
    # B2 (the assignment now follows its own handoff) plus, because the tie is
    # manufactured by moving an entry time backwards: B15 (the courier now
    # enters before it arrived) and B12 (T_building_order is measured from that
    # entry). All three are the corruption, seen from three different chains.
    _assert_gate_fails(bad, "B7", also=("B2", "B12", "B15"))


def test_b7_still_refuses_to_order_within_a_tie(base):
    """Ties must stay unjudged — the heap sequence is not in the artefact."""
    ok = copy.deepcopy(base)
    legs = {lg["ord_id"]: lg for lg in ok["robot_legs"]}
    rows = sorted(ok["per_order"], key=lambda r: r["entered_at_sec"])
    a, b = rows[0], rows[1]
    b["entered_at_sec"] = a["entered_at_sec"]
    # swap the two assignments WITHIN the tie group: still FCFS-clean
    legs[a["ord_id"]]["assigned_at_sec"], legs[b["ord_id"]]["assigned_at_sec"] = (
        legs[b["ord_id"]]["assigned_at_sec"], legs[a["ord_id"]]["assigned_at_sec"]
    )
    assert _check(verify_result(ok), "B7").passed


def test_b11_accepts_the_drain_all_termination_policy(base):
    """B11 hard-coded 'delivery_complete' and so failed every legacy-window run."""
    ok = copy.deepcopy(base)
    sim = ok["kpi_summary"]["simulation"]
    sim["termination_policy"] = "drain_all"
    sim["termination_reason"] = "drain_all"
    assert _check(verify_result(ok), "B11").passed


def test_b11_negative_missing_fleet_block(base):
    """An absent fleet made 'every robot parked at home' vacuously true."""
    bad = copy.deepcopy(base)
    bad["robot_fleet"] = []
    # B10 still passes on the legs' own SOC evidence — the fleet block is
    # B11's to own, and the split is deliberate
    _assert_gate_fails(bad, "B11")


def test_b11_negative_fleet_shorter_than_the_kpi_says(base):
    bad = copy.deepcopy(base)
    bad["robot_fleet"].pop()
    _assert_gate_fails(bad, "B11")


def test_a_robot_run_with_no_finished_trip_is_verified_not_rejected(base):
    """`robot_legs: []` is a cap-truncated HR run — the case B11 exists for.

    Truthiness treated it as "not a robot mode at all" and refused to look,
    misdiagnosing the one run whose diagnosis the gate owns.
    """
    truncated = copy.deepcopy(base)
    truncated["robot_legs"] = []
    report = verify_result(truncated)          # must not raise
    assert not report["all_passed"]
    b1 = _check(report, "B1")
    assert not b1.passed
    # and the gates that cannot judge anything say SKIP, not PASS
    assert _check(report, "B4").skipped


def test_b1_negative_duplicate_robot_leg(base):
    """`_legs` is keyed by ord_id, so a double-published trip used to vanish."""
    bad = copy.deepcopy(base)
    bad["robot_legs"].append(copy.deepcopy(bad["robot_legs"][0]))
    _assert_gate_fails(bad, "B1")


def test_b1_negative_order_dropped_from_the_whole_artefact(base):
    """Self-consistency is not conservation: the scenario is the arbiter.

    Deleting an order from per_order, robot_legs AND the counters left every
    gate green — exactly the dispatcher bug A1 exists to catch in H0.
    """
    bad = copy.deepcopy(base)
    victim = bad["per_order"][10]["ord_id"]
    bad["per_order"] = [r for r in bad["per_order"] if r["ord_id"] != victim]
    bad["robot_legs"] = [lg for lg in bad["robot_legs"] if lg["ord_id"] != victim]
    for key in ("n_orders", "n_delivered"):
        bad["kpi_summary"]["customer"][key] -= 1
    bad["kpi_summary"]["rider"]["n_exited"] -= 1
    # B12 catches it independently, and that is the point of having both: the
    # counters were made self-consistent, but the AGGREGATES still average the
    # 50 orders that were measured, not the 49 that remain
    _assert_gate_fails(bad, "B1", also=("B12",))


def test_b1_reports_when_the_scenario_is_unreachable(base):
    """A moved scenario costs B1 its evidence — not the whole report."""
    bad = copy.deepcopy(base)
    bad["scenario_path"] = "data/data1/DOES_NOT_EXIST.json"
    report = verify_result(bad)                # must not raise
    b1 = _check(report, "B1")
    assert not b1.passed
    assert any("scenario file unavailable" in f for f in b1.failures)
    # every other gate still returned a verdict
    assert all("gate crashed" not in c.detail for c in report["checks"])
    assert _check(report, "B11").passed


def test_b2_negative_robot_leg_runs_backwards(base):
    """The robot half of the timeline was ordered by no gate at all."""
    bad = copy.deepcopy(base)
    lg = bad["robot_legs"][0]
    lg["handoff_started_sec"] = lg["handoff_ended_sec"] + 50.0
    _assert_gate_fails(bad, "B2")


def test_b2_negative_handoff_lag_is_not_one_tick(base):
    """The A4 tick-order contract, now enforced instead of assumed."""
    bad = copy.deepcopy(base)
    bad["robot_legs"][0]["handoff_started_sec"] += 3.0
    _assert_gate_fails(bad, "B2")


def test_b3_still_sees_a_dedicated_car_when_the_kpi_block_is_truncated(base):
    """The dedicated set comes from the config, not from the KPI's keys.

    Deriving it from `kpi_summary.elevator` meant a truncated KPI block turned
    B3's core sub-check into a 결정-13 SKIP that asserted the opposite of the
    config printed on the same line.
    """
    bad = copy.deepcopy(base)
    for ev in ("EV1", "EV2"):
        bad["kpi_summary"]["elevator"].pop(ev)
    bad["robot_legs"][0]["ev_id_up"] = "EV1"
    report = verify_result(bad)
    b3 = _check(report, "B3")
    assert not b3.passed
    assert any("DEDICATED" in f for f in b3.failures)


def test_b4_skips_rather_than_passes_when_no_leg_is_usable(base):
    """A PASS with nothing judged reads as evidence — 결정 13's own rule."""
    bad = copy.deepcopy(base)
    for lg in bad["robot_legs"]:
        lg["ev_wait_up_sec"] = None
    report = verify_result(bad)
    b4 = _check(report, "B4")
    assert b4.skipped and "no usable leg" in b4.detail


def test_b9_checks_the_handoff_claim_even_on_a_mapping_run(base):
    """`vertical_mode == 'handoff'` has nothing to do with floor provenance.

    Folding it into the profile-only branch meant every frozen-mapping HR run
    silently stopped asserting that the courier took no lift and no stairs.
    """
    bad = copy.deepcopy(base)
    bad["floor_source"] = "mapping"
    bad["per_order"][0]["vertical_mode"] = "elevator"
    report = verify_result(bad)
    b9 = _check(report, "B9")
    assert not b9.passed
    assert any("never uses the vertical system" in f for f in b9.failures)


# =====================================================================
# A7-a — B12..B18. Every corruption below is one the B1..B11 set was
# MEASURED to pass in the A5-c review (etc/scie_phase/design_a7a_gates.md);
# each is pinned here as the gate that now owns it.
# =====================================================================


def test_b12_negative_headline_mean_rewritten(base):
    """The review's sharpest finding: the paper's own number was ungated."""
    bad = copy.deepcopy(base)
    bad["kpi_summary"]["customer"]["t_e2e_mean_sec"] = 1.0
    _assert_gate_fails(bad, "B12")


def test_b12_negative_sla_verdict_inverted(base):
    """Flipping every SLA verdict passed all ten gates before B12."""
    bad = copy.deepcopy(base)
    cu = bad["kpi_summary"]["customer"]
    cu["n_sla_violations"] = cu["n_delivered"] - cu["n_sla_violations"]
    cu["sla_violation_rate"] = cu["n_sla_violations"] / cu["n_delivered"]
    for rec in bad["per_order"]:
        rec["sla_violation"] = True
    _assert_gate_fails(bad, "B12")


def test_b12_negative_building_interval_shorter_than_the_handoff(base):
    """The physical floor: the food was inside for at least its own handoff.

    Driven from the CONFIG side (the declared handoff service time), so the
    gate is anchored to the design constant and not only to the artefact's own
    drawn value — a run whose per-order draws were rewritten in step with its
    stamps still has to clear the design floor.
    """
    bad = copy.deepcopy(base)
    bad["config"]["handoff"]["service_mean_sec"] = 10_000.0
    _assert_gate_fails(bad, "B12")


def test_b12_reports_the_h1_join_rather_than_the_courier_row(base):
    """In H1 the courier's row has no delivery — the leg does (A2 함정 2)."""
    assert all(r["delivered_at_sec"] is None for r in base["per_order"])
    b12 = _check(verify_result(base), "B12")
    assert b12.passed
    assert "ord_id join" in b12.detail


def test_b13_negative_warmup_block_deleted(base):
    """A13 SKIPs a missing block; B13 must FAIL — no HR run predates R8-b."""
    bad = copy.deepcopy(base)
    del bad["kpi_summary"]["simulation"]["warmup"]
    _assert_gate_fails(bad, "B13")
    b13 = _check(verify_result(bad), "B13")
    assert not b13.skipped, "a missing measurement must not read as a skip"


def test_b13_negative_cold_building(base):
    """The failure the gate exists for: H1 run cold, so EV waits look free."""
    bad = copy.deepcopy(base)
    bad["kpi_summary"]["simulation"]["warmup"]["util_at_first_order"] = 0.0
    _assert_gate_fails(bad, "B13")


def test_b13_negative_head_shorter_than_saturation(base):
    """A declared head below the measured saturation time is not a warm-up."""
    bad = copy.deepcopy(base)
    bad["kpi_summary"]["simulation"]["warmup"]["head_sec"] = 120.0
    _assert_gate_fails(bad, "B13")


def test_b14_negative_alights_do_not_balance(base):
    """`EV2.n_alights -= 5` — a live edit that passed all ten gates."""
    bad = copy.deepcopy(base)
    bad["kpi_summary"]["elevator"]["EV2"]["n_alights"] -= 5
    _assert_gate_fails(bad, "B14")


def test_b14_negative_declared_car_missing_from_the_kpi(base):
    """Deleting a whole car's block used to cost nothing."""
    bad = copy.deepcopy(base)
    del bad["kpi_summary"]["elevator"]["EV4"]
    _assert_gate_fails(bad, "B14")


def test_b14_negative_robot_dropped_from_the_by_kind_split(base):
    """F2's defect, gated: the split silently omitted every robot boarding."""
    bad = copy.deepcopy(base)
    del bad["kpi_summary"]["elevator"]["EV3"]["n_boardings_by_kind"]["robot"]
    _assert_gate_fails(bad, "B14")


def test_b15_negative_ready_before_the_order(base):
    """`ready` an hour ahead of the order passed all ten gates before B15."""
    bad = copy.deepcopy(base)
    bad["per_order"][0]["ready_time_sec"] -= 3600.0
    _assert_gate_fails(bad, "B15")


def test_b15_negative_arrival_not_reconstructible(base):
    """The identity arm: arrival == dispatch + horizontal, for any σ."""
    bad = copy.deepcopy(base)
    bad["per_order"][0]["horizontal_time_s"] += 10.0
    _assert_gate_fails(bad, "B15")


def test_b16_negative_delivery_to_the_lobby_floor(base):
    """floor 1 has no office node: B4 used to CRASH, and nobody owned it.

    Both halves are asserted — the range failure is reported by B16, and B4
    survives to return a verdict on the other 49 legs instead of losing them
    to a `NodeNotFound` traceback.
    """
    bad = copy.deepcopy(base)
    bad["robot_legs"][0]["floor"] = 1
    _assert_gate_fails(bad, "B16")
    report = verify_result(bad)
    b4 = _check(report, "B4")
    assert "gate crashed" not in b4.detail, "B4 must skip the leg, not crash"
    assert b4.passed and "1 leg(s) unusable" in b4.detail


def test_b16_negative_delivery_above_the_top_floor(base):
    bad = copy.deepcopy(base)
    bad["robot_legs"][0]["floor"] = bad["config"]["building"]["n_floors"] + 1
    _assert_gate_fails(bad, "B16")


def test_b17_negative_trips_in_flight_after_a_clean_finish(base):
    """F3's cap detector: a completed run has nothing in mid-air."""
    bad = copy.deepcopy(base)
    bad["kpi_summary"]["robot"]["n_trips_inflight_at_end"] = 3
    _assert_gate_fails(bad, "B17")


def test_b17_negative_unserved_does_not_decompose(base):
    """`unserved` must be queue + carried, and both are reported separately."""
    bad = copy.deepcopy(base)
    bad["kpi_summary"]["robot"]["n_requests_queued_at_end"] = 2
    _assert_gate_fails(bad, "B17")


def test_b17_negative_f3_fields_absent(base):
    """A run without the F3 counters cannot say whether it was censored."""
    bad = copy.deepcopy(base)
    del bad["kpi_summary"]["robot"]["n_trips_inflight_at_end"]
    _assert_gate_fails(bad, "B17")


def test_a_real_cap_termination_is_reported_as_non_quotable():
    """B17-2 (사용자 확정): a censored run must not have its load quoted.

    Built by actually capping the run rather than by editing a flag, because
    the question the design asked — "does B11 already fail this?" — is only
    answerable on the real artefact. It does, on four counts; what B17-2 adds
    is the CONSEQUENCE in the message, since `utilization_ops` and `drain_*`
    are computed over a window that ends at the last completed event.
    """
    cfg = copy.deepcopy(load_config(CONFIG))
    cfg["simulation"]["max_overrun_sec_robot"] = 600      # cuts K50_1 short
    res = _run("K50_1", config=cfg)
    assert res["kpi_summary"]["simulation"]["terminated_by_cap"] is True

    report = verify_result(res)
    b11 = _check(report, "B11")
    assert not b11.passed
    censored = [f for f in b11.failures if "CENSORED" in f]
    assert censored, "a cap run must be named as censored"
    assert "utilization_ops" in censored[0] and "drain_" in censored[0]
    assert "max_overrun_sec_robot" in censored[0]
    # B17 stays consistent on the same artefact: the F3 decomposition holds
    # even though the run itself is a failure
    assert _check(report, "B17").passed
    assert not any("gate crashed" in c.detail for c in report["checks"])


def test_b18_negative_denials_above_the_frozen_ceiling(base):
    """No gate watched the deny channel at all (A5-⑤-2, A6 이월 3)."""
    from analysis.verify_hr import BOARD_DENIED_MAX

    bad = copy.deepcopy(base)
    k = bad["kpi_summary"]["customer"]["n_orders"]
    bad["kpi_summary"]["robot"]["n_board_denied"] = BOARD_DENIED_MAX[k] + 1
    _assert_gate_fails(bad, "B18")


def test_b18_skips_outside_the_calibrated_envelope(base):
    """The ceiling was measured at one fleet size and one pedestrian rate.

    Applying it to a sizing sweep would judge a number against an envelope
    that never contained it — the pedestrian-rush extreme case scores 737 on
    this same K50 scenario and is a RESULT, not a regression.
    """
    bad = copy.deepcopy(base)
    bad["kpi_summary"]["robot"]["n_robots"] = 3
    bad["kpi_summary"]["robot"]["n_board_denied"] = 10_000
    report = verify_result(bad)
    b18 = _check(report, "B18")
    assert b18.skipped and b18.passed
    assert "outside the calibrated envelope" in b18.detail
    assert "fleet 3" in b18.detail


def test_cli_keeps_going_after_an_unverifiable_file(tmp_path, base):
    """One H0 artefact in the list used to abort before any report was printed."""
    import json

    h0 = _run("K50_1", mode="h0")
    bad_path = tmp_path / "h0.json"
    bad_path.write_text(json.dumps(h0))
    good_path = tmp_path / "hr.json"
    good_path.write_text(json.dumps(base))
    assert main([str(bad_path), str(good_path)]) == 1     # reported, not raised
