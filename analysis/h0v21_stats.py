"""T1~T3 — H0 v2.1 insight analysis (agent KPIs / demand / H1-H3 direction).

    .venv/bin/python -m analysis.h0v21_stats

Consumes the descriptive-track outputs of `experiments/h0_descriptive.py`
(`results/h0_stats/`, run with `--tier all`) and writes the self-contained
review folder `analysis/h0v21_insights/` (tables/ + figures/) that the note
`note_h0v21_insights.md` cites.

Why this module exists next to `analysis/h0_baseline_stats.py`
--------------------------------------------------------------
That module is the **v1-axis** analysis (2026-08-03, 2-EV building). Re-running
it on v2.1 data produces numbers, but they answer v1's questions: its robot
columns are keyed on **EV2**, which in the v2 building is a *people-only* car a
robot can never board (`building.shared_ev_ids` = EV3/EV4). Its output is
therefore not stale-but-directionally-right, it is about the wrong shaft. This
module re-derives the whole analysis on the v2.1 axes and leaves the v1 one
untouched as history.

Three questions, matching the 2026-08-06 request:

  T1  per-agent KPIs — customer / rider / elevator / pedestrian / building,
      each broken down the way that agent class is actually heterogeneous
      (elevator: per car and dedicated-vs-shared; rider: by hire type and by
      floor; pedestrian: by which car it waited for). The robot class is
      empty in H0 by construction; its slots are reported as the zero
      baseline the H1 comparison subtracts from.
  T2  demand — K in {50, 100, 200, 300} scaling, the knee, how much of the
      spread is demand *size* vs demand *pattern* vs seed.
  T3  H1/H2/H3 extension direction — the quantities the phase plans marked
      "미재산출 / v2 실측으로 재산출" and that are measurable from H0 alone:
      the H1 prize bound, shared-car boarding-denial exposure, the vertical
      trip load a robot fleet would add, the G/G/c arrival c_a^2 and counter
      queue bound for H2, and per-floor locker occupancy for H3.

Governance
----------
* **Diagnostic track, 3 seeds (42/7/2026).** Publication-grade numbers remain
  Phase D's (30 seed + CRN). Nothing here goes into the paper as a headline
  figure without being re-run there.
* **These are v2.1 numbers** (post-R8 `window_policy: delivery`). They are NOT
  comparable order-by-order with `archive/h0_v2_frozen/` — changing the warm-up
  length re-aligns the pedestrian RNG, so the same seed is a different
  realization (HANDOFF_v2 §3.8). Compare distributions, never runs.
* No simulation here: pure post-processing of stored runs. The T_e2e
  decomposition reuses `analysis.vv_decomp.decompose_order` verbatim, and its
  float-exact integrity gate is re-asserted on every order of all 84 runs.
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

from analysis.scenario_tiers import k_levels as _tier_k_levels
from analysis.vv_decomp import COMPONENTS, decompose_result

ROOT = Path(__file__).resolve().parent.parent
STATS = ROOT / "results" / "h0_stats"
RUNS = STATS / "runs"
OUT = ROOT / "analysis" / "h0v21_insights"
TABLES = OUT / "tables"
FIGS = OUT / "figures"

SEEDS = (42, 7, 2026)
HANDOFF_SEC = 60.0          # H1 handoff mean (design freeze R0-3)
ROBOT_DROP_SEC = 30.0       # H1 door-side delivery (design freeze, phase_A §0)
ANNUAL_DAYS = 250           # NPV convention: lunch peak x 250 business days (R0-7)
ROBOT_PAX_LIMIT = 11        # a robot may board only while people aboard <= 11
# Residence times swept for H3 locker occupancy. H0 has no customer-pickup
# process, so this is a *parameter sweep*, not a measurement: the demand side
# (when parcels land on a floor) is measured, the pickup side is assumed.
LOCKER_TAU_MIN = (5, 10, 15, 30)

# Figure labels are Korean (this is a Korean-language research track), and
# matplotlib's default DejaVu Sans has no Hangul — without this every label
# renders as tofu boxes and the figure silently becomes unreadable.
plt.rcParams["font.family"] = ["Noto Sans CJK KR", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

# ---- palette (dataviz reference instance; re-validated 2026-08-06) ----------
# node scripts/validate_palette.js "#2a78d6,#eb6834,#1baf7a,#eda100" --mode light
#   --surface "#fcfcfb"  ->  ALL CHECKS PASS (contrast WARN on aqua/yellow,
#   relieved by direct labels + the tables/ CSV beside every figure).
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
GRID = "#e8e8e6"
S1_BLUE = "#2a78d6"
S2_ORANGE = "#eb6834"
S3_AQUA = "#1baf7a"
S4_YELLOW = "#eda100"
NEUTRAL = "#b9b8b3"
CATEGORICAL = [S1_BLUE, S2_ORANGE, S3_AQUA, S4_YELLOW]
# sequential single-hue ramp for K magnitude (light -> dark); 4 corpus levels
K_RAMP = ["#cfe0f5", "#82afe3", "#3579cf", "#174682"]
# T_e2e components, chronological: outside-building stages in warm hues, the
# four in-building stages in the cool hue the paper uses for "what the building
# controls" -- the whole point of the figure is that the cool block is small.
COMPONENT_COLORS = {
    "cook": "#8c6a4f", "rider_wait": "#c9b7a5", "street": S2_ORANGE,
    "walk": "#cfe0f5", "ev_wait": "#82afe3", "ride": "#3579cf", "service": "#174682",
}
IN_BUILDING = ("walk", "ev_wait", "ride", "service")


# ============================================================ input loading

def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    """S0 traits + S1 per-run KPI rows, with the provenance guards that matter.

    Fails loudly rather than silently analysing a half-regenerated directory:
    the corpus must be the full 28 scenarios x 3 seeds, and every row must come
    from the R8 `delivery` window policy (a `legacy_margin` row would carry a
    3,600 s warm-up head in its rate KPIs and quietly drag the K-means down).
    """
    traits = pd.read_csv(STATS / "scenario_traits.csv")
    kpi = pd.read_csv(STATS / "h0_kpi_by_scenario.csv")

    n_scen = traits["scenario"].nunique()
    if n_scen != 28:
        raise SystemExit(
            f"expected the 28-scenario corpus, found {n_scen} scenarios in "
            f"{STATS}. Re-run: python -m experiments.h0_descriptive --tier all"
        )
    if len(kpi) != 28 * len(SEEDS):
        raise SystemExit(
            f"expected {28 * len(SEEDS)} runs (28 scenarios x {len(SEEDS)} "
            f"seeds), found {len(kpi)}. Re-run with --tier all."
        )
    policies = set(kpi["kpi.simulation.window_policy"].unique())
    if policies != {"delivery"}:
        raise SystemExit(
            f"window_policy must be 'delivery' for every row (R8 paper track); "
            f"found {sorted(policies)}"
        )
    reasons = set(kpi["kpi.simulation.termination_reason"].unique())
    if reasons != {"delivery_complete"}:
        raise SystemExit(
            f"every run must terminate as 'delivery_complete'; found "
            f"{sorted(reasons)} — a `cap` trip means the run did not finish"
        )
    missing = set(_tier_k_levels("all")) - set(kpi["K"].unique())
    if missing:
        raise SystemExit(f"corpus K levels missing from the data: {sorted(missing)}")
    print(f"[in] {len(kpi)} runs x {kpi.shape[1]} cols, "
          f"K={sorted(kpi['K'].unique())}, policy=delivery")
    return traits, kpi


def _k_order(df: pd.DataFrame) -> list[int]:
    return sorted(df["K"].unique())


def _ramp(k_list: list[int]) -> dict[int, str]:
    return {k: K_RAMP[i % len(K_RAMP)] for i, k in enumerate(k_list)}


# ============================================== elevator long-format reshape

def ev_long(kpi: pd.DataFrame) -> pd.DataFrame:
    """One row per (scenario, K, seed, car) — the shape every EV question wants.

    The wide CSV has one column per car per metric, so any question of the form
    "dedicated vs shared" turns into hand-written column arithmetic that breaks
    the moment the fleet changes. The fleet is discovered from the column names
    and the shared set from `drv_shared_ev_ids`, so this survives R2's N-EV
    generalisation.
    """
    ev_ids = sorted({c.split(".")[2] for c in kpi.columns if c.startswith("kpi.elevator.")})
    shared = set(str(kpi["drv_shared_ev_ids"].iloc[0]).split("|"))
    rows = []
    for ev in ev_ids:
        p, lo = f"kpi.elevator.{ev}.", ev.lower()
        rows.append(pd.DataFrame({
            "scenario": kpi["scenario"], "K": kpi["K"], "seed": kpi["seed"],
            "ev_id": ev,
            "role": np.where(ev in shared, "shared", "dedicated"),
            "util_delivery": kpi[p + "utilization_delivery"],
            "util_full": kpi[p + "utilization"],
            "mean_pax_delivery": kpi[p + "mean_passengers_delivery"],
            "n_boardings": kpi[p + "n_boardings"],
            "n_boardings_rider": kpi[p + "n_boardings_by_kind.rider"],
            "n_boardings_ped": kpi[p + "n_boardings_by_kind.pedestrian"],
            "w_ev_mean_sec": kpi[p + "w_ev_mean_sec"],
            "w_ev_p95_sec": kpi[p + "w_ev_p95_sec"],
            "w_ev_rider_sec": kpi[p + "w_ev_mean_by_kind_sec.rider"],
            "w_ev_ped_sec": kpi[p + "w_ev_mean_by_kind_sec.pedestrian"],
            "w_ev_ped_p95_sec": kpi[p + "w_ev_p95_by_kind_sec.pedestrian"],
            "capacity_violations": kpi[p + "capacity_violations"],
            "pax_mean_series": kpi[f"drv_{lo}_pax_mean"],
            "pax_max_series": kpi[f"drv_{lo}_pax_max"],
            "pax_ge12_frac": kpi[f"drv_{lo}_pax_ge12_frac"],
            "queue_mean": kpi[f"drv_{lo}_queue_mean"],
            "queue_max": kpi[f"drv_{lo}_queue_max"],
        }))
    return pd.concat(rows, ignore_index=True).sort_values(
        ["K", "scenario", "seed", "ev_id"])


# ================================================ per-order pass (all 84 runs)

def _load_run(stem: str, seed: int) -> dict:
    with gzip.open(RUNS / f"{stem}_s{seed}.json.gz", "rt", encoding="utf-8") as f:
        return json.load(f)


def per_order_pass(kpi: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """One sweep over all 84 stored runs; everything per-order comes from here.

    Returns four long frames: `decomp` (T_e2e components), `floor` (per delivery
    floor), `hire` (per rider hire type), `locker` (per floor x residence time).
    Doing this in one pass matters only for wall time; the reason it is one
    *function* is that all four must be derived from the same run set, or a
    reader comparing two tables is comparing two different corpora.
    """
    stems = sorted(kpi["scenario"].unique())
    dec_rows, floor_rows, hire_rows, locker_rows = [], [], [], []
    integrity_failures: list[str] = []
    n_orders = 0

    for stem in stems:
        for seed in SEEDS:
            res = _load_run(stem, seed)
            K = res["kpi_summary"]["customer"]["n_orders"]
            per_order = res["per_order"]
            n_orders += len(per_order)

            # ---- T_e2e decomposition (V5a integrity gate re-asserted) -------
            rows, fails = decompose_result(res)
            integrity_failures.extend(f"{stem} s{seed}: {m}" for m in fails)
            d = pd.DataFrame(rows)
            rec = {"scenario": stem, "K": K, "seed": seed,
                   "t_e2e_mean": d["t_e2e"].mean()}
            for c in COMPONENTS:
                rec[c] = d[c].mean()
            rec["in_building"] = sum(rec[c] for c in IN_BUILDING)
            rec["in_building_share"] = rec["in_building"] / rec["t_e2e_mean"]
            dec_rows.append(rec)

            po = pd.DataFrame(per_order)
            po["is_stairs"] = po["vertical_mode"] == "stairs"
            # w_R sum is the exact monetisation weight for the H1 prize bound
            # (see h1_prize_bounds): sum_i w_i (t_i - 60)/3600 needs sum_i w_i.
            hire_rows.extend(
                {"scenario": stem, "K": K, "seed": seed, "rider_type": t,
                 "n": len(g), "share": len(g) / len(po),
                 "t_lobby_mean_sec": g["t_lobby_sec"].mean(),
                 "t_e2e_mean_sec": g["t_e2e_sec"].mean(),
                 "ev_wait_up_mean_sec": g["ev_wait_up_sec"].mean(),
                 "stairs_share": g["is_stairs"].mean(),
                 "walked_m_mean": g["walked_m"].mean(),
                 "w_R_krw_per_h": g["w_R_krw_per_h"].mean(),
                 "dist_m_mean": g["dist_m"].mean()}
                for t, g in po.groupby("rider_type")
            )
            floor_rows.extend(
                {"scenario": stem, "K": K, "seed": seed, "floor": int(f),
                 "n": len(g), "share": len(g) / len(po),
                 "t_e2e_mean_sec": g["t_e2e_sec"].mean(),
                 "t_lobby_mean_sec": g["t_lobby_sec"].mean(),
                 "ev_wait_up_mean_sec": g["ev_wait_up_sec"].mean(),
                 "stairs_share": g["is_stairs"].mean(),
                 "walked_m_mean": g["walked_m"].mean()}
                for f, g in po.groupby("floor")
            )

            # ---- H3: per-floor locker occupancy under a residence time -------
            for f, g in po.groupby("floor"):
                t = np.sort(g["delivered_at_sec"].dropna().to_numpy(float))
                for tau_min in LOCKER_TAU_MIN:
                    tau = tau_min * 60.0
                    # occupancy just after each delivery = deliveries landing in
                    # (t_i - tau, t_i]; the max over i is the bank size needed.
                    occ = int(np.max(
                        np.searchsorted(t, t, "right") - np.searchsorted(t, t - tau, "right")
                    )) if t.size else 0
                    locker_rows.append({"scenario": stem, "K": K, "seed": seed,
                                        "floor": int(f), "tau_min": tau_min,
                                        "peak_occupancy": occ, "n_deliveries": int(t.size)})

    if integrity_failures:
        raise SystemExit(
            "T_e2e decomposition integrity gate FAILED "
            f"({len(integrity_failures)} orders):\n  "
            + "\n  ".join(integrity_failures[:10])
        )
    print(f"[T0] decomposition integrity PASS on {n_orders} orders / "
          f"{len(stems) * len(SEEDS)} runs")
    return {
        "decomp": pd.DataFrame(dec_rows),
        "floor": pd.DataFrame(floor_rows),
        "hire": pd.DataFrame(hire_rows),
        "locker": pd.DataFrame(locker_rows),
    }


# ==================================================== T1 — per-agent KPIs

# (column in the wide CSV, output name) per agent class. Kept as data so the
# by-K and by-scenario tables cannot drift apart.
AGENT_KPI_SPEC: dict[str, list[tuple[str, str]]] = {
    "customer": [
        ("kpi.customer.n_orders", "n_orders"),
        ("kpi.customer.n_delivered", "n_delivered"),
        ("kpi.customer.t_e2e_mean_sec", "t_e2e_mean_sec"),
        ("kpi.customer.t_e2e_p95_sec", "t_e2e_p95_sec"),
        ("kpi.customer.n_sla_violations", "n_sla_violations"),
        ("kpi.customer.sla_violation_rate", "sla_violation_rate"),
    ],
    "rider": [
        ("kpi.rider.n_exited", "n_exited"),
        ("kpi.rider.t_lobby_mean_sec", "t_lobby_mean_sec"),
        ("kpi.rider.t_lobby_p95_sec", "t_lobby_p95_sec"),
        ("kpi.rider.ev_wait_up_mean_sec", "ev_wait_up_mean_sec"),
        ("kpi.rider.ev_wait_down_mean_sec", "ev_wait_down_mean_sec"),
        ("drv_stairs_share", "stairs_share"),
        ("drv_walked_m_mean", "walked_m_mean"),
        ("drv_rider_wait_mean_sec", "pool_wait_mean_sec"),
        ("drv_rider_wait_max_sec", "pool_wait_max_sec"),
        ("drv_riders_in_building_mean", "in_building_mean"),
        ("drv_riders_in_building_max", "in_building_max"),
        ("drv_riders_waiting_ev_mean", "waiting_ev_mean"),
        ("drv_riders_waiting_ev_max", "waiting_ev_max"),
        ("kpi.rider.lobby_cost_total_krw", "lobby_cost_total_krw"),
    ],
    "pedestrian": [
        ("kpi.pedestrian.n_spawned", "n_spawned"),
        ("kpi.pedestrian.n_completed", "n_completed"),
        ("kpi.pedestrian.n_in_building_at_end", "n_censored_at_end"),
        ("kpi.pedestrian.ev_wait_mean_sec", "ev_wait_mean_sec"),
        ("drv_peds_waiting_mean", "waiting_mean"),
        ("drv_peds_waiting_max", "waiting_max"),
    ],
    "building": [
        ("kpi.building.opex_running_krw_delivery", "opex_delivery_krw"),
        ("kpi.building.cost_per_order_krw", "cost_per_order_krw"),
        ("kpi.building.w_ev_mean_all_sec", "w_ev_mean_all_sec"),
        ("kpi.building.w_ev_mean_riders_sec", "w_ev_mean_riders_sec"),
        ("kpi.building.capex_total_krw", "capex_total_krw"),
    ],
}


def t1_agent_kpi(kpi: pd.DataFrame, ev: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Per-agent-class KPI tables, seed-averaged, by K and by scenario."""
    long_rows = []
    for by, keys in (("K", ["K"]), ("scenario", ["scenario", "K"])):
        for agent, spec in AGENT_KPI_SPEC.items():
            g = kpi.groupby(keys, as_index=False)[[c for c, _ in spec]].mean()
            g = g.rename(columns=dict(spec))
            m = g.melt(id_vars=keys, var_name="metric", value_name="value")
            m.insert(0, "agent", agent)
            m.insert(0, "scope", by)
            long_rows.append(m)

        # elevator: the fleet aggregate plus the dedicated/shared split, which
        # is the only elevator breakdown the robot modes actually act on.
        #
        # Two-stage on purpose. Counts (boardings, capacity violations) are
        # summed **within a run** across the cars of the group and then
        # *averaged* across runs; rates and waits are averaged throughout.
        # Collapsing that into one groupby sums the counts across scenarios and
        # seeds too, which turns "boardings on the shared cars" into "boardings
        # on the shared cars times the number of scenarios at this K" — a
        # quantity that changes when the corpus changes size.
        counts = ["n_boardings", "n_boardings_rider", "n_boardings_ped",
                  "capacity_violations"]
        means = ["util_delivery", "mean_pax_delivery", "w_ev_mean_sec",
                 "w_ev_rider_sec", "w_ev_ped_sec", "w_ev_ped_p95_sec",
                 "pax_ge12_frac"]
        maxes = ["pax_max_series", "queue_max"]
        within = {**{c: "sum" for c in counts}, **{c: "mean" for c in means},
                  **{c: "max" for c in maxes}}
        for role_label, sub in (
                ("elevator", ev),
                ("elevator_dedicated", ev[ev.role == "dedicated"]),
                ("elevator_shared", ev[ev.role == "shared"])):
            per_run = sub.groupby(["scenario", "K", "seed"], as_index=False).agg(within)
            s = per_run.groupby(keys, as_index=False).mean(numeric_only=True).drop(
                columns=["seed"], errors="ignore")
            m = s.melt(id_vars=keys, var_name="metric", value_name="value")
            m.insert(0, "agent", role_label)
            m.insert(0, "scope", by)
            long_rows.append(m)

    long = pd.concat(long_rows, ignore_index=True)
    by_k = long[long["scope"] == "K"].drop(columns=["scope", "scenario"], errors="ignore")
    by_scen = long[long["scope"] == "scenario"].drop(columns=["scope"])

    # wide, human-readable pivots (one row per metric, one column per K)
    wide_k = by_k.pivot_table(index=["agent", "metric"], columns="K",
                              values="value").reset_index()
    wide_k.columns = [f"K{c}" if isinstance(c, (int, np.integer)) else c
                      for c in wide_k.columns]
    wide_k = wide_k.round(4)
    wide_k.to_csv(TABLES / "agent_kpi_by_k.csv", index=False)
    by_scen.round(4).to_csv(TABLES / "agent_kpi_by_scenario.csv", index=False)

    car = ev.groupby(["K", "ev_id", "role"], as_index=False).mean(
        numeric_only=True).drop(columns=["seed"], errors="ignore").round(4)
    car.to_csv(TABLES / "ev_by_car.csv", index=False)

    print(f"[T1] agent_kpi_by_k.csv ({len(wide_k)} metrics x {wide_k.shape[1] - 2} K "
          f"levels) · agent_kpi_by_scenario.csv ({len(by_scen)}) · "
          f"ev_by_car.csv ({len(car)})")
    return {"by_k": wide_k, "by_scenario": by_scen, "by_car": car}


