"""V-MONO-HR — HR-mode monotonicity battery (Phase A Step A6,
etc/scie_phase/phase_A_robot_h1.md §2 "Step A6").

    .venv/bin/python -m experiments.vv_monotonicity_hr

Checks the 5 expected monotone directions of the H1_SYNC (robot handoff)
model at 10 fixed seeds per level (seeds 1..10), gate = weak inequality
(>=/<=) on the 10-seed mean — the same convention as the H0 battery
(experiments/vv_monotonicity.py): an exact tie still PASSes and is marked
"tie"; only a move in the wrong direction FAILs.

Directions (research_plan_scie.md §2 A6 정본 = etc/scie_phase/phase_A_robot_h1.md
§2, HANDOFF_phase_a.md §3.7/§3.8 for the two 결정 #31 corrections):

  1. robot fleet size 1->3->5 (baseline)       => rider's wait for a free
                                                   robot (`robot_wait_mean_sec`)
                                                   down
  2. K50->K100->K200->K300 (baseline fleet)    => fleet load `utilization_ops_mean`
                                                   up, robot's OWN elevator wait
                                                   (pooled ev_wait_up/down from
                                                   robot_legs) up, `n_board_denied`
                                                   up
  3. paired H0 vs HR at low load (K50_1, CRN)  => HR `t_building_order_mean_sec`
                                                   < H0's (same seed, same
                                                   scenario)
  4. K50->K100->K200->K300 (same runs as #2)   => `n_charge_events` down (weak
                                                   — 0 throughout is the expected
                                                   corpus result, §3.5), fleet
                                                   `soc_end_pct_mean` down
  5. shared EV count 2->3->4 (K200_1)          => robot's OWN elevator wait
                                                   (pooled) down

🔴 Two corrections baked in per 결정 #31 (HANDOFF_phase_a.md §3.7/§3.8) — using
the pre-#31 wording would FAIL a correctly-implemented model:
  * direction 2's fleet-load metric is `utilization_ops_mean`, NOT the fixed-
    window utilization (K200 0.735 / K300 0.738 there — no discrimination once
    the fleet saturates inside a demand window whose length does not grow
    with K).
  * direction 2's externality metric is the ROBOT's own EV wait + board_denied,
    NOT pedestrian EV wait (which the A5-b measurement found DECREASES as K
    rises: H1 30.08 -> 29.73 s — the opposite of the pre-#31 claim).

Direction 3 carries a documented pre-registered risk (phase_A_robot_h1.md §2,
"③에 대한 사전 경고"): H0's low-load rider dwell is thin, so subtracting the
60 s mean handoff cost already eats most of the theoretical "prize ceiling",
and subtracting the robot-wait on top of that can turn the net benefit
negative. A FAIL here is therefore report-worthy, not automatically a defect
— see the module's `direction_3` docstring and the printed decomposition for
the walk-through this script performs at run time (per the plan's explicit
instruction to decompose ceiling vs. drag before concluding either way).

Scenario choice: K50_1/K100_1/K200_1/K300_4 are the exact four reference
scenarios A5's "4개 수요 티어" battery table already uses (HANDOFF_phase_a.md
§4), so this script's numbers sit next to established Phase A reference
points rather than introducing a new arbitrary quartet. K200_1 for direction 5
matches the demand tier phase_A_robot_h1.md §4 point 7 names for the shared-EV
sizing sweep ("공용 3대는 {EV2,EV3,EV4} 하나만").

Config/scenario overrides never touch the checked-in files: every non-default
level is either a `run_baseline(n_robots=...)` call-site override or an
in-memory config dict built from `simulation.space.load_config` + mutation,
mirroring `experiments/vv_monotonicity.py`'s tmp-config pattern (no tempfile
needed here since `run_baseline` accepts a `config` dict directly — A3's
"config dict injection" path, simulation/run.py).

Output: console table (per direction: level means, delta, %, verdict) +
results/vv/monotonicity_hr.csv. Exit code 0 iff every gated direction PASSes
or TIEs (no FAIL) — direction 3 is gated like the others, so a FAIL there
propagates to a non-zero exit; that is intentional (§2 A6 says document, not
suppress).
"""

