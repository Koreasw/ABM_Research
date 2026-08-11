"""Tests for analysis/verify_h0.py (V-AUD gate) + model audit mode.

Covers: every A1..A9 check passing on real dynamic-track result files; a
negative case per check (a deliberately corrupted field must flip that check to
FAIL); the A9 SKIP path for a frozen mapping run; and a smoke test that the
model's audit=True mode completes a K50 run with no assert firing and with
bit-for-bit identical results to a non-audited run.
"""

from __future__ import annotations

import copy
import dataclasses
import json
from collections import deque
from types import SimpleNamespace

import pytest

from analysis.load_data import load_riders
from analysis.rider_arrival_model import type_priority
from analysis.verify_h0 import (
    ROOT,
    basement_structure_failures,
    check_assignment_replay,
    check_basement_integrity,
    load_inputs,
    main,
    verify_result,
)
from simulation.run import run_baseline
from simulation.space import add_lobby_handoff_zones, build_from_config, load_config

RESULTS = ROOT / "results"
PROFILE_FILES = [
    "baseline_h0_K50_1_uniform_s42.json",
    "baseline_h0_K50_1_bottom_heavy_s42.json",
    "baseline_h0_K50_1_top_heavy_s42.json",
    "baseline_h0_K100_1_uniform_s42.json",
    "baseline_h0_K200_1_uniform_s42.json",
    "baseline_h0_K300_4_uniform_s42.json",
]
FROZEN_MAPPING_FILE = "baseline_h0_K50_1_s42.json"


def _load(name: str) -> dict:
    return json.loads((RESULTS / name).read_text())


@pytest.fixture(scope="module")
def base() -> dict:
    return _load("baseline_h0_K50_1_uniform_s42.json")


def _check(report: dict, prefix: str):
    for c in report["checks"]:
        if c.name.startswith(prefix):
            return c
    raise AssertionError(f"no check named {prefix!r}")


def _first(records, pred):
    for i, r in enumerate(records):
        if pred(r):
            return i
    raise AssertionError("no matching record")


# ------------------------------------------------------------ positive path


@pytest.mark.parametrize("name", PROFILE_FILES)
def test_profile_files_all_pass(name: str):
    report = verify_result(RESULTS / name)
    failed = [c.name for c in report["checks"] if not c.passed]
    assert report["all_passed"], f"{name}: failing checks {failed}"
    # Every gate ran except A12, which is *structurally* undecidable from a
    # results JSON (queue lengths, not membership) and is therefore always
    # reported SKIPPED here — its real enforcement is the audit-mode assert,
    # covered by test_audit_mode_smoke_completes.
    #
    # R8-c added A13/A14, which read fields that only exist in results produced
    # after R8-b. They are allowed to skip ONLY for a fixture that genuinely
    # predates those fields; once a fixture carries them (i.e. after the R8-e
    # re-freeze) the gates must run and pass. Encoding the condition rather than
    # widening the expected set keeps the anti-false-green property this
    # assertion exists for (HANDOFF_v2 §3.4).
    sim = json.loads((RESULTS / name).read_text())["kpi_summary"]["simulation"]
    expected_skips = ["A12 hall-call exclusivity"]
    if "warmup" not in sim:
        expected_skips.append("A13 warm-up adequacy")
    if "termination_reason" not in sim:
        expected_skips.append("A14 termination reason")
    skipped = [c.name for c in report["checks"] if c.skipped]
    assert skipped == expected_skips, (skipped, expected_skips)
    # A9 GOF is reported but never gates
    assert report["a9_gof"] is not None
    assert report["a9_gof"]["p_value"] is not None


def test_frozen_mapping_run_skips_a9_and_passes():
    report = verify_result(RESULTS / FROZEN_MAPPING_FILE)
    a9 = _check(report, "A9")
    assert a9.skipped and a9.passed
    assert report["all_passed"], [c.name for c in report["checks"] if not c.passed]
    # A9 (no profile) and A12 (undecidable post-hoc) are the only skips; every
    # other gate really ran. Asserted as a SET rather than a count so that
    # adding a gate does not silently turn into "edit the magic number" —
    # R8 added A13/A14 and the count-based version just needed a bigger number,
    # which would have hidden a genuinely new skip.
    assert {c.name.split()[0] for c in report["checks"] if c.skipped} == {"A9", "A12"}