def t1_breakdowns(po: dict[str, pd.DataFrame]) -> None:
    """Rider-hire-type and delivery-floor breakdowns (per-order derived)."""
    hire = po["hire"].groupby(["K", "rider_type"], as_index=False).mean(
        numeric_only=True).drop(columns=["seed"], errors="ignore").round(3)
    hire.to_csv(TABLES / "rider_by_hire_type.csv", index=False)

    floor = po["floor"].groupby(["K", "floor"], as_index=False).mean(
        numeric_only=True).drop(columns=["seed"], errors="ignore").round(3)
    floor.to_csv(TABLES / "kpi_by_floor.csv", index=False)
    print(f"[T1] rider_by_hire_type.csv ({len(hire)}) · kpi_by_floor.csv ({len(floor)})")


# ======================================================= T2 — demand analysis

# Headline KPIs whose K-scaling the paper's demand section reports.
SCALING_SPEC = [
    ("kpi.customer.t_e2e_mean_sec", "T_e2e mean (s)"),
    ("kpi.customer.t_e2e_p95_sec", "T_e2e p95 (s)"),
    ("kpi.rider.t_lobby_mean_sec", "T_lobby mean (s)"),
    ("kpi.rider.t_lobby_p95_sec", "T_lobby p95 (s)"),
    ("kpi.building.w_ev_mean_riders_sec", "W_EV riders (s)"),
    ("kpi.pedestrian.ev_wait_mean_sec", "W_EV pedestrians (s)"),
    ("drv_riders_in_building_max", "Riders in building, max"),
    ("drv_stairs_share", "Stairs share"),
    ("kpi.building.cost_per_order_krw", "Lobby cost per order (KRW)"),
    ("kpi.customer.n_sla_violations", "SLA violations"),
]