from __future__ import annotations

import csv
import time
from pathlib import Path
from typing import Any

from simulation.run import run_baseline
from simulation.space import load_config

ROOT = Path(__file__).resolve().parent.parent
BASE_CONFIG = ROOT / "configs" / "baseline_10f.yaml"
SCENARIO_DIR = ROOT / "data" / "data1"
OUT_CSV = ROOT / "results" / "vv" / "monotonicity_hr.csv"

SEEDS = list(range(1, 11))  # 10 seeds, matches experiments/vv_monotonicity.py

FIELDNAMES = [
    "direction", "description", "scenario", "param", "metric", "gate",
    "level_a_label", "level_a_value", "level_a_mean", "level_a_n",
    "level_b_label", "level_b_value", "level_b_mean", "level_b_n",
    "delta", "pct_change", "expected", "verdict",
]


# ------------------------------------------------------------- run + metrics

def run_hr(scenario_path: Path, seed: int, *, config: dict | None = None,
           n_robots: int | None = None) -> dict:
    return run_baseline(
        config_path=BASE_CONFIG, scenario_path=scenario_path, config=config,
        rng_seed=seed, floor_profile="uniform", mode="hr", n_robots=n_robots,
    )


def run_h0(scenario_path: Path, seed: int) -> dict:
    return run_baseline(
        config_path=BASE_CONFIG, scenario_path=scenario_path,
        rng_seed=seed, floor_profile="uniform", mode="h0",
    )


def _pooled_robot_ev_wait(result: dict) -> float | None:
    """Pooled mean of robot_legs' ev_wait_up_sec + ev_wait_down_sec.

    Pooling the two raw observation lists (rather than averaging the two
    per-direction means) avoids silently weighting an up-leg and a down-leg
    equally when their counts differ (a robot can end a run mid up-leg).
    """
    legs = result.get("robot_legs") or []
    waits = [lg["ev_wait_up_sec"] for lg in legs if lg.get("ev_wait_up_sec") is not None]
    waits += [lg["ev_wait_down_sec"] for lg in legs if lg.get("ev_wait_down_sec") is not None]
    return (sum(waits) / len(waits)) if waits else None


def _pooled_robot_ev_wait_predecay(result: dict) -> float | None:
    """Same pooling as `_pooled_robot_ev_wait`, restricted to legs assigned
    BEFORE the pedestrian-decay clock starts (`ped_decay.start_after_last_order_sec`
    past the scenario's last order).

    Found during A6 execution (see phase_A_implementation_log.md §A6): the
    unrestricted pooled mean DIPS from K200 to K300 even though board_denied
    and utilization_ops both rise, because K300's drain (~12,000 s) runs deep
    into the decay ramp/floor (HANDOFF_phase_a.md's `pedestrian.ped_decay`
    block, floor_rate_per_min = 27% of peak) while K200's drain (~7,300 s)
    never reaches the decay threshold (7,200 s past the last order) at all —
    so K300's average is diluted by a large low-contention tail K200 does not
    have. This is a whole-run-pooling artefact, not a reversal of the
    underlying contention trend: restricted to the pre-decay (steady-state)
    population both scenarios are sampling from the SAME background regime,
    and the expected increase reappears (measured 41.1 -> 42.0 s, 5-seed
    pilot; the full N-seed figure is in the printed table below).
    Informational only (`gate=False` in the caller) — the primary, gated
    metric stays the naive full-run pool so a real reader sees the same
    number a paper table would quote, with this as the documented footnote.
    """
    legs = result.get("robot_legs") or []
    if not legs:
        return None
    orders = result.get("per_order") or []
    if not orders:
        return None
    last_order_abs = max(o["ord_time_abs_sec"] for o in orders)
    decay_cfg = (result.get("config") or {}).get("simulation", {}).get("ped_decay")
    threshold = (
        last_order_abs + decay_cfg["start_after_last_order_sec"]
        if decay_cfg else float("inf")
    )
    waits = []
    for lg in legs:
        if lg.get("assigned_at_sec") is not None and lg["assigned_at_sec"] >= threshold:
            continue
        for key in ("ev_wait_up_sec", "ev_wait_down_sec"):
            v = lg.get(key)
            if v is not None:
                waits.append(v)
    return (sum(waits) / len(waits)) if waits else None


