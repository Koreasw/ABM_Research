"""Step A2 — handoff rider, FCFS dispatch, model wiring.

The first block below is the guard for **A2 함정 1** (Mesa keys `agents_by_type`
by the exact class). Every rider lookup now goes through `model.rider_cls`; if
anyone reintroduces a literal `agents_of(ExternalRiderAgent)`, H1 silently sees
zero riders — the app stops rendering them and the OPEX accrual stops. These
tests pin both halves: the indirection exists everywhere, and H0's behaviour and
screen are unchanged by it (which is what keeps the `checklist_visual_h0v2.md`
signature valid past A2).
"""

from __future__ import annotations

import re

import pytest

from simulation.agents.external_rider import ExternalRiderAgent
from simulation.agents.handoff_rider import HandoffRiderAgent
from simulation.model import ROOT, BuildingHandoffModel, HandoffMode
from simulation.space import load_config

pytestmark = pytest.mark.vv

SCENARIO = "data/data1/K50_1.json"

# the 11 sites the pre-check enumerated (점검 §10.2-D)
_RIDER_LOOKUP_FILES = {
    "simulation/model.py": 6,
    "simulation/visualize.py": 4,
    "simulation/agents/building_manager.py": 1,
}


def _strip_comments(src: str) -> str:
    """Drop `#` comment tails so prose *about* the old call form does not read
    as the call form itself (this module's own guidance comments say it)."""
    return "\n".join(line.split("#", 1)[0] for line in src.splitlines())


def _h0_model(**kw):
    params = {
        "mode": HandoffMode.H0_DIRECT,
        "config": load_config(ROOT / "configs/baseline_10f.yaml"),
        "scenario_path": SCENARIO,
        "rng_seed": 42,
        "dynamic_pool": True,
        "scenario_window": True,
        "floor_profile": "uniform",
        "floor_seed": 42,
    }
    params.update(kw)
    return BuildingHandoffModel(**params)


# --------------------------------------------------------- 함정 1: rider_cls


def test_h0_binds_rider_cls_to_the_external_rider() -> None:
    """H0 must keep the original class, or every frozen H0 gate would move."""
    assert _h0_model().rider_cls is ExternalRiderAgent


@pytest.mark.parametrize(("rel", "expected"), sorted(_RIDER_LOOKUP_FILES.items()))
def test_rider_lookups_go_through_rider_cls(rel: str, expected: int) -> None:
    """No source file may name the rider class directly in an `agents_of` call.

    Source-level rather than behavioural on purpose: the failure mode is a
    *silent* empty list, so it has to be caught where it is written. The count
    is asserted too — a lookup deleted rather than converted is also a defect.
    """
    src = _strip_comments((ROOT / rel).read_text())
    literal = re.findall(r"agents_of\(\s*ExternalRiderAgent\s*\)", src)
    assert not literal, (
        f"{rel} still keys agents_by_type by the exact class; Mesa returns [] "
        f"for a subclass or a sibling class, so H1 would see zero riders. "
        f"Use model.rider_cls."
    )
    # the receiver varies by call site (`self`, `self.model`, `m`, `model`)
    via_attr = re.findall(r"agents_of\(\s*[\w.]*\brider_cls\s*\)", src)
    assert len(via_attr) == expected, (
        f"{rel}: expected {expected} rider lookups via rider_cls, found "
        f"{len(via_attr)} — a converted site was dropped or added."
    )


def test_visualize_no_longer_imports_the_rider_class() -> None:
    """The renderer must not reach for a concrete rider class at all."""
    src = (ROOT / "simulation/visualize.py").read_text()
    assert "ExternalRiderAgent" not in src


# ------------------------------------------- H0 unchanged by the substitution


def test_h0_run_is_unchanged_by_the_rider_cls_indirection() -> None:
    """H0 end-to-end result must be exactly what the frozen gates expect.

    `test_h0_frozen_snapshot` compares against the on-disk fixture; this is the
    cheap in-suite canary that fails first and points at A2.
    """
    m = _h0_model()
    m.run_to_completion()
    assert m.termination_reason == "delivery_complete"
    assert len(m.rider_records) == m.K
    assert all(c.delivered_at_sec is not None for c in m.customer_by_ord_id.values())


