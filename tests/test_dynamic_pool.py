"""End-to-end tests for the dynamic rider-pool path S4 (plan_rider_pool_dynamic.md).

Static path regression is covered by the existing suite (dynamic_pool=False
default leaves it untouched); here we exercise dynamic_pool=True on K50_1.
"""

from __future__ import annotations

import pytest

from simulation.agents.external_rider import ExternalRiderAgent
from simulation.model import ROOT, BuildingHandoffModel

DATA = ROOT / "data" / "data1" / "K50_1.json"


@pytest.fixture(scope="module")
def dyn_model() -> BuildingHandoffModel:
    if not DATA.exists():
        pytest.skip(f"data not present at {DATA}")
    m = BuildingHandoffModel(dynamic_pool=True)
    m.run_to_completion()
    return m


def test_dynamic_terminates_and_delivers_all(dyn_model: BuildingHandoffModel) -> None:
    m = dyn_model
    assert m.running is False
    assert m.terminated_by_cap is False
    assert all(c.delivered_at_sec is not None for c in m.customer_by_ord_id.values())
    assert len(m.rider_records) == 50
    assert len({r["ord_id"] for r in m.rider_records}) == 50


def test_pool_fully_restored_after_run(dyn_model: BuildingHandoffModel) -> None:
    pool = dyn_model.rider_pool
    assert pool.free == pool.initial          # every rider returned
    assert not pool.waiting
    assert not dyn_model.pending_arrivals
    assert not dyn_model.pending_releases
    assert sum(pool.dispatch_count.values()) == 50


def test_dispatch_provenance_recorded(dyn_model: BuildingHandoffModel) -> None:
    for r in dyn_model.rider_records:
        assert r["ready_time_sec"] is not None
        assert r["dispatch_time_sec"] >= r["ready_time_sec"]
        assert r["rider_wait_sec"] == pytest.approx(
            r["dispatch_time_sec"] - r["ready_time_sec"]
        )
        assert r["rider_wait_sec"] >= 0.0
        assert r["was_fallback"] in (False, True)
        assert r["dist_m"] > 0


def test_arrival_equals_dispatch_plus_travel(dyn_model: BuildingHandoffModel) -> None:
    """sigma_eps=0: entry == dispatch + D/speed(type) ± tick (+dispatch tick)."""
    m = dyn_model
    for r in m.rider_records:
        expected = r["dispatch_time_sec"] + r["horizontal_time_s"]
        assert abs(r["entered_at_sec"] - expected) <= 2 * m.dt


def test_types_follow_cost_rule(dyn_model: BuildingHandoffModel) -> None:
    """K50_1: all D in [338, 4639] m, VOL<=70 → non-fallback = BIKE; fallback
    follows the BIKE-exhausted distance rule (D<400 WALK, D>=400 CAR)."""
    for r in dyn_model.rider_records:
        if not r["was_fallback"] and r["rider_wait_sec"] == 0.0:
            assert r["rider_type"] == "BIKE"
        elif r["was_fallback"]:
            assert r["rider_type"] == ("WALK" if r["dist_m"] < 399.8 else "CAR")


def test_no_wait_arrival_matches_static_formula(
    dyn_model: BuildingHandoffModel,
) -> None:
    """Un-queued BIKE dispatches reproduce the static-path arrival time:
    start + ORD_TIME + COOK + D/speed_BIKE (pool feedback only kicks in on
    exhaustion, plan §전역 설계 결정 1)."""
    m = dyn_model
    speed_bike = m.rider_by_type["BIKE"].speed_mps
    checked = 0
    for r in m.rider_records:
        if r["rider_type"] == "BIKE" and r["rider_wait_sec"] == 0.0:
            static_arrival = (
                r["ord_time_abs_sec"] + r["cook_time_sec"] + r["dist_m"] / speed_bike
            )
            # dispatch happens on the tick boundary after ready → ≤ 2 ticks off
            assert abs(r["entered_at_sec"] - static_arrival) <= 3 * m.dt
            checked += 1
    assert checked > 0