def compute_metrics_hr(result: dict) -> dict[str, float | None]:
    k = result["kpi_summary"]
    rb = k.get("robot") or {}
    return {
        "robot_wait_mean": k["rider"]["robot_wait_mean_sec"],
        "utilization_ops_mean": rb.get("utilization_ops_mean"),
        "pooled_ev_wait": _pooled_robot_ev_wait(result),
        "pooled_ev_wait_predecay": _pooled_robot_ev_wait_predecay(result),
        "n_board_denied": rb.get("n_board_denied"),
        "n_charge_events": rb.get("n_charge_events"),
        "soc_end_mean": rb.get("soc_end_pct_mean"),
        "t_building_order_mean": k["customer"]["t_building_order_mean_sec"],
        "handoff_mean": k["rider"]["handoff_mean_sec"],
    }


def compute_metrics_h0(result: dict) -> dict[str, float | None]:
    k = result["kpi_summary"]
    return {"t_building_order_mean": k["customer"]["t_building_order_mean_sec"]}


def mean_of(rows: list[dict[str, float | None]], key: str) -> float | None:
    vals = [r[key] for r in rows if r.get(key) is not None]
    return sum(vals) / len(vals) if vals else None


# ------------------------------------------------------------------ judging

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

def direction_1() -> list[dict]:
    """robot fleet 1->3->5 (K50_1) => rider's wait for a free robot down."""
    scenario = SCENARIO_DIR / "K50_1.json"
    levels = [1, 3, 5]
    rows_by_level = {}
    for n in levels:
        rows_by_level[n] = [
            compute_metrics_hr(run_hr(scenario, seed, n_robots=n)) for seed in SEEDS
        ]
    out = []
    for a, b in zip(levels, levels[1:]):
        out.append(make_row(
            1, f"n_robots {a}->{b} -> robot_wait down", "K50_1", "robot.n_robots",
            "robot_wait_mean", True, str(a), a, mean_of(rows_by_level[a], "robot_wait_mean"),
            len(SEEDS), str(b), b, mean_of(rows_by_level[b], "robot_wait_mean"),
            len(SEEDS), "decrease"))
    return out


def direction_2_and_4() -> list[dict]:
    """K50->K100->K200->K300 (baseline fleet, shared 2 EVs): direction 2's
    utilization_ops/pooled-ev-wait/board_denied AND direction 4's
    charge_events/soc_end share the same run set — K is the only thing
    varying, so one battery of runs answers both directions."""
    stems = ["K50_1", "K100_1", "K200_1", "K300_4"]
    rows_by_stem = {}
    for stem in stems:
        scenario = SCENARIO_DIR / f"{stem}.json"
        rows_by_stem[stem] = [compute_metrics_hr(run_hr(scenario, seed)) for seed in SEEDS]

    out = []
    # --- direction 2: utilization_ops up, pooled robot EV wait up, board_denied up
    for metric, expect in (
        ("utilization_ops_mean", "increase"),
        ("pooled_ev_wait", "increase"),
        ("n_board_denied", "increase"),
    ):
        for a, b in zip(stems, stems[1:]):
            out.append(make_row(
                2, f"K up ({a}->{b}) -> {metric} up", f"{a}->{b}", "K (scenario)",
                metric, True, a, a, mean_of(rows_by_stem[a], metric), len(SEEDS),
                b, b, mean_of(rows_by_stem[b], metric), len(SEEDS), expect))
    # informational footnote (gate=False, see _pooled_robot_ev_wait_predecay
    # docstring): the naive full-run pool is diluted by K300's long drain
    # running into the pedestrian-decay floor, which K200's shorter drain
    # never reaches. Restricted to legs assigned before decay starts, both
    # scenarios sample the same background regime and the expected increase
    # reappears.
    for a, b in zip(stems, stems[1:]):
        out.append(make_row(
            2, f"info: K up ({a}->{b}) -> pooled ev_wait (pre-decay legs only) up",
            f"{a}->{b}", "K (scenario)", "pooled_ev_wait_predecay", False,
            a, a, mean_of(rows_by_stem[a], "pooled_ev_wait_predecay"), len(SEEDS),
            b, b, mean_of(rows_by_stem[b], "pooled_ev_wait_predecay"), len(SEEDS),
            "increase"))
    # --- direction 4: charge events down (weak -- 0 throughout is expected,
    # §3.5), ending SOC down
    for metric in ("n_charge_events", "soc_end_mean"):
        for a, b in zip(stems, stems[1:]):
            out.append(make_row(
                4, f"K up ({a}->{b}) -> {metric} down", f"{a}->{b}", "K (scenario)",
                metric, True, a, a, mean_of(rows_by_stem[a], metric), len(SEEDS),
                b, b, mean_of(rows_by_stem[b], metric), len(SEEDS), "decrease"))
    return out


