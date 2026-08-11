"""V-ALL39 — full-corpus completion battery (etc/plan_h0_verification.md §2 L7).

    .venv/bin/python -m experiments.vv_all39

NAME HISTORY: this script is still called "vv_all39" (kept unrenamed --
too many cross-references in plan/report docs) but no longer runs 39
scenarios. Regime change 사용자 확정 2026-08-03 (2차): K500/K750/K1000 (11
files) are now held out of the modelling corpus for this study (see
analysis/scenario_tiers.py, configs/scenario_tiers.yaml). This script now
runs the 28-scenario modelling corpus (primary 20 + extreme 8), resolved via
analysis.scenario_tiers.scenario_paths("all") rather than a raw
data/data1/K*.json glob, x 3 fixed seeds through the paper track
(simulation.run.run_baseline: dynamic rider pool + scenario window +
floor_profile="uniform", all other args default) and gates each of the 84
runs through analysis.verify_h0's A1..A9 checks. This is a completion
battery for experiment-budget sizing (per-K wall time), not a unit test, so
it is a standalone script rather than a pytest module — 84 in-process model
runs would dominate the suite's runtime.

Everything runs in-process (no subprocess/CLI, no per-run JSON written to
disk): run_baseline's return dict is handed straight to
analysis.verify_h0.verify_result. Only the aggregate CSV report is persisted,
to results/vv/all39_battery.csv (verification-run convention, plan §6;
filename kept for the same reason as the module name).

Historical note (V-DATA, etc/plan_h0_verification.md L7): data/data1/
K1000_4.json and K1000_5.json were byte-for-byte identical (md5 match) --
that was a known scenario-data duplicate within the old 39-file corpus, not
a bug in this script. Both K1000 files (and the rest of the K1000/K750/K500
group) are outside the corpus entirely now, so the duplicate is moot here --
see analysis/vv_data_integrity.py for where the duplicate-detection logic
itself lives.
"""

from __future__ import annotations

import csv
import time
from pathlib import Path

from analysis.scenario_tiers import scenario_paths as _tier_scenario_paths
from analysis.verify_h0 import verify_result
from simulation.run import run_baseline

ROOT = Path(__file__).resolve().parent.parent
SCENARIO_DIR = ROOT / "data" / "data1"
OUT_CSV = ROOT / "results" / "vv" / "all39_battery.csv"

SEEDS = [42, 7, 2026]
AUDIT_SEED = 42          # tick-level audit sweep covers the corpus at one seed

FIELDNAMES = [
    "scenario_stem", "K", "seed", "delivered",
    "wall_sec", "verify_sec", "all_passed", "failed_checks",
    "skipped_checks", "audit", "a4_min_slack_sec", "a9_gof_p",
]


def _k_group(stem: str) -> str:
    """Nominal K group from a scenario stem, e.g. 'K1000_4' -> 'K1000'."""
    return stem.split("_")[0]


