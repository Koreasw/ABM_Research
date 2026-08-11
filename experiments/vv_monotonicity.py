"""V-MONO — monotonicity direction battery (Stage V4b, etc/plan_h0_verification.md §2 L4).

    .venv/bin/python -m experiments.vv_monotonicity

Checks 6 expected monotone directions of the paper-track model (dynamic
rider pool + scenario window + floor_profile="uniform", all other args
default — same track as experiments/vv_all39.py) at a low/high parameter
level, 10 fixed seeds per level (seeds 1..10), gate = weak inequality
(>=/<=) on the **10-seed mean**. A direction FAILs iff the mean moves the
wrong way; an exact tie (mean_low == mean_high) still PASSes and is marked
"tie" in the table (plan §2 L4 gate wording).

Directions (see module docstring below each runner for the closed-form
parameter/metric choice):
  1. pedestrian arrival_rate_per_min 6->18       => W_EV, T_e2e up
  2. elevator.max_speed_mps 2.5->5.0             => T_e2e down
  3. rider_process.walk_speed_mps 1.2->1.8       => T_lobby down
  4. RIDERS available_number (1,1,1)->orig(10,15,50) => rider_wait, fallback down
  5. return_leg OFF->ON (tight pool 1,1,1)       => rider_wait up (fallback: informational)
  6. K50_1 -> K200_1 -> K300_4 (same seed set)  => W_EV up

Scenario choice (plan §2 L4 note): all directions use K50_1 as the base
scenario, including direction 1. A 3-seed pretest at K50_1 already showed a
clean monotone increase in both W_EV and T_e2e when arrival_rate_per_min
went 6->18 (v1 pretest, 2 EVs / no basements: W_EV ~28 -> ~58 s, T_e2e
~1587 -> ~1628 s; the v2 10-seed re-run of W4b gives 18.29 -> 58.77 s and
1579.69 -> 1621.74 s — same direction, lower low-level W_EV because 4 cars
absorb the 6/min load that 2 could not. The v1 figures are kept as the
record of why K50_1 was chosen, and must not be cited as a v2 result) —
K300_4 was also
tried and shows the same direction (and larger magnitude), but K50_1 is
cheaper and keeps the design matrix uniform across directions 1-5, so no
need to escalate to K300_4. Direction 6 is exactly the 3 scenarios named in
the plan, updated for the 28-file corpus (K50_1, K200_1, K300_4 — K1000_1 is
out of corpus for this study per 사용자 확정 2026-08-03 2차, so the top rung moves
down to K300_4 and K200_1 fills the middle to keep three ascending K levels),
same 10-seed set.

Direction 5 caveat (found during pretesting, documented rather than
"fixed" per task instructions): at the tight 1/1/1 pool, return_leg ON
raises mean rider_wait_sec (as expected — riders are busy longer, so the
finite pool is more congested) but *lowers* raw fallback-substitution count.
Cause: RiderPool.was_fallback flags a dispatch where the assigned type was
not the cost-optimal (rank-0) type for that order; a FIFO-queued order that
finally gets served *specifically because the rank-0 type freed up* is not
flagged "fallback" even though it waited a long time in queue. Under
return_leg the queue is deeper, so more releases end up serving the
longest-waiting order with the type that just freed (often ends up being
rank-0 by the time its turn comes), lowering the raw fallback count while
raising the actual wait congestion. The plan explicitly allows either
"fallback(또는 rider_wait)" as the gate metric — this script gates on
rider_wait_sec (the metric that behaves as the plan's causal story
predicts: tighter effective supply -> more waiting) and reports fallback
count as informational only (not gated) for direction 5.

Config/scenario overrides never touch the checked-in files: every
low/high level is materialized as a tmp YAML (config) or tmp JSON
(scenario, for the RIDERS available_number rows) copy under a throwaway
tempfile.TemporaryDirectory, mirroring the config-dict-override pattern in
tests/test_vv_golden_path.py (there it's an in-memory dict passed straight
to BuildingHandoffModel; here run_baseline only accepts a config **path**,
so the dict is written to a tmp file instead).

Output: console table (per direction: level means, delta, %, verdict) +
results/vv/monotonicity.csv (plan §6 vv/ convention). Exit code 0 iff every
direction's gated metric(s) PASS or TIE (no FAIL).
"""

from __future__ import annotations

import csv
import json
import tempfile
import time
from pathlib import Path
from typing import Any

import yaml

from simulation.run import run_baseline
from simulation.space import load_config