def direction_3() -> list[dict]:
    """paired (CRN) H0 vs HR at low load (K50_1) => HR T_building_order < H0's.

    Pre-registered risk (phase_A_robot_h1.md §2, "③에 대한 사전 경고"): the
    handoff (60 s mean) alone consumes most of the low-load "prize ceiling"
    (H0's own T_building_order minus the handoff), so adding the robot's own
    queueing on top can flip the sign. This function also prints/returns the
    decomposition (ceiling = H0 mean - handoff mean; drag = robot_wait mean)
    so a FAIL here can be judged "expected given the ceiling" rather than
    treated as an unexplained defect — per the plan's explicit instruction to
    decompose before concluding.

    K50_2 (the only other low-load corpus file) and the K100_1/K200_1 tiers
    are run too, ungated (`gate=False`), purely to show where — if anywhere —
    the sign recovers as load rises (root-cause material, not part of the
    direction's PASS/FAIL determination, which is K50_1 alone per "저부하").
    """
    out = []
    primary_stem = "K50_1"
    scenario = SCENARIO_DIR / f"{primary_stem}.json"
    h0_rows = [compute_metrics_h0(run_h0(scenario, s)) for s in SEEDS]
    hr_rows = [compute_metrics_hr(run_hr(scenario, s)) for s in SEEDS]
    out.append(make_row(
        3, "paired H0 vs HR (K50_1, low load) -> HR T_building_order < H0",
        primary_stem, "mode", "t_building_order_mean", True,
        "H0", "h0", mean_of(h0_rows, "t_building_order_mean"), len(SEEDS),
        "HR", "hr", mean_of(hr_rows, "t_building_order_mean"), len(SEEDS), "decrease"))
    # informational decomposition rows (not gated): ceiling components
    out.append(make_row(
        3, "info: HR robot_wait_mean (drag component)", primary_stem, "mode",
        "robot_wait_mean", False, "H0", "h0", None, len(SEEDS),
        "HR", "hr", mean_of(hr_rows, "robot_wait_mean"), len(SEEDS), "decrease"))
    out.append(make_row(
        3, "info: HR handoff_mean (fixed ~60s cost)", primary_stem, "mode",
        "handoff_mean", False, "H0", "h0", None, len(SEEDS),
        "HR", "hr", mean_of(hr_rows, "handoff_mean"), len(SEEDS), "decrease"))

    # ungated secondary evidence: other low-load file + rising K
    for stem in ("K50_2", "K100_1", "K200_1"):
        s = SCENARIO_DIR / f"{stem}.json"
        h0r = [compute_metrics_h0(run_h0(s, seed)) for seed in SEEDS]
        hrr = [compute_metrics_hr(run_hr(s, seed)) for seed in SEEDS]
        out.append(make_row(
            3, f"info: paired H0 vs HR ({stem}) -- sign trend, not gated", stem,
            "mode", "t_building_order_mean", False,
            "H0", "h0", mean_of(h0r, "t_building_order_mean"), len(SEEDS),
            "HR", "hr", mean_of(hrr, "t_building_order_mean"), len(SEEDS), "decrease"))
    return out


