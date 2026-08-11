"""V-KPIWIN — dual measurement-window KPIs (full window vs order span).

Locks the additive `*_orderspan` fields added to simulation.kpi.summarize:
  1. frozen full-window fields are bit-unchanged (regression snapshot),
  2. order-span helpers match their closed-form definition,
  3. order-span util / OPEX equal an independent recompute from the model's
     cumulative snapshots (end-to-end wiring),
  4. structural invariants that DO hold (order span ⊂ full window, busy-tick
     numerator monotonicity). The plan's suggested `util_orderspan >= util_full`
     is intentionally NOT asserted — it is empirically false per EV because the
     elevators are saturated by pedestrian traffic across the whole ±1 h ped
     window, not concentrated in the order span (see test_util_window_robust).
"""
from __future__ import annotations

import pytest

from simulation.kpi import _order_span, _tick_index, summarize
from simulation.run import run_baseline

# low/mid/high within the 28-file modelling corpus; K1000_1 is out of
# corpus for this study (사용자 확정 2026-08-04).
_SCEN = ["K50_1", "K200_1", "K300_4"]


def _run(stem: str, seed: int = 42) -> dict:
    return run_baseline(
        scenario_path=f"data/data1/{stem}.json", rng_seed=seed, floor_profile="uniform"
    )


def _legacy_summary(stem: str, seed: int = 42) -> dict:
    """Summary of a run pinned to the pre-R8 window/termination contract.

    `configs/baseline_10f.yaml` declares `window_policy: delivery` since R8-f, so
    the frozen full-window anchors below would otherwise be measuring a different
    contract. Overriding the policy in a copy keeps this regression pointed at
    what it was written to protect — and its continued agreement is independent
    evidence that R8 left the legacy path bit-identical.
    """
    import copy

    from simulation.model import ROOT, BuildingHandoffModel
    from simulation.space import load_config

    cfg = copy.deepcopy(load_config(ROOT / "configs" / "baseline_10f.yaml"))
    cfg["simulation"]["window_policy"] = "legacy_margin"
    cfg["simulation"]["max_overrun_sec"] = 3600.0   # pre-R8 value
    m = BuildingHandoffModel(
        config=cfg, scenario_path=f"data/data1/{stem}.json", rng_seed=seed,
        dynamic_pool=True, scenario_window=True, floor_profile="uniform",
    )
    m.run_to_completion()
    return summarize(m)


# --------------------------------------------------------------------------- 1
def test_frozen_full_window_fields_unchanged() -> None:
    """Explicit regression snapshot: full-window fields of K50_1/seed42 pinned
    to the H0 v2 baseline (4 EVs·34 m corridor·ped 7.5/min — plan_h0_revision.md
    §1).

    Re-frozen 2026-08-03 for §1.6 (people-only basements B1/B2): pedestrians
    ride to and from parking, so the cars got busier (util 0.71~0.74 -> 0.77~0.81)
    and ran longer. A *fall* in utilisation would mean the basement stops are
    not being served — check the rank conversions first.

    Re-frozen again 2026-08-04 for the office layout change ([4,9,14,19,24,29]
    -> [2,7,12,22,27,32], mirrored about the corridor midpoint with a 10 m
    service core). Riders now walk further along the corridor to reach an
    office, so the in-building leg lengthened: t_lobby 247.46 -> 248.02 s
    (+0.23%) and cost per order 564.8 -> 567.9 KRW. The whole-run wall span
    moved 10615 -> 10612 s. These are single-seed values; V2-VAR measured the
    30-seed CI95 half-width at 1.8~4.3% for w_ev_mean, so seed-level swings in
    that field are noise, not signal.
    """
    s = _legacy_summary("K50_1")
    assert s["simulation"]["window_policy"] == "legacy_margin"
    assert s["customer"]["n_delivered"] == 50
    assert s["simulation"]["wall_span_sec"] == pytest.approx(10612.0)
    assert s["simulation"]["ticks"] == 10612
    assert s["elevator"]["EV1"]["utilization"] == pytest.approx(0.8157745947983415)
    assert s["elevator"]["EV2"]["utilization"] == pytest.approx(0.8132303053147381)
    assert s["elevator"]["EV3"]["utilization"] == pytest.approx(0.7908970976253298)
    assert s["elevator"]["EV4"]["utilization"] == pytest.approx(0.7796833773087071)
    assert s["elevator"]["EV1"]["n_boardings"] == 354
    assert s["building"]["opex_running_krw"] == pytest.approx(28394.4)
    assert s["building"]["cost_per_order_krw"] == pytest.approx(567.9)


