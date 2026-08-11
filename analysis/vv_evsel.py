"""V-EVSEL — EV dispatch-heuristic staleness quantification (plan §2 L5-3).

    .venv/bin/python -m analysis.vv_evsel

Quantifies how often the H0 "designated-dispatch" heuristic
(ControlSystemAgent.choose_elevator) commits a passenger to an EV that is no
longer the min-estimated-wait EV by the time the hall call is actually
registered, and bounds the extra wait that staleness can cost. This is the
defence figure behind the paper's designated-dispatch simplification.

SELECTION vs REGISTRATION (why staleness exists)
------------------------------------------------
choose_elevator picks argmin `_estimate_wait(ev, from_floor)` at the moment a
passenger *enters the building / finishes service* (ExternalRiderAgent /
PedestrianAgent __init__ or post-service). The passenger then walks to that EV
shaft and only registers the hall call on arrival — several sim-seconds later.
During that walk the EVs move, so the committed EV can differ from the current
argmin. The commitment is irrevocable (the passenger is already at that shaft),
which is exactly the heuristic's cost.

The `evsel` model instrumentation (opt-in, bit-identical when off) re-evaluates
the *same* cost function against live EV state at registration time and logs,
per hall call: the chosen EV, the re-eval-optimal EV, `stale` (they differ), the
two estimates, a physical lower bound on the re-eval-optimal EV's wait, and the
realized wait once the passenger boards.

METRICS
-------
* stale ratio = #stale / #hall-calls, per (scenario, seed, kind) and overall.
* additional-wait upper bound (per stale hall call):
      harm = max(0, observed_wait(chosen) - LB(re-eval-optimal))
  `observed_wait(chosen)` is the realized register->board time on the committed
  EV (an exact measurement). `LB(re-eval-optimal)` is a STRICT physical lower
  bound on how long the re-eval-optimal EV would have needed to reach the floor
  — pure directional travel `|pos - from_floor| * per_floor_sec`, ignoring door
  cycles and every intermediate stop. Because the true counterfactual wait is
  >= LB, `observed - LB` upper-bounds the true additional wait; clipping at 0
  drops "false-alarm" stale flags where the committed EV was in fact no slower
  than the other EV's physical floor (a genuine no-harm case). This is a
  deliberately CONSERVATIVE (loose-high) bound: exact counterfactuals need a
  full re-simulation, which is out of scope here.
* heuristic-predicted delta (secondary, tighter): est_chosen - est_reeval_best,
  the improvement the heuristic's OWN cost model would have claimed at
  registration time. >0 by construction on stale calls. Reported alongside as a
  model-consistent (not physical) view of the gap.

Representative scenarios K50_1 / K200_1 / K300_4 x seeds {42, 7, 2026}
(low / mid / high demand within the 28-file corpus — the old K1000_1 top rung
is out of corpus for this study, 사용자 확정 2026-08-03 2차, so K200_1 takes the
middle slot to keep a 3-step monotone K ladder).
Writes results/vv/evsel_stale.csv (verification-run convention, plan §6).
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

from simulation.run import run_baseline

ROOT = Path(__file__).resolve().parent.parent
OUT_CSV = ROOT / "results" / "vv" / "evsel_stale.csv"

SCENARIOS = ["K50_1", "K200_1", "K300_4"]
SEEDS = [42, 7, 2026]

FIELDNAMES = [
    "scenario", "seed", "kind",
    "n_calls", "n_stale", "stale_ratio",
    "harm_mean_sec", "harm_p95_sec", "harm_max_sec",
    "hdelta_mean_sec", "hdelta_p95_sec", "hdelta_max_sec",
]


def _harm(event: dict) -> float:
    """Conservative upper bound on additional wait for one stale hall call."""
    return max(0.0, event["observed_wait_sec"] - event["reeval_best_lb_sec"])


def _hdelta(event: dict) -> float:
    """Heuristic's own predicted improvement at registration time (>=0)."""
    return event["est_chosen_sec"] - event["est_reeval_best_sec"]


def _summary_row(scenario: str, seed, kind: str, events: list[dict]) -> dict:
    # a hall call counts only once it has boarded (observed wait known)
    calls = [e for e in events if e["observed_wait_sec"] is not None]
    stale = [e for e in calls if e["stale"]]
    harms = np.array([_harm(e) for e in stale], dtype=float)
    hdeltas = np.array([_hdelta(e) for e in stale], dtype=float)

    def stat(a: np.ndarray, fn) -> float | str:
        return round(float(fn(a)), 3) if a.size else ""

    return {
        "scenario": scenario,
        "seed": seed,
        "kind": kind,
        "n_calls": len(calls),
        "n_stale": len(stale),
        "stale_ratio": round(len(stale) / len(calls), 4) if calls else "",
        "harm_mean_sec": stat(harms, np.mean),
        "harm_p95_sec": stat(harms, lambda a: np.percentile(a, 95)),
        "harm_max_sec": stat(harms, np.max),
        "hdelta_mean_sec": stat(hdeltas, np.mean),
        "hdelta_p95_sec": stat(hdeltas, lambda a: np.percentile(a, 95)),
        "hdelta_max_sec": stat(hdeltas, np.max),
    }


def _kinds(events: list[dict]) -> list[str]:
    present = {e["kind"] for e in events}
    return [k for k in ("rider", "pedestrian") if k in present] + ["all"]


def _by_kind(events: list[dict], kind: str) -> list[dict]:
    return events if kind == "all" else [e for e in events if e["kind"] == kind]


def run() -> list[dict]:
    rows: list[dict] = []
    pooled: list[dict] = []  # all events across every scenario/seed

    for scenario in SCENARIOS:
        for seed in SEEDS:
            result = run_baseline(
                scenario_path=f"data/data1/{scenario}.json",
                rng_seed=seed,
                floor_profile="uniform",
                evsel=True,
            )
            events = result["evsel_events"]
            pooled.extend(events)
            for kind in _kinds(events):
                row = _summary_row(scenario, seed, kind, _by_kind(events, kind))
                rows.append(row)
                if kind == "all":
                    print(
                        f"[{scenario:<8} s{seed:<4}] calls={row['n_calls']:<5} "
                        f"stale={row['n_stale']:<4} "
                        f"ratio={row['stale_ratio']:<7} "
                        f"harm(mean/p95/max)="
                        f"{row['harm_mean_sec']}/{row['harm_p95_sec']}/"
                        f"{row['harm_max_sec']}s"
                    )

    for kind in _kinds(pooled):
        rows.append(_summary_row("ALL", "ALL", kind, _by_kind(pooled, kind)))

    return rows


def write_csv(rows: list[dict]) -> None:
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    rows = run()
    write_csv(rows)
    print(f"\nwrote {OUT_CSV} ({len(rows)} rows)")
    for r in rows:
        if r["scenario"] == "ALL":
            print(
                f"  TOTAL[{r['kind']:<10}] calls={r['n_calls']:<6} "
                f"stale_ratio={r['stale_ratio']} "
                f"harm mean/p95/max={r['harm_mean_sec']}/{r['harm_p95_sec']}/"
                f"{r['harm_max_sec']}s"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
