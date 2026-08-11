"""S2 — H0 baseline insight analysis over the descriptive track.

    .venv/bin/python -m analysis.h0_baseline_stats                 # tier=primary (default)
    .venv/bin/python -m analysis.h0_baseline_stats --tier extreme

⚠️ SUPERSEDED 2026-08-06 — use `analysis/h0v21_stats.py`.
============================================================================
This module asks **v1's questions**, and two of them are about the wrong shaft
now. Its robot columns (`ev2_ge12_frac`, `h1_ev2_trip_ratio`,
`f2_ev2_denial_exposure.png`) are keyed on **EV2**, which in the v2 building is
a *people-only* car a robot can never board — the shared cars are EV3/EV4
(`building.shared_ev_ids`). Re-running this on v2.1 data therefore produces
numbers that are not stale-but-directionally-right; they are measurements of a
shaft the robot never uses. It also reads only 2 of the 4 cars.

It still runs, and its non-robot output (T_e2e decomposition, prize bound,
c_a^2, variance decomposition) is sound, so it is kept as the v1-axis record.
**Do not quote its robot figures.** The v2.1 equivalents live in
`analysis/h0v21_insights/` (see that folder's README for the mapping).
============================================================================

Consumes the S0/S1 outputs of experiments/h0_descriptive.py
(results/h0_stats/{scenario_traits,h0_kpi_by_scenario}.csv + runs/*_s42.json.gz)
and produces the review folder analysis/h0_insights/ (tables/ + figures/) that
the S3 note (note_h0_demand_insights.md) cites.

Tiering (etc/plan_h0_revision.md §1.4, §3 R5): results/h0_stats/ is generated
by experiments/h0_descriptive.py for one tier at a time (its own --tier flag,
default 'primary'). This script's --tier must match whatever tier that run
used -- load_inputs() checks the 'tier' column scenario_traits.csv carries
(added by R5) and raises if it disagrees with the requested --tier, so a
stale or mismatched results/h0_stats/ directory fails loudly instead of
silently mislabeling a table. The verification battery is untouched by any
of this: it always covers all 39 scenarios. Organized around the five
questions of the 2026-08-03 plan:

  Q0  where does T_e2e go? (pre-building cook/pool/street vs in-building) —
      reuses analysis.vv_decomp.decompose_order verbatim (V5a float-exact
      integrity gate re-asserted here on every order).
  Q1  rider labor structure and the H1 "prize" upper bound
      (T_lobby - 60 s handoff, monetized w_R-weighted, x250 days per R0-7).
  Q2  elevator headroom: utilization vs wait knee, EV2 occupancy exposure
      (share of order-span ticks with >= 12 people aboard = H1 robot
      boarding-denial exposure under the "robot only if people <= 11" rule).
  Q3  floor/mode structure: stairs share, low-floor share, and the EV2
      vertical-trip demand H1 adds (2 robot rides per order, no batching
      per R0-4, vs today's *measured* EV2 person-boardings).
  Q4  demand time-structure: interarrival CV^2 amplification from the raw
      order process (S0) to the building-door arrival process (S1) — the
      c_a^2 input Phase B's G/G/c docking needs.

Plus a nested variance decomposition (between-K / within-K scenario / seed)
telling Phase D which KPIs are demand-*pattern* sensitive vs demand-*size*
sensitive.

Governance: diagnostic track, 3 seeds (42/7/2026); publication-grade numbers
remain Phase D's. No simulation here — pure post-processing of stored runs.
"""

from __future__ import annotations

import gzip
import json
import shutil
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from analysis.scenario_tiers import TIER_CHOICES, tier_of_k
from analysis.scenario_tiers import k_levels as _tier_k_levels
from analysis.vv_decomp import COMPONENTS, decompose_result

ROOT = Path(__file__).resolve().parent.parent
STATS = ROOT / "results" / "h0_stats"
RUNS = STATS / "runs"
OUT = ROOT / "analysis" / "h0_insights"
TABLES = OUT / "tables"
FIGS = OUT / "figures"