# --------------------------------------------------------------------------- 2
def test_tick_index_closed_form() -> None:
    """Nearest-tick rounding and clamping to [0, n]."""
    # clock_start=1000, dt=1.0, n=100
    assert _tick_index(1000.0, 1.0, 1000.0, 100) == 0
    assert _tick_index(1000.0, 1.0, 1042.4, 100) == 42   # rounds down
    assert _tick_index(1000.0, 1.0, 1042.6, 100) == 43   # rounds up
    assert _tick_index(1000.0, 1.0, 500.0, 100) == 0     # clamp low
    assert _tick_index(1000.0, 1.0, 99999.0, 100) == 100  # clamp high
    # dt=0.5 quantisation
    assert _tick_index(0.0, 0.5, 10.0, 100) == 20


def test_order_span_closed_form() -> None:
    class _C:  # minimal customer stub
        def __init__(self, ordt, delv):
            self.ord_time_sec = ordt
            self.delivered_at_sec = delv

    assert _order_span([_C(100, 500), _C(80, 480), _C(120, 900)]) == (80, 900)
    # undelivered orders are ignored in the max-delivery bound
    assert _order_span([_C(100, 500), _C(80, None)]) == (80, 500)
    # no deliveries at all -> None (KPIs fall back to full window)
    assert _order_span([_C(100, None)]) is None
    assert _order_span([]) is None


def test_windowed_fraction_formula() -> None:
    """The (cum[j1]-cum[j0])/(j1-j0) pattern the code uses, hand-checked."""
    cum = [0, 1, 1, 2, 3, 3, 4]  # busy at ticks 1,4,7... cumulative
    j0, j1 = 1, 5
    assert (cum[j1] - cum[j0]) / (j1 - j0) == pytest.approx((3 - 1) / 4)


# --------------------------------------------------------------------------- 3
def test_util_orderspan_matches_model_recompute() -> None:
    """End-to-end: summary util_orderspan == independent recompute from the
    model's per-tick cumulative busy history and the span tick indices."""
    res = run_baseline(
        scenario_path="data/data1/K50_1.json", rng_seed=42, floor_profile="uniform"
    )
    # re-run to get the live model object (run_baseline returns only the dict)
    from simulation.model import ROOT, BuildingHandoffModel, HandoffMode
    from simulation.space import load_config

    m = BuildingHandoffModel(
        mode=HandoffMode.H0_DIRECT,
        config=load_config(ROOT / "configs" / "baseline_10f.yaml"),
        scenario_path="data/data1/K50_1.json",
        rng_seed=42,
        dynamic_pool=True,
        scenario_window=True,
        floor_profile="uniform",
    )
    m.run_to_completion()
    s = summarize(m)

    span = _order_span(list(m.customer_by_ord_id.values()))
    j0 = _tick_index(m.clock_start_sec, m.dt, span[0], m.tick_count)
    j1 = _tick_index(m.clock_start_sec, m.dt, span[1], m.tick_count)
    for idx, ev in enumerate(m.elevators):
        cum = m._ev_busy_cum[idx]
        expected = (cum[j1] - cum[j0]) / (j1 - j0)
        assert s["elevator"][ev.ev_id]["utilization_orderspan"] == pytest.approx(expected)
    # (sanity: deterministic run reproduced the frozen full-window util)
    assert s["elevator"]["EV1"]["utilization"] == pytest.approx(
        res["kpi_summary"]["elevator"]["EV1"]["utilization"]
    )


