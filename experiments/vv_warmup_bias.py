"""V21-NEW / WARMUP — is 600 s of warm-up enough? (head-only sweep)

    .venv/bin/python -m experiments.vv_warmup_bias

This is the measurement that justifies `warmup_sec: 600.0` in
`configs/baseline_10f.yaml` (R8-f) and the A13 warm-up-adequacy gate. It was run
ad hoc while designing R8 (etc/plan_h0v21_window.md §1.2); this module is its
reproducible form — the numbers in the plan and in
`etc/verification_report_h0v2.md` must come from here, not from a scratchpad.

**What it sweeps.** `simulation.warmup_sec` ∈ {0, 300, 600, 900, 1800, 3600,
7200} × 8 seeds × 2 scenarios (K100_1 mid, K300_4 high) = 112 runs, everything
else on the paper track (delivery policy, dynamic pool, floor_profile="uniform").

**Why the head moves alone here.** Under `window_policy: delivery` the tail is
anchored to the order data, not to the head: pedestrian spawning has no cutoff,
the cap is `max(ORD) + max_overrun_sec`, and termination fires on "all delivered
∧ all riders out". So `warmup_sec` is a pure head knob — the tail is fixed *by
construction*, and no manual pinning is needed.

    ⚠️ Do NOT reproduce this by sweeping `window_margin_sec` under
    `legacy_margin`. That knob sets the head AND the tail simultaneously
    (`ped_end = max(ORD) + margin`), so shrinking it also cuts background
    traffic off earlier, and late orders get delivered into an emptying
    building. The artefact reads as "longer warm-up ⇒ more congestion"
    (W_EV 23.0 → 16.6, −28% at margin 0) and it is entirely tail. This trap is
    the direct reason R8 abolished the pedestrian cutoff
    (plan_h0v21_window.md §1.2 함정 기록).

**How to read it.** The claim being tested is a *null*: delivery KPIs must show
no monotone trend in head length, with every level inside ±1 SE of the others.
`head_trend_max_z` per (scenario, KPI) is the largest |level mean − grand mean| /
SE — a small value is the finding. The warm-up state columns
(`util_at_first_order`, `peds_at_first_order`) do the opposite: they must rise
steeply from head=0 and flatten by 600 s, which is what A13 gates on.

Outputs: results/vv/warmup_bias.csv — run-level raw rows followed by a
per-(scenario, KPI, head) summary block.
"""

from __future__ import annotations

import copy
import csv
import statistics
import tempfile
import time
from pathlib import Path

import yaml

from simulation.run import run_baseline
from simulation.space import load_config

ROOT = Path(__file__).resolve().parent.parent
BASE_CONFIG = ROOT / "configs" / "baseline_10f.yaml"
OUT_CSV = ROOT / "results" / "vv" / "warmup_bias.csv"

# low/mid/high representatives of the 28-file corpus are K50_1/K200_1/K300_4;
# this sweep uses the mid and high rungs — the head effect is a warm-up-state
# question, and the low rung adds seeds' worth of noise, not signal.
SCENARIOS = ["K100_1", "K300_4"]
HEADS_SEC = [0.0, 300.0, 600.0, 900.0, 1800.0, 3600.0, 7200.0]
SEEDS = [1, 2, 3, 4, 5, 6, 7, 8]

# KPIs the null is about: if warm-up length mattered, these would move.
KPI_FIELDS = [
    ("t_e2e_mean_sec", "T_e2e mean (s)"),
    ("t_lobby_mean_sec", "T_lobby mean (s)"),
    ("w_ev_mean_sec", "W_EV mean (s)"),
    ("utilization_delivery_mean", "utilization_delivery"),
    ("utilization_orderspan_mean", "utilization_orderspan"),
]

RUN_FIELDS = [
    "scenario_stem", "seed", "warmup_sec", "K", "delivered",
    "t_e2e_mean_sec", "t_e2e_p95_sec", "t_lobby_mean_sec", "w_ev_mean_sec",
    "sla_violation_rate",
    "utilization_delivery_mean", "utilization_orderspan_mean",
    # warm-up state at the first order — the thing that is *supposed* to move
    "util_at_first_order", "peds_at_first_order", "peds_waiting_at_first_order",
    "ped_boardings_per_min", "warmup_ratio",
    # tail invariance evidence: these must not depend on the head
    "clock_start_sec", "ped_end_sec", "ticks", "termination_reason",
    "ped_n_spawned", "wall_sec",
]

SUMMARY_FIELDS = [
    "scenario_stem", "kpi", "kpi_label", "warmup_sec", "n_seeds",
    "mean", "sd", "sem", "dev_from_grand_mean", "z_vs_grand_mean",
]


