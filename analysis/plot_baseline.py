"""Post-run static charts for the H0 baseline — S7 (plan Part F).

    python -m analysis.plot_baseline results/baseline_h0_K50_1.json

Consumes a simulation.run results JSON and writes six PNGs to
results/figures/ (or --out): the end-to-end delivery-time distribution vs the
deadline and the strict lower bound, T_e2e against that bound, dwell time by
rider type, the elevator queue/position time series, the elevator-wait
distribution, and the delivered-vs-mapping floor distribution.

The strict lower bound reuses analysis.verify_baseline._strict_lower_bound so
this figure and the S6 check #4 gate cannot drift apart.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless: write files, never open a window
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from analysis.verify_baseline import ROOT, _strict_lower_bound  # noqa: E402
from simulation.space import (  # noqa: E402
    add_lobby_handoff_zones,
    build_from_config,
)
from simulation.vertical_transport import VerticalTransportModel  # noqa: E402

_TYPE_COLORS = {"BIKE": "#2ca02c", "WALK": "#1f77b4", "CAR": "#d62728"}


def _lower_bounds(res: dict) -> dict[int, float]:
    """LB_strict per ord_id, computed with the same helper the S6 gate uses."""
    cfg = res["config"]
    g = add_lobby_handoff_zones(
        build_from_config(cfg),
        n_locker_compartments=cfg["locker"]["n_compartments"],
    )
    vt = VerticalTransportModel.from_config(cfg)
    walk_speed = cfg["rider_process"]["walk_speed_mps"]
    return {
        rec["ord_id"]: _strict_lower_bound(rec, g, vt, walk_speed)
        for rec in res["per_order"]
    }


# --------------------------------------------------------------------- charts


def plot_t_e2e_hist(res: dict, lb: dict, ax) -> None:
    """1. T_e2e histogram with median, mean deadline slack, and LB markers."""
    t_e2e = np.array([r["t_e2e_sec"] for r in res["per_order"]]) / 60.0
    deadlines = np.array(
        [(r["deadline_abs_sec"] - r["ord_time_abs_sec"]) for r in res["per_order"]]
    ) / 60.0
    lb_arr = np.array([lb[r["ord_id"]] for r in res["per_order"]]) / 60.0
    n_viol = sum(1 for r in res["per_order"] if r["sla_violation"])

    ax.hist(t_e2e, bins=20, color="#4c72b0", edgecolor="white", alpha=0.85)
    ax.axvline(np.median(t_e2e), color="black", ls="-", lw=1.5,
               label=f"median {np.median(t_e2e):.1f} min")
    ax.axvline(np.mean(deadlines), color="#d62728", ls="--", lw=1.5,
               label=f"mean deadline {np.mean(deadlines):.1f} min")
    ax.axvline(np.mean(lb_arr), color="#2ca02c", ls=":", lw=1.5,
               label=f"mean strict LB {np.mean(lb_arr):.1f} min")
    ax.set_xlabel("end-to-end delivery time $T_{e2e}$ (min)")
    ax.set_ylabel("orders")
    ax.set_title(f"$T_{{e2e}}$ distribution  (SLA violations: {n_viol}/{len(t_e2e)})")
    ax.legend(fontsize=8)


def plot_t_e2e_vs_lb(res: dict, lb: dict, ax) -> None:
    """2. T_e2e vs strict lower bound scatter (all points above the y=x line)."""
    for rt, color in _TYPE_COLORS.items():
        pts = [(lb[r["ord_id"]] / 60.0, r["t_e2e_sec"] / 60.0)
               for r in res["per_order"] if r["rider_type"] == rt]
        if pts:
            xs, ys = zip(*pts)
            ax.scatter(xs, ys, s=28, color=color, alpha=0.8, label=rt,
                       edgecolor="white", linewidth=0.5)
    lo = 0.0
    hi = max(max(r["t_e2e_sec"] for r in res["per_order"]),
             max(lb.values())) / 60.0 * 1.05
    ax.plot([lo, hi], [lo, hi], color="0.5", ls="--", lw=1,
            label="$T_{e2e}=$ LB (physical floor)")
    ax.set_xlim(lo, hi)
    ax.set_ylim(lo, hi)
    ax.set_xlabel("strict lower bound (min)")
    ax.set_ylabel("observed $T_{e2e}$ (min)")
    ax.set_title("$T_{e2e}$ vs strict lower bound")
    ax.legend(fontsize=8)


def plot_t_lobby_by_type(res: dict, ax) -> None:
    """3. Building dwell time (T_lobby) boxplot, split by rider type."""
    order = ["BIKE", "WALK", "CAR"]
    data, labels, colors = [], [], []
    for rt in order:
        vals = [r["t_lobby_sec"] for r in res["per_order"] if r["rider_type"] == rt]
        if vals:
            data.append(vals)
            labels.append(f"{rt}\n(n={len(vals)})")
            colors.append(_TYPE_COLORS[rt])
    bp = ax.boxplot(data, tick_labels=labels, patch_artist=True, widths=0.5)
    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.6)
    for median in bp["medians"]:
        median.set_color("black")
    ax.set_ylabel("building dwell $T_{lobby}$ (s)")
    ax.set_title("Rider dwell time by type")


def plot_ev_timeseries(res: dict, ax) -> None:
    """4. EV queue length and car position over time (twin axes)."""
    mv = res["model_vars"]
    t = (np.array(mv["clock_sec"]) - mv["clock_sec"][0]) / 60.0
    ax.plot(t, mv["ev1_queue"], color="#ff7f0e", lw=1, label="EV1 queue")
    ax.plot(t, mv["ev2_queue"], color="#d62728", lw=1, label="EV2 queue")
    ax.set_xlabel("elapsed time (min)")
    ax.set_ylabel("hall-call queue length (persons)")
    ax.set_title("Elevator queue & car position")
    ax.legend(loc="upper left", fontsize=8)

    ax2 = ax.twinx()
    ax2.plot(t, mv["ev1_floor"], color="#1f77b4", lw=0.6, alpha=0.5, label="EV1 floor")
    ax2.plot(t, mv["ev2_floor"], color="#4c72b0", lw=0.6, alpha=0.5, label="EV2 floor")
    ax2.set_ylabel("car position (floor)")
    ax2.legend(loc="upper right", fontsize=8)


def plot_ev_wait_dist(res: dict, ax) -> None:
    """5. Rider elevator-wait distribution (up vs down legs)."""
    up = [r["ev_wait_up_sec"] for r in res["per_order"]
          if r["ev_wait_up_sec"] is not None]
    down = [r["ev_wait_down_sec"] for r in res["per_order"]
            if r["ev_wait_down_sec"] is not None]
    kpi_ev = res["kpi_summary"]["elevator"]
    hi = max(up + down + [1.0])
    bins = np.linspace(0, hi, 16)
    ax.hist(up, bins=bins, color="#2ca02c", alpha=0.55,
            label=f"up (n={len(up)}, mean {np.mean(up):.1f}s)")
    ax.hist(down, bins=bins, color="#9467bd", alpha=0.55,
            label=f"down (n={len(down)}, mean {np.mean(down):.1f}s)")
    ax.set_xlabel("elevator wait $W_{EV}$ (s)")
    ax.set_ylabel("rider legs")
    # R8 §4-1: headline utilization = delivery window; fall back to the
    # full-window field on the legacy path, where the delivery window is absent.
    util = ", ".join(
        f"{k} util {(v['utilization_delivery'] if v.get('utilization_delivery') is not None else v['utilization']):.0%}"
        for k, v in kpi_ev.items()
    )
    span = ("delivery window"
            if any(v.get("utilization_delivery") is not None for v in kpi_ev.values())
            else "full window")
    ax.set_title(f"Rider elevator wait  ({util}; {span})")
    ax.legend(fontsize=8)


def _floor_reference(res: dict) -> tuple[np.ndarray, str]:
    """Reference floor counts + legend label for plot_floor_distribution.

    Profile runs (`floor_source == "profile"`, Stage 3+ paper track) carry no
    mapping file (`mapping_path` is None — KNOWN CRASH #2 if opened blindly);
    the reference is the profile's expected count K * probs, already
    normalized by FloorDemandModel and stored verbatim in `floor_probs` so
    this does not re-normalize. Mapping runs (frozen v4/v5 regression path,
    or legacy results predating the `floor_source` provenance key) load the
    ground-truth mapping file's floor counts, as before.
    """
    if res.get("floor_source") == "profile":
        K = res["kpi_summary"]["customer"]["n_orders"]
        ref_counts = K * np.array(res["floor_probs"])
        label = f"expected (profile: {res['floor_profile']})"
        return ref_counts, label

    mapping_path = Path(res["mapping_path"])
    if not mapping_path.is_absolute():
        mapping_path = ROOT / mapping_path
    mapping = json.loads(mapping_path.read_text())
    n_floors = res["config"]["building"]["n_floors"]
    floors = list(range(2, n_floors + 1))
    mapping_counts = mapping.get("floor_distribution_2_to_10")
    if mapping_counts is None:
        mapping_counts = [
            sum(1 for o in mapping["orders"] if o["floor"] == f) for f in floors
        ]
    return np.array(mapping_counts), "v4 mapping (ground truth)"


def plot_floor_distribution(res: dict, ref_counts, ref_label: str, ax) -> None:
    """6. Delivered-order floor distribution vs the reference (mapping ground
    truth, or profile expected share — see _floor_reference)."""
    n_floors = res["config"]["building"]["n_floors"]
    floors = list(range(2, n_floors + 1))
    delivered = np.array(
        [sum(1 for r in res["per_order"] if r["floor"] == f) for f in floors]
    )

    x = np.arange(len(floors))
    ax.bar(x - 0.2, ref_counts, width=0.4, color="0.6", label=ref_label)
    ax.bar(x + 0.2, delivered, width=0.4, color="#4c72b0",
           label="delivered in sim")
    ax.set_xticks(x)
    ax.set_xticklabels(floors)
    ax.set_xlabel("floor")
    ax.set_ylabel("orders")
    ax.set_title("Order floor distribution: reference vs delivered")
    ax.legend(fontsize=8)


# ------------------------------------------------------------------------ CLI


def generate_figures(results_path: Path, out_dir: Path) -> list[Path]:
    """Render all six figures; returns the written PNG paths."""
    res = json.loads(results_path.read_text())
    lb = _lower_bounds(res)
    ref_counts, ref_label = _floor_reference(res)

    out_dir.mkdir(parents=True, exist_ok=True)
    stem = results_path.stem
    written: list[Path] = []

    specs = [
        ("t_e2e_hist", lambda ax: plot_t_e2e_hist(res, lb, ax)),
        ("t_e2e_vs_lb", lambda ax: plot_t_e2e_vs_lb(res, lb, ax)),
        ("t_lobby_by_type", lambda ax: plot_t_lobby_by_type(res, ax)),
        ("ev_timeseries", lambda ax: plot_ev_timeseries(res, ax)),
        ("ev_wait_dist", lambda ax: plot_ev_wait_dist(res, ax)),
        ("floor_distribution",
         lambda ax: plot_floor_distribution(res, ref_counts, ref_label, ax)),
    ]
    for name, draw in specs:
        fig, ax = plt.subplots(figsize=(7, 4.5))
        draw(ax)
        fig.tight_layout()
        path = out_dir / f"{stem}__{name}.png"
        fig.savefig(path, dpi=130)
        plt.close(fig)
        written.append(path)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="H0 baseline post-run charts (S7)")
    parser.add_argument("results", help="results JSON from simulation.run")
    parser.add_argument("--out", default="results/figures", help="output directory")
    args = parser.parse_args(argv)

    results_path = Path(args.results)
    if not results_path.is_absolute():
        results_path = ROOT / results_path
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir

    written = generate_figures(results_path, out_dir)
    print(f"plot_baseline: {len(written)} figures -> {out_dir}")
    for p in written:
        print(f"  {p.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