ROOT = Path(__file__).resolve().parent.parent
BASE_CONFIG = ROOT / "configs" / "baseline_10f.yaml"
SCENARIO_DIR = ROOT / "data" / "data1"
OUT_CSV = ROOT / "results" / "vv" / "monotonicity.csv"

SEEDS = list(range(1, 11))  # 10 seeds, plan §2 L4

FIELDNAMES = [
    "direction", "description", "scenario", "param", "metric", "gate",
    "level_a_label", "level_a_value", "level_a_mean", "level_a_n",
    "level_b_label", "level_b_value", "level_b_mean", "level_b_n",
    "delta", "pct_change", "expected", "verdict",
]


# ------------------------------------------------------------- tmp helpers

def make_cfg(tmpdir: Path, overrides: dict[tuple[str, str], Any]) -> Path:
    """baseline_10f.yaml + nested (section, key) -> value overrides, as a tmp copy."""
    cfg = load_config(BASE_CONFIG)
    for (section, key), value in overrides.items():
        cfg[section][key] = value
    tag = "_".join(f"{s}.{k}={v}" for (s, k), v in overrides.items())
    p = tmpdir / f"cfg_{tag}.yaml"
    p.write_text(yaml.safe_dump(cfg))
    return p


def make_scenario_pool(tmpdir: Path, stem: str, counts: tuple[int, int, int]) -> Path:
    """Scenario JSON copy with RIDERS available_number (column 6) forced to counts."""
    src = SCENARIO_DIR / f"{stem}.json"
    d = json.loads(src.read_text())
    for row, c in zip(d["RIDERS"], counts):
        row[6] = c
    p = tmpdir / f"{stem}_pool_{'_'.join(map(str, counts))}.json"
    p.write_text(json.dumps(d))
    return p


# ------------------------------------------------------------- run + metrics

def compute_metrics(result: dict) -> dict[str, float | None]:
    kpi = result["kpi_summary"]
    orders = result["per_order"]
    waits = [o["rider_wait_sec"] for o in orders if o.get("rider_wait_sec") is not None]
    fb_series = result["model_vars"].get("fallback_cum")
    fallback_cum = (
        float(fb_series[-1]) if fb_series
        else float(sum(1 for o in orders if o.get("was_fallback")))
    )
    return {
        "w_ev_mean": kpi["building"]["w_ev_mean_riders_sec"],
        "t_e2e_mean": kpi["customer"]["t_e2e_mean_sec"],
        "t_lobby_mean": kpi["rider"]["t_lobby_mean_sec"],
        "rider_wait_mean": (sum(waits) / len(waits)) if waits else 0.0,
        "fallback_cum": fallback_cum,
    }


def run_seeds(config_path: Path, scenario_path: Path, seeds: list[int],
              return_leg: bool = False) -> list[dict[str, float | None]]:
    rows = []
    for seed in seeds:
        res = run_baseline(
            config_path=config_path, scenario_path=scenario_path,
            rng_seed=seed, floor_profile="uniform", return_leg=return_leg,
        )
        rows.append(compute_metrics(res))
    return rows


def mean_of(rows: list[dict[str, float | None]], key: str) -> float | None:
    vals = [r[key] for r in rows if r[key] is not None]
    return sum(vals) / len(vals) if vals else None


# ------------------------------------------------------------- judging

def judge(mean_a: float | None, mean_b: float | None, expect: str) -> str:
    """expect='increase': b should be >= a. expect='decrease': b should be <= a."""
    if mean_a is None or mean_b is None:
        return "FAIL"
    delta = mean_b - mean_a
    eps = 1e-9
    if expect == "increase":
        if delta > eps:
            return "PASS"
        return "tie" if abs(delta) <= eps else "FAIL"
    else:  # decrease
        if delta < -eps:
            return "PASS"
        return "tie" if abs(delta) <= eps else "FAIL"


def make_row(direction: int, description: str, scenario: str, param: str, metric: str,
             gate: bool, label_a: str, value_a: Any, mean_a: float | None, n_a: int,
             label_b: str, value_b: Any, mean_b: float | None, n_b: int,
             expect: str) -> dict:
    delta = (mean_b - mean_a) if (mean_a is not None and mean_b is not None) else None
    pct = (delta / mean_a * 100) if (delta is not None and mean_a) else None
    verdict = judge(mean_a, mean_b, expect) if gate else "info"
    return {
        "direction": direction, "description": description, "scenario": scenario,
        "param": param, "metric": metric, "gate": gate,
        "level_a_label": label_a, "level_a_value": value_a,
        "level_a_mean": mean_a, "level_a_n": n_a,
        "level_b_label": label_b, "level_b_value": value_b,
        "level_b_mean": mean_b, "level_b_n": n_b,
        "delta": delta, "pct_change": pct, "expected": expect, "verdict": verdict,
    }