def t2_demand(kpi: pd.DataFrame, traits: pd.DataFrame,
              ev: pd.DataFrame) -> pd.DataFrame:
    """K-scaling table + the utilization/wait knee + variance decomposition."""
    k_list = _k_order(kpi)
    rows = []
    for col, label in SCALING_SPEC:
        per_scen = kpi.groupby(["K", "scenario"], as_index=False)[col].mean()
        rec = {"kpi": label, "column": col}
        base = per_scen[per_scen.K == k_list[0]][col].mean()
        for k in k_list:
            v = per_scen[per_scen.K == k][col]
            rec[f"K{k}"] = round(v.mean(), 4)
            rec[f"K{k}_scen_min"] = round(v.min(), 4)
            rec[f"K{k}_scen_max"] = round(v.max(), 4)
            # scenario-to-scenario spread at fixed K: how much demand *pattern*
            # moves the KPI once demand *size* is held constant.
            rec[f"K{k}_scen_cv"] = (round(v.std(ddof=1) / v.mean(), 4)
                                    if len(v) > 1 and v.mean() else None)
        rec["K300_over_K50"] = (round(per_scen[per_scen.K == k_list[-1]][col].mean() / base, 3)
                                if base else None)
        rows.append(rec)
    scaling = pd.DataFrame(rows)
    scaling.to_csv(TABLES / "demand_scaling_by_k.csv", index=False)

    # ---- the knee: fleet utilization vs the wait it produces ---------------
    knee = ev.groupby(["K", "scenario", "seed"], as_index=False).agg(
        util_delivery=("util_delivery", "mean"),
        mean_pax=("mean_pax_delivery", "mean"),
        w_ev=("w_ev_mean_sec", "mean"),
        w_ev_rider=("w_ev_rider_sec", "mean"),
        w_ev_ped=("w_ev_ped_sec", "mean"),
    ).groupby(["K", "scenario"], as_index=False).mean(numeric_only=True).drop(
        columns=["seed"], errors="ignore")
    knee.round(4).to_csv(TABLES / "ev_knee_by_scenario.csv", index=False)

    # ---- variance decomposition -------------------------------------------
    vd = variance_decomposition(kpi)
    print(f"[T2] demand_scaling_by_k.csv ({len(scaling)}) · "
          f"ev_knee_by_scenario.csv ({len(knee)}) · "
          f"variance_decomposition.csv ({len(vd)})")
    return knee


