"""H0 descriptive-statistics track (S0 + S1) — demand-insight study, NOT V&V.

    .venv/bin/python -m experiments.h0_descriptive                    # primary tier, S0 + S1
    .venv/bin/python -m experiments.h0_descriptive --tier extreme
    .venv/bin/python -m experiments.h0_descriptive --tier all --traits-only
    .venv/bin/python -m experiments.h0_descriptive --battery-only --workers 40

Purpose (2026-08-03 user decision): before Phase A implements the robot modes,
characterize how the *current human-only* H0 system behaves across the
analysis scenarios — per-scenario KPI rows (not the K-pooled aggregates the
V&V track produced) plus raw-demand traits, as inputs for the S2 insight
analysis (analysis/h0_baseline_stats.py, forthcoming) and the note
etc/note_h0_demand_insights.md.

Governance:
  * Publication-grade numbers remain Phase D's (30-seed CRN) responsibility;
    this track is diagnostic. 3 seeds per scenario (battery convention
    42/7/2026) — V5e showed scenario/K effects (+62~366%) dwarf seed CI
    (<=3.7% half-width at n=30), so 3 seeds suffice for description.
  * Outputs go to results/h0_stats/ (NOT results/vv/ — that directory is the
    frozen V&V record).
  * simulation/ code is untouched: everything here derives from
    run_baseline()'s existing result dict (kpi_summary + per_order +
    model_vars). The frozen-snapshot gate (tests/test_h0_frozen_snapshot.py)
    guards that invariant.
  * Scenario set (etc/plan_h0_revision.md §1.4, §3 R5): tiered via
    analysis.scenario_tiers, default `--tier primary` (K50/K100/K200, 20
    scenarios). `--tier all` is the full 28-file modelling corpus
    (primary 20 + extreme 8). K500/K750/K1000 (11 files) are
    excluded from the corpus (사용자 확정 2026-08-03 2차) and cannot be
    selected by any flag. STAGE3_*.json are a separate track, always
    excluded. The verification battery (experiments/vv_all39.py etc.) now
    runs the same 28-file corpus through analysis.scenario_tiers -- the
    pre-2026-08-03 rule that the battery stayed at 39 raw files no longer
    holds.

2026-08-06 (T0b, H0 v2.1 insight track): the derived columns were generalised
off the 2-EV building they were written against.

  * Per-car columns are now emitted for **every** car in `kpi_summary`
    (`drv_ev{i}_*`), with the fleet read from the result, not hardcoded. v1's
    `drv_ev1_*`/`drv_ev2_*` measured 2 of 4 cars.
  * Robot boarding-denial exposure moved to the **shared** cars
    (`config.building.shared_ev_ids` = EV3/EV4) as
    `drv_shared_pax_ge12_frac_{all,any}`. The v1 column measured it on EV2,
    which in v2 is a people-only car a robot can never board -- so the number
    was not merely stale, it was about the wrong shaft. The per-car
    `drv_ev{i}_pax_ge12_frac` columns (EV2 included) are kept as the contrast.
  * Time-series aggregates use the R8 **delivery** window, matching
    `utilization_delivery`; `drv_window_used` records the window per row and
    reads `orderspan` on the legacy_margin path.
  * Added H2 inputs (rider-state split: `drv_riders_waiting_ev_*`) and H3
    inputs (`drv_deliv_per_floor_*`, `drv_floor_burst10_max`).

S1 runs in parallel (ProcessPoolExecutor): each run_baseline() call is a pure
function of (scenario, rng_seed) — no shared state, no file writes — so
process-parallel execution is bit-identical to serial (V5d determinism).
Cross-check: every (scenario, seed) row's `delivered` must equal the serial
V-ALL39 battery's value (results/vv/all39_battery.csv).
"""

from __future__ import annotations

import os

os.environ.setdefault("OMP_NUM_THREADS", "1")  # worker hygiene; sim is not BLAS-bound

import argparse
import csv
import gzip
import json
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

from analysis.load_data import load_scenario
from analysis.scenario_tiers import TIER_CHOICES, tier_of_k
from analysis.scenario_tiers import scenario_paths as _tier_scenario_paths
from simulation.run import run_baseline

