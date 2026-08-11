"""V-WIN — window-policy KPI bias quantification (V21-W6, R8 redefinition).

    .venv/bin/python -m experiments.vv_window_bias

**Axis change, 2026-08-06 (R8 / etc/HANDOFF_r8_step78.md §3.2).** Until R8 this
script compared `scenario_window` False (legacy fixed lunch-peak horizon) vs
True (D4 data-derived span ±1h). That axis is no longer runnable *and* no longer
the interesting one:

  * not runnable — `configs/baseline_10f.yaml` declares `window_policy: delivery`
    since R8-f, and an **explicit** `scenario_window=False` against a delivery
    config is rejected with ValueError by design (explicit contradictions are not
    silently papered over; see plan_h0v21_window.md §11 "가드는 명시적 모순에만").
  * not the interesting one — R8 replaced the whole window/termination contract,
    so the question a reviewer asks now is "what did *that* change buy?", not
    "what would the pre-D4 fixed window have said?".

New axis: **`simulation.window_policy` legacy_margin ↔ delivery.**

| | legacy arm (`legacy_margin`) | delivery arm (`delivery`) |
|---|---|---|
| clock start | `min(ORD) − window_margin_sec` (3600 s) | `min(ORD) − warmup_sec` (600 s) |
| pedestrian spawn end | `max(ORD) + margin` | no cutoff (runs to termination) |
| cap | `ped_end + max_overrun` | `max(ORD) + max_overrun` |
| termination | drain-all (background pedestrians included) | all orders delivered ∧ all riders out |

Both arms are run through the paper track (`simulation.run.run_baseline`:
dynamic rider pool, `floor_profile="uniform"`, `return_leg=False`) for K50_1,
K200_1, K300_4 × seed {1..5}, holding every other switch fixed. The legacy arm
pins `max_overrun_sec: 3600.0` (the pre-R8 value — under `legacy_margin` the cap
is anchored to `ped_end`, so 3600 was and remains ample) and passes
`scenario_window=True`, which is exactly the pre-R8 paper track. The delivery arm
leaves `scenario_window` at the sentinel `None` so the policy derives the window.
Same pattern as `tests/test_kpi_window.py::_legacy_summary`.

**The old conclusion is retired.** The pre-R8 report read "the fixed lunch window
under-estimates congestion by W_EV +37.8~53.3%". That sentence is about the
*retired* axis (fixed vs data-derived) and must not be carried over — it is
re-derived here on the new axis.

Reading the output: `t_e2e/t_lobby/w_ev/sla/rider_wait` are **group I** KPIs
(HANDOFF_r8_step78 §2) — they *should* land on top of each other, and any
consistent gap is a finding. `ticks/wall_span/utilization/ped n_spawned` are
**group II** — they must move, and the direction is pre-declared. The table marks
each metric with its group so the two are never read the same way.

Outputs: results/vv/window_bias.csv (run-level raw, one row per scenario × seed ×
policy) + a seed-averaged comparison table printed to stdout (also appended to
the CSV as summary rows).
"""

from __future__ import annotations

import copy
import csv
import tempfile
import time
from pathlib import Path

import yaml

from simulation.run import run_baseline
from simulation.space import load_config

ROOT = Path(__file__).resolve().parent.parent
BASE_CONFIG = ROOT / "configs" / "baseline_10f.yaml"
OUT_CSV = ROOT / "results" / "vv" / "window_bias.csv"

SCENARIOS = ["K50_1", "K200_1", "K300_4"]
SEEDS = [1, 2, 3, 4, 5]

# pre-R8 cap slack for the legacy arm: cap = ped_end + overrun there, so the
# R8-f bump to 7200 (needed once the cap anchor moved to max(ORD)) would only
# widen an already-ample margin and would make the arm not-quite-legacy.
LEGACY_OVERRUN_SEC = 3600.0

RUN_FIELDNAMES = [
    "scenario_stem", "seed", "policy", "K", "delivered",
    # group I — must agree
    "t_e2e_mean_sec", "t_e2e_p95_sec", "t_lobby_mean_sec", "w_ev_mean_sec",
    "sla_violation_rate",
    # group II — must move
    "ticks", "wall_span_sec", "utilization_mean", "ped_n_spawned",
    "ped_n_in_building_at_end", "termination_reason",
    # group III — invariant by definition
    "utilization_orderspan_mean", "utilization_delivery_mean",
    "opex_running_krw_delivery",
    # window structure
    "clock_start_sec", "ped_start_sec", "ped_end_sec", "terminated_by_cap", "wall_sec",
]

