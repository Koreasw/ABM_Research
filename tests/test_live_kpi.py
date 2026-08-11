"""S7.1 — live-KPI DataCollector series, KPI report builders, and the
SolaraViz parameter wiring on the model side (mapping-path derivation,
rng_seed stream).

The Solara UI itself can't run under pytest; everything here exercises the
model/kpi layer those components read from.
"""

from __future__ import annotations

import numpy as np

from simulation.agents.external_rider import ExternalRiderAgent
from simulation.kpi import summarize, summary_to_csv, summary_to_markdown, summary_to_rows
from simulation.model import ROOT, BuildingHandoffModel, HandoffMode
from simulation.space import load_config

_NEW_SERIES = [
    "backlog",
    "sla_rate_running",
    "t_e2e_running_mean",
    "t_lobby_running_mean",
    "riders_walking",
    "riders_waiting_ev",
    "riders_riding_ev",
    "riders_on_stairs",
    "riders_in_service",
    "ev1_util_window",
    "ev2_util_window",
    "opex_running_krw",
    "peds_waiting",
]

_STATE_SERIES = _NEW_SERIES[4:9]


def _model(seed: int = 42) -> BuildingHandoffModel:
    cfg = load_config(ROOT / "configs" / "baseline_10f.yaml")
    return BuildingHandoffModel(mode=HandoffMode.H0_DIRECT, config=cfg, rng_seed=seed)


def _step_until_riders(m: BuildingHandoffModel, cap: int = 3000) -> None:
    for _ in range(cap):
        if not m.running:
            break
        m.step()
        if len(m.agents_of(ExternalRiderAgent)) >= 3:
            break


def test_new_series_collected_and_sane() -> None:
    m = _model()
    _step_until_riders(m)
    df = m.datacollector.get_model_vars_dataframe()
    for col in _NEW_SERIES:
        assert col in df.columns, f"missing model reporter: {col}"
    last = df.iloc[-1]
    assert last["backlog"] >= 0
    assert 0.0 <= last["sla_rate_running"] <= 100.0
    assert 0.0 <= last["ev1_util_window"] <= 100.0
    assert 0.0 <= last["ev2_util_window"] <= 100.0
    assert last["opex_running_krw"] >= 0.0
    assert last["peds_waiting"] >= 0


def test_rider_state_groups_partition_riders_in_building() -> None:
    """The 5 state-group series must sum to riders_in_building at every tick
    (the groups partition the live FSM states)."""
    m = _model()
    _step_until_riders(m)
    for _ in range(300):  # keep stepping through active traffic
        if not m.running:
            break
        m.step()
    df = m.datacollector.get_model_vars_dataframe()
    group_sum = sum(df[c] for c in _STATE_SERIES)
    assert (group_sum == df["riders_in_building"]).all()


def test_backlog_consistent_with_orders_and_deliveries() -> None:
    m = _model()
    _step_until_riders(m)
    placed = sum(
        1 for c in m.customer_by_ord_id.values() if c.ord_time_sec <= m.clock_sec
    )
    delivered = sum(
        1 for c in m.customer_by_ord_id.values() if c.delivered_at_sec is not None
    )
    assert m.backlog() == placed - delivered


def test_mapping_path_derived_from_scenario_stem() -> None:
    m = _model()
    assert m.mapping_path.name == "K50_1_floor_mapping_v4.json"
    assert m.mapping_path.exists()


def test_rng_seed_changes_arrivals_but_not_vertical_modes() -> None:
    """rng_seed drives rider-type/ε sampling (arrival times move), while the
    vertical mode stays pinned to mode_seed XOR ord_id (plan §주의점 1)."""
    o42 = _model(seed=42).orders
    o7 = _model(seed=7).orders
    modes42 = {o.ord_id: o.vertical_mode for o in o42}
    modes7 = {o.ord_id: o.vertical_mode for o in o7}
    assert modes42 == modes7
    arr42 = {o.ord_id: o.arrival_time_sec for o in o42}
    arr7 = {o.ord_id: o.arrival_time_sec for o in o7}
    assert any(abs(arr42[i] - arr7[i]) > 1e-9 for i in arr42)


def test_kpi_report_builders_on_completed_run() -> None:
    m = _model()
    m.run_to_completion()
    assert not m.running and not m.terminated_by_cap

    summary = summarize(m)
    rows = summary_to_rows(summary)
    sections = {s for s, _, _ in rows}
    for expected in ("Simulation", "Customer", "Rider", "Elevator EV1",
                     "Elevator EV2", "Pedestrian", "Building"):
        assert expected in sections

    meta = {"scenario": m.scenario_path.name, "rng_seed": m.rng_seed}
    md = summary_to_markdown(summary, meta)
    assert md.startswith("# H0 Baseline — KPI Report")
    assert "## Customer" in md and "## Elevator EV1" in md
    assert "**scenario**: K50_1.json" in md

    csv_text = summary_to_csv(summary, meta)
    lines = csv_text.strip().split("\n")
    assert lines[0] == "section,metric,value"
    assert len(lines) == 1 + len(meta) + len(rows)
    # running means settle to the final KPI values at end of run
    df = m.datacollector.get_model_vars_dataframe()
    assert np.isclose(
        df["t_e2e_running_mean"].iloc[-1], summary["customer"]["t_e2e_mean_sec"]
    )
    assert np.isclose(
        df["t_lobby_running_mean"].iloc[-1], summary["rider"]["t_lobby_mean_sec"]
    )


def test_summary_to_rows_formats_none_as_na() -> None:
    rows = summary_to_rows({"customer": {"t_e2e_mean_sec": None}})
    assert rows == [("Customer", "t_e2e_mean_sec", "n/a")]