VD_KPIS = {
    "kpi.customer.t_e2e_mean_sec": "T_e2e mean",
    "kpi.customer.t_e2e_p95_sec": "T_e2e p95",
    "kpi.rider.t_lobby_mean_sec": "T_lobby mean",
    "kpi.building.w_ev_mean_riders_sec": "W_EV riders",
    "kpi.pedestrian.ev_wait_mean_sec": "W_EV pedestrians",
    "drv_shared_pax_ge12_frac_any": "Shared-EV denial exposure",
    "drv_stairs_share": "Stairs share",
    "drv_arrival_ia_cv2": "Door arrival c_a^2",
    "drv_riders_in_building_max": "Riders in building, max",
}


def variance_decomposition(kpi: pd.DataFrame) -> pd.DataFrame:
    """Nested sum-of-squares shares: between-K / within-K scenario / seed.

    Tells Phase D which KPIs are demand-*size* sensitive (large between-K) vs
    demand-*pattern* sensitive (large within-K) vs mostly noise (large seed) —
    i.e. which axis the experiment design has to spend runs on.
    """
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
            "share_between_K": round(ss_k / total, 4) if total else None,
            "share_within_K_scenario": round(ss_scen / total, 4) if total else None,
            "share_seed": round(ss_seed / total, 4) if total else None,
        })
    df = pd.DataFrame(rows)
    df.to_csv(TABLES / "variance_decomposition.csv", index=False)
    return df


# ============================================ T3 — H1/H2/H3 direction check

def t3_h1(kpi: pd.DataFrame, ev: pd.DataFrame, po: dict) -> pd.DataFrame:
    """H1: prize bound, shared-car denial exposure, added vertical trip load."""
    # --- prize bound -------------------------------------------------------
    # Upper bound on what a robot can save per order = the rider's whole lobby
    # dwell minus the handoff. The bound is loose *in the model* (counter walk
    # and robot wait are not subtracted), not in the arithmetic:
    #   sum_i w_i (t_i - 60)/3600 = lobby_cost - (60/3600) sum_i w_i
    hire = po["hire"]
    wage_sum = hire.assign(wsum=hire["n"] * hire["w_R_krw_per_h"]).groupby(
        ["scenario", "K", "seed"], as_index=False)["wsum"].sum()
    base = kpi[["scenario", "K", "seed", "kpi.rider.t_lobby_mean_sec",
                "kpi.rider.lobby_cost_total_krw"]].merge(
        wage_sum, on=["scenario", "K", "seed"])
    base["prize_sec_per_order"] = (base["kpi.rider.t_lobby_mean_sec"]
                                   - HANDOFF_SEC).clip(lower=0)
    base["prize_krw_per_day"] = (base["kpi.rider.lobby_cost_total_krw"]
                                 - base["wsum"] * HANDOFF_SEC / 3600.0)
    prize = base.groupby(["K", "scenario"], as_index=False).mean(
        numeric_only=True).drop(columns=["seed"], errors="ignore")
    prize["prize_krw_per_year"] = prize["prize_krw_per_day"] * ANNUAL_DAYS

    # --- denial exposure + trip transfer -----------------------------------
    sh = ev[ev.role == "shared"].groupby(["K", "scenario"], as_index=False).agg(
        shared_boardings=("n_boardings", "sum"),
        shared_boardings_ped=("n_boardings_ped", "sum"),
        shared_pax_mean=("mean_pax_delivery", "mean"),
        shared_pax_max=("pax_max_series", "max"),
        shared_util_delivery=("util_delivery", "mean"),
        shared_ped_wait_sec=("w_ev_ped_sec", "mean"),
    )
    sh[["shared_boardings", "shared_boardings_ped"]] /= len(SEEDS)  # sum over seeds
    ded = ev[ev.role == "dedicated"].groupby(["K", "scenario"], as_index=False).agg(
        dedicated_util_delivery=("util_delivery", "mean"),
        dedicated_ped_wait_sec=("w_ev_ped_sec", "mean"),
        dedicated_pax_mean=("mean_pax_delivery", "mean"),
    )
    exposure = kpi.groupby(["K", "scenario"], as_index=False).agg(
        denial_frac_all=("drv_shared_pax_ge12_frac_all", "mean"),
        denial_frac_any=("drv_shared_pax_ge12_frac_any", "mean"),
    )
    d = prize.merge(sh, on=["K", "scenario"]).merge(
        ded, on=["K", "scenario"]).merge(exposure, on=["K", "scenario"])

    out = pd.DataFrame({
        "scenario": d["scenario"], "K": d["K"],
        "t_lobby_mean_sec": d["kpi.rider.t_lobby_mean_sec"].round(1),
        "h1_prize_ub_sec_per_order": d["prize_sec_per_order"].round(1),
        "h1_prize_ub_krw_per_day": d["prize_krw_per_day"].round(0),
        "h1_prize_ub_krw_per_year": d["prize_krw_per_year"].round(-3),
        # 2 rides per order (up + down), no batching (design freeze R0-4)
        "h1_robot_rides": 2 * d["K"],
        "shared_person_boardings_now": d["shared_boardings"].round(0),
        "h1_shared_trip_ratio": (2 * d["K"] / d["shared_boardings"]).round(3),
        "shared_util_delivery": d["shared_util_delivery"].round(4),
        "dedicated_util_delivery": d["dedicated_util_delivery"].round(4),
        "shared_pax_mean": d["shared_pax_mean"].round(3),
        "shared_pax_max": d["shared_pax_max"],
        "denial_exposure_all_frac": d["denial_frac_all"].round(5),
        "denial_exposure_any_frac": d["denial_frac_any"].round(5),
        # two-sided externality baseline: today the two groups of cars are
        # interchangeable for pedestrians, so any post-H1 gap is the robot's.
        "ped_wait_shared_sec": d["shared_ped_wait_sec"].round(2),
        "ped_wait_dedicated_sec": d["dedicated_ped_wait_sec"].round(2),
        "ped_wait_gap_sec": (d["shared_ped_wait_sec"]
                             - d["dedicated_ped_wait_sec"]).round(3),
    }).sort_values(["K", "scenario"])
    out.to_csv(TABLES / "hr_h1_prediagnosis.csv", index=False)
    print(f"[T3] hr_h1_prediagnosis.csv ({len(out)} rows)")
    return out