# (field, label, KPI group). Group I = must agree, II = must move,
# III = invariant by definition (HANDOFF_r8_step78 §2).
KPI_METRICS = [
    ("t_e2e_mean_sec", "T_e2e mean (s)", "I"),
    ("t_e2e_p95_sec", "T_e2e p95 (s)", "I"),
    ("t_lobby_mean_sec", "T_lobby mean (s)", "I"),
    ("w_ev_mean_sec", "W_EV mean (s)", "I"),
    ("sla_violation_rate", "SLA violation rate", "I"),
    ("ticks", "ticks", "II"),
    ("utilization_mean", "utilization (full)", "II"),
    ("ped_n_spawned", "pedestrians spawned", "II"),
    ("utilization_orderspan_mean", "utilization_orderspan", "III"),
    ("utilization_delivery_mean", "utilization_delivery", "III"),
]


# ------------------------------------------------------------------- configs

def _write_arm_configs(tmpdir: Path) -> dict[str, Path]:
    """Derive one config file per policy arm from configs/baseline_10f.yaml.

    A file (not an in-memory dict) because `run_baseline` takes `config_path` —
    keeping both arms on the same entry point is the point of the exercise.
    """
    base = load_config(BASE_CONFIG)
    assert base["simulation"]["window_policy"] == "delivery", (
        "baseline_10f.yaml is expected to declare the delivery policy since R8-f; "
        f"found {base['simulation'].get('window_policy')!r}"
    )

    paths: dict[str, Path] = {}

    legacy = copy.deepcopy(base)
    legacy["simulation"]["window_policy"] = "legacy_margin"
    legacy["simulation"]["max_overrun_sec"] = LEGACY_OVERRUN_SEC
    paths["legacy_margin"] = tmpdir / "arm_legacy_margin.yaml"

    paths["delivery"] = tmpdir / "arm_delivery.yaml"

    for policy, cfg in (("legacy_margin", legacy), ("delivery", base)):
        with paths[policy].open("w", encoding="utf-8") as f:
            yaml.safe_dump(cfg, f, sort_keys=False, allow_unicode=True)
    return paths


# ------------------------------------------------------------------ extract

def _mean_over_cars(elevator: dict, field: str) -> float:
    vals = [ev[field] for ev in elevator.values()]
    return sum(vals) / len(vals)


def _extract(result: dict) -> dict:
    kpi = result["kpi_summary"]
    sim = kpi["simulation"]
    ped = kpi["pedestrian"]
    return {
        "K": kpi["customer"]["n_orders"],
        "delivered": kpi["customer"]["n_delivered"],
        "t_e2e_mean_sec": kpi["customer"]["t_e2e_mean_sec"],
        "t_e2e_p95_sec": kpi["customer"]["t_e2e_p95_sec"],
        "t_lobby_mean_sec": kpi["rider"]["t_lobby_mean_sec"],
        "w_ev_mean_sec": kpi["building"]["w_ev_mean_riders_sec"],
        "sla_violation_rate": kpi["customer"]["sla_violation_rate"],
        "ticks": sim["ticks"],
        "wall_span_sec": sim["wall_span_sec"],
        "utilization_mean": _mean_over_cars(kpi["elevator"], "utilization"),
        "ped_n_spawned": ped["n_spawned"],
        # field is additive (R8-b) and present under both policies; under
        # legacy_margin drain-all it is 0 by construction.
        "ped_n_in_building_at_end": ped.get("n_in_building_at_end"),
        "termination_reason": sim.get("termination_reason"),
        "utilization_orderspan_mean": _mean_over_cars(kpi["elevator"], "utilization_orderspan"),
        "utilization_delivery_mean": _mean_over_cars(kpi["elevator"], "utilization_delivery"),
        "opex_running_krw_delivery": kpi["building"]["opex_running_krw_delivery"],
        "clock_start_sec": sim["clock_start_sec"],
        "ped_start_sec": sim["ped_window_sec"][0],
        "ped_end_sec": sim["ped_window_sec"][1],
        "terminated_by_cap": sim["terminated_by_cap"],
        "wall_sec": result["runtime_wall_sec"],
    }