def run_battery(seeds: list[int] | None = None, audit: bool = False) -> list[dict]:
    """Run the corpus x seeds through the A1..A12 gate.

    `audit=True` turns on the model's tick-level asserts (rider conservation,
    car capacity, A12 hall-call exclusivity, A10-2 no rider below ground). Those
    are the only enforcement A12 has -- the post-hoc check reports SKIPPED
    because a results JSON records queue lengths, not membership. It is off by
    default so `wall_sec` stays a clean per-run cost estimate for experiment
    budgeting; the audit sweep is run separately (see main()).
    """
    seeds = SEEDS if seeds is None else seeds
    scenarios = _tier_scenario_paths("all", data_dir=SCENARIO_DIR)
    assert len(scenarios) == 28, f"expected 28 scenarios, found {len(scenarios)}"

    rows: list[dict] = []
    for scenario_path in scenarios:
        stem = scenario_path.stem
        for seed in seeds:
            result = run_baseline(
                scenario_path=scenario_path,
                rng_seed=seed,
                floor_profile="uniform",
                audit=audit,
            )
            t_verify0 = time.perf_counter()
            report = verify_result(result)
            verify_sec = time.perf_counter() - t_verify0

            kpi = result["kpi_summary"]
            failed = [c.name for c in report["checks"] if not c.passed]
            skipped = [c.name for c in report["checks"] if c.skipped]
            a4 = report.get("a4_slack") or {}
            gof = report.get("a9_gof") or {}

            row = {
                "scenario_stem": stem,
                "K": kpi["customer"]["n_orders"],
                "seed": seed,
                "delivered": kpi["customer"]["n_delivered"],
                "wall_sec": result["runtime_wall_sec"],
                "verify_sec": round(verify_sec, 3),
                "all_passed": report["all_passed"],
                "failed_checks": ";".join(failed),
                "skipped_checks": ";".join(skipped),
                "audit": audit,
                "a4_min_slack_sec": a4.get("slack_min_sec"),
                "a9_gof_p": gof.get("p_value"),
            }
            rows.append(row)

            tag = "PASS" if report["all_passed"] else "FAIL"
            print(
                f"[{tag}] {stem:<10} seed={seed:<5} "
                f"delivered={row['delivered']}/{row['K']} "
                f"wall={row['wall_sec']:.2f}s verify={row['verify_sec']:.2f}s"
                + ("" if report["all_passed"] else f"  failed={failed}")
            )

    return rows


def write_csv(rows: list[dict]) -> None:
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def summarize(rows: list[dict]) -> bool:
    n = len(rows)
    n_pass = sum(1 for r in rows if r["all_passed"])
    fails = [r for r in rows if not r["all_passed"]]

    print("\n" + "=" * 72)
    print(f"V-ALL39 battery: {n} runs, {n_pass} passed, {len(fails)} failed")
    if fails:
        print("FAILING runs:")
        for r in fails:
            print(f"  - {r['scenario_stem']} seed={r['seed']}: {r['failed_checks']}")

    # per-K-group wall time (wall_sec = run only, per plan spec; not verify)
    groups: dict[str, list[float]] = {}
    for r in rows:
        groups.setdefault(_k_group(r["scenario_stem"]), []).append(r["wall_sec"])

    def k_num(k: str) -> int:
        return int(k[1:])

    print("\nPer-K-group wall time (run only, seconds):")
    total_wall = 0.0
    for k in sorted(groups, key=k_num):
        vals = groups[k]
        total_wall += sum(vals)
        print(f"  {k:<8} n={len(vals):<3} mean={sum(vals) / len(vals):8.2f}s "
              f"min={min(vals):7.2f}s max={max(vals):7.2f}s")
    print(f"\nTotal run wall time (all {n} runs): {total_wall:.1f}s "
          f"({total_wall / 60:.1f} min)")

    return not fails


def main() -> int:
    """Battery (clean wall times) + a single-seed audit sweep for A12.

    Two passes rather than one audited pass: `wall_sec` feeds experiment-budget
    sizing, so the headline numbers must not carry audit overhead. The audit
    sweep covers the whole corpus at one seed, which is what makes the A12 /
    A10-2 tick-level asserts a claim about the corpus rather than about one run.
    """
    rows = run_battery()
    audit_rows = run_battery(seeds=[AUDIT_SEED], audit=True)
    write_csv(rows + audit_rows)
    all_passed = summarize(rows)
    audit_passed = all(r["all_passed"] for r in audit_rows)
    print(
        f"\naudit sweep (seed {AUDIT_SEED}, tick-level A12/A10-2 asserts): "
        f"{sum(1 for r in audit_rows if r['all_passed'])}/{len(audit_rows)} passed"
    )
    print(f"wrote {OUT_CSV} ({len(rows) + len(audit_rows)} rows)")
    return 0 if (all_passed and audit_passed) else 1


if __name__ == "__main__":
    raise SystemExit(main())