def test_cli_main_exit_codes(tmp_path, base):
    assert main([str(RESULTS / "baseline_h0_K50_1_uniform_s42.json")]) == 0
    bad = copy.deepcopy(base)
    bad["kpi_summary"]["simulation"]["terminated_by_cap"] = True
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(bad))
    assert main([str(p)]) == 1


# ------------------------------------------------------------ negative cases


def test_a1_negative_cap_termination(base):
    bad = copy.deepcopy(base)
    bad["kpi_summary"]["simulation"]["terminated_by_cap"] = True
    report = verify_result(bad)
    assert not _check(report, "A1").passed
    assert not report["all_passed"]


def test_a2_negative_delivered_before_entered(base):
    bad = copy.deepcopy(base)
    rec = bad["per_order"][0]
    rec["delivered_at_sec"] = rec["entered_at_sec"] - 5.0  # breaks entered<delivered
    report = verify_result(bad)
    assert not _check(report, "A2").passed


def test_a3_negative_broken_horizontal(base):
    bad = copy.deepcopy(base)
    bad["per_order"][0]["horizontal_time_s"] += 37.0  # dist/v and arrival identity
    report = verify_result(bad)
    assert not _check(report, "A3").passed


def test_a4_negative_impossible_t_e2e(base):
    bad = copy.deepcopy(base)
    bad["per_order"][0]["t_e2e_sec"] = 1.0  # far below the closed-form floor
    report = verify_result(bad)
    assert not _check(report, "A4").passed


def test_a5_negative_stairs_identity(base):
    bad = copy.deepcopy(base)
    i = _first(bad["per_order"], lambda r: r["vertical_mode"] == "stairs")
    bad["per_order"][i]["t_lobby_sec"] += 10.0  # breaks the exact decomposition
    report = verify_result(bad)
    assert not _check(report, "A5").passed


def test_a5_negative_elevator_ride_floor(base):
    bad = copy.deepcopy(base)
    i = _first(bad["per_order"], lambda r: r["vertical_mode"] == "elevator")
    # inflate the recorded waits so the residual can no longer clear the ride floor
    rec = bad["per_order"][i]
    rec["ev_wait_up_sec"] = rec["t_lobby_sec"]
    report = verify_result(bad)
    assert not _check(report, "A5").passed


def test_a6_negative_capacity_violation(base):
    bad = copy.deepcopy(base)
    next(iter(bad["kpi_summary"]["elevator"].values()))["capacity_violations"] = 3
    report = verify_result(bad)
    assert not _check(report, "A6").passed


def test_a6_negative_residual_passengers(base):
    """A6 must catch a car whose passenger count does not close the books.

    R8 changed what "residual" means. The old mutation set ev1_pax[-1] = 2 and
    relied on A6's "cars must be empty at end" clause — a drain-all property.
    Under the `delivery` policy a car legitimately ends with passengers aboard,
    so that literal 2 can coincide with the true residual and the mutation
    becomes a no-op (observed on the re-frozen fixture). Perturbing the count
    *relative to the truth* breaks the conservation identity
    (boards - alights == still aboard) under either policy.
    """
    bad = copy.deepcopy(base)
    bad["model_vars"]["ev1_pax"][-1] += 1
    report = verify_result(bad)
    assert not _check(report, "A6").passed
    assert not _check(report, "A11").passed   # same identity, per declared car


def test_a7_negative_fallback_flag(base):
    bad = copy.deepcopy(base)
    i = _first(bad["per_order"], lambda r: not r["was_fallback"])
    bad["per_order"][i]["was_fallback"] = True  # replay expects False
    report = verify_result(bad)
    assert not _check(report, "A7").passed


def test_a7_negative_wrong_type(base):
    bad = copy.deepcopy(base)
    # flip a non-fallback order to a pricier eligible type: replay's rank-1 pick
    # no longer matches the recorded type
    i = _first(bad["per_order"],
               lambda r: not r["was_fallback"] and r["rider_type"] == "BIKE")
    bad["per_order"][i]["rider_type"] = "CAR"
    report = verify_result(bad)
    assert not _check(report, "A7").passed