ROBOT_FLEET_SIZES = (1, 2, 3, 4, 5, 6, 8)


def t3_h2(kpi: pd.DataFrame, traits: pd.DataFrame) -> pd.DataFrame:
    """H2: the G/G/c inputs Phase B B5 needs, measured on v2.1.

    The handoff counter of H2 is a queue whose arrivals are riders *reaching the
    building* — not the raw order process. Those are different processes (the
    cook time and the street leg smooth or clump the stream), so the c_a^2 that
    an Allen-Cunneen approximation needs is the door one, and the amplification
    from raw to door is itself the interesting number.
    """
    door = kpi.groupby(["K", "scenario"], as_index=False).agg(
        door_ia_mean_sec=("drv_arrival_ia_mean_sec", "mean"),
        door_ia_cv2=("drv_arrival_ia_cv2", "mean"),
        door_peak10=("drv_arrival_peak10_over_mean", "mean"),
        riders_in_building_max=("drv_riders_in_building_max", "max"),
        riders_in_building_mean=("drv_riders_in_building_mean", "mean"),
        riders_waiting_ev_max=("drv_riders_waiting_ev_max", "max"),
        backlog_max=("drv_backlog_max", "max"),
        service_time_mean_sec=("drv_service_time_mean_sec", "mean"),
    )
    raw = traits[["scenario", "K", "ia_cv2", "peak10_over_mean", "ia_mean_sec"]].rename(
        columns={"ia_cv2": "raw_ia_cv2", "peak10_over_mean": "raw_peak10",
                 "ia_mean_sec": "raw_ia_mean_sec"})
    d = raw.merge(door, on=["scenario", "K"])
    d["ca2_amplification"] = (d["door_ia_cv2"] / d["raw_ia_cv2"]).round(3)

    # ---- offered load on the robot fleet -----------------------------------
    # Two loads, and confusing them is the trap. The handoff *counter* is busy
    # for E[handoff] = 60 s per order (R0-3), but the *robot* is busy for a
    # whole round trip, and it is the robot that is the server.
    #
    # The cycle is estimated from the measured H0 rider, who walks the same
    # graph and rides the same cars:
    #     T_lobby = walk-in + EV wait up + ride up + service + EV wait down
    #               + ride down + walk-out                      (measured)
    # A robot does the same legs but drops in 30 s instead of the rider's
    # measured service time, and adds the 60 s handoff:
    #     cycle ~= T_lobby - service + 30 + 60
    # It is an estimate, not a measurement -- the robot's counter walk and its
    # queueing for a *shared-only* car are not in it, so it is a LOWER bound on
    # cycle time and therefore on fleet size. That is the useful direction: if
    # the lower bound already says N robots is too few, N is too few.
    lam = 1.0 / d["door_ia_mean_sec"]
    tl = kpi.groupby(["K", "scenario"], as_index=False).agg(
        t_lobby=("kpi.rider.t_lobby_mean_sec", "mean"),
        service=("drv_service_time_mean_sec", "mean"))
    d = d.merge(tl, on=["K", "scenario"])
    d["robot_cycle_est_sec"] = (d["t_lobby"] - d["service"]
                                + ROBOT_DROP_SEC + HANDOFF_SEC)
    for c in ROBOT_FLEET_SIZES:
        d[f"rho_counter_c{c}"] = (lam * HANDOFF_SEC / c).round(4)
        d[f"rho_robot_c{c}"] = (lam * d["robot_cycle_est_sec"] / c).round(4)
    # Smallest fleet with rho < 1. Not a design answer (rho just below 1 is a
    # terrible operating point) -- it is the floor below which H1/H2 cannot
    # clear the demand at all, and the number the design freeze's n_robots=3
    # has to be checked against.
    d["min_robots_rho_lt_1"] = np.ceil(lam * d["robot_cycle_est_sec"]).astype(int)
    # lambda above is the span average. Arrivals are not uniform (peak10 is the
    # busiest 10-min bin over the mean bin), so a fleet sized on the average
    # runs a growing queue through the peak. This is the peak-sized fleet.
    d["min_robots_peak10"] = np.ceil(
        lam * d["door_peak10"] * d["robot_cycle_est_sec"]).astype(int)
    d = d.round(4)
    d.to_csv(TABLES / "h2_queue_inputs.csv", index=False)
    print(f"[T3] h2_queue_inputs.csv ({len(d)} rows)")
    return d


def t3_h3(po: dict, kpi: pd.DataFrame) -> pd.DataFrame:
    """H3: per-floor locker bank size as a function of assumed residence time."""
    lk = po["locker"]
    # per (scenario, tau): the worst floor, seed-averaged; and the corpus worst
    per_scen = lk.groupby(["K", "scenario", "seed", "tau_min"], as_index=False).agg(
        peak_floor_occupancy=("peak_occupancy", "max"),
        busiest_floor_deliveries=("n_deliveries", "max"),
    ).groupby(["K", "scenario", "tau_min"], as_index=False).mean(
        numeric_only=True).drop(columns=["seed"], errors="ignore")
    per_scen.round(3).to_csv(TABLES / "h3_locker_by_scenario.csv", index=False)

    by_k = per_scen.groupby(["K", "tau_min"], as_index=False).agg(
        mean_peak_occupancy=("peak_floor_occupancy", "mean"),
        max_peak_occupancy=("peak_floor_occupancy", "max"),
    )
    # A bank sized for the corpus-worst floor is what a building actually buys;
    # the mean is what an average building would need. Both are reported because
    # the gap is the sizing risk.
    burst = kpi.groupby(["K"], as_index=False).agg(
        floor_burst10_max=("drv_floor_burst10_max", "max"),
        deliv_per_floor_max=("drv_deliv_per_floor_max", "max"),
        deliv_per_floor_mean=("drv_deliv_per_floor_mean", "mean"),
    )
    by_k = by_k.merge(burst, on="K").round(3)
    by_k.to_csv(TABLES / "h3_locker_sizing.csv", index=False)
    print(f"[T3] h3_locker_sizing.csv ({len(by_k)}) · "
          f"h3_locker_by_scenario.csv ({len(per_scen)})")
    return by_k