def direction_5() -> list[dict]:
    """shared EV 2->3->4 (K200_1, baseline 5-robot fleet) => robot's own
    pooled EV wait down. Config sets `building.shared_ev_ids` directly (no
    `robot.n_robots` change) -- phase_A_robot_h1.md §4 point 7 names
    {EV2,EV3,EV4} as THE 3-shared configuration (geometry is symmetric but the
    ev_id ascending tie-break is not, so EV1 is not interchangeable with EV2
    here)."""
    scenario = SCENARIO_DIR / "K200_1.json"
    configs = {
        2: ["EV3", "EV4"],
        3: ["EV2", "EV3", "EV4"],
        4: ["EV1", "EV2", "EV3", "EV4"],
    }
    rows_by_n = {}
    for n_shared, ids in configs.items():
        cfg = load_config(BASE_CONFIG)
        cfg["building"]["shared_ev_ids"] = ids
        rows_by_n[n_shared] = [
            compute_metrics_hr(run_hr(scenario, seed, config=cfg)) for seed in SEEDS
        ]
    out = []
    levels = [2, 3, 4]
    for a, b in zip(levels, levels[1:]):
        out.append(make_row(
            5, f"shared EV {a}->{b} (K200_1) -> pooled robot ev_wait down", "K200_1",
            "building.shared_ev_ids", "pooled_ev_wait", True,
            str(a), configs[a], mean_of(rows_by_n[a], "pooled_ev_wait"), len(SEEDS),
            str(b), configs[b], mean_of(rows_by_n[b], "pooled_ev_wait"), len(SEEDS),
            "decrease"))
    return out


# ------------------------------------------------------------------- report

def print_rows(rows: list[dict]) -> None:
    for r in rows:
        gate_tag = "" if r["gate"] else " [info]"
        a = r["level_a_mean"]
        b = r["level_b_mean"]
        pct = r["pct_change"]

        def fmt(x):
            return "n/a" if x is None else (f"{x:.3f}" if abs(x) < 10 else f"{x:.1f}")

        print(
            f"[dir{r['direction']}] {r['metric']:<22} "
            f"{r['level_a_label']:>8}={fmt(a):<12} "
            f"{r['level_b_label']:>8}={fmt(b):<12} "
            f"delta={fmt(r['delta']):<12} "
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

    print("=== direction 1: robot fleet 1->3->5 (K50_1) ===")
    r1 = direction_1(); print_rows(r1); all_rows += r1
    n_runs += 3 * len(SEEDS)

    print("=== direction 2+4: K50->K100->K200->K300 (baseline fleet) ===")
    r24 = direction_2_and_4(); print_rows(r24); all_rows += r24
    n_runs += 4 * len(SEEDS)

    print("=== direction 3: paired H0 vs HR (K50_1 low load + trend evidence) ===")
    r3 = direction_3(); print_rows(r3); all_rows += r3
    n_runs += 2 * len(SEEDS) * 4  # K50_1 + K50_2 + K100_1 + K200_1, each paired

    print("=== direction 5: shared EV 2->3->4 (K200_1) ===")
    r5 = direction_5(); print_rows(r5); all_rows += r5
    n_runs += 3 * len(SEEDS)

    write_csv(all_rows)
    verdicts = overall_verdicts(all_rows)

    wall = time.perf_counter() - t0
    print("\n" + "=" * 72)
    print(f"V-MONO-HR: {n_runs} runs, wall={wall:.1f}s ({wall / 60:.1f} min)")
    print("\nPer-direction verdict:")
    all_ok = True
    for d in sorted(verdicts):
        v = verdicts[d]
        print(f"  direction {d}: {v.upper()}")
        if v == "FAIL":
            all_ok = False
    print(f"\nwrote {OUT_CSV} ({len(all_rows)} rows)")
    print("OVERALL:", "PASS" if all_ok else "FAIL (see module docstring re: direction 3)")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