# ------------------------------- A7 same-tick exit/dispatch ambiguity (V1R fix)
# model.step: _dispatch_riders (new-ready grants) runs BEFORE the agent sweep in
# which riders exit and release stock, but both stamp the same clock. A replay
# that orders all releases before all dispatches at equal time judges new-ready
# grants against post-release stock and false-FAILs under pool exhaustion (the
# V-EXT 1/1/1 scenarios). check_assignment_replay resolves this with a
# two-snapshot tolerance; these synthetic cases lock both orientations and that
# a genuinely wrong type still fails both snapshots.


def _exhausted_pool_replay(rec3_rank: int, rec3_fallback: bool, rec3_ready: float):
    """Pool 1/1/1, orders 0..2 exhaust it; order 3 dispatches at ord 0's exit tick.

    rec3_rank selects order 3's recorded type by cost-priority rank at 500 m.
    """
    riders = [dataclasses.replace(r, available_number=1)
              for r in load_riders(ROOT / "data/data1/K50_1.json")]
    pri = type_priority(riders, 500.0)
    x, y, z = pri  # cost-priority order at 500 m

    def rec(oid, rider_type, ready, dispatch, exit_, fallback):
        return {
            "ord_id": oid, "rider_type": rider_type, "dist_m": 500.0,
            "ready_time_sec": ready, "dispatch_time_sec": dispatch,
            "exited_at_sec": exit_, "was_fallback": fallback,
            "rider_wait_sec": dispatch - ready,
        }

    per_order = [
        rec(0, x, 100.0, 100.0, 200.0, False),   # exits at t=200
        rec(1, y, 100.0, 100.0, 400.0, True),
        rec(2, z, 100.0, 100.0, 400.0, True),    # pool now exhausted
        rec(3, pri[rec3_rank], rec3_ready, 200.0, 300.0, rec3_fallback),
    ]
    orders = [SimpleNamespace(ord_id=i, vol=1.0) for i in range(4)]
    inp = {
        "res": {"per_order": per_order, "return_leg": False},
        "riders": riders,
        "scenario": SimpleNamespace(orders=orders, K=4),
    }
    return check_assignment_replay(inp, 1.0)


def test_a7_same_tick_queued_grant_after_release_accepted():
    # ord 3 queued (ready 150, pool empty) and granted the rank-0 type by
    # ord 0's exit at the same tick 200 — only the post-release snapshot
    # explains the grant (rank 0 -> was_fallback False)
    result = _exhausted_pool_replay(rec3_rank=0, rec3_fallback=False, rec3_ready=150.0)
    assert result.passed, result.failures


def test_a7_same_tick_dispatch_before_release_accepted():
    # ord 1 becomes ready at ord 0's exit tick (t=200): the model dispatches
    # BEFORE the exit lands, so it grants rank-1 y (x not yet back). A
    # release-first replay would demand x — the false FAIL fixed in V1R; only
    # the pre-release snapshot explains the recorded (y, was_fallback=True).
    riders = [dataclasses.replace(r, available_number=1)
              for r in load_riders(ROOT / "data/data1/K50_1.json")]
    pri = type_priority(riders, 500.0)
    x, y, z = pri
    per_order = [
        {"ord_id": 0, "rider_type": x, "dist_m": 500.0, "ready_time_sec": 100.0,
         "dispatch_time_sec": 100.0, "exited_at_sec": 200.0, "was_fallback": False,
         "rider_wait_sec": 0.0},
        # ready exactly at ord 0's exit tick: model grants y (x not yet back),
        # a release-first replay would demand x -> false FAIL before the fix
        {"ord_id": 1, "rider_type": y, "dist_m": 500.0, "ready_time_sec": 200.0,
         "dispatch_time_sec": 200.0, "exited_at_sec": 320.0, "was_fallback": True,
         "rider_wait_sec": 0.0},
    ]
    orders = [SimpleNamespace(ord_id=i, vol=1.0) for i in range(2)]
    inp = {
        "res": {"per_order": per_order, "return_leg": False},
        "riders": riders,
        "scenario": SimpleNamespace(orders=orders, K=2),
    }
    result = check_assignment_replay(inp, 1.0)
    assert result.passed, result.failures