# ------------------------------------------------------------- directions

def direction_1(tmpdir: Path) -> list[dict]:
    """Pedestrian arrival rate 6->18 /min => W_EV, T_e2e up (K50_1)."""
    scenario = SCENARIO_DIR / "K50_1.json"
    rows_low = run_seeds(
        make_cfg(tmpdir, {("pedestrian", "arrival_rate_per_min"): 6.0}), scenario, SEEDS)
    rows_high = run_seeds(
        make_cfg(tmpdir, {("pedestrian", "arrival_rate_per_min"): 18.0}), scenario, SEEDS)
    out = []
    for metric in ("w_ev_mean", "t_e2e_mean"):
        out.append(make_row(
            1, "ped rate up -> W_EV, T_e2e up", "K50_1", "pedestrian.arrival_rate_per_min",
            metric, True, "low", 6.0, mean_of(rows_low, metric), len(SEEDS),
            "high", 18.0, mean_of(rows_high, metric), len(SEEDS), "increase"))
    return out


def direction_2(tmpdir: Path) -> list[dict]:
    """EV max speed 2.5->5.0 m/s => T_e2e down (K50_1)."""
    scenario = SCENARIO_DIR / "K50_1.json"
    rows_low = run_seeds(
        make_cfg(tmpdir, {("elevator", "max_speed_mps"): 2.5}), scenario, SEEDS)
    rows_high = run_seeds(
        make_cfg(tmpdir, {("elevator", "max_speed_mps"): 5.0}), scenario, SEEDS)
    return [make_row(
        2, "EV speed up -> T_e2e down", "K50_1", "elevator.max_speed_mps",
        "t_e2e_mean", True, "low", 2.5, mean_of(rows_low, "t_e2e_mean"), len(SEEDS),
        "high", 5.0, mean_of(rows_high, "t_e2e_mean"), len(SEEDS), "decrease")]


def direction_3(tmpdir: Path) -> list[dict]:
    """rider_process.walk_speed_mps 1.2->1.8 => T_lobby down (K50_1)."""
    scenario = SCENARIO_DIR / "K50_1.json"
    rows_low = run_seeds(
        make_cfg(tmpdir, {("rider_process", "walk_speed_mps"): 1.2}), scenario, SEEDS)
    rows_high = run_seeds(
        make_cfg(tmpdir, {("rider_process", "walk_speed_mps"): 1.8}), scenario, SEEDS)
    return [make_row(
        3, "walk speed up -> T_lobby down", "K50_1", "rider_process.walk_speed_mps",
        "t_lobby_mean", True, "low", 1.2, mean_of(rows_low, "t_lobby_mean"), len(SEEDS),
        "high", 1.8, mean_of(rows_high, "t_lobby_mean"), len(SEEDS), "decrease")]


def direction_4(tmpdir: Path) -> list[dict]:
    """RIDERS available_number (1,1,1) -> original (10,15,50) => rider_wait, fallback down."""
    stem = "K50_1"
    scenario_low = make_scenario_pool(tmpdir, stem, (1, 1, 1))
    scenario_high = SCENARIO_DIR / f"{stem}.json"  # original stock, no override needed
    cfg = BASE_CONFIG
    rows_low = run_seeds(cfg, scenario_low, SEEDS)
    rows_high = run_seeds(cfg, scenario_high, SEEDS)
    out = []
    for metric in ("rider_wait_mean", "fallback_cum"):
        out.append(make_row(
            4, "pool stock up -> rider_wait, fallback down", stem, "RIDERS.available_number",
            metric, True, "low(1,1,1)", "1,1,1", mean_of(rows_low, metric), len(SEEDS),
            "high(orig)", "10,15,50", mean_of(rows_high, metric), len(SEEDS), "decrease"))
    return out


def direction_5(tmpdir: Path) -> list[dict]:
    """return_leg OFF->ON at tight pool (1,1,1) => rider_wait up (fallback: informational)."""
    stem = "K50_1"
    scenario = make_scenario_pool(tmpdir, stem, (1, 1, 1))
    cfg = BASE_CONFIG
    rows_off = run_seeds(cfg, scenario, SEEDS, return_leg=False)
    rows_on = run_seeds(cfg, scenario, SEEDS, return_leg=True)
    out = [make_row(
        5, "return_leg ON -> rider_wait up (tight pool)", stem + " pool(1,1,1)",
        "return_leg", "rider_wait_mean", True, "off", False,
        mean_of(rows_off, "rider_wait_mean"), len(SEEDS), "on", True,
        mean_of(rows_on, "rider_wait_mean"), len(SEEDS), "increase")]
    out.append(make_row(
        5, "return_leg ON -> fallback up (informational, see module docstring)",
        stem + " pool(1,1,1)", "return_leg", "fallback_cum", False, "off", False,
        mean_of(rows_off, "fallback_cum"), len(SEEDS), "on", True,
        mean_of(rows_on, "fallback_cum"), len(SEEDS), "increase"))
    return out