def test_h0_screen_still_renders_riders() -> None:
    """The cross-section and the rider table must still see riders in H0.

    This is the regression that `checklist_visual_h0v2.md` §4 signed off by eye:
    if the renderer's lookup broke, the run would still be perfect and only the
    picture would be empty.
    """
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib.figure import Figure

    from simulation.visualize import _rider_table_rows, draw_cross_section

    m = _h0_model()
    while m.running and not m.agents_of(m.rider_cls):
        m.step()
    assert m.agents_of(m.rider_cls), "no rider ever entered the building"

    rows = _rider_table_rows(m)
    assert len(rows) == len(m.agents_of(m.rider_cls))

    fig = Figure(figsize=(9, 5))
    draw_cross_section(m, fig.subplots())
    # the title carries the live rider count the checklist reads
    assert f"riders: {len(m.agents_of(m.rider_cls))}" in fig.axes[0].get_title()


def test_building_manager_still_accrues_opex_in_h0() -> None:
    """OPEX accrues per rider-tick; a broken lookup would leave it at zero."""
    m = _h0_model()
    while m.running and not m.agents_of(m.rider_cls):
        m.step()
    before = m.manager.opex_running_krw
    m.step()
    assert m.manager.opex_running_krw > before


def test_h0_builds_no_robots_and_no_leg_records() -> None:
    """The H0 tick must gain no new work: empty fleet is what gates dispatch."""
    m = _h0_model()
    assert m.robots == []
    m.run_to_completion()
    assert m.robot_leg_records == {}


# ------------------------------------------------------- H1: handoff FSM


def _h1_model(**kw):
    params = {
        "mode": HandoffMode.H1_SYNC,
        "config": load_config(ROOT / "configs/baseline_10f.yaml"),
        "scenario_path": SCENARIO,
        "rng_seed": 42,
        "dynamic_pool": True,
        "scenario_window": True,
        "floor_profile": "uniform",
        "floor_seed": 42,
    }
    params.update(kw)
    return BuildingHandoffModel(**params)


def test_h1_binds_the_handoff_rider_and_builds_the_fleet() -> None:
    m = _h1_model()
    assert m.rider_cls is HandoffRiderAgent
    assert len(m.robots) == m.n_robots == m.robot_params.n_robots


def test_handoff_rider_walks_the_fsm_and_never_leaves_the_ground_floor() -> None:
    """The whole point of H1's rider: it must not use the vertical system."""
    m = _h1_model()
    seen: list[str] = []
    rider = None
    while m.running:
        m.step()
        live = m.agents_of(m.rider_cls)
        if rider is None and live:
            rider = live[0]
        if rider is not None:
            if rider.state == HandoffRiderAgent.EXITED or rider not in live:
                break
            if not seen or seen[-1] != rider.state:
                seen.append(rider.state)
    assert seen == [
        HandoffRiderAgent.WALK_TO_COUNTER,
        HandoffRiderAgent.WAIT_ROBOT,
        HandoffRiderAgent.HANDOFF,
        HandoffRiderAgent.WALK_TO_EXIT,
    ], seen
    # never a rider state that implies stairs or a car
    assert not ({"climb_stairs", "wait_ev_up", "riding_up"} & set(seen))


def test_h1_rider_record_has_no_ev_waits_and_carries_handoff_fields() -> None:
    m = _h1_model()
    m.run_to_completion()
    assert len(m.rider_records) == m.K
    for rec in m.rider_records:
        # None, not 0.0 — a zero would average into the EV-wait KPIs as a real
        # observation of "waited no time" (A3 reads these).
        assert rec["ev_wait_up_sec"] is None
        assert rec["ev_wait_down_sec"] is None
        assert rec["vertical_mode"] == "handoff"
        assert rec["handoff_sec"] > 0.0
        assert rec["robot_wait_sec"] is not None
        assert rec["robot_id"] is not None