ROOT = Path(__file__).resolve().parent.parent
SCENARIO_DIR = ROOT / "data" / "data1"
OUT_DIR = ROOT / "results" / "h0_stats"
RUNS_DIR = OUT_DIR / "runs"
TRAITS_CSV = OUT_DIR / "scenario_traits.csv"
KPI_CSV = OUT_DIR / "h0_kpi_by_scenario.csv"
ALL39_CSV = ROOT / "results" / "vv" / "all39_battery.csv"

SEEDS = [42, 7, 2026]          # V-ALL39 battery convention (cross-checkable)
# (A K1000_5 data-integrity exclusion used to live here -- K1000_5 is a
# byte-clone of K1000_4, V-DATA finding. It is gone because K1000 as a whole
# is outside the modelling corpus now, so the duplicate pair is unreachable.)
PEAK_BIN_SEC = 600.0           # 10-min bins for the burstiness ratio
DEFAULT_TIER = "primary"       # analysis default (plan §1.4, §3 R5)


def scenario_stems(tier: str = "all") -> list[str]:
    """Scenario stems for `tier` (TIER_CHOICES: 'primary' | 'extreme' | 'all').

    'all' is the 28-file modelling corpus, not every file in data/data1:
    K500/K750/K1000 are held out (사용자 확정 2026-08-03 2차) and
    analysis.scenario_tiers already withholds them, so no extra filtering is
    applied here.
    """
    stems = sorted(p.stem for p in _tier_scenario_paths(tier, data_dir=SCENARIO_DIR))
    if tier == "all":
        assert len(stems) == 28, f"expected 28 corpus scenarios, found {len(stems)}"
    return stems


def k_of(stem: str) -> int:
    return int(stem.split("_")[0][1:])


# --------------------------------------------------------------------- helpers

def _mean(xs) -> float | None:  # noqa: ANN001
    xs = [x for x in xs if x is not None]
    return float(np.mean(xs)) if xs else None


def _p95(xs) -> float | None:  # noqa: ANN001
    xs = [x for x in xs if x is not None]
    return float(np.percentile(xs, 95)) if xs else None


def _interarrival_stats(times_sec: list[float]) -> tuple[float | None, float | None]:
    """(mean interarrival sec, CV^2 of interarrival) from event times.

    CV^2 (squared coefficient of variation, ddof=1) is the c_a^2 that the
    Phase B G/G/c docking (Allen–Cunneen) needs for the arrival process.
    """
    ts = np.sort(np.asarray(times_sec, dtype=float))
    if ts.size < 3:
        return (None, None)
    ia = np.diff(ts)
    m = float(ia.mean())
    if m <= 0.0:
        return (m, None)
    return (m, float(ia.var(ddof=1) / m**2))


def _peak_count(times_sec: list[float], bin_sec: float = PEAK_BIN_SEC) -> int:
    """Largest number of events falling in any fixed `bin_sec` bin.

    The absolute count, not the peak/mean ratio: a locker bank is sized by how
    many parcels actually arrive in a window, and a ratio hides that a floor
    with a 3x peak of 2 orders needs no lockers at all.
    """
    ts = np.sort(np.asarray(times_sec, dtype=float))
    if ts.size == 0:
        return 0
    edges = np.arange(ts[0], ts[-1] + bin_sec, bin_sec)
    if edges.size < 2:
        return int(ts.size)
    counts, _ = np.histogram(ts, bins=edges)
    return int(counts.max())


def _peak_over_mean(times_sec: list[float], bin_sec: float = PEAK_BIN_SEC) -> float | None:
    """max 10-min-bin event count / mean bin count over the [min,max] span."""
    ts = np.asarray(times_sec, dtype=float)
    if ts.size == 0:
        return None
    span = float(ts.max() - ts.min())
    n_bins = max(int(np.ceil(span / bin_sec)), 1)
    edges = ts.min() + bin_sec * np.arange(n_bins + 1)
    edges[-1] = max(edges[-1], ts.max() + 1e-9)  # include the last event
    counts, _ = np.histogram(ts, bins=edges)
    mean_count = ts.size / n_bins
    return float(counts.max() / mean_count) if mean_count > 0 else None


