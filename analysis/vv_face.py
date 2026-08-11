"""V-FACE — face-validity sanity checks (etc/plan_h0_verification.md §2 L5 item 2,
Stage V5b of the H0 verification plan).

    .venv/bin/python -m analysis.vv_face

Runs every scenario in the 28-file modelling corpus (primary 20 + extreme 8,
resolved via analysis.scenario_tiers) x 3 seeds through the paper track
(simulation.run.run_baseline: dynamic rider pool + scenario window +
floor_profile="uniform", all other args default), pools the per-order
records across all 84 runs, and checks four "does this look
right" properties that plain KPI aggregates don't surface on their own:

  1. stairs-by-floor   — vertical_mode == "stairs" share per floor; should be
                          ~0 on high floors (climbing 9 flights is dominated).
  2. T_e2e-by-floor slope — per-floor mean T_e2e should be (weakly) increasing
                          in floor number; flag only a *clear* reversal
                          (decrease beyond 2x the pooled standard error of the
                          adjacent-floor means), not sampling noise or ties.
  3. deadline slack distribution — slack_sec = deadline_abs_sec -
                          delivered_at_sec (>0 means delivered before the
                          deadline; this is exactly -(T_e2e - allowed_time),
                          consistent with CustomerAgent.sla_violation =
                          delivered_at_sec > dlv_deadline_sec). Explains the
                          plan's §0.3 fact 4 smoke observation (0% SLA
                          violations in all 3 smoke runs) directly from the
                          slack histogram/percentiles rather than just the
                          violation count.
  4. T_lobby-by-K sanity — mean T_lobby (minutes) per nominal K group. The v2
                          gate is the *direction* (in-building time must not
                          fall as demand rises, 2*SE noise tolerance); v1's
                          "K50 ~ 4.1 min" absolute anchor is retired to a
                          printed historical note, because it was measured on
                          the 2-EV / 800 m2 / no-basement building (plan §7)
                          and the absolute chain already has a proper oracle in
                          tests/test_vv_golden_path_v2.py.

Everything runs in-process (mirrors experiments/vv_all39.py's pattern):
run_baseline's return dict's "per_order" list is consumed directly, nothing
is written to disk except the four result CSVs + one histogram PNG in
results/vv/ (verification-run convention, plan §6). No existing file is
touched; no pytest, no model/config changes.

CORPUS REGIME CHANGE (사용자 확정 2026-08-03, 2차): K500/K750/K1000 (11 files)
are held out of the modelling corpus for this study. This script therefore runs
the 28-scenario corpus resolved via analysis.scenario_tiers.scenario_paths("all")
(primary 20 + extreme 8) instead of a raw data/data1/K*.json glob of 39 files.
The old V-DATA note about K1000_4 ≡ K1000_5 being byte-identical is moot here —
both are outside the corpus (duplicate detection lives in
analysis/vv_data_integrity.py).

Scope consequence: the K1000-only findings this script produced under the old
39-file regime (notably the SLA-slack CAUTION in the v1 report, whose violations
were all K1000) are no longer reproducible from its output, by design — that
demand range is out of scope, not merely unreported.
"""

from __future__ import annotations

import csv
import statistics
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless: write files, never open a window
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from analysis.scenario_tiers import scenario_paths as _tier_scenario_paths  # noqa: E402
from simulation.run import run_baseline  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SCENARIO_DIR = ROOT / "data" / "data1"
OUT_DIR = ROOT / "results" / "vv"

SEEDS = [42, 7, 2026]

STAIRS_HIGH_FLOOR_MIN = 7          # floors >= this are "high floor" for check 1
STAIRS_HIGH_FLOOR_RATIO_MAX = 0.01  # "~0" tolerance: 1%
TE2E_REVERSAL_Z = 2.0               # "clear reversal" = drop > Z * pooled SE
# v1's K50 T_lobby anchor. RETIRED as a gate in v2 (plan §7 — v1 figures come
# from a 2-EV / 800 m2 / 27 m-corridor / no-basement building); kept only so the
# report can print the historical value next to the current one. See
# check_tlobby_by_k for what replaced it.
V1_TLOBBY_K50_REFERENCE_MIN = 4.1


def _k_group(stem: str) -> str:
    """Nominal K group from a scenario stem, e.g. 'K1000_4' -> 'K1000'."""
    return stem.split("_")[0]