def t3_te2e_ceiling(po: dict) -> pd.DataFrame:
    """The structural ceiling on any in-building intervention.

    A robot can only touch the in-building part of T_e2e (and not even all of
    it — the customer still waits for the ride). So the in-building share is a
    hard upper bound on the T_e2e improvement *any* of H1/H2/H3 can deliver,
    and it is the reason the primary outcome axis is rider labour, not T_e2e.
    """
    d = po["decomp"].groupby("K", as_index=False).mean(numeric_only=True).drop(
        columns=["seed"], errors="ignore")
    cols = ["K", "t_e2e_mean", *COMPONENTS, "in_building", "in_building_share"]
    d = d[cols]
    for c in COMPONENTS:
        d[f"{c}_share"] = (d[c] / d["t_e2e_mean"]).round(4)
    d = d.round(3)
    d.to_csv(TABLES / "te2e_decomposition_by_k.csv", index=False)
    po["decomp"].round(3).to_csv(TABLES / "te2e_decomposition_by_scenario.csv",
                                 index=False)
    print(f"[T3] te2e_decomposition_by_k.csv ({len(d)} rows)")
    return d


# =================================================================== figures

def _style(ax, xlabel: str = "", ylabel: str = "", title: str = "") -> None:
    ax.set_facecolor(SURFACE)
    ax.grid(True, color=GRID, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=INK2, labelsize=9)
    if xlabel:
        ax.set_xlabel(xlabel, color=INK2, fontsize=9)
    if ylabel:
        ax.set_ylabel(ylabel, color=INK2, fontsize=9)
    if title:
        ax.set_title(title, color=INK, fontsize=11, loc="left", pad=8)


def _num(v: float) -> str:
    """Direct-label format. Never scientific notation — a label reading
    `1.59e+03` on a seconds axis is unreadable at a glance, which defeats the
    point of labelling the mark at all."""
    if v is None or not np.isfinite(v):
        return "n/a"
    a = abs(v)
    if a >= 100:
        return f"{v:,.0f}"
    if a >= 10:
        return f"{v:.1f}"
    if a >= 1:
        return f"{v:.2f}"
    return f"{v:.3f}"


def _save(fig, name: str) -> None:
    fig.patch.set_facecolor(SURFACE)
    fig.tight_layout()
    fig.savefig(FIGS / name, dpi=150, facecolor=SURFACE)
    plt.close(fig)
    print(f"[fig] {name}")


def fig_agent_scaling(kpi: pd.DataFrame, ev: pd.DataFrame) -> None:
    """g1 — one small multiple per agent class: how K moves its headline KPI."""
    k_list = _k_order(kpi)
    panels = [
        ("Customer — T_e2e mean", kpi, "kpi.customer.t_e2e_mean_sec", "s", S1_BLUE),
        ("Rider — T_lobby mean", kpi, "kpi.rider.t_lobby_mean_sec", "s", S2_ORANGE),
        ("Rider — EV wait (up)", kpi, "kpi.rider.ev_wait_up_mean_sec", "s", S2_ORANGE),
        ("Pedestrian — EV wait", kpi, "kpi.pedestrian.ev_wait_mean_sec", "s", S3_AQUA),
        ("Elevator — utilization (delivery)", None, "util_delivery", "", S4_YELLOW),
        ("Elevator — mean passengers", None, "mean_pax_delivery", "명", S4_YELLOW),
    ]
    fig, axes = plt.subplots(2, 3, figsize=(13.5, 7.2))
    for ax, (title, src, col, unit, color) in zip(axes.ravel(), panels):
        if src is None:
            per_scen = ev.groupby(["K", "scenario"], as_index=False)[col].mean()
        else:
            per_scen = src.groupby(["K", "scenario"], as_index=False)[col].mean()
        _style(ax, "K (주문 수)", unit, title)
        for k in k_list:
            v = per_scen[per_scen.K == k][col]
            ax.scatter([k] * len(v), v, s=34, color=NEUTRAL, alpha=0.85,
                       edgecolors=SURFACE, linewidths=1.2, zorder=3)
        means = per_scen.groupby("K")[col].mean()
        ax.plot(means.index, means.to_numpy(), color=color, linewidth=2, zorder=4,
                marker="o", markersize=8, markeredgecolor=SURFACE, markeredgewidth=1.5)
        for k in k_list:  # direct labels (contrast relief for the WARN hues)
            ax.annotate(_num(means[k]), (k, means[k]), textcoords="offset points",
                        xytext=(0, 9), ha="center", fontsize=8, color=INK)
        ax.set_xticks(k_list)
    fig.suptitle("g1 — 에이전트 클래스별 수요(K) 스케일링  ·  점=시나리오, 선=K 평균 "
                 "(H0 v2.1, 28 시나리오 × 3 seed)", color=INK, fontsize=12, x=0.01,
                 ha="left")
    _save(fig, "g1_agent_scaling.png")


def fig_shared_vs_dedicated(ev: pd.DataFrame) -> None:
    """g2 — the two-sided-externality baseline: shared and dedicated cars today."""
    d = ev.groupby(["K", "role"], as_index=False).mean(numeric_only=True)
    k_list = sorted(d["K"].unique())
    metrics = [("util_delivery", "가동률 (배달창)", ""),
               ("w_ev_ped_sec", "보행자 EV 대기 (s)", "s"),
               ("w_ev_rider_sec", "라이더 EV 대기 (s)", "s"),
               ("mean_pax_delivery", "평균 재차 인원 (명)", "명")]
    fig, axes = plt.subplots(1, 4, figsize=(15, 3.8))
    width = 0.38
    for ax, (col, title, unit) in zip(axes, metrics):
        _style(ax, "K", unit, title)
        x = np.arange(len(k_list))
        for i, (role, label, color) in enumerate(
                (("dedicated", "전용 EV1·EV2", S1_BLUE),
                 ("shared", "공용 EV3·EV4", S2_ORANGE))):
            v = [d[(d.K == k) & (d.role == role)][col].iloc[0] for k in k_list]
            # 2px surface gap between adjacent bars
            ax.bar(x + (i - 0.5) * (width + 0.02), v, width, label=label, color=color,
                   edgecolor=SURFACE, linewidth=2, zorder=3)
            for xi, vi in zip(x + (i - 0.5) * (width + 0.02), v):
                ax.annotate(_num(vi), (xi, vi), textcoords="offset points",
                            xytext=(0, 3), ha="center", fontsize=7.5, color=INK)
        ax.set_ylim(0, max(d[col]) * 1.18)
        ax.set_xticks(x)
        ax.set_xticklabels([f"K{k}" for k in k_list])
    axes[0].legend(frameon=False, fontsize=9, labelcolor=INK2, ncol=2,
                   loc="upper left", bbox_to_anchor=(0, -0.16))
    fig.suptitle("g2 — 공용(EV3·EV4) vs 전용(EV1·EV2): 로봇 도입 전 기준선. "
                 "H0에서 두 그룹은 통계적으로 같다 — H1 이후의 격차가 곧 로봇 효과다",
                 color=INK, fontsize=12, x=0.01, ha="left")
    _save(fig, "g2_shared_vs_dedicated.png")