# ------------------------------------------------------------------- S0 traits

TRAIT_FIELDS = [
    "scenario", "K", "tier", "n_orders",
    "ord_span_sec", "orders_per_h",
    "ia_mean_sec", "ia_cv2", "peak10_over_mean",
    "cook_mean_sec", "cook_p95_sec",
    "vol_mean", "vol_max",
    "lead_mean_sec", "lead_min_sec",
    "pool_bike", "pool_walk", "pool_car",
]


def scenario_traits(stem: str) -> dict:
    """Raw-demand traits straight from the scenario JSON (no simulation).

    Uses analysis.load_data.load_scenario so units follow the official
    schema exactly (all times already in seconds). `tier` is stamped from
    analysis.scenario_tiers so downstream readers (h0_baseline_stats.py)
    can tell which corpus produced a given row without cross-referencing
    the run command (plan §1.4, §3 R5).
    """
    sc = load_scenario(SCENARIO_DIR / f"{stem}.json")
    ord_times = [o.ord_time_sec for o in sc.orders]
    leads = [o.dlv_deadline_sec - o.ord_time_sec for o in sc.orders]
    span = (max(ord_times) - min(ord_times)) if ord_times else 0.0
    ia_mean, ia_cv2 = _interarrival_stats(ord_times)
    pool = {r.type: r.available_number for r in sc.riders}
    return {
        "scenario": stem,
        "K": sc.K,
        "tier": tier_of_k(sc.K),
        "n_orders": len(sc.orders),
        "ord_span_sec": round(span, 1),
        "orders_per_h": round(len(sc.orders) / span * 3600.0, 2) if span > 0 else None,
        "ia_mean_sec": round(ia_mean, 2) if ia_mean is not None else None,
        "ia_cv2": round(ia_cv2, 4) if ia_cv2 is not None else None,
        "peak10_over_mean": round(_peak_over_mean(ord_times), 3),
        "cook_mean_sec": round(_mean([o.cook_time_sec for o in sc.orders]), 1),
        "cook_p95_sec": round(_p95([o.cook_time_sec for o in sc.orders]), 1),
        "vol_mean": round(_mean([o.vol for o in sc.orders]), 1),
        "vol_max": max(o.vol for o in sc.orders),
        "lead_mean_sec": round(_mean(leads), 1),
        "lead_min_sec": round(min(leads), 1),
        "pool_bike": pool.get("BIKE"),
        "pool_walk": pool.get("WALK"),
        "pool_car": pool.get("CAR"),
    }


def write_traits(tier: str = DEFAULT_TIER) -> None:
    rows = [scenario_traits(stem) for stem in scenario_stems(tier)]
    rows.sort(key=lambda r: (r["K"], r["scenario"]))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with TRAITS_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=TRAIT_FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"[S0] wrote {TRAITS_CSV} ({len(rows)} rows, tier={tier})")


# ------------------------------------------------------------------ S1 battery

def _flatten_kpi(kpi: dict) -> dict:
    """kpi_summary -> flat {'kpi.section.metric': value} (elevator keyed by EV id)."""
    out: dict = {}

    def rec(prefix: str, block: dict) -> None:
        for k, v in block.items():
            key = f"{prefix}.{k}"
            if isinstance(v, dict):
                rec(key, v)
            elif isinstance(v, list):
                out[key] = json.dumps(v)
            else:
                out[key] = v

    rec("kpi", kpi)
    return out


def _window_mask(model_vars: dict, span: list | None) -> np.ndarray | None:
    if span is None:
        return None
    clock = np.asarray(model_vars["clock_sec"], dtype=float)
    mask = (clock >= span[0]) & (clock <= span[1])
    return mask if mask.any() else None


def _series(model_vars: dict, key: str, mask: np.ndarray) -> np.ndarray:
    return np.asarray(model_vars[key], dtype=float)[mask]


