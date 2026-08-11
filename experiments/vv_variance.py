"""V-VAR — 30-seed variance / CI-width / channel-decomposition battery.

Stage V5e, etc/plan_h0_verification.md §2 L6 item 2 (V-VAR).

    .venv/bin/python -m experiments.vv_variance

Runs three representative scenarios (K50_1, K200_1, K300_4 — low/mid/high
within the 28-file corpus; K1000_1 is out of corpus for this study per 사용자
확정 2026-08-03 2차) through the
paper track (simulation.run.run_baseline: dynamic rider pool + scenario
window + floor_profile="uniform", all other args default) over 30 seeds, and
reports, per primary KPI:

  1. across-seed mean, SD, 95% CI half-width (absolute + relative %), and
     (for T_e2e p95) the seed-to-seed stability of the per-run p95 via an
     n-1 jackknife standard error of the mean-of-per-run-p95.
  2. a seed-count convergence curve: the 95% CI relative half-width recomputed
     on the first n = 10 / 20 / 30 seeds ("is 30 enough, or is 50+ needed?").
  3. a variance-channel decomposition. §0.3 fact 7: floor_seed defaults to
     rng_seed, so a plain rng_seed sweep drives variance through TWO channels
     (pedestrian stream + floor-assignment draw). Re-running the same 30
     rng_seeds with floor_seed pinned to 42 removes the floor channel, leaving
     the pedestrian channel alone. The reported ratio
        ped_channel_var_ratio = Var(floor-pinned) / Var(full 2-channel)
     quantifies how much of the total run-to-run variance the single
     pedestrian channel already accounts for (V-DET confirms the structure
     qualitatively; this sizes it).

Seed set: rng_seed = 1..30 (SEEDS below). The floor-pinned channel run fixes
floor_seed = FLOOR_PIN (42) while sweeping the same rng_seeds.

Budget: (30 full + 30 floor-pinned) x 3 scenarios = 180 in-process runs.
At the vv_all39 per-run wall times (K50 ~0.8s, K200 ~1.4s, K300 ~1.9s) that
is ~4 min — the old ~10 min estimate assumed the K1000 rung (~7.6s/run), which
is out of corpus.

Gate: this is an analysis script, not a unit test. A small spot-check
(SPOT_SEEDS per scenario) is passed through analysis.verify_h0.verify_result
as a smoke gate; the full 180-run A1..A9 sweep is not repeated here (V3
already ran the corpus x3 through the gate, all PASS).

Outputs (plan §6 vv/ convention):
  results/vv/variance_30seed.csv   — run-level raw (180 rows)
  results/vv/variance_summary.csv  — per-KPI CI/convergence/channel tables

Interpretation is left to stdout + CSV only (paper wording is the main
session's job, per the V5e split: 오퍼스 실행 / Fable 해석).
"""

from __future__ import annotations

import csv
import time
from pathlib import Path

import numpy as np
from scipy import stats

from analysis.verify_h0 import verify_result
from simulation.run import run_baseline

ROOT = Path(__file__).resolve().parent.parent
SCENARIO_DIR = ROOT / "data" / "data1"
OUT_RAW = ROOT / "results" / "vv" / "variance_30seed.csv"
OUT_SUMMARY = ROOT / "results" / "vv" / "variance_summary.csv"

SCENARIOS = ["K50_1", "K200_1", "K300_4"]
SEEDS = list(range(1, 31))          # rng_seed = 1..30
FLOOR_PIN = 42                      # floor_seed for the pedestrian-only channel
CONV_NS = [10, 20, 30]             # seed-count convergence subsets
SPOT_SEEDS = [1, 2, 3]             # verify_h0 smoke-gate spot check per scenario

# Primary KPIs (plan §2 L6 item 2 "주요 KPI (최소: ...)"). Each entry maps a
# short key -> a callable pulling the per-run scalar from a run_baseline dict.
KPI_KEYS = ["t_e2e_mean", "t_e2e_p95", "t_lobby_mean", "w_ev_mean", "rider_wait_mean"]


