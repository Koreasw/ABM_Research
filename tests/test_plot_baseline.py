"""S7 — analysis/plot_baseline.py (post-run charts, plan Part F).

The results JSON is the defined interface (same one S6 verifies), so these
tests drive the real file when present and assert six non-empty PNGs land in
the output directory. The per-chart draw functions are also exercised on a
tiny synthetic record set so a plotting regression is caught without a full
simulation run.
"""

from __future__ import annotations

import json

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402

from analysis.plot_baseline import (  # noqa: E402
    ROOT,
    _floor_reference,
    generate_figures,
    plot_ev_wait_dist,
    plot_t_lobby_by_type,
)

RESULTS_PATH = ROOT / "results" / "baseline_h0_K50_1.json"

needs_results = pytest.mark.skipif(
    not RESULTS_PATH.exists(),
    reason="baseline results JSON not generated yet (run simulation.run first)",
)


@needs_results
def test_generate_six_figures(tmp_path) -> None:
    written = generate_figures(RESULTS_PATH, tmp_path)
    assert len(written) == 6
    names = {p.name.split("__")[-1] for p in written}
    assert names == {
        "t_e2e_hist.png",
        "t_e2e_vs_lb.png",
        "t_lobby_by_type.png",
        "ev_timeseries.png",
        "ev_wait_dist.png",
        "floor_distribution.png",
    }
    for p in written:
        assert p.exists() and p.stat().st_size > 1000  # non-trivial PNG


@needs_results
def test_lower_bound_holds_in_scatter_data(tmp_path) -> None:
    """The T_e2e-vs-LB figure must never plot a point below the y=x line
    (that would contradict the S6 strict-lower-bound gate)."""
    from analysis.plot_baseline import _lower_bounds

    res = json.loads(RESULTS_PATH.read_text())
    lb = _lower_bounds(res)
    tick = res["config"]["simulation"].get("tick_sec", 1.0)
    for rec in res["per_order"]:
        assert rec["t_e2e_sec"] >= lb[rec["ord_id"]] - tick - 1e-6


def _synthetic_res() -> dict:
    per_order = [
        {"ord_id": i, "rider_type": rt, "t_lobby_sec": 200.0 + i,
         "ev_wait_up_sec": 10.0 + i, "ev_wait_down_sec": 15.0 + i}
        for i, rt in enumerate(["BIKE", "WALK", "CAR", "CAR"])
    ]
    # R8 §4-1: the headline is `utilization_delivery`; `utilization` stays as
    # the legacy-path fallback, so the stub carries both.
    return {
        "per_order": per_order,
        "kpi_summary": {"elevator": {
            "EV1": {"utilization": 0.68, "utilization_delivery": 0.71},
            "EV2": {"utilization": 0.64, "utilization_delivery": 0.67}}},
    }


def _synthetic_res_legacy() -> dict:
    """Same stub on the legacy window path: no delivery window exists there."""
    res = _synthetic_res()
    for ev in res["kpi_summary"]["elevator"].values():
        ev["utilization_delivery"] = None
    return res


def test_boxplot_and_wait_draw_without_error() -> None:
    for res in (_synthetic_res(), _synthetic_res_legacy()):
        for draw in (plot_t_lobby_by_type, plot_ev_wait_dist):
            fig, ax = plt.subplots()
            draw(res, ax)
            plt.close(fig)


def test_ev_wait_title_quotes_the_delivery_window() -> None:
    """The plot must name which window its utilization figure came from —
    a bare percentage is exactly what R8 §4-1/§4-2 set out to stop."""
    fig, ax = plt.subplots()
    plot_ev_wait_dist(_synthetic_res(), ax)
    title = ax.get_title()
    plt.close(fig)
    assert "delivery window" in title
    assert "71%" in title and "67%" in title, title

    fig, ax = plt.subplots()
    plot_ev_wait_dist(_synthetic_res_legacy(), ax)
    legacy_title = ax.get_title()
    plt.close(fig)
    assert "full window" in legacy_title
    assert "68%" in legacy_title and "64%" in legacy_title, legacy_title


def test_floor_reference_profile_mode() -> None:
    """floor_source == 'profile': reference = K * floor_probs (no file I/O),
    label names the active profile (etc/demand_mapping.md Stage 5)."""
    res = {
        "floor_source": "profile",
        "floor_profile": "bottom_heavy",
        "floor_probs": [0.2, 0.2, 0.2, 0.1, 0.1, 0.1, 1 / 30, 1 / 30, 1 / 30],
        "kpi_summary": {"customer": {"n_orders": 90}},
    }
    ref_counts, label = _floor_reference(res)
    assert label == "expected (profile: bottom_heavy)"
    assert np.allclose(ref_counts, 90 * np.array(res["floor_probs"]))
    # top-heavy shape sanity: bottom_heavy is front-loaded (2F..4F highest)
    assert ref_counts[0] > ref_counts[-1]


def test_floor_reference_mapping_mode() -> None:
    """floor_source != 'profile' (or absent, as in pre-Stage-4 legacy
    results): reference = ground-truth counts loaded from mapping_path."""
    mapping_path = ROOT / "data" / "floor_mapping" / "K50_1_floor_mapping_v4.json"
    mapping = json.loads(mapping_path.read_text())
    res = {
        "mapping_path": str(mapping_path),
        "config": {"building": {"n_floors": 10}},
    }
    ref_counts, label = _floor_reference(res)
    assert label == "v4 mapping (ground truth)"
    assert list(ref_counts) == mapping["floor_distribution_2_to_10"]