def fig_knee(knee: pd.DataFrame) -> None:
    """g3 — utilization vs the wait it produces, coloured by K."""
    k_list = sorted(knee["K"].unique())
    ramp = _ramp(k_list)
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.4))
    for ax, (ycol, ylabel, title) in zip(
            axes, (("w_ev_rider", "라이더 EV 대기 (s)", "배달 라이더가 겪는 대기"),
                   ("w_ev_ped", "보행자 EV 대기 (s)", "상주 보행자가 겪는 대기 (공유 외부성)"))):
        _style(ax, "EV 가동률 (배달창, 4대 평균 — 적재율 아님)", ylabel, title)
        for k in k_list:
            sub = knee[knee.K == k]
            ax.scatter(sub["util_delivery"], sub[ycol], s=64, color=ramp[k],
                       edgecolors=SURFACE, linewidths=1.6, zorder=3, label=f"K{k}")
        ax.legend(frameon=False, fontsize=9, labelcolor=INK2)
    fig.suptitle("g3 — 무릎 점검: 가동률이 오를 때 대기가 어떻게 반응하는가 "
                 "(점 = 시나리오 1개, 3 seed 평균)", color=INK, fontsize=12,
                 x=0.01, ha="left")
    _save(fig, "g3_util_wait_knee.png")


def fig_te2e(decomp_k: pd.DataFrame) -> None:
    """g4 — where T_e2e goes: the ceiling on any in-building intervention."""
    fig, ax = plt.subplots(figsize=(9.5, 5))
    _style(ax, "K (주문 수)", "T_e2e 평균 (s)",
           "g4 — T_e2e 7성분 분해: 건물 안(파랑 계열)이 로봇이 손댈 수 있는 전부다")
    k_list = decomp_k["K"].tolist()
    x = np.arange(len(k_list))
    bottom = np.zeros(len(k_list))
    for c in COMPONENTS:
        v = decomp_k[c].to_numpy(float)
        ax.bar(x, v, 0.6, bottom=bottom, label=c, color=COMPONENT_COLORS[c],
               edgecolor=SURFACE, linewidth=2, zorder=3)  # 2px surface gap
        bottom += v
    for xi, k in zip(x, k_list):
        share = decomp_k[decomp_k.K == k]["in_building_share"].iloc[0]
        ax.annotate(f"건물 내 {share:.1%}", (xi, bottom[xi]), textcoords="offset points",
                    xytext=(0, 6), ha="center", fontsize=9, color=INK)
    ax.set_xticks(x)
    ax.set_xticklabels([f"K{k}" for k in k_list])
    ax.set_ylim(0, bottom.max() * 1.10)
    ax.legend(frameon=False, fontsize=8.5, labelcolor=INK2, ncol=7,
              loc="upper left", bbox_to_anchor=(0, -0.12))
    _save(fig, "g4_te2e_decomposition.png")


def fig_h1(h1: pd.DataFrame) -> None:
    """g5 — H1 prize bound and the denial exposure it would run into."""
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.2))
    k_list = sorted(h1["K"].unique())
    ramp = _ramp(k_list)

    _style(axes[0], "K", "백만원/년", "H1 상금 상한 (연간, 라이더 임금 가중)")
    for k in k_list:
        v = h1[h1.K == k]["h1_prize_ub_krw_per_year"] / 1e6
        axes[0].scatter([k] * len(v), v, s=48, color=ramp[k], edgecolors=SURFACE,
                        linewidths=1.4, zorder=3)
    m = h1.groupby("K")["h1_prize_ub_krw_per_year"].mean() / 1e6
    axes[0].plot(m.index, m.to_numpy(), color=S2_ORANGE, linewidth=2, zorder=4)
    for k in k_list:
        axes[0].annotate(f"{m[k]:,.0f}백만", (k, m[k]), textcoords="offset points",
                         xytext=(0, 11), ha="center", fontsize=8.5, color=INK)
    axes[0].set_xticks(k_list)

    # Only the "any shared car full" series is drawn: "both full" is exactly
    # 0.00000 at every K and every scenario, and a row of zero bars reads as
    # "small" when the finding is "never". The zero is stated in words instead.
    _style(axes[1], "K", "배달창 tick 비율",
           "공용 EV 탑승거부 노출 — 공용 1대 이상 만차(≥12명)")
    x = np.arange(len(k_list))
    v = [h1[h1.K == k]["denial_exposure_any_frac"].mean() for k in k_list]
    axes[1].bar(x, v, 0.55, color=S4_YELLOW, edgecolor=SURFACE, linewidth=2, zorder=3)
    for xi, vi in zip(x, v):
        axes[1].annotate(f"{vi:.5f}", (xi, vi), textcoords="offset points",
                         xytext=(0, 4), ha="center", fontsize=8.5, color=INK)
    axes[1].set_xticks(x)
    axes[1].set_xticklabels([f"K{k}" for k in k_list])
    axes[1].set_ylim(0, max(v) * 1.45 if max(v) else 1)
    axes[1].annotate("공용 2대 동시 만차 = 0.00000\n(전 K · 전 28 시나리오 · 3 seed)\n"
                     "→ 로봇이 실제로 거부당하는 tick이 없다",
                     (0.03, 0.80), xycoords="axes fraction", fontsize=9, color=S2_ORANGE)

    _style(axes[2], "K", "", "공용 EV 수직 트립 증가율 (로봇 왕복 2K / 현 사람 보딩)")
    v = h1.groupby("K")["h1_shared_trip_ratio"].mean()
    axes[2].bar(np.arange(len(k_list)), v.to_numpy(), 0.55, color=S1_BLUE,
                edgecolor=SURFACE, linewidth=2, zorder=3)
    for xi, k in enumerate(k_list):
        axes[2].annotate(f"+{v[k]:.0%}", (xi, v[k]), textcoords="offset points",
                         xytext=(0, 4), ha="center", fontsize=9, color=INK)
    axes[2].set_xticks(np.arange(len(k_list)))
    axes[2].set_xticklabels([f"K{k}" for k in k_list])

    fig.suptitle("g5 — H1 사전진단: 상금 상한 · 거부 노출 · 공용 EV 부하 증가",
                 color=INK, fontsize=12, x=0.01, ha="left")
    _save(fig, "g5_h1_prediagnosis.png")