def _k_num(k: str) -> int:
    return int(k[1:])


# --------------------------------------------------------------- collection

def collect_orders() -> list[dict]:
    """Run all 28 corpus scenarios x 3 seeds in-process, pool per-order records."""
    scenarios = _tier_scenario_paths("all", SCENARIO_DIR)
    assert len(scenarios) == 28, f"expected 28 corpus scenarios, found {len(scenarios)}"

    orders: list[dict] = []
    for scenario_path in scenarios:
        stem = scenario_path.stem
        k_group = _k_group(stem)
        for seed in SEEDS:
            result = run_baseline(
                scenario_path=scenario_path,
                rng_seed=seed,
                floor_profile="uniform",
            )
            n_orders = result["kpi_summary"]["customer"]["n_orders"]
            n_delivered = result["kpi_summary"]["customer"]["n_delivered"]
            for rec in result["per_order"]:
                slack_sec = rec["deadline_abs_sec"] - rec["delivered_at_sec"]
                orders.append(
                    {
                        "scenario_stem": stem,
                        "k_group": k_group,
                        "seed": seed,
                        "ord_id": rec["ord_id"],
                        "floor": rec["floor"],
                        "vertical_mode": rec["vertical_mode"],
                        "t_e2e_sec": rec["t_e2e_sec"],
                        "t_lobby_sec": rec["t_lobby_sec"],
                        "slack_sec": slack_sec,
                        "sla_violation": rec["sla_violation"],
                    }
                )
            print(
                f"  {stem:<10} seed={seed:<5} delivered={n_delivered}/{n_orders} "
                f"records={len(result['per_order'])}"
            )
    return orders


# --------------------------------------------------------------- check 1

def check_stairs_by_floor(orders: list[dict]) -> tuple[list[dict], str, list[str]]:
    by_floor: dict[int, list[str]] = defaultdict(list)
    for o in orders:
        by_floor[o["floor"]].append(o["vertical_mode"])

    rows = []
    violations = []
    for floor in sorted(by_floor):
        modes = by_floor[floor]
        n_total = len(modes)
        n_stairs = sum(1 for m in modes if m == "stairs")
        ratio = n_stairs / n_total if n_total else None
        rows.append(
            {
                "floor": floor,
                "n_total": n_total,
                "n_stairs": n_stairs,
                "stairs_ratio": ratio,
            }
        )
        if floor >= STAIRS_HIGH_FLOOR_MIN and ratio is not None and ratio > STAIRS_HIGH_FLOOR_RATIO_MAX:
            violations.append(f"floor {floor}: stairs_ratio={ratio:.4f} > {STAIRS_HIGH_FLOOR_RATIO_MAX}")

    verdict = "FAIL" if violations else "PASS"
    return rows, verdict, violations


# --------------------------------------------------------------- check 2

def check_te2e_by_floor(orders: list[dict]) -> tuple[list[dict], str, list[str]]:
    by_floor: dict[int, list[float]] = defaultdict(list)
    for o in orders:
        if o["t_e2e_sec"] is not None:
            by_floor[o["floor"]].append(o["t_e2e_sec"])

    floors = sorted(by_floor)
    rows = []
    stats = {}
    for floor in floors:
        vals = by_floor[floor]
        n = len(vals)
        mean = statistics.fmean(vals)
        se = (statistics.pstdev(vals) / (n ** 0.5)) if n > 1 else 0.0
        stats[floor] = (mean, se, n)
        rows.append(
            {
                "floor": floor,
                "n": n,
                "t_e2e_mean_sec": mean,
                "t_e2e_mean_min": mean / 60.0,
                "se_sec": se,
            }
        )

    reversals = []
    ties_noise = []
    for a, b in zip(floors, floors[1:]):
        mean_a, se_a, _ = stats[a]
        mean_b, se_b, _ = stats[b]
        diff = mean_b - mean_a  # expect >= 0
        se_diff = (se_a ** 2 + se_b ** 2) ** 0.5
        if diff < 0:
            if abs(diff) > TE2E_REVERSAL_Z * se_diff:
                reversals.append(
                    f"floor {a}->{b}: mean {mean_a:.1f}s -> {mean_b:.1f}s "
                    f"(drop {abs(diff):.1f}s > {TE2E_REVERSAL_Z}*SE={TE2E_REVERSAL_Z * se_diff:.1f}s)"
                )
            else:
                ties_noise.append(
                    f"floor {a}->{b}: mean {mean_a:.1f}s -> {mean_b:.1f}s "
                    f"(drop {abs(diff):.1f}s within noise, SE={se_diff:.1f}s)"
                )

    if reversals:
        verdict = "FAIL"
    elif ties_noise:
        verdict = "CAUTION"
    else:
        verdict = "PASS"
    return rows, verdict, reversals + (["(noise-tolerant ties: " + "; ".join(ties_noise) + ")"] if ties_noise else [])