def test_a7_same_tick_true_violation_still_fails():
    # ord 3 records the dominated type z while y-or-better is explainable under
    # neither the pre- nor post-release snapshot -> must FAIL
    riders = [dataclasses.replace(r, available_number=1)
              for r in load_riders(ROOT / "data/data1/K50_1.json")]
    pri = type_priority(riders, 500.0)
    x, y, z = pri
    per_order = [
        {"ord_id": 0, "rider_type": x, "dist_m": 500.0, "ready_time_sec": 100.0,
         "dispatch_time_sec": 100.0, "exited_at_sec": 200.0, "was_fallback": False,
         "rider_wait_sec": 0.0},
        {"ord_id": 1, "rider_type": z, "dist_m": 500.0, "ready_time_sec": 200.0,
         "dispatch_time_sec": 200.0, "exited_at_sec": 320.0, "was_fallback": True,
         "rider_wait_sec": 0.0},
    ]
    orders = [SimpleNamespace(ord_id=i, vol=1.0) for i in range(2)]
    inp = {
        "res": {"per_order": per_order, "return_leg": False},
        "riders": riders,
        "scenario": SimpleNamespace(orders=orders, K=2),
    }
    result = check_assignment_replay(inp, 1.0)
    assert not result.passed


def test_a8_negative_window_arithmetic(base):
    bad = copy.deepcopy(base)
    bad["window"]["ped_start_sec"] += 100.0  # != min ORD - margin, != clock_start
    report = verify_result(bad)
    assert not _check(report, "A8").passed


def test_a9_negative_corrupted_floor(base):
    bad = copy.deepcopy(base)
    rec = bad["per_order"][0]
    rec["floor"] = 2 if rec["floor"] != 2 else 10  # no longer matches rederivation
    report = verify_result(bad)
    assert not _check(report, "A9").passed


# ------------------------------------------------------------ audit mode


def test_audit_mode_smoke_completes():
    """K50_1 profile run with audit=True runs to completion, no assert fires."""
    res = run_baseline(
        scenario_path="data/data1/K50_1.json",
        rng_seed=42,
        floor_profile="uniform",
        audit=True,
    )
    assert res["kpi_summary"]["customer"]["n_delivered"] == 50
    assert res["kpi_summary"]["simulation"]["terminated_by_cap"] is False
    # the audited run is itself a valid V-AUD subject
    report = verify_result(res)
    assert report["all_passed"], [c.name for c in report["checks"] if not c.passed]


def test_audit_off_is_bit_for_bit_identical():
    """audit=True must not perturb results vs the default audit=False path."""
    common = dict(
        scenario_path="data/data1/K50_1.json", rng_seed=42, floor_profile="uniform"
    )
    plain = run_baseline(**common)
    audited = run_baseline(**common, audit=True)
    assert plain["per_order"] == audited["per_order"]
    assert plain["kpi_summary"] == audited["kpi_summary"]


# ------------------------------------------------ A10 / A11 (v2 basements + fleet)


def test_a10_passes_on_basement_run(base):
    """A10 is satisfied by a normal v2 run and reports the basements it saw."""
    report = verify_result(base)
    a10 = _check(report, "A10")
    assert a10.passed and not a10.skipped
    assert "2 basement level(s)" in a10.detail
    assert "riders 0 below ground" in a10.detail


def test_a10_negative_rider_delivered_below_ground(base):
    """A10-2: an order on a basement floor is a defect — riders stay above ground.

    This is the half of the *old* (pre-§1.6) A10 that survived the inversion:
    the basements exist for background pedestrians, so a delivery reaching one
    means the rider path escaped the office floors.

    Checked through `check_basement_integrity` rather than `verify_result`
    because the earlier walk-based gates (A4/A5) route through the graph and
    raise NodeNotFound on a below-ground order before A10 is ever reached. The
    corruption is still detected either way — this asserts *which* invariant
    names it.
    """
    bad = copy.deepcopy(base)
    bad["per_order"][0]["floor"] = -1
    result = check_basement_integrity(load_inputs(bad))
    assert not result.passed
    assert "below ground" in " ".join(result.failures)


def test_a10_negative_ev_leaves_declared_range(base):
    """A10-3: a car below the deepest declared basement fails.

    ev{i}_floor is in floor-RANK units (B2 = -1, B1 = 0, 1F = 1), so with two
    basements the floor of the range is -1; -2 would be a third basement the
    building never declared.
    """
    bad = copy.deepcopy(base)
    bad["model_vars"]["ev1_floor"][10] = -2.0
    report = verify_result(bad)
    assert not _check(report, "A10").passed


