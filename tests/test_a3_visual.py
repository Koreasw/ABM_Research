"""Step A3 — the render requirements `checklist_visual_h1.md` §0 depends on.

The H1 visual checklist is signed after A7, but it cannot be *executed* unless
the app draws robots, the counter, the fleet queue and the shared/dedicated
split. Those are R1~R6; R7 (the `rider_cls` substitution) was done in A2 and is
guarded in `test_a2_handoff.py`.

Every test here also carries the constraint that makes the already-signed H0
checklist survive A3: with an empty fleet the H0 figure and panel must be
exactly what they were. So each requirement is asserted twice — present in H1,
absent in H0.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402

from simulation.model import ROOT, BuildingHandoffModel, HandoffMode  # noqa: E402
from simulation.space import load_config  # noqa: E402
from simulation.visualize import (  # noqa: E402
    _ROBOT_BUCKET_COLORS,
    _elevator_table_rows,
    _kpi_panel_markdown,
    draw_cross_section,
    node_xy,
)

pytestmark = pytest.mark.vv


def _model(mode: HandoffMode):
    return BuildingHandoffModel(
        mode=mode,
        config=load_config(ROOT / "configs" / "baseline_10f.yaml"),
        scenario_path="data/data1/K50_1.json",
        rng_seed=42,
        dynamic_pool=True,
        floor_profile="uniform",
        floor_seed=42,
    )


def _stepped(mode: HandoffMode, until_busy: bool = True):
    """Step into the peak, until at least one robot has left the robot zone."""
    m = _model(mode)
    for _ in range(4000):
        if not m.running:
            break
        m.step()
        if until_busy and any(not rb.is_charging for rb in m.robots):
            break
    return m


@pytest.fixture(scope="module")
def hr_busy():
    m = _stepped(HandoffMode.H1_SYNC)
    assert any(not rb.is_charging for rb in m.robots), "no robot ever left home"
    return m


# --------------------------------------------------------- R1~R3: the marker


def test_robots_are_drawn_with_their_own_shape(hr_busy) -> None:
    """R1: a diamond marker — squares are already the office glyph."""
    fig, ax = plt.subplots(figsize=(9, 5))
    draw_cross_section(hr_busy, ax)
    diamonds = [ln for ln in ax.lines if ln.get_marker() == "D"]
    assert len(diamonds) == sum(
        1 for rb in hr_busy.robots if node_xy(hr_busy, rb.node) is not None
    )
    plt.close(fig)


def test_h0_figure_draws_no_robot_markers() -> None:
    """The H0 screen is signed; an empty fleet must leave it untouched."""
    m = _stepped(HandoffMode.H0_DIRECT, until_busy=False)
    fig, ax = plt.subplots(figsize=(9, 5))
    draw_cross_section(m, ax)
    assert not [ln for ln in ax.lines if ln.get_marker() == "D"]
    plt.close(fig)


def test_robot_labels_carry_bucket_and_soc(hr_busy) -> None:
    """R2 + R3 on one marker: the reporting bucket and the SOC percentage."""
    fig, ax = plt.subplots(figsize=(9, 5))
    draw_cross_section(hr_busy, ax)
    texts = [t.get_text() for t in ax.texts]
    labels = [t for t in texts if any(b in t for b in _ROBOT_BUCKET_COLORS)
              and t.endswith("%")]
    assert len(labels) == len(hr_busy.robots)
    for rb in hr_busy.robots:
        assert any(t.startswith(rb.report_bucket) for t in labels)
    plt.close(fig)


def test_every_reporting_bucket_has_a_color() -> None:
    """A new robot state must not fall through to an unlabelled black square."""
    from simulation.agents.robot import REPORT_BUCKETS

    assert set(_ROBOT_BUCKET_COLORS) == set(REPORT_BUCKETS)


def test_legend_lists_only_occupied_buckets(hr_busy) -> None:
    fig, ax = plt.subplots(figsize=(9, 5))
    draw_cross_section(hr_busy, ax)
    labels = {t.get_text() for t in ax.get_legend().get_texts()}
    occupied = {f"◆ {rb.report_bucket}" for rb in hr_busy.robots}
    assert occupied <= labels
    assert len([lb for lb in labels if lb.startswith("◆")]) == len(occupied)
    plt.close(fig)


# ------------------------------------------------------------ R4: the counter


def test_handoff_counter_is_a_distinct_lobby_point() -> None:
    """R4: it must be drawn, and NOT on top of the robot zone or the corridor.

    §2ⓐ asks the observer to judge that the handoff happens *at the counter*;
    that is unanswerable if the counter shares a pixel with its neighbours.
    """
    m = _model(HandoffMode.H1_SYNC)
    xy = node_xy(m, "lobby_handoff_counter")
    assert xy is not None
    others = [node_xy(m, n) for n in
              ("lobby_robot_pickup_zone", "lobby_direct_corridor", "lobby_entry")]
    assert all(abs(xy[0] - o[0]) > 1.0 for o in others)
    fig, ax = plt.subplots(figsize=(9, 5))
    draw_cross_section(m, ax)
    assert any(t.get_text() == "counter" for t in ax.texts)
    plt.close(fig)


# ------------------------------------------------- R5/R6: the sidebar panels


def test_panel_shows_the_robot_queue_and_fleet(hr_busy) -> None:
    """R5: the dispatch backlog is the saturation signal §4ⓕ watches."""
    md = _kpi_panel_markdown(hr_busy)
    assert "로봇 배차대기 주문 수" in md
    assert "로봇 가동/전체" in md
    assert "SOC 최저/현재평균 [%]" in md
    assert "T_building_order mean/p95 [s]" in md


def test_h0_panel_keeps_its_original_rows() -> None:
    m = _stepped(HandoffMode.H0_DIRECT, until_busy=False)
    md = _kpi_panel_markdown(m)
    assert "로봇" not in md
    assert "수단 EV / 계단" in md


def test_panel_and_table_label_shared_versus_dedicated(hr_busy) -> None:
    """R6: which car a robot may use is a property the observer must see."""
    md = _kpi_panel_markdown(hr_busy)
    for ev in hr_busy.elevators:
        tag = "공용" if ev.shared_with_robot else "전용"
        assert f"{ev.ev_id}[{tag}]" in md
    rows = {r["EV"]: r["구분"] for r in _elevator_table_rows(hr_busy)}
    assert rows == {
        ev.ev_id: ("공용" if ev.shared_with_robot else "전용")
        for ev in hr_busy.elevators
    }