def _write_head_configs(tmpdir: Path) -> dict[float, Path]:
    """One derived config per head length, all on the delivery policy."""
    base = load_config(BASE_CONFIG)
    assert base["simulation"]["window_policy"] == "delivery", (
        "this sweep is only meaningful under the delivery policy (tail anchored "
        f"to the orders); baseline declares {base['simulation'].get('window_policy')!r}"
    )
    paths: dict[float, Path] = {}
    for head in HEADS_SEC:
        cfg = copy.deepcopy(base)
        cfg["simulation"]["warmup_sec"] = head
        p = tmpdir / f"warmup_{int(head)}.yaml"
        with p.open("w", encoding="utf-8") as f:
            yaml.safe_dump(cfg, f, sort_keys=False, allow_unicode=True)
        paths[head] = p
    return paths


def _mean_over_cars(elevator: dict, field: str) -> float:
    vals = [ev[field] for ev in elevator.values() if ev[field] is not None]
    return sum(vals) / len(vals) if vals else 0.0


def _extract(result: dict) -> dict:
    kpi = result["kpi_summary"]
    sim = kpi["simulation"]
    warm = sim.get("warmup") or {}
    util_delivery = _mean_over_cars(kpi["elevator"], "utilization_delivery")
    util_first = warm.get("util_at_first_order")
    return {
        "K": kpi["customer"]["n_orders"],
        "delivered": kpi["customer"]["n_delivered"],
        "t_e2e_mean_sec": kpi["customer"]["t_e2e_mean_sec"],
        "t_e2e_p95_sec": kpi["customer"]["t_e2e_p95_sec"],
        "t_lobby_mean_sec": kpi["rider"]["t_lobby_mean_sec"],
        "w_ev_mean_sec": kpi["building"]["w_ev_mean_riders_sec"],
        "sla_violation_rate": kpi["customer"]["sla_violation_rate"],
        "utilization_delivery_mean": util_delivery,
        "utilization_orderspan_mean": _mean_over_cars(kpi["elevator"], "utilization_orderspan"),
        "util_at_first_order": util_first,
        "peds_at_first_order": warm.get("peds_at_first_order"),
        "peds_waiting_at_first_order": warm.get("peds_waiting_at_first_order"),
        "ped_boardings_per_min": warm.get("ped_boardings_per_min"),
        # the A13-② statistic itself, recomputed here so the CSV shows the
        # quantity the gate compares against WARMUP_RATIO_FLOOR.
        "warmup_ratio": (
            None if (util_first is None or util_delivery == 0)
            else util_first / util_delivery
        ),
        "clock_start_sec": sim["clock_start_sec"],
        "ped_end_sec": sim["ped_window_sec"][1],
        "ticks": sim["ticks"],
        "termination_reason": sim.get("termination_reason"),
        "ped_n_spawned": kpi["pedestrian"]["n_spawned"],
        "wall_sec": result["runtime_wall_sec"],
    }


def run_sweep(head_configs: dict[float, Path]) -> list[dict]:
    rows: list[dict] = []
    for stem in SCENARIOS:
        scenario_path = ROOT / "data" / "data1" / f"{stem}.json"
        for head in HEADS_SEC:
            for seed in SEEDS:
                result = run_baseline(
                    config_path=head_configs[head],
                    scenario_path=scenario_path,
                    rng_seed=seed,
                    floor_profile="uniform",
                )
                row = {"scenario_stem": stem, "seed": seed, "warmup_sec": head,
                       **_extract(result)}
                rows.append(row)
            last = rows[-1]
            level = [r for r in rows
                     if r["scenario_stem"] == stem and r["warmup_sec"] == head]
            print(
                f"[{stem:<8} head={int(head):>4}s] "
                f"W_EV={statistics.fmean(r['w_ev_mean_sec'] for r in level):6.2f}s "
                f"util_deliv={statistics.fmean(r['utilization_delivery_mean'] for r in level):.4f} "
                f"util@first={statistics.fmean(r['util_at_first_order'] for r in level):.4f} "
                f"ped_end={last['ped_end_sec']:.0f}"
            )
    return rows