def derive_row(result: dict) -> dict:
    """One flat CSV row from a run_baseline() result dict."""
    kpi = result["kpi_summary"]
    per_order = result["per_order"]
    mv = result["model_vars"]

    row: dict = {
        "scenario": Path(result["scenario_path"]).stem,
        "K": kpi["customer"]["n_orders"],
        "tier": tier_of_k(kpi["customer"]["n_orders"]),
        "seed": result["rng_seed"],
        "wall_sec": result["runtime_wall_sec"],
    }
    row.update(_flatten_kpi(kpi))

    # ---- per_order derived (rider-side structure) --------------------------
    floors = [r["floor"] for r in per_order]
    n = len(per_order)
    stairs = [r for r in per_order if r["vertical_mode"] == "stairs"]
    entered = [r["entered_at_sec"] for r in per_order]
    ia_mean, ia_cv2 = _interarrival_stats(entered)
    row.update({
        "drv_stairs_share": round(len(stairs) / n, 4) if n else None,
        "drv_floor_mean": round(_mean(floors), 3),
        "drv_share_floor_le5": round(sum(1 for f in floors if f <= 5) / n, 4) if n else None,
        "drv_evwait_up_p95_sec": _p95([r["ev_wait_up_sec"] for r in per_order]),
        "drv_evwait_down_p95_sec": _p95([r["ev_wait_down_sec"] for r in per_order]),
        "drv_walked_m_mean": _mean([r["walked_m"] for r in per_order]),
        "drv_rider_wait_mean_sec": _mean([r["rider_wait_sec"] for r in per_order]),
        "drv_rider_wait_max_sec": max(
            (r["rider_wait_sec"] for r in per_order if r["rider_wait_sec"] is not None),
            default=None,
        ),
        "drv_fallback_n": sum(1 for r in per_order if r["was_fallback"]),
        "drv_n_bike": sum(1 for r in per_order if r["rider_type"] == "BIKE"),
        "drv_n_walk": sum(1 for r in per_order if r["rider_type"] == "WALK"),
        "drv_n_car": sum(1 for r in per_order if r["rider_type"] == "CAR"),
        # building-arrival process (counter arrival process under H1/H2):
        "drv_arrival_ia_mean_sec": round(ia_mean, 2) if ia_mean is not None else None,
        "drv_arrival_ia_cv2": round(ia_cv2, 4) if ia_cv2 is not None else None,
        "drv_arrival_peak10_over_mean": _peak_over_mean(entered),
    })

    # ---- per_order derived, H3 (locker) sizing inputs -----------------------
    # A locker bank is sized by how many parcels can be *outstanding on one
    # floor at once*, so the two demand-side inputs are the per-floor delivery
    # count and the per-floor 10-min burst. H0 has no customer-pickup process,
    # so the residence time that turns a burst into an occupancy is a Phase C
    # parameter, not something measurable here -- the tau-parametric occupancy
    # is computed in the T3 analysis, which sweeps tau over the same runs.
    by_floor: dict[int, list[float]] = {}
    for r in per_order:
        if r["delivered_at_sec"] is not None:
            by_floor.setdefault(r["floor"], []).append(r["delivered_at_sec"])
    row.update({
        "drv_deliv_per_floor_max": max((len(v) for v in by_floor.values()), default=0),
        "drv_deliv_per_floor_mean": round(_mean([len(v) for v in by_floor.values()]), 3)
        if by_floor else None,
        "drv_floor_burst10_max": max(
            (_peak_count(v) for v in by_floor.values()), default=None),
        "drv_service_time_mean_sec": _mean([r["service_time_sec"] for r in per_order]),
    })

    # ---- model_vars derived, restricted to the delivery window -------------
    # R8 made `delivery` ([min ORD, last rider exit]) the reported window and
    # `utilization_delivery` the headline rate KPI, so the time-series
    # aggregates below use the same window; `drv_window_used` records which one
    # actually applied, because the legacy_margin path has no delivery window
    # and falls back to the order span (they differ by 55~91 s of final-rider
    # descent, i.e. by nothing at three decimals -- kpi.py "R8-b" note).
    span = kpi["simulation"].get("delivery_window_sec")
    window_used = "delivery"
    if span is None:
        span, window_used = kpi["simulation"]["orderspan_window_sec"], "orderspan"
    mask = _window_mask(mv, span)
    row["drv_window_used"] = window_used if mask is not None else None
    if mask is not None:
        # N-EV generalisation (R2): the fleet is declared by config, not by
        # this script. v1 hardcoded ev1_/ev2_ and so measured 2 of the 4 cars
        # -- and, worse, measured robot boarding-denial exposure on EV2, which
        # in v2 is a *people-only* car the robot can never board.
        ev_ids = list(kpi["elevator"])                       # ['EV1'...'EV4']
        shared = set(result["config"]["building"]["shared_ev_ids"])   # {'EV3','EV4'}
        pax = {e: _series(mv, f"{e.lower()}_pax", mask) for e in ev_ids}
        que = {e: _series(mv, f"{e.lower()}_queue", mask) for e in ev_ids}
        for e in ev_ids:
            lo = e.lower()
            row[f"drv_{lo}_pax_mean"] = round(float(pax[e].mean()), 3)
            row[f"drv_{lo}_pax_max"] = int(pax[e].max())
            row[f"drv_{lo}_queue_mean"] = round(float(que[e].mean()), 3)
            row[f"drv_{lo}_queue_max"] = int(que[e].max())
            # A robot may board a car only while people aboard <= 11 (design
            # freeze R0-1/R0-2), so ticks at >= 12 are that car's denial
            # exposure. Reported for every car, but only the shared ones are
            # reachable by a robot -- the dedicated columns exist as the
            # contrast that shows the exposure is a property of load, not of
            # which car happens to be shared.
            row[f"drv_{lo}_pax_ge12_frac"] = round(float((pax[e] >= 12).mean()), 4)
        shared_ids = [e for e in ev_ids if e in shared]
        dedic_ids = [e for e in ev_ids if e not in shared]
        blocked = np.vstack([pax[e] >= 12 for e in shared_ids])
        row.update({
            # `all` = every shared car is full, so a robot is denied no matter
            # which it picks -- the real denial rate. `any` = at least one is,
            # i.e. the robot's choice was constrained. The gap between the two
            # is the redundancy the 2-shared-car fleet buys.
            "drv_shared_pax_ge12_frac_all": round(float(blocked.all(axis=0).mean()), 4),
            "drv_shared_pax_ge12_frac_any": round(float(blocked.any(axis=0).mean()), 4),
            "drv_shared_pax_mean": round(
                float(np.mean([pax[e].mean() for e in shared_ids])), 3),
            "drv_dedicated_pax_mean": round(
                float(np.mean([pax[e].mean() for e in dedic_ids])), 3),
            "drv_shared_queue_mean": round(
                float(np.mean([que[e].mean() for e in shared_ids])), 3),
            "drv_dedicated_queue_mean": round(
                float(np.mean([que[e].mean() for e in dedic_ids])), 3),
            "drv_shared_ev_ids": "|".join(shared_ids),
        })
        row.update({
            "drv_riders_in_building_mean": round(
                float(_series(mv, "riders_in_building", mask).mean()), 3),
            "drv_riders_in_building_max": int(_series(mv, "riders_in_building", mask).max()),
            # H2 sizes a counter queue, so the rider-state split matters, not
            # just the head count: waiting-for-EV riders are the ones a
            # handoff counter would remove from the vertical system.
            "drv_riders_waiting_ev_mean": round(
                float(_series(mv, "riders_waiting_ev", mask).mean()), 3),
            "drv_riders_waiting_ev_max": int(_series(mv, "riders_waiting_ev", mask).max()),
            "drv_riders_in_service_mean": round(
                float(_series(mv, "riders_in_service", mask).mean()), 3),
            "drv_peds_waiting_mean": round(float(_series(mv, "peds_waiting", mask).mean()), 3),
            "drv_peds_waiting_max": int(_series(mv, "peds_waiting", mask).max()),
            "drv_backlog_max": int(_series(mv, "backlog", mask).max()),
            "drv_dispatch_queue_max": int(np.nanmax(_series(mv, "dispatch_queue_len", mask))),
        })
    fb = np.asarray(mv["fallback_cum"], dtype=float)
    row["drv_fallback_cum_final"] = int(np.nanmax(fb)) if np.isfinite(fb).any() else None
    return row


