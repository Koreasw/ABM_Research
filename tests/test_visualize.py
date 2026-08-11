"""S7 — simulation/visualize.py + simulation/app.py (live cross-section).

The Solara server itself can't run under pytest, but the pieces it depends on
can: node→(x,y) mapping, the pure matplotlib renderer against a real stepped
model, and the app module's construction of the SolaraViz page.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from simulation.agents.external_rider import ExternalRiderAgent
from simulation.model import ROOT, BuildingHandoffModel, HandoffMode  # noqa: E402
from simulation.space import load_config  # noqa: E402
from simulation.visualize import (  # noqa: E402
    _CHARGING_MARK,
    _building_geom,
    _elevator_table_rows,
    _kpi_panel_markdown,
    _rider_table_rows,
    _stair_x,
    build_kpi_report,
    draw_cross_section,
    node_xy,
)

_SHAFT_HALF_W = 0.35  # matches the axvspan half-width in draw_cross_section


def _model(n_basements: int | None = None):
    cfg = load_config(ROOT / "configs" / "baseline_10f.yaml")
    if n_basements is not None:
        cfg["building"]["n_basements"] = n_basements
        if n_basements == 0:
            cfg["pedestrian"].pop("ground_split", None)
    return BuildingHandoffModel(mode=HandoffMode.H0_DIRECT, config=cfg, rng_seed=42)


def test_node_xy_maps_known_nodes() -> None:
    m = _model()
    # corridor position → (x, floor)
    assert node_xy(m, "floor_3_corr_7") == (7.0, 3.0)
    # office offset off the corridor line by ±0.3 floors
    ox, oy = node_xy(m, "floor_2_office_0")
    assert ox == 2.0 and abs(oy - 2.30) < 1e-9  # north side, above corridor
    ox2, oy2 = node_xy(m, "floor_2_office_6")
    assert oy2 < 2.0  # south side, below corridor
    # elevator node at its shaft position
    assert node_xy(m, "ev_EV1_5")[0] in m.config["building"]["ev_corridor_positions_m"]
    # unknown / locker node → None (not drawn)
    assert node_xy(m, "lobby_locker_compartment_0") is None
    assert node_xy(m, "does_not_exist") is None


def test_draw_cross_section_runs_on_stepped_model() -> None:
    m = _model()
    # step into the lunch peak until riders are actively in the building
    for _ in range(2500):
        if not m.running:
            break
        m.step()
        if m.agents_of(ExternalRiderAgent):
            break
    assert m.agents_of(ExternalRiderAgent), "expected active riders at the peak"
    fig, ax = plt.subplots(figsize=(9, 5))
    draw_cross_section(m, ax)  # must not raise
    # scaffold + agents produced artists
    assert ax.patches, "no elevator car rectangles drawn"
    assert ax.lines, "no agent markers / floor lines drawn"
    plt.close(fig)


def test_draw_cross_section_on_fresh_model() -> None:
    """Tick 0 (no active agents yet) must still render the empty building."""
    m = _model()
    fig, ax = plt.subplots()
    draw_cross_section(m, ax)
    plt.close(fig)


# --- H0 v2 visual requirements (plan_h0_revision.md §1.5) --------------------


def test_four_ev_shafts_do_not_overlap() -> None:
    """§1.5-2 비겹침: the four shafts (north EV1/EV3, south EV2/EV4 sharing
    corridor positions 16/18) must occupy disjoint x bands, so no two columns
    are drawn on top of each other."""
    m = _model()
    geom = _building_geom(m)
    assert len(geom["ev_x"]) == 4
    spans = sorted(
        (x - _SHAFT_HALF_W, x + _SHAFT_HALF_W) for x in geom["ev_x"].values()
    )
    for (_, prev_hi), (next_lo, _) in zip(spans, spans[1:], strict=False):
        assert prev_hi < next_lo, f"overlapping EV shafts: {spans}"
    # ...and none of them collides with the stair column
    stair = _stair_x(m.config["building"]["corridor_length_m"])
    for lo, hi in spans:
        assert hi < stair - 0.4 or lo > stair + 0.4


def test_ev_shafts_offset_toward_their_side() -> None:
    """North bank draws left of its corridor position, south bank right, so the
    side is readable off the plot (the label carries N/S as well)."""
    m = _model()
    geom = _building_geom(m)
    b = m.config["building"]
    for ev, pos, side in zip(
        m.elevators, b["ev_corridor_positions_m"], b["ev_sides"], strict=True
    ):
        x = geom["ev_x"][ev.ev_id]
        if side == "north":
            assert x < pos, f"{ev.ev_id} (north) should draw left of {pos}"
        else:
            assert x > pos, f"{ev.ev_id} (south) should draw right of {pos}"
    # the two banks that share a position end up on opposite sides of it
    assert geom["ev_x"]["EV1"] < b["ev_corridor_positions_m"][0] < geom["ev_x"]["EV2"]


def test_cross_section_draws_basement_rows_in_rank_space() -> None:
    """§1.6: B1/B2 rows sit below 1F, on the RANK axis (labels skip 0).

    Inverted from the §1.3-era test that asserted no basement row existed —
    the v1 dock is still gone, but §1.6 added people-only levels, so the plot
    must extend downward again. Ranks are 0 (B1) and -1 (B2); the tick *labels*
    read B1/B2, which is what tells the two conventions apart.
    """
    m = _model()
    fig, ax = plt.subplots()
    draw_cross_section(m, ax)
    ticks = list(ax.get_yticks())
    labels = [t.get_text() for t in ax.get_yticklabels()]
    assert min(ticks) == -1                       # B2 rank, not label
    assert ax.get_ylim()[0] < -1.0
    assert labels[:3] == ["B2", "B1", "1"]
    assert labels[-1] == "10"
    # ground floor keeps rank == label, so nothing above ground moved
    assert ticks[labels.index("1")] == 1
    plt.close(fig)


def test_cross_section_has_no_basement_row_when_disabled() -> None:
    """n_basements=0 restores the pre-§1.6 axis exactly (regression path)."""
    m = _model(n_basements=0)
    fig, ax = plt.subplots()
    draw_cross_section(m, ax)
    assert ax.get_ylim()[0] > 0.0
    assert min(ax.get_yticks()) == 1
    assert not any("B" in t.get_text() for t in ax.get_yticklabels())
    plt.close(fig)


def test_cross_section_spans_v2_corridor_and_marks_charging() -> None:
    """복도 축 0~34 m (§1.5-1) and the 1F robot zone carries the charging
    marker (§1.5-4) because that zone doubles as the dock in v2."""
    m = _model()
    fig, ax = plt.subplots()
    draw_cross_section(m, ax)
    lo, hi = ax.get_xlim()
    assert lo <= 0.0 and hi >= m.config["building"]["corridor_length_m"]
    assert any(_CHARGING_MARK in t.get_text() for t in ax.texts), (
        "1F robot zone should be marked as a charging dock"
    )
    # every EV shaft is labelled with its id and the side it serves
    labels = {t.get_text() for t in ax.texts}
    assert {"EV1·N", "EV2·S", "EV3·N", "EV4·S"} <= labels
    plt.close(fig)


def test_kpi_panel_and_agent_tables_on_stepped_model() -> None:
    """S7.1 live components: the pure builders behind KPIPanel / RiderTable /
    ElevatorTable must work headless on a mid-run model."""
    m = _model()
    for _ in range(2500):
        if not m.running:
            break
        m.step()
        if m.agents_of(ExternalRiderAgent):
            break
    assert m.agents_of(ExternalRiderAgent)

    md = _kpi_panel_markdown(m)
    assert "라이브 KPI" in md and "delivered / K" in md and "| 지표 | 값 |" in md

    rider_rows = _rider_table_rows(m)
    assert rider_rows and {"ord_id", "state", "체류 [s]"} <= set(rider_rows[0])
    dwell = [r["체류 [s]"] for r in rider_rows]
    assert dwell == sorted(dwell, reverse=True)

    ev_rows = _elevator_table_rows(m)
    assert [r["EV"] for r in ev_rows] == ["EV1", "EV2", "EV3", "EV4"]
    assert all(r["dir"] in ("▲", "▼", "—") for r in ev_rows)


def test_build_kpi_report_after_completion() -> None:
    m = _model()
    m.run_to_completion()
    md, csv_text, stem = build_kpi_report(m)
    assert stem == "kpi_h0_K50_1_seed42"
    assert md.startswith("# H0 Baseline — KPI Report")
    assert "**scenario**: K50_1.json" in md
    assert csv_text.splitlines()[0] == "section,metric,value"


def test_app_builds_solara_page() -> None:
    import simulation.app as app

    assert app.page is not None
    # the model is built per browser session by make_model() — it must NOT be a
    # module-level object, or every solara kernel would share one model (see the
    # app module docstring: that is what killed the play loop after a refresh)
    assert not hasattr(app, "_model")
    m = app.make_model()
    assert m.K == 50
    # S7.1 parameter sidebar (rng_seed slider + scenario select) + dynamic
    # rider-pool switches (plan_rider_pool_dynamic.md S5) + the demand
    # profile select (etc/demand_mapping.md Stage 5). floor_profile MUST be
    # a model_params key: SolaraViz Reset reconstructs the model via
    # type(model)(**model_params), and without this key Reset would
    # silently fall back to v4 mapping mode and crash on scenarios lacking
    # a v4 mapping file.
    assert set(app.model_params) == {
        "rng_seed", "scenario_path", "floor_profile", "dynamic_pool", "return_leg"
    }
    assert app.model_params["dynamic_pool"]["type"] == "Checkbox"
    assert m.dynamic_pool is True
    assert app.model_params["floor_profile"]["type"] == "Select"
    assert app.model_params["floor_profile"]["values"] == [
        "uniform", "bottom_heavy", "top_heavy"
    ]
    assert m.floor_profile == "uniform"
    scenarios = app.model_params["scenario_path"]["values"]
    assert "data/data1/K50_1.json" in scenarios
    # all 39 data1 scenarios are offered now (floor/office no longer needs a
    # per-scenario v4 mapping file — the demand profile replaces it)
    assert len(scenarios) == 39
    for s in scenarios:
        assert (ROOT / s).exists()


# ------------------------------------------------- R8-g floor-demand panel


def test_floor_profiles_produce_different_demand() -> None:
    """The profile selector must actually move the floor histogram.

    Regression for a 2026-08-05 report that `uniform` and `bottom_heavy`
    "gave the same result". The model was fine — the report came from
    etc/building_10f_layout.html, a static geometry drawing with no demand
    concept at all, and from the app, where a changed Select only takes effect
    on Reset and nothing on screen showed which profile was live. Nothing had
    ever pinned "different profile => different demand", so this does.
    """
    import collections

    from simulation.model import BuildingHandoffModel

    hist = {}
    for prof in ("uniform", "bottom_heavy", "top_heavy"):
        m = BuildingHandoffModel(
            scenario_path="data/data1/K50_1.json", rng_seed=42,
            dynamic_pool=True, floor_profile=prof,
        )
        hist[prof] = collections.Counter(o.floor for o in m.orders)
        assert sum(hist[prof].values()) == m.K

    # same seed, same scenario, genuinely different floor demand
    assert hist["uniform"] != hist["bottom_heavy"] != hist["top_heavy"]
    low = range(2, 5)      # 2..4F carry weight 0.20 under bottom_heavy
    high = range(8, 11)    # 8..10F carry weight 0.20 under top_heavy
    assert (sum(hist["bottom_heavy"][f] for f in low)
            > sum(hist["bottom_heavy"][f] for f in high))
    assert (sum(hist["top_heavy"][f] for f in high)
            > sum(hist["top_heavy"][f] for f in low))


def test_floor_demand_panel_names_the_live_profile() -> None:
    """The panel must state which profile/policy is live and show both the
    design probabilities and the realised histogram — that is what makes a
    profile change observable without diffing result JSONs."""
    from simulation.model import BuildingHandoffModel
    from simulation.visualize import _floor_demand_markdown

    m = BuildingHandoffModel(
        scenario_path="data/data1/K50_1.json", rng_seed=42,
        dynamic_pool=True, floor_profile="bottom_heavy",
    )
    md = _floor_demand_markdown(m)
    assert "bottom_heavy" in md
    assert m.window_policy in md
    assert "Reset" in md                     # the trap that caused the report
    assert "0.200" in md                     # design probability of a low floor
    for f in range(2, m.n_floors + 1):
        assert f"| {f}F |" in md