def summarize(rows: list[dict]) -> list[dict]:
    """Per (scenario, KPI, head): level mean and its distance from the grand mean.

    `z_vs_grand_mean` = |level mean − grand mean| / SEM(level). The null this
    experiment tests is "all levels agree", so small z across every head is the
    result; a monotone ladder in the means would be the refutation.
    """
    out: list[dict] = []
    for stem in SCENARIOS:
        for field, label in KPI_FIELDS:
            all_vals = [r[field] for r in rows
                        if r["scenario_stem"] == stem and r[field] is not None]
            grand = statistics.fmean(all_vals) if all_vals else 0.0
            for head in HEADS_SEC:
                vals = [r[field] for r in rows
                        if r["scenario_stem"] == stem
                        and r["warmup_sec"] == head and r[field] is not None]
                if not vals:
                    continue
                mean = statistics.fmean(vals)
                sd = statistics.stdev(vals) if len(vals) > 1 else 0.0
                sem = sd / (len(vals) ** 0.5) if vals else 0.0
                dev = mean - grand
                out.append({
                    "scenario_stem": stem, "kpi": field, "kpi_label": label,
                    "warmup_sec": head, "n_seeds": len(vals),
                    "mean": round(mean, 6), "sd": round(sd, 6),
                    "sem": round(sem, 6), "dev_from_grand_mean": round(dev, 6),
                    "z_vs_grand_mean": (round(abs(dev) / sem, 3) if sem > 0 else None),
                })
    return out


def write_csv(rows: list[dict], summary: list[dict]) -> None:
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=RUN_FIELDS)
        w.writeheader()
        w.writerows(rows)
        f.write("\n")
        w2 = csv.DictWriter(f, fieldnames=SUMMARY_FIELDS)
        w2.writeheader()
        w2.writerows(summary)


def print_report(rows: list[dict], summary: list[dict]) -> None:
    for stem in SCENARIOS:
        print("\n" + "=" * 92)
        print(f"{stem}: delivery KPIs vs warm-up head "
              f"(n={len(SEEDS)} seeds/level; tail fixed by the delivery policy)")
        print("=" * 92)
        head_cols = "".join(f"{int(h):>10}" for h in HEADS_SEC)
        print(f"{'kpi':<24}{head_cols}{'max z':>9}")
        print("-" * (24 + 10 * len(HEADS_SEC) + 9))
        for field, label in KPI_FIELDS:
            cells = ""
            zs = []
            for head in HEADS_SEC:
                r = next((s for s in summary
                          if s["scenario_stem"] == stem and s["kpi"] == field
                          and s["warmup_sec"] == head), None)
                cells += "       n/a" if r is None else f"{r['mean']:>10.3f}"
                if r is not None and r["z_vs_grand_mean"] is not None:
                    zs.append(r["z_vs_grand_mean"])
            print(f"{label:<24}{cells}{(max(zs) if zs else 0):>9.2f}")

        print("\n  warm-up state at the first order (must rise, then flatten):")
        print(f"  {'head (s)':>9} {'util@first':>11} {'ratio A13-②':>13} "
              f"{'peds':>6} {'ped_end (s)':>13} {'ticks':>8}")
        for head in HEADS_SEC:
            level = [r for r in rows
                     if r["scenario_stem"] == stem and r["warmup_sec"] == head]
            ratios = [r["warmup_ratio"] for r in level if r["warmup_ratio"] is not None]
            print(f"  {int(head):>9} "
                  f"{statistics.fmean(r['util_at_first_order'] for r in level):>11.4f} "
                  f"{(statistics.fmean(ratios) if ratios else 0.0):>13.4f} "
                  f"{statistics.fmean(r['peds_at_first_order'] for r in level):>6.1f} "
                  f"{level[0]['ped_end_sec']:>13.0f} "
                  f"{statistics.fmean(r['ticks'] for r in level):>8.0f}")


def check_tail_invariance(rows: list[dict]) -> bool:
    """The head knob must not move the tail — otherwise we are back in the trap."""
    ok = True
    for stem in SCENARIOS:
        ends = {r["ped_end_sec"] for r in rows if r["scenario_stem"] == stem}
        if len(ends) != 1:
            ok = False
            print(f"[FAIL] {stem}: ped_end moved with the head — {sorted(ends)}")
        else:
            print(f"[PASS] {stem}: ped_end fixed at {ends.pop():.0f}s across all heads")
    return ok


def main() -> int:
    t0 = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="vv_warmup_bias_") as td:
        rows = run_sweep(_write_head_configs(Path(td)))
    summary = summarize(rows)
    write_csv(rows, summary)
    print_report(rows, summary)
    print()
    ok = check_tail_invariance(rows)
    wall = time.perf_counter() - t0
    print(f"\nwrote {OUT_CSV} ({len(rows)} run rows + {len(summary)} summary rows)")
    print(f"total wall time: {wall:.1f}s ({wall / 60:.1f} min)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