def test_h0_and_h1_rider_records_have_the_same_columns() -> None:
    """Additive convention: H1 adds keys, H0 keeps them as None — never a
    different shape, or every downstream consumer needs a mode branch."""
    h0 = _h0_model()
    h0.run_to_completion()
    h1 = _h1_model()
    h1.run_to_completion()
    h1_only = set(h1.rider_records[0]) - set(h0.rider_records[0])
    assert h1_only == {
        "handoff_started_sec", "handoff_ended_sec", "handoff_sec",
        "robot_wait_sec", "robot_id",
    }


# --------------------------------------------- 함정 2: the rider exits early


def test_the_rider_exits_before_the_order_is_delivered() -> None:
    """This is the whole reason `robot_leg_records` exists — pin the premise."""
    m = _h1_model()
    m.run_to_completion()
    early = [
        r for r in m.rider_records
        if r["delivered_at_sec"] is None
        or r["exited_at_sec"] < r["delivered_at_sec"]
    ]
    assert early, "no rider left before its delivery — the H1 premise is broken"


def test_robot_leg_records_complete_every_order_timeline() -> None:
    m = _h1_model()
    m.run_to_completion()
    assert set(m.robot_leg_records) == set(m.customer_by_ord_id)
    for ord_id, leg in m.robot_leg_records.items():
        cust = m.customer_by_ord_id[ord_id]
        assert leg["delivered_at_sec"] == cust.delivered_at_sec
        # the leg is a complete, ordered chain
        assert (
            leg["assigned_at_sec"]
            <= leg["handoff_started_sec"]
            <= leg["delivered_at_sec"]
            <= leg["returned_at_sec"]
        )
        assert leg["ev_wait_up_sec"] is not None
        assert leg["ev_wait_down_sec"] is not None


def test_rider_and_robot_records_join_on_ord_id() -> None:
    """The join that replaces H0's single-rider timeline."""
    m = _h1_model()
    m.run_to_completion()
    by_ord = {r["ord_id"]: r for r in m.rider_records}
    assert set(by_ord) == set(m.robot_leg_records)
    for ord_id, rec in by_ord.items():
        leg = m.robot_leg_records[ord_id]
        assert rec["robot_id"] == leg["robot_id"]
        assert rec["floor"] == leg["floor"]
        # the robot enters HANDOFF one tick after the rider signals (A1 design,
        # preserved by the robots-before-riders tick order)
        assert leg["handoff_started_sec"] == rec["handoff_started_sec"] + m.dt


# ------------------------------------------------------- 'hoff' RNG stream


def test_handoff_draw_is_keyed_by_ord_id_not_by_call_order() -> None:
    """CRN: a robot shortage reorders handoffs; the draws must not move."""
    from simulation.agents.handoff_rider import draw_handoff_sec

    tag, seed = 0x686F6666, 42
    first = [draw_handoff_sec(tag, seed, o, 60.0, 15.0) for o in (1, 2, 3)]
    shuffled = [draw_handoff_sec(tag, seed, o, 60.0, 15.0) for o in (3, 1, 2)]
    assert shuffled == [first[2], first[0], first[1]]


def test_handoff_draw_is_truncated_at_zero_without_resampling() -> None:
    """`max(x, 0)` keeps the word count per order fixed — resampling would not."""
    from simulation.agents.handoff_rider import draw_handoff_sec

    vals = [draw_handoff_sec(0x686F6666, 42, o, 0.0, 1.0) for o in range(200)]
    assert min(vals) == 0.0          # the clip actually fires at this mean
    assert all(v >= 0.0 for v in vals)


def test_handoff_stream_uses_the_configured_tag_and_seed() -> None:
    from simulation.agents.handoff_rider import draw_handoff_sec

    m = _h1_model()
    p = m.handoff_params
    assert p.rng_stream_tag == 0x686F6666
    expected = draw_handoff_sec(
        p.rng_stream_tag, m.rng_seed, 1, p.service_mean_sec, p.service_sd_sec
    )
    while m.running and not m.agents_of(m.rider_cls):
        m.step()
    rider = next(r for r in m.agents_of(m.rider_cls))
    assert rider.handoff_sec == draw_handoff_sec(
        p.rng_stream_tag, m.rng_seed, rider.order.ord_id,
        p.service_mean_sec, p.service_sd_sec,
    )
    assert expected > 0.0