HANDOFF_SEC = 60.0          # H1 handoff mean (design freeze R0-3)
ANNUAL_DAYS = 250           # NPV convention: lunch peak x 250 business days (R0-7)
DEFAULT_TIER = "primary"    # analysis default (plan §1.4, §3 R5)
# Palette/axis domain. K500/K750/K1000 are outside the modelling
# corpus (사용자 확정 2026-08-03 2차) and can no longer appear in any input, but
# they stay listed here so the colour ramp assigned to K50..K300 is unchanged
# from the v1 figures. Iterate _present_k_order(), never this list, when
# indexing data.
K_ORDER = [50, 100, 200, 300, 500, 750, 1000]

# ---- palette (dataviz reference instance; validated 2026-08-03) -------------
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
GRID = "#e8e8e6"
S1_BLUE = "#2a78d6"
S2_ORANGE = "#eb6834"
S3_AQUA = "#1baf7a"
S4_YELLOW = "#eda100"
NEUTRAL = "#b9b8b3"
# sequential 7-step single-hue (blue, light->dark) for K magnitude
K_RAMP = ["#cfe0f5", "#a9c8ec", "#82afe3", "#5b95da", "#3579cf", "#2560ab", "#174682"]
K_COLOR = dict(zip(K_ORDER, K_RAMP, strict=True))


def _style_ax(ax) -> None:  # noqa: ANN001
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK2, labelsize=9)
    ax.grid(True, color=GRID, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)


def _fig(w: float = 7.2, h: float = 4.2, ncols: int = 1):  # noqa: ANN001
    fig, axes = plt.subplots(1, ncols, figsize=(w, h), facecolor=SURFACE)
    for ax in np.atleast_1d(axes):
        _style_ax(ax)
    return fig, axes


def _save(fig, name: str) -> None:  # noqa: ANN001
    fig.tight_layout()
    fig.savefig(FIGS / name, dpi=150, facecolor=SURFACE)
    plt.close(fig)
    print(f"[S2] figure {name}")


def _present_k_order(df: pd.DataFrame, col: str = "K") -> list[int]:
    """K_ORDER filtered down to the K levels actually present in `df`.

    Figure/table builders below were originally written for the old
    38-scenario "all" corpus (K in {50..1000}); the corpus is now 28 files
    with K <= 300 (사용자 확정 2026-08-03 2차) and a tier restriction narrows
    it further, so callers iterate this instead of the raw K_ORDER constant
    to avoid indexing/annotating K levels that are absent.
    """
    present = set(df[col].unique())
    return [k for k in K_ORDER if k in present]


# ------------------------------------------------------------------- loaders