def fig_h2(h2: pd.DataFrame) -> None:
    """g6 — arrival burstiness amplification and counter load."""
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.4))
    k_list = sorted(h2["K"].unique())
    ramp = _ramp(k_list)

    _style(axes[0], "원시 주문 과정 c_a²", "건물 도착 c_a² (H2 큐 입력)",
           "c_a² 증폭: 조리+거리 이동이 도착을 뭉치게 한다")
    lim = [0, max(h2["raw_ia_cv2"].max(), h2["door_ia_cv2"].max()) * 1.08]
    axes[0].plot(lim, lim, color=NEUTRAL, linewidth=1.5, linestyle="--", zorder=2)
    axes[0].annotate("y = x (증폭 없음)", (lim[1] * 0.62, lim[1] * 0.66), fontsize=8,
                     color=INK2)
    for k in k_list:
        sub = h2[h2.K == k]
        axes[0].scatter(sub["raw_ia_cv2"], sub["door_ia_cv2"], s=60, color=ramp[k],
                        edgecolors=SURFACE, linewidths=1.5, zorder=3, label=f"K{k}")
    axes[0].legend(frameon=False, fontsize=9, labelcolor=INK2)

    _style(axes[1], "로봇 대수 c", "ρ = λ_door · 로봇 1주기 / c",
           "로봇 부하 (1주기 = 인계 60s + 왕복 + 인도 30s)")
    cs = list(ROBOT_FLEET_SIZES)
    for k, color in zip(k_list, [K_RAMP[i] for i in range(len(k_list))]):
        v = [h2[h2.K == k][f"rho_robot_c{c}"].mean() for c in cs]
        axes[1].plot(cs, v, color=color, linewidth=2, marker="o", markersize=7,
                     markeredgecolor=SURFACE, markeredgewidth=1.5, zorder=3,
                     label=f"K{k}")
        need = int(h2[h2.K == k]["min_robots_rho_lt_1"].max())
        axes[1].annotate(f"K{k}: 최소 {need}대", (cs[0], v[0]),
                         textcoords="offset points", xytext=(6, 4), fontsize=8.5,
                         color=INK)
    axes[1].axhline(1.0, color=S2_ORANGE, linewidth=1.5, linestyle="--", zorder=2)
    axes[1].annotate("ρ = 1 (포화)", (1.05, 1.35), fontsize=8.5, color=S2_ORANGE)
    axes[1].annotate("설계 동결\nn_robots = 3", (3.1, 11.6), fontsize=8.5, color=INK2)
    axes[1].axvline(3, color=NEUTRAL, linewidth=1.2, linestyle=":", zorder=2)
    axes[1].set_xticks(cs)
    axes[1].set_ylim(0, None)
    fig.suptitle("g6 — H2 큐 입력 (Allen–Cunneen G/G/c 사전 재산출, v2.1 실측)",
                 color=INK, fontsize=12, x=0.01, ha="left")
    _save(fig, "g6_h2_queue_inputs.png")


def fig_h3(h3: pd.DataFrame) -> None:
    """g7 — locker bank size vs assumed residence time."""
    fig, ax = plt.subplots(figsize=(9, 4.6))
    _style(ax, "가정한 사물함 체류시간 τ (분)", "한 층 최대 동시 점유 (칸)",
           "g7 — H3 락커 사이징: 층당 필요 칸 수 (실선 = 코퍼스 최악 층, 점선 = 평균)")
    k_list = sorted(h3["K"].unique())
    for k, color in zip(k_list, [K_RAMP[i] for i in range(len(k_list))]):
        sub = h3[h3.K == k].sort_values("tau_min")
        ax.plot(sub["tau_min"], sub["max_peak_occupancy"], color=color, linewidth=2,
                marker="o", markersize=8, markeredgecolor=SURFACE,
                markeredgewidth=1.5, zorder=4, label=f"K{k} 최악")
        ax.plot(sub["tau_min"], sub["mean_peak_occupancy"], color=color, linewidth=1.6,
                linestyle=":", zorder=3)
        last = sub.iloc[-1]
        ax.annotate(f"K{k}: {last['max_peak_occupancy']:.0f}칸",
                    (last["tau_min"], last["max_peak_occupancy"]),
                    textcoords="offset points", xytext=(6, -2), fontsize=8.5, color=INK)
    ax.legend(frameon=False, fontsize=9, labelcolor=INK2, ncol=4,
              loc="upper left", bbox_to_anchor=(0, -0.14))
    ax.set_xticks(list(LOCKER_TAU_MIN))
    ax.set_xlim(3, 34)
    _save(fig, "g7_h3_locker_sizing.png")


def fig_variance(vd: pd.DataFrame) -> None:
    """g8 — where the spread lives: demand size vs pattern vs seed."""
    fig, ax = plt.subplots(figsize=(10, 4.6))
    _style(ax, "분산 기여 비율", "",
           "g8 — 분산 분해: 수요 크기(K) vs 패턴(시나리오) vs seed")
    y = np.arange(len(vd))[::-1]
    left = np.zeros(len(vd))
    for col, lab, color in (("share_between_K", "K 간 (수요 크기)", S1_BLUE),
                            ("share_within_K_scenario", "K 내 시나리오 (수요 패턴)", S2_ORANGE),
                            ("share_seed", "seed (잡음)", NEUTRAL)):
        v = vd[col].to_numpy(float)
        ax.barh(y, v, 0.62, left=left, label=lab, color=color, edgecolor=SURFACE,
                linewidth=2, zorder=3)
        for yi, (li, vi) in enumerate(zip(left, v)):
            if vi > 0.08:
                ax.annotate(f"{vi:.0%}", (li + vi / 2, y[yi]), ha="center",
                            va="center", fontsize=8, color=SURFACE)
        left += v
    ax.set_yticks(y)
    ax.set_yticklabels(vd["kpi"], fontsize=9, color=INK)
    ax.set_xlim(0, 1)
    ax.legend(frameon=False, fontsize=9, labelcolor=INK2, ncol=3,
              loc="upper left", bbox_to_anchor=(0, -0.12))
    _save(fig, "g8_variance_decomposition.png")


# ====================================================================== main

def main() -> int:
    TABLES.mkdir(parents=True, exist_ok=True)
    FIGS.mkdir(parents=True, exist_ok=True)

    traits, kpi = load_inputs()
    ev = ev_long(kpi)
    po = per_order_pass(kpi)

    # folder self-containment: the two S0/S1 inputs travel with the analysis
    for src in ("scenario_traits.csv", "h0_kpi_by_scenario.csv"):
        shutil.copy(STATS / src, TABLES / src)

    t1_agent_kpi(kpi, ev)
    t1_breakdowns(po)
    knee = t2_demand(kpi, traits, ev)
    vd = pd.read_csv(TABLES / "variance_decomposition.csv")
    decomp_k = t3_te2e_ceiling(po)
    h1 = t3_h1(kpi, ev, po)
    h2 = t3_h2(kpi, traits)
    h3 = t3_h3(po, kpi)

    fig_agent_scaling(kpi, ev)
    fig_shared_vs_dedicated(ev)
    fig_knee(knee)
    fig_te2e(decomp_k)
    fig_h1(h1)
    fig_h2(h2)
    fig_h3(h3)
    fig_variance(vd)

    # ---- console digest (the numbers the note quotes) ----------------------
    print("\n=== H0 v2.1 digest (3 seed, 28 scenarios) ===")
    for k in _k_order(kpi):
        s = kpi[kpi.K == k]
        e = ev[ev.K == k]
        d = decomp_k[decomp_k.K == k].iloc[0]
        p = h1[h1.K == k]
        print(f"K{k:<4} T_e2e={s['kpi.customer.t_e2e_mean_sec'].mean():7.1f}s "
              f"in_bldg={d['in_building_share']:.1%}  "
              f"T_lobby={s['kpi.rider.t_lobby_mean_sec'].mean():6.1f}s  "
              f"util={e['util_delivery'].mean():.3f} pax={e['mean_pax_delivery'].mean():.2f}  "
              f"W_EV(r/p)={s['kpi.building.w_ev_mean_riders_sec'].mean():5.1f}/"
              f"{s['kpi.pedestrian.ev_wait_mean_sec'].mean():5.1f}s  "
              f"deny_all={p['denial_exposure_all_frac'].mean():.5f} "
              f"trip+{p['h1_shared_trip_ratio'].mean():.0%}  "
              f"prize={p['h1_prize_ub_krw_per_year'].mean() / 1e6:6.1f}M/yr")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