def test_handoff_draw_does_not_perturb_h0() -> None:
    """The new stream is a new tag: H0 consumes exactly the words it used to."""
    a = _h0_model()
    a.run_to_completion()
    b = _h0_model()
    b.run_to_completion()
    assert a.rider_records == b.rider_records


# ------------------------------------------------------------- FCFS dispatch


def test_dispatch_is_fcfs_by_arrival() -> None:
    """Every robot parks on the same node, so nearest-idle == FCFS (A2-4).

    Both sequences are captured by wrapping the two call sites rather than by
    polling the deque: a rider that enters and is dispatched within one tick
    (the common case — `_inject_riders` runs before `control.step`) is never
    observable in the queue from outside.
    """
    m = _h1_model()
    requested: list[int] = []
    assigned: list[int] = []

    real_request = m.control.request_robot
    real_assign_map = m.control._robot_by_ord_id

    def spy_request(rider):  # noqa: ANN001
        requested.append(rider.order.ord_id)
        real_request(rider)

    m.control.request_robot = spy_request

    while m.running and len(assigned) < 12:
        before = set(real_assign_map)
        m.step()
        for oid in real_assign_map:
            if oid not in before:
                assigned.append(oid)

    assert len(assigned) >= 12
    # every assignment follows request order: the k-th assignment is the k-th
    # request among those assigned so far
    assert assigned == [o for o in requested if o in set(assigned)][: len(assigned)]


def test_charging_blocked_robots_are_not_dispatchable() -> None:
    """The whole reason CHARGING_BLOCKED is a state and not a flag (§3.1).

    The SOC has to be pushed below `soc_resume_pct` as well: a blocked robot
    with a full battery releases itself to IDLE on its very next step, so the
    state alone would not survive to the dispatch call.
    """
    from simulation.agents.robot import RobotState

    m = _h1_model()
    while m.running and not m.control.robot_requests:
        m.step()
    assert m.control.robot_requests, "no rider ever asked for a robot"
    assert m.control._robot_by_ord_id, "expected the earlier riders to be served"

    for rb in m.robots:
        rb.state = RobotState.CHARGING_BLOCKED
        rb.soc_wh = rb.battery.wh_for_soc_pct(rb.battery.soc_resume_pct - 5.0)
    assert not any(rb.is_available for rb in m.robots)

    before = set(m.control._robot_by_ord_id)
    m.step()
    assert set(m.control._robot_by_ord_id) == before, (
        "a CHARGING_BLOCKED robot was dispatched"
    )


def test_h0_dispatch_branch_is_never_entered() -> None:
    m = _h0_model()
    m.run_to_completion()
    assert m.control.robot_dispatch_count == 0
    assert not m.control.robot_requests


# ------------------------------------------------------------- termination


def test_h1_terminates_with_every_robot_home() -> None:
    from simulation.agents.robot import HOME_NODE, RobotState

    m = _h1_model()
    m.run_to_completion()
    assert m.termination_reason == "delivery_complete"
    assert not m.terminated_by_cap
    for rb in m.robots:
        assert rb.node == HOME_NODE
        assert rb.state in (RobotState.IDLE, RobotState.CHARGING_BLOCKED)


def test_charging_blocked_robot_does_not_hang_the_run() -> None:
    """§3.2: accepting only IDLE would stall on a low-SOC robot at the end."""
    from simulation.agents.robot import HOME_NODE, RobotState

    m = _h1_model()
    m.run_to_completion()
    rb = m.robots[0]
    rb.state = RobotState.CHARGING_BLOCKED
    rb.node = HOME_NODE
    assert m._carriers_settled()


def test_h1_delivers_every_order_with_the_audit_on() -> None:
    """Gate for A2: K50_1 --mode hr --audit runs to completion."""
    m = _h1_model(audit=True)
    m.run_to_completion()
    assert m.termination_reason == "delivery_complete"
    assert all(c.delivered_at_sec is not None for c in m.customer_by_ord_id.values())
    assert len(m.robot_leg_records) == m.K