def run_all(arm_configs: dict[str, Path]) -> list[dict]:
    rows: list[dict] = []
    for stem in SCENARIOS:
        scenario_path = ROOT / "data" / "data1" / f"{stem}.json"
        for seed in SEEDS:
            for policy in ("legacy_margin", "delivery"):
                result = run_baseline(
                    config_path=arm_configs[policy],
                    scenario_path=scenario_path,
                    rng_seed=seed,
                    dynamic_pool=True,
                    return_leg=False,
                    # legacy arm reproduces the pre-R8 paper track (D4 span);
                    # delivery arm lets the policy derive the window (sentinel).
                    scenario_window=True if policy == "legacy_margin" else None,
                    floor_profile="uniform",
                )
                row = {
                    "scenario_stem": stem,
                    "seed": seed,
                    "policy": policy,
                    **_extract(result),
                }
                rows.append(row)
                print(
                    f"[run] {stem:<10} seed={seed} policy={policy:<14} "
                    f"delivered={row['delivered']}/{row['K']} "
                    f"ticks={row['ticks']:<6} "
                    f"T_e2e={row['t_e2e_mean_sec']:.1f}s "
                    f"W_EV={row['w_ev_mean_sec']:.2f}s "
                    f"reason={row['termination_reason']} "
                    f"wall={row['wall_sec']:.2f}s"
                )
    return rows


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs)


def build_comparison(rows: list[dict]) -> list[dict]:
    """Seed-averaged legacy_margin vs delivery, one dict per scenario × metric."""
    comparison: list[dict] = []
    for stem in SCENARIOS:
        legacy_rows = [r for r in rows
                       if r["scenario_stem"] == stem and r["policy"] == "legacy_margin"]
        delivery_rows = [r for r in rows
                         if r["scenario_stem"] == stem and r["policy"] == "delivery"]
        assert len(legacy_rows) == len(delivery_rows) == len(SEEDS)
        for field, label, group in KPI_METRICS:
            legacy_vals = [r[field] for r in legacy_rows if r[field] is not None]
            delivery_vals = [r[field] for r in delivery_rows if r[field] is not None]
            legacy_mean = _mean(legacy_vals) if legacy_vals else None
            delivery_mean = _mean(delivery_vals) if delivery_vals else None
            if legacy_mean is None or delivery_mean is None:
                delta = None
                delta_pct = None
            else:
                delta = delivery_mean - legacy_mean
                delta_pct = (delta / legacy_mean * 100.0) if legacy_mean != 0 else None
            comparison.append({
                "scenario_stem": stem,
                "metric": field,
                "metric_label": label,
                "kpi_group": group,
                "legacy_margin_mean": legacy_mean,
                "delivery_mean": delivery_mean,
                "delta": delta,
                "delta_pct": delta_pct,
                "n_seeds": len(SEEDS),
            })
    return comparison


SUMMARY_FIELDNAMES = [
    "scenario_stem", "metric", "metric_label", "kpi_group",
    "legacy_margin_mean", "delivery_mean", "delta", "delta_pct", "n_seeds",
]


def write_csv(rows: list[dict], comparison: list[dict]) -> None:
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=RUN_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
        # summary rows appended below the raw run rows, same file (plan spec:
        # "run-level raw + summary"), distinguished by their own header.
        f.write("\n")
        writer2 = csv.DictWriter(f, fieldnames=SUMMARY_FIELDNAMES)
        writer2.writeheader()
        writer2.writerows(comparison)


def print_table(comparison: list[dict]) -> None:
    print("\n" + "=" * 104)
    print("V-WIN: window_policy legacy_margin vs delivery "
          f"(seed-averaged, n={len(SEEDS)} seeds each)")
    print("  group I = must agree · II = must move · III = invariant by definition")
    print("=" * 104)
    header = (f"{'scenario':<10} {'g':<2} {'metric':<24} {'legacy_margin':>14} "
              f"{'delivery':>14} {'delta':>12} {'delta%':>9}")
    print(header)
    print("-" * len(header))
    for c in comparison:
        def fmt(v, pct=False):
            if v is None:
                return "n/a"
            if pct:
                return f"{v:+.1f}%"
            if c["metric"] == "sla_violation_rate":
                return f"{v:.4%}"
            return f"{v:.3f}" if abs(v) < 10 else f"{v:.1f}"

        print(
            f"{c['scenario_stem']:<10} {c['kpi_group']:<2} {c['metric_label']:<24} "
            f"{fmt(c['legacy_margin_mean']):>14} {fmt(c['delivery_mean']):>14} "
            f"{fmt(c['delta']):>12} {fmt(c['delta_pct'], pct=True):>9}"
        )
        if c["metric"] in ("sla_violation_rate", "ped_n_spawned"):
            print()


def main() -> int:
    t0 = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="vv_window_bias_") as td:
        arm_configs = _write_arm_configs(Path(td))
        rows = run_all(arm_configs)
    comparison = build_comparison(rows)
    write_csv(rows, comparison)
    print_table(comparison)
    elapsed = time.perf_counter() - t0
    print(f"\nwrote {OUT_CSV} ({len(rows)} run rows + {len(comparison)} summary rows)")
    print(f"total wall time: {elapsed:.1f}s ({elapsed / 60:.1f} min)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