def direction_6() -> list[dict]:
    """K50_1 -> K200_1 -> K300_4 (same 10 seeds) => W_EV up, pairwise."""
    stems = ["K50_1", "K200_1", "K300_4"]
    cfg = BASE_CONFIG
    means = {}
    for stem in stems:
        rows = run_seeds(cfg, SCENARIO_DIR / f"{stem}.json", SEEDS)
        means[stem] = mean_of(rows, "w_ev_mean")
    out = []
    for a, b in zip(stems, stems[1:]):
        out.append(make_row(
            6, f"K up ({a}->{b}) -> W_EV up", f"{a}->{b}", "K (scenario)",
            "w_ev_mean", True, a, a, means[a], len(SEEDS),
            b, b, means[b], len(SEEDS), "increase"))
    return out


# ------------------------------------------------------------- report

def print_rows(rows: list[dict]) -> None:
    for r in rows:
        gate_tag = "" if r["gate"] else " [info]"
        a = r["level_a_mean"]
        b = r["level_b_mean"]
        pct = r["pct_change"]
        print(
            f"[dir{r['direction']}] {r['metric']:<16} "
            f"{r['level_a_label']:>10}={a if a is None else round(a, 2):<10} "
            f"{r['level_b_label']:>10}={b if b is None else round(b, 2):<10} "
            f"delta={r['delta'] if r['delta'] is None else round(r['delta'], 2):<10} "
            f"pct={'n/a' if pct is None else f'{pct:+.1f}%':<8} "
            f"-> {r['verdict'].upper()}{gate_tag}"
        )


def overall_verdicts(rows: list[dict]) -> dict[int, str]:
    """Per-direction verdict from gated rows only: FAIL > tie > PASS."""
    result: dict[int, str] = {}
    for r in rows:
        if not r["gate"]:
            continue
        d = r["direction"]
        v = r["verdict"]
        cur = result.get(d, "PASS")
        if v == "FAIL" or cur == "FAIL":
            result[d] = "FAIL"
        elif v == "tie" or cur == "tie":
            result[d] = "tie"
        else:
            result[d] = "PASS"
    return result


def write_csv(rows: list[dict]) -> None:
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    t0 = time.perf_counter()
    n_runs = 0
    all_rows: list[dict] = []

    with tempfile.TemporaryDirectory(prefix="vv_mono_") as tmp:
        tmpdir = Path(tmp)

        print("=== direction 1: pedestrian rate up ===")
        r1 = direction_1(tmpdir); print_rows(r1); all_rows += r1
        n_runs += 2 * len(SEEDS)

        print("=== direction 2: EV speed up ===")
        r2 = direction_2(tmpdir); print_rows(r2); all_rows += r2
        n_runs += 2 * len(SEEDS)

        print("=== direction 3: walk speed up ===")
        r3 = direction_3(tmpdir); print_rows(r3); all_rows += r3
        n_runs += 2 * len(SEEDS)

        print("=== direction 4: pool stock up ===")
        r4 = direction_4(tmpdir); print_rows(r4); all_rows += r4
        n_runs += 2 * len(SEEDS)

        print("=== direction 5: return_leg ON (tight pool) ===")
        r5 = direction_5(tmpdir); print_rows(r5); all_rows += r5
        n_runs += 2 * len(SEEDS)

        print("=== direction 6: K up ===")
        r6 = direction_6(); print_rows(r6); all_rows += r6
        n_runs += 3 * len(SEEDS)

    write_csv(all_rows)
    verdicts = overall_verdicts(all_rows)

    wall = time.perf_counter() - t0
    print("\n" + "=" * 72)
    print(f"V-MONO: {n_runs} runs, wall={wall:.1f}s ({wall / 60:.1f} min)")
    print("\nPer-direction verdict:")
    all_ok = True
    for d in sorted(verdicts):
        v = verdicts[d]
        print(f"  direction {d}: {v.upper()}")
        if v == "FAIL":
            all_ok = False
    print(f"\nwrote {OUT_CSV} ({len(all_rows)} rows)")
    print("OVERALL:", "PASS" if all_ok else "FAIL")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