def one_run(task: tuple[str, int]) -> dict:
    """Worker: one (scenario, seed) run + derived row + raw gz dump."""
    stem, seed = task
    result = run_baseline(
        scenario_path=SCENARIO_DIR / f"{stem}.json",
        rng_seed=seed,
        floor_profile="uniform",
    )
    raw_path = RUNS_DIR / f"{stem}_s{seed}.json.gz"
    with gzip.open(raw_path, "wt", encoding="utf-8") as f:
        json.dump(result, f, default=str)
    return derive_row(result)


def crosscheck_all39(rows: list[dict]) -> int:
    """delivered must match the serial V-ALL39 battery for every (stem, seed)."""
    if not ALL39_CSV.exists():
        print("[S1] WARNING: all39_battery.csv not found — cross-check skipped")
        return 0
    with ALL39_CSV.open() as f:
        ref = {
            (r["scenario_stem"], int(r["seed"])): int(r["delivered"])
            for r in csv.DictReader(f)
        }
    mismatches = [
        (r["scenario"], r["seed"], r["kpi.customer.n_delivered"], ref[(r["scenario"], r["seed"])])
        for r in rows
        if (r["scenario"], r["seed"]) in ref
        and int(r["kpi.customer.n_delivered"]) != ref[(r["scenario"], r["seed"])]
    ]
    for m in mismatches:
        print(f"[S1] CROSS-CHECK FAIL: {m[0]} seed={m[1]} delivered={m[2]} != battery {m[3]}")
    n_checked = sum(1 for r in rows if (r["scenario"], r["seed"]) in ref)
    print(f"[S1] cross-check vs all39_battery: {n_checked} rows compared, "
          f"{len(mismatches)} mismatches")
    return len(mismatches)