def load_inputs(tier: str = DEFAULT_TIER) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load S0 traits + S1 KPI CSVs, gated against the requested `tier`.

    results/h0_stats/ is a single-tier snapshot produced by
    experiments/h0_descriptive.py --tier <tier>; this raises rather than
    silently analyzing a mismatched corpus (e.g. running --tier extreme
    here against a results/h0_stats/ that was actually generated for
    'primary'). Pre-R5 files lack the 'tier' column entirely -- those are
    accepted with a warning rather than a hard failure, since regenerating
    is a separate, expensive step (plan says wiring only, no regeneration).
    """
    traits = pd.read_csv(STATS / "scenario_traits.csv")
    kpi = pd.read_csv(STATS / "h0_kpi_by_scenario.csv")
    assert len(traits) > 0 and len(kpi) > 0, "empty S0/S1 inputs"
    if "tier" in traits.columns:
        found = set(traits["tier"].unique())
        if found != {tier}:
            raise ValueError(
                f"results/h0_stats/scenario_traits.csv was generated for tier(s) "
                f"{sorted(found)}, not the requested --tier {tier!r}. Regenerate via "
                f"`python -m experiments.h0_descriptive --tier {tier}` first."
            )
    else:
        print("[S2] WARNING: scenario_traits.csv has no 'tier' column "
              "(pre-R5 file) -- skipping tier consistency check")
    unknown = set(kpi["scenario"]) - set(traits["scenario"])
    assert not unknown, f"h0_kpi_by_scenario.csv has scenarios missing from traits: {sorted(unknown)}"
    return traits, kpi


def load_run_s42(stem: str) -> dict:
    with gzip.open(RUNS / f"{stem}_s42.json.gz", "rt", encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------- Q0: decomposition (seed 42)

def build_decomp(traits: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for stem in traits["scenario"]:
        result = load_run_s42(stem)
        comp_rows, fails = decompose_result(result)
        assert not fails, f"{stem}: decomp integrity failures: {fails[:3]}"
        df = pd.DataFrame(comp_rows)
        mean = df[COMPONENTS + ["t_e2e"]].mean()
        pre = mean["cook"] + mean["rider_wait"] + mean["street"]
        inb = mean["walk"] + mean["ev_wait"] + mean["ride"] + mean["service"]
        wage_sum = sum(r["w_R_krw_per_h"] for r in result["per_order"])
        k = int(result["kpi_summary"]["customer"]["n_orders"])
        rows.append({
            "scenario": stem,
            "K": k,
            "tier": tier_of_k(k),
            **{c: round(mean[c], 2) for c in COMPONENTS},
            "t_e2e_mean": round(mean["t_e2e"], 2),
            "pre_building_sec": round(pre, 2),
            "in_building_sec": round(inb, 2),
            "in_building_share": round(inb / mean["t_e2e"], 4),
            "wage_sum_krw_per_h": round(wage_sum, 1),
        })
    df = pd.DataFrame(rows).sort_values(["K", "scenario"])
    df.to_csv(TABLES / "decomp_by_scenario.csv", index=False)
    print(f"[S2] wrote tables/decomp_by_scenario.csv ({len(df)} rows)")
    return df


# ------------------------------------------------- per-scenario summary table

def build_summary(traits: pd.DataFrame, kpi: pd.DataFrame) -> pd.DataFrame:
    """Seed-averaged key KPIs per scenario, joined with S0 traits."""
    agg = kpi.groupby(["scenario", "K"], as_index=False).agg(
        t_e2e_mean_sec=("kpi.customer.t_e2e_mean_sec", "mean"),
        t_e2e_p95_sec=("kpi.customer.t_e2e_p95_sec", "mean"),
        sla_violations=("kpi.customer.n_sla_violations", "mean"),
        t_lobby_mean_sec=("kpi.rider.t_lobby_mean_sec", "mean"),
        t_lobby_p95_sec=("kpi.rider.t_lobby_p95_sec", "mean"),
        lobby_cost_krw=("kpi.rider.lobby_cost_total_krw", "mean"),
        w_ev_riders_sec=("kpi.building.w_ev_mean_riders_sec", "mean"),
        w_ev_all_sec=("kpi.building.w_ev_mean_all_sec", "mean"),
        ped_ev_wait_sec=("kpi.pedestrian.ev_wait_mean_sec", "mean"),
        # R8 §3.4: headline utilization unified on the delivery window. The
        # order-span figure agrees with it to the third decimal (the two spans
        # differ only by the 55~91 s from the last delivery to the last rider
        # exit), so this is a naming/provenance change, not a value change —
        # but the paper must quote one window, and that window is `delivery`.
        ev1_util_del=("kpi.elevator.EV1.utilization_delivery", "mean"),
        ev2_util_del=("kpi.elevator.EV2.utilization_delivery", "mean"),
        ev1_pax_del=("kpi.elevator.EV1.mean_passengers_delivery", "mean"),
        ev2_pax_del=("kpi.elevator.EV2.mean_passengers_delivery", "mean"),
        ev1_boardings=("kpi.elevator.EV1.n_boardings", "mean"),
        ev2_boardings=("kpi.elevator.EV2.n_boardings", "mean"),
        ev2_pax_mean=("drv_ev2_pax_mean", "mean"),
        ev2_pax_max=("drv_ev2_pax_max", "max"),
        ev2_ge12_frac=("drv_ev2_pax_ge12_frac", "mean"),
        stairs_share=("drv_stairs_share", "mean"),
        share_floor_le5=("drv_share_floor_le5", "mean"),
        riders_in_building_max=("drv_riders_in_building_max", "max"),
        arrival_ia_cv2=("drv_arrival_ia_cv2", "mean"),
        arrival_peak10=("drv_arrival_peak10_over_mean", "mean"),
        rider_wait_mean_sec=("drv_rider_wait_mean_sec", "mean"),
        fallback_n=("drv_fallback_n", "mean"),
    )
    df = traits.merge(agg, on=["scenario", "K"]).sort_values(["K", "scenario"])
    df.to_csv(TABLES / "scenario_summary.csv", index=False)
    print(f"[S2] wrote tables/scenario_summary.csv ({len(df)} rows x {df.shape[1]} cols)")
    return df


# ------------------------------------------------- variance decomposition

VD_KPIS = {
    "kpi.customer.t_e2e_mean_sec": "T_e2e mean",
    "kpi.rider.t_lobby_mean_sec": "T_lobby mean",
    "kpi.building.w_ev_mean_riders_sec": "W_EV riders",
    "kpi.pedestrian.ev_wait_mean_sec": "W_EV pedestrians",
    "drv_ev2_pax_ge12_frac": "EV2 pax>=12 frac",
    "drv_stairs_share": "Stairs share",
    "drv_arrival_ia_cv2": "Arrival c_a^2",
}


def variance_decomposition(kpi: pd.DataFrame) -> pd.DataFrame:
    """Nested sum-of-squares shares: between-K / within-K scenario / seed."""
    rows = []
    for col, label in VD_KPIS.items():
        d = kpi[["K", "scenario", col]].dropna()
        y = d[col].astype(float)
        grand = y.mean()
        k_means = d.groupby("K")[col].transform("mean")
        s_means = d.groupby("scenario")[col].transform("mean")
        ss_k = ((k_means - grand) ** 2).sum()
        ss_scen = ((s_means - k_means) ** 2).sum()
        ss_seed = ((y - s_means) ** 2).sum()
        total = ss_k + ss_scen + ss_seed
        rows.append({
            "kpi": label, "column": col,
            "share_between_K": round(ss_k / total, 4),
            "share_within_K_scenario": round(ss_scen / total, 4),
            "share_seed": round(ss_seed / total, 4),
        })
    df = pd.DataFrame(rows)
    df.to_csv(TABLES / "variance_decomposition.csv", index=False)
    print(f"[S2] wrote tables/variance_decomposition.csv ({len(df)} rows)")
    return df


# ------------------------------------------------- robot pre-diagnosis table

def robot_prediagnosis(summary: pd.DataFrame, decomp: pd.DataFrame) -> pd.DataFrame:
    d = summary.merge(
        decomp[["scenario", "wage_sum_krw_per_h", "in_building_share"]], on="scenario"
    )
    prize_sec = (d["t_lobby_mean_sec"] - HANDOFF_SEC).clip(lower=0)
    # KRW/day upper bound, exact per-order weighting: sum_i w_i*(t_i-60)/3600
    # = lobby_cost (= sum w_i*t_i/3600) - (60/3600)*sum w_i. The "upper bound"
    # is in the model (counter walk / robot wait not subtracted), not the math.
    prize_day = d["lobby_cost_krw"] - d["wage_sum_krw_per_h"] * HANDOFF_SEC / 3600.0
    df = pd.DataFrame({
        "scenario": d["scenario"], "K": d["K"],
        "t_lobby_mean_sec": d["t_lobby_mean_sec"].round(1),
        "h1_prize_ub_sec_per_order": prize_sec.round(1),
        "h1_prize_ub_krw_per_day": prize_day.round(0),
        "h1_prize_ub_krw_per_year": (prize_day * ANNUAL_DAYS).round(-3),
        "ev2_ge12_frac": d["ev2_ge12_frac"].round(4),
        "ev2_pax_max": d["ev2_pax_max"],
        "h1_robot_rides": 2 * d["K"],
        "ev2_boardings_now": d["ev2_boardings"].round(0),
        "h1_ev2_trip_ratio": (2 * d["K"] / d["ev2_boardings"]).round(2),
        "arrival_ia_cv2": d["arrival_ia_cv2"].round(2),
        "stairs_share": d["stairs_share"].round(3),
        "share_floor_le5": d["share_floor_le5"].round(3),
        "riders_in_building_max": d["riders_in_building_max"],
        "in_building_share": d["in_building_share"].round(3),
    }).sort_values(["K", "scenario"])
    df.to_csv(TABLES / "robot_prediagnosis.csv", index=False)
    print(f"[S2] wrote tables/robot_prediagnosis.csv ({len(df)} rows)")
    return df


# ------------------------------------------------------------------- figures

def _k_scatter_line(ax, summary, ycol, ylabel):  # noqa: ANN001
    k_order = _present_k_order(summary)
    for k in k_order:
        sub = summary[summary["K"] == k]
        ax.scatter(sub["K"], sub[ycol], s=42, color=NEUTRAL, alpha=0.85,
                   edgecolors=SURFACE, linewidths=1.2, zorder=3)
    means = summary.groupby("K")[ycol].mean().reindex(k_order)
    ax.plot(k_order, means.values, color=S1_BLUE, linewidth=2, zorder=4,
            marker="o", markersize=7, markeredgecolor=SURFACE, markeredgewidth=1.2)
    ax.set_xscale("log")
    ax.set_xticks(k_order)
    ax.set_xticklabels([str(k) for k in k_order])
    ax.minorticks_off()
    ax.set_xlabel("K (orders per lunch peak)", color=INK2, fontsize=9)
    ax.set_ylabel(ylabel, color=INK2, fontsize=9)


def fig1_scaling(summary: pd.DataFrame) -> None:
    fig, axes = _fig(9.6, 4.0, ncols=2)
    _k_scatter_line(axes[0], summary, "t_lobby_mean_sec", "T_lobby mean (s)")
    axes[0].set_title("Rider dwell scales gently, then jumps at K1000",
                      loc="left", fontsize=10, color=INK)
    _k_scatter_line(axes[1], summary, "w_ev_riders_sec", "Rider EV wait mean (s)")
    axes[1].set_title("EV wait: the same knee, x3 at K1000",
                      loc="left", fontsize=10, color=INK)
    for ax in axes:
        ax.annotate("gray dots = individual scenarios (3-seed mean)\nblue = K-group mean",
                    xy=(0.02, 0.98), xycoords="axes fraction", va="top",
                    fontsize=8, color=INK2)
    _save(fig, "f1_scaling_tlobby_wev.png")


def fig2_denial(summary: pd.DataFrame) -> None:
    fig, ax = _fig(7.0, 4.0)
    _k_scatter_line(ax, summary, "ev2_ge12_frac", "Share of order-span ticks, EV2 pax >= 12")
    ax.set_title("H1 robot boarding-denial exposure across the demand corpus",
                 loc="left", fontsize=10, color=INK)
    means = summary.groupby("K")["ev2_ge12_frac"].mean()
    # The v1 title claimed this was "a K>=500 phenomenon" and annotated K1000 /
    # K500 by name. Those levels are out of corpus for this study (사용자 확정
    # 2026-08-03 2차), so the claim can no longer be evidenced by this figure
    # and the hard-coded annotations would be dead code. Annotate the highest K
    # actually present instead.
    present = _present_k_order(summary)
    if present:
        k_top = present[-1]
        if k_top in means.index:
            ax.annotate(f"K{k_top}: {means[k_top]:.1%}", xy=(k_top, means[k_top]),
                        xytext=(-64, 6), textcoords="offset points",
                        fontsize=9, color=INK)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    _save(fig, "f2_ev2_denial_exposure.png")


def fig3_knee(summary: pd.DataFrame) -> None:
    fig, ax = _fig(7.0, 4.4)
    for k in _present_k_order(summary):
        sub = summary[summary["K"] == k]
        ax.scatter(sub["ev2_util_del"], sub["w_ev_riders_sec"], s=48,
                   color=K_COLOR[k], edgecolors=SURFACE, linewidths=1.2,
                   zorder=3, label=f"K{k}")
    ax.set_xlabel("EV2 utilization (delivery window; time in use, not load)",
                  color=INK2, fontsize=9)
    ax.set_ylabel("Rider EV wait mean (s)", color=INK2, fontsize=9)
    ax.set_title("The system sits on a queueing knee: util 94%->99%, wait x3 then x6+",
                 loc="left", fontsize=10, color=INK)
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    leg = ax.legend(loc="upper left", fontsize=8, frameon=False, ncols=2,
                    title="K (light -> dark)", title_fontsize=8)
    for t in leg.get_texts():
        t.set_color(INK2)
    leg.get_title().set_color(INK2)
    _save(fig, "f3_util_vs_wait_knee.png")


def fig4_ca2(summary: pd.DataFrame) -> None:
    fig, ax = _fig(7.0, 4.4)
    xlim = summary["ia_cv2"].max() * 1.15
    ylim = summary["arrival_ia_cv2"].max() * 1.08
    ax.plot([0, xlim], [0, xlim], color=NEUTRAL, linewidth=1.2, linestyle="--",
            zorder=2)
    ax.annotate("y = x (no amplification)", xy=(xlim * 0.66, xlim * 0.66),
                xytext=(8, -14), textcoords="offset points",
                fontsize=8, color=INK2)
    ax.set_xlim(0, xlim)
    ax.set_ylim(0, ylim)
    for k in _present_k_order(summary):
        sub = summary[summary["K"] == k]
        ax.scatter(sub["ia_cv2"], sub["arrival_ia_cv2"], s=48, color=K_COLOR[k],
                   edgecolors=SURFACE, linewidths=1.2, zorder=3, label=f"K{k}")
    ax.set_xlabel("Order-process interarrival CV$^2$ (raw scenario data)",
                  color=INK2, fontsize=9)
    ax.set_ylabel("Building-arrival interarrival CV$^2$ (simulated)",
                  color=INK2, fontsize=9)
    ax.set_title("Pool dispatch + street travel amplify burstiness 3-8x at K>=200",
                 loc="left", fontsize=10, color=INK)
    leg = ax.legend(loc="upper left", fontsize=8, frameon=False, ncols=2,
                    title="K (light -> dark)", title_fontsize=8)
    for t in leg.get_texts():
        t.set_color(INK2)
    leg.get_title().set_color(INK2)
    _save(fig, "f4_ca2_amplification.png")


def fig5_composition(decomp: pd.DataFrame) -> None:
    k_order = _present_k_order(decomp)
    by_k = decomp.groupby("K")[
        ["pre_building_sec", "in_building_sec", "walk", "ev_wait", "ride", "service"]
    ].mean().reindex(k_order)
    x = np.arange(len(k_order))
    fig, axes = _fig(9.6, 4.2, ncols=2)

    ax = axes[0]
    ax.bar(x, by_k["pre_building_sec"], width=0.62, color=NEUTRAL,
           edgecolor=SURFACE, linewidth=2, zorder=3, label="Pre-building (cook+pool+street)")
    ax.bar(x, by_k["in_building_sec"], bottom=by_k["pre_building_sec"], width=0.62,
           color=S1_BLUE, edgecolor=SURFACE, linewidth=2, zorder=3,
           label="In-building (walk+EV+ride+service)")
    for i, k in enumerate(k_order):
        share = by_k["in_building_sec"][k] / (by_k["pre_building_sec"][k] + by_k["in_building_sec"][k])
        ax.annotate(f"{share:.0%}",
                    xy=(i, by_k["pre_building_sec"][k] + by_k["in_building_sec"][k] / 2),
                    ha="center", va="center", fontsize=8, color=SURFACE)
    ax.set_ylim(0, 2000)
    ax.set_title("T_e2e is dominated by what happens before the building",
                 loc="left", fontsize=10, color=INK)
    ax.set_ylabel("Mean seconds per order", color=INK2, fontsize=9)
    leg = ax.legend(loc="upper left", fontsize=8, frameon=False)
    for t in leg.get_texts():
        t.set_color(INK2)

    ax = axes[1]
    bottom = np.zeros(len(k_order))
    for col, color, label in [
        ("walk", S1_BLUE, "walk"), ("ev_wait", S2_ORANGE, "EV wait"),
        ("ride", S3_AQUA, "ride"), ("service", S4_YELLOW, "service"),
    ]:
        vals = by_k[col].values
        ax.bar(x, vals, bottom=bottom, width=0.62, color=color,
               edgecolor=SURFACE, linewidth=2, zorder=3, label=label)
        for i, v in enumerate(vals):
            if v >= 18:
                ax.annotate(f"{v:.0f}", xy=(x[i], bottom[i] + v / 2), ha="center",
                            va="center", fontsize=7.5, color=SURFACE
                            if color in (S1_BLUE, S2_ORANGE) else INK)
        bottom += vals
    ax.set_title("In-building leg: EV wait is the only component that scales",
                 loc="left", fontsize=10, color=INK)
    ax.set_ylabel("Mean seconds per order (delivery leg)", color=INK2, fontsize=9)
    leg = ax.legend(loc="upper left", fontsize=8, frameon=False)
    for t in leg.get_texts():
        t.set_color(INK2)

    for ax in axes:
        ax.set_xticks(x)
        ax.set_xticklabels([f"K{k}" for k in k_order])
        ax.grid(axis="x", visible=False)
    _save(fig, "f5_te2e_composition.png")


def fig6_variance(vd: pd.DataFrame) -> None:
    fig, ax = _fig(7.6, 3.8)
    y = np.arange(len(vd))[::-1]
    left = np.zeros(len(vd))
    for col, color, label in [
        ("share_between_K", S1_BLUE, "between K (demand size)"),
        ("share_within_K_scenario", S2_ORANGE, "within K, between scenarios (pattern)"),
        ("share_seed", S3_AQUA, "between seeds (stochastic)"),
    ]:
        vals = vd[col].values
        ax.barh(y, vals, left=left, height=0.6, color=color,
                edgecolor=SURFACE, linewidth=2, zorder=3, label=label)
        for i, v in enumerate(vals):
            if v >= 0.06:
                ax.annotate(f"{v:.0%}", xy=(left[i] + v / 2, y[i]), ha="center",
                            va="center", fontsize=7.5,
                            color=SURFACE if color != S3_AQUA else INK)
        left += vals
    ax.set_yticks(y)
    ax.set_yticklabels(vd["kpi"], fontsize=9)
    ax.set_xlim(0, 1)
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    ax.set_title("What drives each KPI: demand size vs demand pattern vs noise",
                 loc="left", fontsize=10, color=INK)
    leg = ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.10), ncols=3,
                    fontsize=8, frameon=False)
    for t in leg.get_texts():
        t.set_color(INK2)
    ax.grid(axis="y", visible=False)
    _save(fig, "f6_variance_decomposition.png")


# ---------------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--tier", choices=TIER_CHOICES, default=DEFAULT_TIER,
        help=f"demand-scenario tier results/h0_stats/ was generated for "
             f"(default: {DEFAULT_TIER}). Must match the --tier used with "
             "experiments.h0_descriptive that produced the input CSVs -- "
             "see analysis/scenario_tiers.py.",
    )
    args = ap.parse_args(argv)
    tier = args.tier

    TABLES.mkdir(parents=True, exist_ok=True)
    FIGS.mkdir(parents=True, exist_ok=True)

    traits, kpi = load_inputs(tier)
    # self-contained copies of the S0/S1 inputs for future review
    shutil.copy2(STATS / "scenario_traits.csv", TABLES / "scenario_traits.csv")
    shutil.copy2(STATS / "h0_kpi_by_scenario.csv", TABLES / "h0_kpi_by_scenario.csv")

    decomp = build_decomp(traits)
    summary = build_summary(traits, kpi)
    vd = variance_decomposition(kpi)
    pre = robot_prediagnosis(summary, decomp)

    fig1_scaling(summary)
    fig2_denial(summary)
    fig3_knee(summary)
    fig4_ca2(summary)
    fig5_composition(decomp)
    fig6_variance(vd)

    # headline numbers for the S3 note
    print(f"\n[S2] headline aggregates (tier={tier}, K levels={_tier_k_levels(tier)})")
    if tier == "primary" and _tier_k_levels(tier)[0] == 50:
        print("  note: K50 has only 2 scenarios -- treat as a low-demand "
              "reference point, not on equal statistical footing with "
              "K100/K200 (plan §1.4).")
    for k in _present_k_order(summary):
        s = summary[summary["K"] == k]
        d = decomp[decomp["K"] == k]
        p = pre[pre["K"] == k]
        print(f"  K{k:<5} in_building_share={d['in_building_share'].mean():.3f} "
              f"t_lobby={s['t_lobby_mean_sec'].mean():6.1f}s "
              f"prize_ub={p['h1_prize_ub_sec_per_order'].mean():6.1f}s/ord "
              f"ev2_ge12={s['ev2_ge12_frac'].mean():6.3f} "
              f"trip_ratio={p['h1_ev2_trip_ratio'].mean():5.2f} "
              f"ca2 {s['ia_cv2'].mean():4.2f}->{s['arrival_ia_cv2'].mean():5.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