# --------------------------------------------------------------- check 3

def check_slack(orders: list[dict]) -> tuple[list[dict], str, str, list[float]]:
    all_slack = [o["slack_sec"] for o in orders]
    n = len(all_slack)
    n_violations = sum(1 for o in orders if o["sla_violation"])
    # cross-check: slack < 0 should exactly match sla_violation flag
    n_slack_neg = sum(1 for s in all_slack if s < 0)
    consistent = n_violations == n_slack_neg

    def _stats(vals: list[float]) -> dict:
        arr = np.asarray(vals, dtype=float)
        return {
            "n": len(arr),
            "min_sec": float(arr.min()),
            "p5_sec": float(np.percentile(arr, 5)),
            "p25_sec": float(np.percentile(arr, 25)),
            "median_sec": float(np.percentile(arr, 50)),
            "mean_sec": float(arr.mean()),
            "p95_sec": float(np.percentile(arr, 95)),
            "max_sec": float(arr.max()),
            "n_violations": int((arr < 0).sum()),
            "violation_rate": float((arr < 0).mean()),
        }

    rows = [{"group": "ALL", **_stats(all_slack)}]
    by_k: dict[str, list[float]] = defaultdict(list)
    for o in orders:
        by_k[o["k_group"]].append(o["slack_sec"])
    for k in sorted(by_k, key=_k_num):
        rows.append({"group": k, **_stats(by_k[k])})

    overall = rows[0]
    # "SLA slack too generous" flag: the deadline is essentially never binding
    # if the violation rate is negligible AND the 5th percentile of slack is
    # still comfortably positive. A handful of outlier violations at the top of
    # the demand range would not by themselves make the deadline a binding
    # constraint for the KPI as a whole.
    min_min = overall["min_sec"] / 60.0
    p5_min = overall["p5_sec"] / 60.0
    violation_rate = overall["violation_rate"]
    generous = violation_rate < 0.005 and p5_min > 5.0

    verdict = "CAUTION" if generous else "PASS"
    # The narrative here is DERIVED, never carried over. v1 reported 14 violations
    # in 40,350 orders, all of them K1000, and the v1 report's SLA CAUTION rested
    # on that. K1000 is outside this study's corpus (plan §0.4), so that finding
    # is not reproducible here by construction — restating it would be citing a
    # demand tier this battery never runs (plan §7). The worst K group below is
    # therefore read off the current run, whatever it turns out to be.
    worst = max((r for r in rows[1:]), key=lambda r: r["violation_rate"], default=None)
    if overall["n_violations"] == 0:
        where = (
            f"no order in the corpus missed its deadline (0/{n}); the tightest "
            f"margin anywhere was {min_min:.2f}min of slack"
        )
    else:
        where = (
            f"violations concentrate at {worst['group']} "
            f"({worst['n_violations']}/{worst['n']}, {worst['violation_rate']:.4%})"
        )
    note = (
        f"n={n}, violations={overall['n_violations']} ({violation_rate:.4%}), "
        f"min={min_min:.2f}min, p5={p5_min:.2f}min, mean={overall['mean_sec'] / 60.0:.2f}min. "
        f"slack<0 vs sla_violation flag consistent: {consistent} (n_slack_neg={n_slack_neg}). "
        f"plan §0.3 fact 4 smoke observation (0% SLA violations) came from 3 single-seed "
        f"smoke runs; over the full corpus battery {where}."
    )
    if generous:
        note += (
            " -> SLA slack is generous almost everywhere (violation rate < 0.5%, p5 > 5min): "
            "SLA / S_customer 판별력 문제 (deadline is not binding under current demand/config "
            "for the vast majority of orders; the SLA-violation and deadline-relative "
            "satisfaction KPIs will barely discriminate between H0 configurations unless "
            "deadlines are tightened or load is raised)."
        )
    return rows, verdict, note, all_slack


