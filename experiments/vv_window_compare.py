"""V21-NEW / WINDOW-COMPARE — where did the utilization distortion come from?

    .venv/bin/python -m experiments.vv_window_compare

This is the measurement that decided *which* part of the pre-R8 window contract
was actually mispricing elevator utilization (etc/plan_h0v21_window.md §1.3).
It was run ad hoc while designing R8; this module is its reproducible form.

**The trick: one run, four windows.** Ending a run earlier is a strict *prefix*
of ending it later — the termination check only breaks the loop, it never
mutates state — so a single `legacy_margin` (drain-all) run contains every
earlier stopping point inside it. All four windows are therefore computed
*exactly* from one run's cumulative EV-busy snapshots (`model._ev_busy_cum`),
with no re-simulation and no seed misalignment. Running four separate policies
would have compared four different pedestrian realisations and measured noise.

| window | span | what it is |
|---|---|---|
| `full` | `[clock_start, clock_end]` | pre-R8 headline `utilization` |
| `to_ped_end` | `[clock_start, ped_end]` | drops only the `peds == 0` drain tail |
| `to_rider_exit` | `[clock_start, last rider exit]` | drops the whole tail |
| `delivery` | `[first ORD, last rider exit]` | R8 headline `utilization_delivery` |
| `orderspan` | `[first ORD, last delivery]` | the frozen `utilization_orderspan` |

Differencing them attributes the distortion to one cause each:

    peds==0 condition = to_ped_end − full
    ped_end guard     = to_rider_exit − to_ped_end
    warm-up head      = delivery − to_rider_exit
    (residual)        = orderspan − delivery

**The finding.** The warm-up head dominates by two orders of magnitude; the
`peds == 0` termination condition — the thing that looked like the culprit —
contributes almost nothing. That is why R8 promoted `utilization_delivery`
rather than merely changing when the loop stops, and it is also the evidence
that `utilization_orderspan` was already reporting the right number all along.

4 scenarios × 3 seeds = 12 runs, `legacy_margin` policy (the long arm — it must
outlive the rider exit for the tail windows to exist).

Output: results/vv/window_compare.csv (run-level rows + a per-scenario
attribution summary).
"""

from __future__ import annotations

import copy
import csv
import statistics
import tempfile
import time
from pathlib import Path

import yaml

from simulation.kpi import _tick_index
from simulation.model import BuildingHandoffModel
from simulation.space import load_config

ROOT = Path(__file__).resolve().parent.parent
BASE_CONFIG = ROOT / "configs" / "baseline_10f.yaml"
OUT_CSV = ROOT / "results" / "vv" / "window_compare.csv"

SCENARIOS = ["K50_1", "K100_1", "K200_1", "K300_4"]
SEEDS = [42, 7, 2026]
LEGACY_OVERRUN_SEC = 3600.0     # pre-R8 value; cap = ped_end + overrun here

WINDOWS = ["full", "to_ped_end", "to_rider_exit", "delivery", "orderspan"]

# (label, minuend, subtrahend) — each difference isolates exactly one cause.
ATTRIBUTIONS = [
    ("peds==0 condition", "to_ped_end", "full"),
    ("ped_end guard", "to_rider_exit", "to_ped_end"),
    ("warm-up head", "delivery", "to_rider_exit"),
    ("orderspan residual", "orderspan", "delivery"),
]

RUN_FIELDS = [
    "scenario_stem", "seed", "K", "delivered", "ticks",
    "clock_start_sec", "first_order_sec", "last_delivery_sec",
    "last_rider_exit_sec", "ped_end_sec", "clock_end_sec",
    "head_sec", "tail_total_sec", "tail_ped_end_guard_sec", "tail_peds_zero_sec",
    *[f"util_{w}" for w in WINDOWS],
    *[f"attr_{label.split()[0]}" for label, _, _ in ATTRIBUTIONS],
    "util_delivery_reported", "util_orderspan_reported", "wall_sec",
]

SUMMARY_FIELDS = [
    "scenario_stem", "quantity", "unit", "mean", "sd", "n_seeds",
]