def test_a10_1_structure_predicate_accepts_and_rejects():
    """A10-1 on a real graph, then on graphs corrupted two different ways.

    The config-driven builder cannot place an office below ground, so this
    invariant is unreachable from config alone — it is tested against a hand
    corrupted graph so it is not merely a comment (see the helper's docstring).
    """
    g = add_lobby_handoff_zones(
        build_from_config(load_config(ROOT / "configs" / "baseline_10f.yaml")),
        n_locker_compartments=8,
    )
    ev_ids = list(g.graph["ev_ids"])
    assert basement_structure_failures(g, 2, ev_ids) == []

    # (a) an office below ground: a basement stops being a boarding level
    with_office = g.copy()
    with_office.add_node(
        "floor_B1_office_0", type="office", floor=-1, office_id=0,
        corridor_position_m=4, side="north",
    )
    fails = basement_structure_failures(with_office, 2, ev_ids)
    assert fails and any("below ground" in f for f in fails)

    # (b) a car that skips a basement: fewer stop nodes than declared EVs
    missing_stop = g.copy()
    missing_stop.remove_node("ev_EV4_B2")
    fails = basement_structure_failures(missing_stop, 2, ev_ids)
    assert fails and any("basement floor -2" in f for f in fails)


def test_a10_zero_basement_run_passes(base):
    """A config with no basements verifies as a basement-free building.

    Guards the default that makes the pre-§1.6 regression path work: an absent
    `n_basements` key means zero, so replaying an archived config cannot silently
    gain two floors it never declared.
    """
    old = copy.deepcopy(base)
    del old["config"]["building"]["n_basements"]
    # a basement-free building must never show a car below 1F
    for key in list(old["model_vars"]):
        if key.endswith("_floor"):
            old["model_vars"][key] = [max(v, 1.0) for v in old["model_vars"][key]]
    report = verify_result(old)
    a10 = _check(report, "A10")
    assert a10.passed, a10.failures
    assert "0 basement level(s)" in a10.detail


def test_a11_negative_missing_declared_ev(base):
    """A11: dropping a declared car from the KPI schema fails even though the
    remaining cars are internally consistent (which is all A6 would see)."""
    bad = copy.deepcopy(base)
    del bad["kpi_summary"]["elevator"]["EV4"]
    report = verify_result(bad)
    assert not _check(report, "A11").passed
    assert not report["all_passed"]


def test_a11_negative_unbalanced_car(base):
    bad = copy.deepcopy(base)
    bad["kpi_summary"]["elevator"]["EV2"]["n_alights"] -= 1
    report = verify_result(bad)
    assert not _check(report, "A11").passed


def test_a12_is_skipped_but_enforced_in_audit_mode(base):
    """A12 never gates post-hoc; its detail must say where the real gate lives."""
    a12 = _check(verify_result(base), "A12")
    assert a12.skipped and a12.passed
    assert "audit" in a12.detail


def test_a12_audit_assert_fires_on_double_registration():
    """The audit-mode A12 assert actually trips when a passenger double-queues.

    Registers one pedestrian at a second car by hand and steps the model: the
    tick-level census must reject it. Without this, A12 would be a comment.
    """
    from simulation.model import BuildingHandoffModel, HandoffMode

    m = BuildingHandoffModel(
        mode=HandoffMode.H0_DIRECT,
        scenario_path="data/data1/K50_1.json",
        rng_seed=42,
        floor_profile="uniform",
        dynamic_pool=True,
        audit=True,
    )
    for _ in range(400):
        m.step()
        queued = [
            (ev, floor, p)
            for ev in m.elevators
            for floor, q in ev.hall_calls.items()
            for p in q
        ]
        if queued:
            break
    assert queued, "no hall call materialised in 400 ticks — cannot exercise A12"

    ev, floor, passenger = queued[0]
    other = next(e for e in m.elevators if e is not ev)
    other.hall_calls.setdefault(floor, deque()).append(passenger)
    with pytest.raises(AssertionError, match="queued twice"):
        m.step()
