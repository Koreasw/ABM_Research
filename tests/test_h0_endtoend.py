"""End-to-end test: H0 baseline delivers all 50 K50_1 orders (plan S5 완료 기준)."""

from __future__ import annotations

import pytest

from simulation.kpi import summarize
from simulation.model import ROOT, BuildingHandoffModel

DATA = ROOT / "data" / "data1" / "K50_1.json"


@pytest.fixture(scope="module")
def completed_model() -> BuildingHandoffModel:
    if not DATA.exists():
        pytest.skip(f"data not present at {DATA}")
    m = BuildingHandoffModel()
    m.run_to_completion()
    return m


def test_terminates_before_cap(completed_model: BuildingHandoffModel) -> None:
    m = completed_model
    assert m.running is False
    assert m.terminated_by_cap is False


def test_all_orders_delivered(completed_model: BuildingHandoffModel) -> None:
    m = completed_model
    assert all(c.delivered_at_sec is not None for c in m.customer_by_ord_id.values())
    assert len(m.rider_records) == 50
    ord_ids = [r["ord_id"] for r in m.rider_records]
    assert sorted(ord_ids) == sorted(o.ord_id for o in m.orders)
    assert len(set(ord_ids)) == 50  # no duplicates


def test_rider_entry_matches_planned_arrival(completed_model: BuildingHandoffModel) -> None:
    """Deterministic arrivals (sigma_eps=0): entry == synthesized arrival ± tick."""
    m = completed_model
    for r in m.rider_records:
        assert abs(r["entered_at_sec"] - r["arrival_time_planned_sec"]) <= m.dt


def test_floors_offices_modes_match_replay(completed_model: BuildingHandoffModel) -> None:
    m = completed_model
    by_ord = {o.ord_id: o for o in m.orders}
    for r in m.rider_records:
        o = by_ord[r["ord_id"]]
        assert r["floor"] == o.floor
        assert r["office_id"] == o.office_id
        assert r["vertical_mode"] == o.vertical_mode
        assert r["rider_type"] == o.rider_type


def test_t_lobby_positive_and_waits_nonnegative(
    completed_model: BuildingHandoffModel,
) -> None:
    m = completed_model
    for r in m.rider_records:
        assert r["t_lobby_sec"] > 0
        if r["vertical_mode"] == "elevator":
            assert r["ev_wait_up_sec"] is not None and r["ev_wait_up_sec"] >= 0
            assert r["ev_wait_down_sec"] is not None and r["ev_wait_down_sec"] >= 0
        else:
            assert r["ev_wait_up_sec"] is None
            assert r["ev_wait_down_sec"] is None


def test_weak_lower_bound_on_t_e2e(completed_model: BuildingHandoffModel) -> None:
    """T_e2e >= COOK + horizontal + service (delivery happens after arrival +
    in-building travel + full service). Strict LB is S6's job; this is the
    coarse sanity floor that catches broken time wiring."""
    m = completed_model
    for r in m.rider_records:
        floor_time = (
            r["cook_time_sec"] + r["horizontal_time_s"] + r["service_time_sec"]
        )
        assert r["t_e2e_sec"] >= floor_time - 2 * m.dt


def test_elevator_conservation(completed_model: BuildingHandoffModel) -> None:
    m = completed_model
    for ev in m.elevators:
        # R8: the invariant is boards - alights == whoever is still riding. Under
        # the drain-all policy that residual is 0 and this is the old equality;
        # under `delivery` the run stops at the last RIDER exit, so background
        # pedestrians can be mid-ride (verify_h0 A6 uses the same identity).
        assert len(ev.boarding_log) - ev.alight_count == len(ev.passengers)
        assert ev.capacity_violations == 0
        if m.termination_policy == "drain_all":
            assert len(ev.passengers) == 0      # nobody stuck on board
            assert ev.queue_length() == 0       # nobody stuck waiting
        else:
            # anyone left behind must be background traffic, never a courier
            assert all(p.kind == "pedestrian" for p in ev.passengers)
            assert all(
                p.kind == "pedestrian"
                for q in ev.hall_calls.values() for p in q
            )


def test_pedestrians_all_completed(completed_model: BuildingHandoffModel) -> None:
    from simulation.agents.pedestrian import PedestrianAgent

    m = completed_model
    # R8: pedestrian conservation, not pedestrian completion. Under `delivery`
    # the run ends with the background stream mid-flight by design; what must
    # still hold is that every spawned pedestrian is either done or still in
    # the building — none vanished.
    still_inside = len(m.agents_of(PedestrianAgent))
    assert m.ped_spawned == len(m.ped_done_log) + still_inside
    if m.termination_policy == "drain_all":
        assert still_inside == 0
    assert all(
        p["ev_wait_sec"] is not None and p["ev_wait_sec"] >= 0
        for p in m.ped_done_log
    )


def test_stairs_share_matches_precompute(completed_model: BuildingHandoffModel) -> None:
    """Mode counts must equal the precompute layer's sample (8/50 stairs for
    K50_1 seed 42) — the RNG-consistency guarantee, end to end."""
    m = completed_model
    n_stairs = sum(1 for r in m.rider_records if r["vertical_mode"] == "stairs")
    assert n_stairs == 8


def test_kpi_summary_complete(completed_model: BuildingHandoffModel) -> None:
    k = summarize(completed_model)
    assert k["customer"]["n_delivered"] == 50
    assert k["rider"]["n_exited"] == 50
    assert k["rider"]["t_lobby_mean_sec"] > 0
    assert 0 <= k["customer"]["sla_violation_rate"] <= 1
    for ev in k["elevator"].values():
        assert 0 <= ev["utilization"] <= 1
        assert ev["capacity_violations"] == 0
    assert k["building"]["capex_total_krw"] == 0.0
    assert k["building"]["cost_per_order_krw"] > 0
    # R8: the KPI carries the censored count, so conservation is still exact
    ped = k["pedestrian"]
    assert ped["n_completed"] + ped["n_in_building_at_end"] == ped["n_spawned"]
    if completed_model.termination_policy == "drain_all":
        assert ped["n_in_building_at_end"] == 0


def test_determinism_same_seed_identical_results() -> None:
    if not DATA.exists():
        pytest.skip(f"data not present at {DATA}")
    a = BuildingHandoffModel()
    a.run_to_completion()
    b = BuildingHandoffModel()
    b.run_to_completion()
    key = lambda m: [  # noqa: E731
        (r["ord_id"], r["t_e2e_sec"], r["t_lobby_sec"], r["walked_m"])
        for r in sorted(m.rider_records, key=lambda r: r["ord_id"])
    ]
    assert key(a) == key(b)
    assert a.tick_count == b.tick_count