def kpi_values(result: dict) -> dict[str, float | None]:
    kpi = result["kpi_summary"]
    orders = result["per_order"]
    waits = [o["rider_wait_sec"] for o in orders if o.get("rider_wait_sec") is not None]
    return {
        "t_e2e_mean": kpi["customer"]["t_e2e_mean_sec"],
        "t_e2e_p95": kpi["customer"]["t_e2e_p95_sec"],
        "t_lobby_mean": kpi["rider"]["t_lobby_mean_sec"],
        # W_EV = elevator boarding wait for riders (matches vv_monotonicity);
        # rider_wait = pool-assignment wait (dispatch - ready), a distinct channel.
        "w_ev_mean": kpi["building"]["w_ev_mean_riders_sec"],
        "rider_wait_mean": (sum(waits) / len(waits)) if waits else 0.0,
    }


RAW_FIELDS = [
    "scenario", "channel", "rng_seed", "floor_seed", "delivered", "wall_sec",
    *KPI_KEYS,
]


# ------------------------------------------------------------- run batteries

def run_channel(stem: str, floor_seed: int | None, channel: str,
                spot: bool) -> list[dict]:
    """30-seed sweep of one scenario. floor_seed=None -> default(=rng_seed)."""
    scenario_path = SCENARIO_DIR / f"{stem}.json"
    rows: list[dict] = []
    for seed in SEEDS:
        res = run_baseline(
            scenario_path=scenario_path, rng_seed=seed,
            floor_profile="uniform", floor_seed=floor_seed,
        )
        vals = kpi_values(res)
        row = {
            "scenario": stem, "channel": channel, "rng_seed": seed,
            "floor_seed": res["floor_seed"], "delivered": res["kpi_summary"]["customer"]["n_delivered"],
            "wall_sec": res["runtime_wall_sec"], **vals,
        }
        rows.append(row)
        if spot and seed in SPOT_SEEDS:
            report = verify_result(res)
            tag = "PASS" if report["all_passed"] else "FAIL"
            failed = [c.name for c in report["checks"] if not c.passed]
            print(f"    [gate {tag}] {stem} {channel} seed={seed}"
                  + ("" if report["all_passed"] else f"  failed={failed}"))
            if not report["all_passed"]:
                raise SystemExit(f"verify_h0 gate FAILED: {stem} seed={seed} {failed}")
    return rows


# --------------------------------------------------------------- statistics

def ci_stats(xs: list[float]) -> dict[str, float]:
    """mean, SD (n-1), 95% CI half-width (t), relative half-width %."""
    a = np.asarray(xs, dtype=float)
    n = len(a)
    mean = float(a.mean())
    sd = float(a.std(ddof=1)) if n > 1 else 0.0
    if n > 1:
        tcrit = float(stats.t.ppf(0.975, df=n - 1))
        half = tcrit * sd / np.sqrt(n)
    else:
        half = 0.0
    rel = (half / abs(mean) * 100.0) if mean != 0 else 0.0
    return {"n": n, "mean": mean, "sd": sd, "ci95_half": half, "ci95_rel_pct": rel}


def jackknife_se(xs: list[float]) -> float:
    """n-1 jackknife SE of the mean (seed-to-seed stability of per-run p95)."""
    a = np.asarray(xs, dtype=float)
    n = len(a)
    if n < 2:
        return 0.0
    total = a.sum()
    loo = (total - a) / (n - 1)            # leave-one-out means
    loo_bar = loo.mean()
    return float(np.sqrt((n - 1) / n * np.sum((loo - loo_bar) ** 2)))


# ----------------------------------------------------------------- summarize

SUMMARY_FIELDS = [
    "scenario", "kpi", "analysis", "n",
    "mean", "sd", "ci95_half", "ci95_rel_pct", "jackknife_se",
    "var_full", "var_ped_only", "ped_channel_var_ratio",
]