# --------------------------------------------------------------------------- 4
def test_opex_orderspan_matches_model_recompute() -> None:
    from simulation.model import ROOT, BuildingHandoffModel, HandoffMode
    from simulation.space import load_config

    m = BuildingHandoffModel(
        mode=HandoffMode.H0_DIRECT,
        config=load_config(ROOT / "configs" / "baseline_10f.yaml"),
        scenario_path="data/data1/K50_1.json",
        rng_seed=42,
        dynamic_pool=True,
        scenario_window=True,
        floor_profile="uniform",
    )
    m.run_to_completion()
    s = summarize(m)
    span = _order_span(list(m.customer_by_ord_id.values()))
    j0 = _tick_index(m.clock_start_sec, m.dt, span[0], m.tick_count)
    j1 = _tick_index(m.clock_start_sec, m.dt, span[1], m.tick_count)
    expected = round(m._opex_cum[j1] - m._opex_cum[j0], 1)
    assert s["building"]["opex_running_krw_orderspan"] == pytest.approx(expected)
    # OPEX is near window-invariant (rider dwell lies inside the span); the
    # order-span figure is <= the full total by the last riders' exit tail.
    assert 0.0 < expected <= s["building"]["opex_running_krw"]


# --------------------------------------------------------------------------- 5
@pytest.mark.parametrize("stem", _SCEN)
def test_orderspan_subset_and_numerator_monotone(stem: str) -> None:
    """Structural invariants that always hold: the order span is a strict
    sub-window of the full run, and the busy-tick numerator is monotone."""
    from simulation.model import ROOT, BuildingHandoffModel, HandoffMode
    from simulation.space import load_config

    m = BuildingHandoffModel(
        mode=HandoffMode.H0_DIRECT,
        config=load_config(ROOT / "configs" / "baseline_10f.yaml"),
        scenario_path=f"data/data1/{stem}.json",
        rng_seed=42,
        dynamic_pool=True,
        scenario_window=True,
        floor_profile="uniform",
    )
    m.run_to_completion()
    s = summarize(m)
    sim = s["simulation"]
    t0, t1 = sim["orderspan_window_sec"]
    # order span strictly inside the full [clock_start, clock_end] window
    assert sim["clock_start_sec"] <= t0 < t1 <= sim["clock_end_sec"]
    assert 0.0 < sim["wall_span_orderspan_sec"] < sim["wall_span_sec"]

    span = _order_span(list(m.customer_by_ord_id.values()))
    j0 = _tick_index(m.clock_start_sec, m.dt, span[0], m.tick_count)
    j1 = _tick_index(m.clock_start_sec, m.dt, span[1], m.tick_count)
    for idx, ev in enumerate(m.elevators):
        cum = m._ev_busy_cum[idx]
        busy_span = cum[j1] - cum[j0]
        assert 0 <= busy_span <= ev.busy_ticks          # numerator monotone
        uo = s["elevator"][ev.ev_id]["utilization_orderspan"]
        assert 0.0 <= uo <= 1.0
        assert 0.0 <= s["elevator"][ev.ev_id]["utilization"] <= 1.0


# --------------------------------------------------------------------------- 6
def test_util_window_robust() -> None:
    """Finding (re-characterized for H0 v2): EV util is window-ROBUST — full
    window and order span land within ~0.08 of each other for every EV. Unlike
    v1 (2 saturated EVs at 90-99%, direction not fixed), the v2 fleet of 4 EVs
    runs at ~70-92% and the order span is consistently the busier sub-window
    (uo >= uf for all EVs in all 3 demo scenarios) because the doubled fleet
    de-saturates the ±1 h pedestrian tails. Do NOT re-pin a false
    `uo == uf` or v1's both-directions claim."""
    for stem in _SCEN:
        s = _run(stem)["kpi_summary"]
        for ev in s["elevator"].values():
            uf, uo = ev["utilization"], ev["utilization_orderspan"]
            assert 0.65 <= uf <= 1.0 and 0.65 <= uo <= 1.0   # both sane
            assert abs(uo - uf) < 0.10                       # window-robust
            assert uo >= uf - 1e-9                           # v2: span is busier