def test_mid_run_conservation_per_type() -> None:
    """free + en-route + in-building + returning == initial, every 50 ticks."""
    if not DATA.exists():
        pytest.skip(f"data not present at {DATA}")
    m = BuildingHandoffModel(dynamic_pool=True, return_leg=True)
    while m.running and m.tick_count < 20000:
        m.step()
        if m.tick_count % 50 != 0:
            continue
        en_route: dict[str, int] = {}
        for _, _, o in m.pending_arrivals:
            en_route[o.rider_type] = en_route.get(o.rider_type, 0) + 1
        in_building: dict[str, int] = {}
        for a in m.agents_of(ExternalRiderAgent):
            t = a.order.rider_type
            in_building[t] = in_building.get(t, 0) + 1
        returning: dict[str, int] = {}
        for _, t in m.pending_releases:
            returning[t] = returning.get(t, 0) + 1
        pool = m.rider_pool
        for t in pool.initial:
            total = (
                pool.free[t]
                + en_route.get(t, 0)
                + in_building.get(t, 0)
                + returning.get(t, 0)
            )
            assert total == pool.initial[t], f"{t} leak at tick {m.tick_count}"
    assert m.running is False and m.terminated_by_cap is False
    # R8: with return_leg the `delivery` policy stops as soon as the last rider
    # is OUT OF THE BUILDING, which can leave riders still biking back to their
    # shop — `pending_releases` is deliberately not a termination blocker
    # (plan_h0v21_window.md §2.2). Conservation must still close exactly, so
    # assert that rather than the strictly stronger "pool fully restored".
    pool = m.rider_pool
    assert not m.pending_arrivals and not m.agents_of(ExternalRiderAgent)
    returning_end: dict[str, int] = {}
    for _, t in m.pending_releases:
        returning_end[t] = returning_end.get(t, 0) + 1
    for t in pool.initial:
        assert pool.free[t] + returning_end.get(t, 0) == pool.initial[t], t
    if m.termination_policy == "drain_all":
        assert pool.free == pool.initial


def test_forced_exhaustion_queue_then_release() -> None:
    """Tiny pool (1/1/1): orders queue for stock, still all delivered, and
    rider_wait shows up in the records (SLA violations recorded, no cancels)."""
    if not DATA.exists():
        pytest.skip(f"data not present at {DATA}")
    from simulation.space import load_config

    # 3 riders x 50 orders can't finish inside the default 1h overrun cap —
    # raise it so the queue actually drains (delivery ~15 min/order/rider)
    cfg = load_config(ROOT / "configs" / "baseline_10f.yaml")
    cfg["simulation"]["max_overrun_sec"] = 8 * 3600.0
    m = BuildingHandoffModel(dynamic_pool=True, config=cfg)
    pool = m.rider_pool
    for t in list(pool.initial):
        pool.initial[t] = 1
        pool.free[t] = 1
    m.run_to_completion()
    assert m.running is False and m.terminated_by_cap is False
    assert len(m.rider_records) == 50
    assert all(
        c.delivered_at_sec is not None for c in m.customer_by_ord_id.values()
    )
    assert pool.free == pool.initial
    waited = [r for r in m.rider_records if r["rider_wait_sec"] > 0]
    assert waited, "3-rider fleet must force queueing on 50 orders"
    assert pool.queued_count == len(waited)


def test_free_series_collected(dyn_model: BuildingHandoffModel) -> None:
    df = dyn_model.datacollector.get_model_vars_dataframe()
    assert df["free_bike"].iloc[-1] == 10.0
    assert df["free_walk"].iloc[-1] == 15.0
    assert df["free_car"].iloc[-1] == 50.0
    assert df["free_bike"].min() >= 0.0
    assert df["dispatch_queue_len"].iloc[-1] == 0.0


def test_pool_summary_and_fleet_rows() -> None:
    """S5 visualization row builders: phases cover the fleet lifecycle and
    row counts reconcile with the model state mid-run."""
    if not DATA.exists():
        pytest.skip(f"data not present at {DATA}")
    from simulation.visualize import _fleet_table_rows, _pool_summary_rows

    m = BuildingHandoffModel(dynamic_pool=True, return_leg=True)
    seen_phases: set[str] = set()
    while m.running and m.tick_count < 6000:
        m.step()
        if m.tick_count % 25 != 0:
            continue
        rows = _fleet_table_rows(m)
        expected = (
            len(m.rider_pool.waiting)
            + len(m.pending_arrivals)
            + len(m.agents_of(ExternalRiderAgent))
            + len(m.pending_releases)
        )
        assert len(rows) == expected
        seen_phases |= {r["단계"].split(":")[0] for r in rows}
        summary = _pool_summary_rows(m)
        assert {s["type"] for s in summary} == {"BIKE", "WALK", "CAR"}
        for s in summary:
            assert s["가용"] + s["배달중"] == s["초기"]
    assert "② 배차·이동중" in seen_phases
    assert "③ 건물내" in seen_phases
    assert "④ 복귀중" in seen_phases  # return_leg=True


def test_static_path_unaffected_by_new_fields() -> None:
    """dynamic_pool=False keeps rider_pool None and NaN pool series."""
    if not DATA.exists():
        pytest.skip(f"data not present at {DATA}")
    m = BuildingHandoffModel()  # default static
    assert m.rider_pool is None
    for _ in range(300):
        m.step()
    df = m.datacollector.get_model_vars_dataframe()
    assert df["free_bike"].isna().all()
    rec_fields = None
    if m.rider_records:
        rec_fields = m.rider_records[0]
        assert rec_fields["dispatch_time_sec"] is None
        assert rec_fields["was_fallback"] is None