def run_battery(workers: int, tier: str = DEFAULT_TIER) -> tuple[list[dict], int]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    tasks = [(stem, seed) for stem in scenario_stems(tier) for seed in SEEDS]
    tasks.sort(key=lambda t: -k_of(t[0]))  # longest-first: no K1000 tail straggler

    t0 = time.perf_counter()
    rows: list[dict] = []
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(one_run, t): t for t in tasks}
        for i, fut in enumerate(as_completed(futures), 1):
            stem, seed = futures[fut]
            rows.append(fut.result())  # worker exceptions re-raise here
            if i % 20 == 0 or i == len(tasks):
                print(f"[S1] {i}/{len(tasks)} runs done "
                      f"({time.perf_counter() - t0:.1f}s elapsed)")
    wall = time.perf_counter() - t0

    rows.sort(key=lambda r: (r["K"], r["scenario"], SEEDS.index(r["seed"])))
    fieldnames = sorted({k for r in rows for k in r}, key=lambda k: (
        ["scenario", "K", "tier", "seed", "wall_sec"].index(k)
        if k in ("scenario", "K", "tier", "seed", "wall_sec") else 5, k))
    with KPI_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"[S1] wrote {KPI_CSV} ({len(rows)} rows x {len(fieldnames)} cols) "
          f"in {wall:.1f}s wall ({workers} workers, tier={tier})")
    return rows, crosscheck_all39(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--traits-only", action="store_true")
    ap.add_argument("--battery-only", action="store_true")
    ap.add_argument("--workers", type=int, default=40)
    ap.add_argument(
        "--tier", choices=TIER_CHOICES, default=DEFAULT_TIER,
        help=f"demand-scenario tier to analyze (default: {DEFAULT_TIER}; "
             "'all' reproduces the pre-R5 38-scenario run). "
             "See analysis/scenario_tiers.py / configs/scenario_tiers.yaml.",
    )
    args = ap.parse_args()

    if not args.battery_only:
        write_traits(args.tier)
    mismatches = 0
    if not args.traits_only:
        _, mismatches = run_battery(args.workers, args.tier)
    return 1 if mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