def summarize(raw: list[dict]) -> list[dict]:
    out: list[dict] = []
    by_key = {(r["scenario"], r["channel"]): [] for r in raw}
    for r in raw:
        by_key[(r["scenario"], r["channel"])].append(r)

    for stem in SCENARIOS:
        full = sorted(by_key[(stem, "full")], key=lambda r: r["rng_seed"])
        ped = sorted(by_key[(stem, "floor_pinned")], key=lambda r: r["rng_seed"])

        for kpi in KPI_KEYS:
            full_vals = [r[kpi] for r in full]

            # (1) CI + (2) convergence: first n = 10/20/30 seeds
            for n in CONV_NS:
                st = ci_stats(full_vals[:n])
                row = {
                    "scenario": stem, "kpi": kpi, "analysis": f"ci_n{n}", "n": n,
                    "mean": round(st["mean"], 4), "sd": round(st["sd"], 4),
                    "ci95_half": round(st["ci95_half"], 4),
                    "ci95_rel_pct": round(st["ci95_rel_pct"], 3),
                    "jackknife_se": "", "var_full": "", "var_ped_only": "",
                    "ped_channel_var_ratio": "",
                }
                # p95 seed-to-seed stability: jackknife SE at the full n=30 row
                if kpi == "t_e2e_p95" and n == max(CONV_NS):
                    row["jackknife_se"] = round(jackknife_se(full_vals[:n]), 4)
                out.append(row)

            # (3) variance-channel decomposition (both 30-seed samples)
            ped_vals = [r[kpi] for r in ped]
            var_full = float(np.var(full_vals, ddof=1)) if len(full_vals) > 1 else 0.0
            var_ped = float(np.var(ped_vals, ddof=1)) if len(ped_vals) > 1 else 0.0
            ratio = (var_ped / var_full) if var_full > 0 else None
            out.append({
                "scenario": stem, "kpi": kpi, "analysis": "channel", "n": len(SEEDS),
                "mean": "", "sd": "", "ci95_half": "", "ci95_rel_pct": "",
                "jackknife_se": "",
                "var_full": round(var_full, 6), "var_ped_only": round(var_ped, 6),
                "ped_channel_var_ratio": (None if ratio is None else round(ratio, 4)),
            })
    return out


# --------------------------------------------------------------------- io

def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def print_report(summary: list[dict]) -> None:
    for stem in SCENARIOS:
        print("\n" + "=" * 78)
        print(f"scenario {stem}")
        print("-" * 78)
        # CI + convergence table
        print(f"{'kpi':<16} {'n':>3} {'mean':>12} {'sd':>10} "
              f"{'ci95_half':>11} {'ci95_rel%':>10} {'jack_se':>9}")
        for r in summary:
            if r["scenario"] != stem or r["analysis"].startswith("channel"):
                continue
            print(f"{r['kpi']:<16} {r['n']:>3} {r['mean']:>12} {r['sd']:>10} "
                  f"{r['ci95_half']:>11} {r['ci95_rel_pct']:>10} "
                  f"{str(r['jackknife_se']):>9}")
        # channel decomposition table
        print(f"\n  channel decomposition (Var floor-pinned / Var full, 30 seeds):")
        print(f"  {'kpi':<16} {'var_full':>14} {'var_ped_only':>14} {'ped_ratio':>10}")
        for r in summary:
            if r["scenario"] != stem or r["analysis"] != "channel":
                continue
            print(f"  {r['kpi']:<16} {str(r['var_full']):>14} "
                  f"{str(r['var_ped_only']):>14} {str(r['ped_channel_var_ratio']):>10}")


def main() -> int:
    t0 = time.perf_counter()
    raw: list[dict] = []
    for stem in SCENARIOS:
        print(f"=== {stem}: full 2-channel sweep (floor_seed=rng_seed) ===")
        raw += run_channel(stem, floor_seed=None, channel="full", spot=True)
        print(f"=== {stem}: floor-pinned sweep (floor_seed={FLOOR_PIN}) ===")
        raw += run_channel(stem, floor_seed=FLOOR_PIN, channel="floor_pinned", spot=True)

    write_csv(OUT_RAW, RAW_FIELDS, raw)
    summary = summarize(raw)
    write_csv(OUT_SUMMARY, SUMMARY_FIELDS, summary)
    print_report(summary)

    wall = time.perf_counter() - t0
    total_run_wall = sum(r["wall_sec"] for r in raw)
    print("\n" + "=" * 78)
    print(f"V-VAR: {len(raw)} runs, script wall={wall:.1f}s ({wall/60:.1f} min), "
          f"sum(run wall)={total_run_wall:.1f}s")
    print(f"wrote {OUT_RAW} ({len(raw)} rows)")
    print(f"wrote {OUT_SUMMARY} ({len(summary)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