def _legacy_config(tmpdir: Path) -> Path:
    base = load_config(BASE_CONFIG)
    cfg = copy.deepcopy(base)
    cfg["simulation"]["window_policy"] = "legacy_margin"
    cfg["simulation"]["max_overrun_sec"] = LEGACY_OVERRUN_SEC
    p = tmpdir / "legacy_margin.yaml"
    with p.open("w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, sort_keys=False, allow_unicode=True)
    return p


def _util_over(model, t0: float, t1: float) -> float:
    """Fleet-mean utilization over the absolute clock span [t0, t1].

    Same estimator `simulation.kpi` uses for the *_orderspan / *_delivery
    fields: cumulative busy ticks differenced at the nearest tick indices,
    divided by the tick count of the span. Averaged over the declared fleet.
    """
    n = model.tick_count
    j0 = _tick_index(model.clock_start_sec, model.dt, t0, n)
    j1 = _tick_index(model.clock_start_sec, model.dt, t1, n)
    span_ticks = j1 - j0
    if span_ticks <= 0:
        return 0.0
    return statistics.fmean(
        (cum[j1] - cum[j0]) / span_ticks for cum in model._ev_busy_cum
    )


def run_one(config_path: Path, stem: str, seed: int) -> dict:
    t0 = time.perf_counter()
    model = BuildingHandoffModel(
        config=load_config(config_path),
        scenario_path=ROOT / "data" / "data1" / f"{stem}.json",
        rng_seed=seed,
        dynamic_pool=True,
        scenario_window=True,
        floor_profile="uniform",
    )
    model.run_to_completion()
    wall = time.perf_counter() - t0

    customers = list(model.customer_by_ord_id.values())
    deliveries = [c.delivered_at_sec for c in customers if c.delivered_at_sec is not None]
    exits = [r["exited_at_sec"] for r in model.rider_records
             if r.get("exited_at_sec") is not None]
    assert deliveries and exits, f"{stem}/{seed}: run produced no deliveries or exits"

    clock_start = model.clock_start_sec
    clock_end = clock_start + model.tick_count * model.dt
    first_order = model.first_order_sec
    last_delivery = max(deliveries)
    last_exit = max(exits)
    ped_end = model.ped_end_sec

    # The drain-all tail splits at ped_end: before it the loop is held open by
    # the `clock >= ped_end` guard, after it by background pedestrians still
    # inside. Clamped because a cap trip could land clock_end before ped_end.
    tail_total = max(0.0, clock_end - last_exit)
    tail_ped_end = max(0.0, min(clock_end, ped_end) - last_exit)
    tail_peds_zero = max(0.0, clock_end - max(last_exit, ped_end))

    spans = {
        "full": (clock_start, clock_end),
        "to_ped_end": (clock_start, min(clock_end, ped_end)),
        "to_rider_exit": (clock_start, last_exit),
        "delivery": (first_order, last_exit),
        "orderspan": (first_order, last_delivery),
    }
    utils = {w: _util_over(model, *spans[w]) for w in WINDOWS}

    # cross-check against the fields kpi.py reports for the same two spans —
    # if these disagree the estimator here has drifted from the shipped one.
    from simulation.kpi import summarize as _summarize
    kpi = _summarize(model)
    reported_delivery = statistics.fmean(
        ev["utilization_delivery"] for ev in kpi["elevator"].values()
        if ev["utilization_delivery"] is not None
    )
    reported_orderspan = statistics.fmean(
        ev["utilization_orderspan"] for ev in kpi["elevator"].values()
        if ev["utilization_orderspan"] is not None
    )
    assert abs(utils["delivery"] - reported_delivery) < 1e-9, (
        f"{stem}/{seed}: local delivery-window estimator disagrees with kpi.py "
        f"({utils['delivery']} vs {reported_delivery})"
    )
    assert abs(utils["orderspan"] - reported_orderspan) < 1e-9, (
        f"{stem}/{seed}: local orderspan estimator disagrees with kpi.py "
        f"({utils['orderspan']} vs {reported_orderspan})"
    )

    row = {
        "scenario_stem": stem, "seed": seed,
        "K": model.K, "delivered": len(deliveries), "ticks": model.tick_count,
        "clock_start_sec": clock_start, "first_order_sec": first_order,
        "last_delivery_sec": last_delivery, "last_rider_exit_sec": last_exit,
        "ped_end_sec": ped_end, "clock_end_sec": clock_end,
        "head_sec": first_order - clock_start,
        "tail_total_sec": tail_total,
        "tail_ped_end_guard_sec": tail_ped_end,
        "tail_peds_zero_sec": tail_peds_zero,
        **{f"util_{w}": utils[w] for w in WINDOWS},
        **{f"attr_{label.split()[0]}": utils[a] - utils[b]
           for label, a, b in ATTRIBUTIONS},
        "util_delivery_reported": reported_delivery,
        "util_orderspan_reported": reported_orderspan,
        "wall_sec": wall,
    }
    print(
        f"[run] {stem:<8} seed={seed:<5} head={row['head_sec']:.0f}s "
        f"tail={tail_total:.0f}s (ped_end {tail_ped_end:.0f} / peds==0 {tail_peds_zero:.0f})  "
        + "  ".join(f"{w}={utils[w]:.4f}" for w in WINDOWS)
    )
    return row


def summarize(rows: list[dict]) -> list[dict]:
    out: list[dict] = []

    def add(stem: str, quantity: str, unit: str, vals: list[float]) -> None:
        out.append({
            "scenario_stem": stem, "quantity": quantity, "unit": unit,
            "mean": round(statistics.fmean(vals), 6),
            "sd": round(statistics.stdev(vals), 6) if len(vals) > 1 else 0.0,
            "n_seeds": len(vals),
        })

    for stem in SCENARIOS:
        rs = [r for r in rows if r["scenario_stem"] == stem]
        for key in ("head_sec", "tail_total_sec",
                    "tail_ped_end_guard_sec", "tail_peds_zero_sec"):
            add(stem, key, "sec", [r[key] for r in rs])
        for w in WINDOWS:
            add(stem, f"util_{w}", "fraction", [r[f"util_{w}"] for r in rs])
        for label, _, _ in ATTRIBUTIONS:
            key = f"attr_{label.split()[0]}"
            add(stem, f"{key}_pp", "percentage_point",
                [r[key] * 100.0 for r in rs])
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


def print_report(rows: list[dict]) -> None:
    print("\n" + "=" * 100)
    print("V-WINCMP: four windows on the same run (seed-averaged, "
          f"n={len(SEEDS)}; legacy_margin drain-all arm)")
    print("=" * 100)
    print(f"{'scenario':<10} {'tail (s)':>10} {'ped_end':>9} {'peds==0':>9} "
          + "".join(f"{w:>15}" for w in WINDOWS))
    print("-" * 100)
    for stem in SCENARIOS:
        rs = [r for r in rows if r["scenario_stem"] == stem]
        print(f"{stem:<10} "
              f"{statistics.fmean(r['tail_total_sec'] for r in rs):>10.0f} "
              f"{statistics.fmean(r['tail_ped_end_guard_sec'] for r in rs):>9.0f} "
              f"{statistics.fmean(r['tail_peds_zero_sec'] for r in rs):>9.0f} "
              + "".join(f"{statistics.fmean(r[f'util_{w}'] for r in rs):>15.4f}"
                        for w in WINDOWS))

    print("\nattribution of the utilization gap (percentage points, seed-averaged)")
    print("-" * 100)
    print(f"{'scenario':<10}" + "".join(f"{lbl:>22}" for lbl, _, _ in ATTRIBUTIONS))
    for stem in SCENARIOS:
        rs = [r for r in rows if r["scenario_stem"] == stem]
        print(f"{stem:<10}" + "".join(
            f"{statistics.fmean(r[f'attr_{lbl.split()[0]}'] for r in rs) * 100:>22.3f}"
            for lbl, _, _ in ATTRIBUTIONS))
    print("\nreading: the warm-up head column dwarfs the other three — the "
          "`peds == 0`\ncondition that R8 removed was never the problem, the "
          "warm-up head was.")


def main() -> int:
    t0 = time.perf_counter()
    rows: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="vv_window_compare_") as td:
        cfg = _legacy_config(Path(td))
        for stem in SCENARIOS:
            for seed in SEEDS:
                rows.append(run_one(cfg, stem, seed))
    summary = summarize(rows)
    write_csv(rows, summary)
    print_report(rows)
    wall = time.perf_counter() - t0
    print(f"\nwrote {OUT_CSV} ({len(rows)} run rows + {len(summary)} summary rows)")
    print(f"total wall time: {wall:.1f}s ({wall / 60:.1f} min)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