# --------------------------------------------------------------- check 4

def check_tlobby_by_k(orders: list[dict]) -> tuple[list[dict], str, list[str]]:
    """T_lobby face validity — v2 gate is the K direction, not the v1 absolute.

    v1 gated K50's mean T_lobby against a ~4.1 min reference. That number came
    from a 2-EV / 800 m2 / 27 m-corridor / no-basement building, so under plan
    §7 it cannot be a v2 oracle: the v2 changes push T_lobby in *opposite*
    directions (a 34 m corridor lengthens the in-building walk, four cars
    shorten the EV wait), and landing near 4.1 min would be a coincidence
    rather than a validation. The absolute geometry and kinematics already have
    a proper oracle — the hand-calculated constants in
    tests/test_vv_golden_path_v2.py (W2) — so duplicating that job here with a
    fitted band would add no detection power.

    What survives without any external reference is the *shape*: T_lobby must
    not fall as demand rises. That is gated below with the same 2*SE
    noise tolerance check 2 uses, so a tie or sampling wobble does not fail.
    The v1 figure is still printed, labelled, as history.
    """
    by_k: dict[str, list[float]] = defaultdict(list)
    for o in orders:
        if o["t_lobby_sec"] is not None:
            by_k[o["k_group"]].append(o["t_lobby_sec"])

    rows = []
    stats: dict[str, tuple[float, float]] = {}
    for k in sorted(by_k, key=_k_num):
        vals = by_k[k]
        mean_sec = statistics.fmean(vals)
        se = (statistics.pstdev(vals) / (len(vals) ** 0.5)) if len(vals) > 1 else 0.0
        stats[k] = (mean_sec, se)
        rows.append(
            {
                "k_group": k,
                "n": len(vals),
                "t_lobby_mean_sec": mean_sec,
                "t_lobby_mean_min": mean_sec / 60.0,
                "se_sec": se,
            }
        )

    notes = []
    verdict = "PASS"
    if not rows:
        return rows, "CAUTION", ["no T_lobby records pooled"]

    # --- gate: no clear decrease as K rises ---------------------------------
    groups = [r["k_group"] for r in rows]
    for a, b in zip(groups, groups[1:]):
        mean_a, se_a = stats[a]
        mean_b, se_b = stats[b]
        diff = mean_b - mean_a
        se_diff = (se_a ** 2 + se_b ** 2) ** 0.5
        if diff < 0 and abs(diff) > TE2E_REVERSAL_Z * se_diff:
            verdict = "FAIL"
            notes.append(
                f"{a}->{b}: T_lobby mean {mean_a:.1f}s -> {mean_b:.1f}s "
                f"(drop {abs(diff):.1f}s > {TE2E_REVERSAL_Z}*SE={TE2E_REVERSAL_Z * se_diff:.1f}s) "
                "— in-building time must not fall as demand rises"
            )
    first, last = rows[0], rows[-1]
    notes.append(
        f"{first['k_group']} ({first['t_lobby_mean_min']:.2f}min) -> "
        f"{last['k_group']} ({last['t_lobby_mean_min']:.2f}min): T_lobby "
        f"{'increases' if last['t_lobby_mean_sec'] > first['t_lobby_mean_sec'] else 'decreases/flat'} "
        "with K (gated, 2*SE noise tolerance)"
    )

    # --- history, not a gate -------------------------------------------------
    k50_row = next((r for r in rows if r["k_group"] == "K50"), None)
    if k50_row is not None:
        notes.append(
            f"K50 T_lobby mean={k50_row['t_lobby_mean_min']:.2f}min "
            f"(v1 reported ~{V1_TLOBBY_K50_REFERENCE_MIN}min on the 2-EV/800m2/"
            "no-basement building — printed as history, NOT a v2 pass/fail bound)"
        )

    return rows, verdict, notes


# --------------------------------------------------------------- CSV/PNG IO

def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_slack_hist(all_slack: list[float], path: Path) -> None:
    slack_min = np.asarray(all_slack, dtype=float) / 60.0
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(slack_min, bins=60, color="#4C72B0", edgecolor="none")
    ax.axvline(0.0, color="crimson", linewidth=1.2, linestyle="--", label="deadline (slack=0)")
    ax.set_xlabel("deadline slack = DLV_DEADLINE - delivered_at  [min]")
    ax.set_ylabel("order count")
    ax.set_title(
        f"V-FACE: deadline slack distribution (pooled, n={len(slack_min)}, "
        f"39 scenarios x {len(SEEDS)} seeds)"
    )
    ax.legend()
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=130)
    plt.close(fig)


# --------------------------------------------------------------- main

def main() -> int:
    print(f"V-FACE: collecting per-order records ({len(SEEDS)} seeds x 39 scenarios)...")
    orders = collect_orders()
    print(f"\npooled orders: {len(orders)}")

    stairs_rows, stairs_verdict, stairs_violations = check_stairs_by_floor(orders)
    _write_csv(OUT_DIR / "face_stairs_by_floor.csv", stairs_rows)

    te2e_rows, te2e_verdict, te2e_notes = check_te2e_by_floor(orders)
    _write_csv(OUT_DIR / "face_te2e_by_floor.csv", te2e_rows)

    slack_rows, slack_verdict, slack_note, all_slack = check_slack(orders)
    _write_csv(OUT_DIR / "face_slack.csv", slack_rows)
    _write_slack_hist(all_slack, OUT_DIR / "face_slack_hist.png")

    tlobby_rows, tlobby_verdict, tlobby_notes = check_tlobby_by_k(orders)
    _write_csv(OUT_DIR / "face_tlobby_by_k.csv", tlobby_rows)

    print("\n" + "=" * 78)
    print("V-FACE — face validity checks")
    print("=" * 78)

    print(f"\n[1] stairs-by-floor: {stairs_verdict}")
    for r in stairs_rows:
        flag = " <-- high-floor" if r["floor"] >= STAIRS_HIGH_FLOOR_MIN else ""
        print(
            f"    floor {r['floor']:>2}: n={r['n_total']:>6} stairs={r['n_stairs']:>5} "
            f"ratio={r['stairs_ratio']:.4f}{flag}"
        )
    if stairs_violations:
        for v in stairs_violations:
            print(f"    VIOLATION: {v}")

    print(f"\n[2] T_e2e-by-floor slope: {te2e_verdict}")
    for r in te2e_rows:
        print(f"    floor {r['floor']:>2}: n={r['n']:>6} mean={r['t_e2e_mean_min']:.2f}min (SE={r['se_sec']:.2f}s)")
    for note in te2e_notes:
        print(f"    {note}")

    print(f"\n[3] deadline slack distribution: {slack_verdict}")
    print(f"    {slack_note}")
    print("    by K group (min/p5/mean, minutes):")
    for r in slack_rows:
        print(
            f"      {r['group']:<8} n={r['n']:>6} min={r['min_sec']/60:.2f} p5={r['p5_sec']/60:.2f} "
            f"mean={r['mean_sec']/60:.2f} violations={r['n_violations']} ({r['violation_rate']:.4%})"
        )

    print(f"\n[4] T_lobby-by-K sanity: {tlobby_verdict}")
    for r in tlobby_rows:
        print(f"    {r['k_group']:<8} n={r['n']:>6} mean={r['t_lobby_mean_min']:.2f}min")
    for note in tlobby_notes:
        print(f"    {note}")

    print("\n" + "-" * 78)
    print(f"wrote {OUT_DIR / 'face_stairs_by_floor.csv'}")
    print(f"wrote {OUT_DIR / 'face_te2e_by_floor.csv'}")
    print(f"wrote {OUT_DIR / 'face_slack.csv'}")
    print(f"wrote {OUT_DIR / 'face_slack_hist.png'}")
    print(f"wrote {OUT_DIR / 'face_tlobby_by_k.csv'}")

    overall = {stairs_verdict, te2e_verdict, slack_verdict, tlobby_verdict}
    print(f"\noverall: stairs={stairs_verdict} te2e_slope={te2e_verdict} "
          f"slack={slack_verdict} tlobby={tlobby_verdict}")
    return 1 if "FAIL" in overall else 0


if __name__ == "__main__":
    raise SystemExit(main())
