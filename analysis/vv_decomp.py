"""V-DECOMP — delivery-time decomposition stacked bar (Stage V5a, etc/plan_h0_verification.md §2 L5 #1).

    python -m analysis.vv_decomp

Draft paper figure: decompose each order's end-to-end delivery time T_e2e
(= delivered - ord) into the additive chain of stages it passes through, then
draw two stacked-bar figures — per-K-group **mean** and **95th percentile**.

Components (bottom -> top of the stack, in chronological order):

    cook        ready_time - ord_time          food preparation
    rider_wait  dispatch_time - ready_time      wait in the dynamic rider pool
    street      (arrival - dispatch) + entry_lag  shop -> building street leg
                                                  (dist/v; entry_lag <= 1 tick is
                                                  the spawn-quantization slice,
                                                  folded in here)
    walk        lobby_entry -> vertical -> office (tick-faithful graph walk)
    ev_wait     ev_wait_up_sec                  hall-call wait for a busy car
    ride        vertical up-leg                 elevator: RESIDUAL board->alight
                                                (incl. door cycle + SCAN inter-
                                                mediate stops); stairs: climb timer
    service     service_time (tick-quantized)   drop-off at the office

This is the T_e2e (delivery) leg only: it stops at `delivered`, so it covers
the UP journey (walk-up + ride-up + service) and NOT the rider's return/exit.
It is therefore a *delivery-leg* refinement of the round-trip A5 t_lobby
identity (analysis/verify_h0.check_lobby_identity), whose tick-faithful helpers
(_walk_ticks / _timer_ticks) and elevator treatment we reuse verbatim.

Why `ride` is a residual for elevators (faithful to A5): under load the SCAN
car makes intermediate stops for other passengers, so the true board->alight
span exceeds the direct kinematic floor 2 travel(1,f)+door. The kinematic value
is only a lower bound, so ride is measured as the leftover
(delivered - entered - walk - ev_wait - service) and *gated* to clear that
kinematic floor (>= floor - 1 tick, same allowance as A5 / verify_baseline #4).
For stairs the climb is a deterministic off-graph timer, so the whole leg is
reconstructed exactly (float-epsilon residual) — a genuine independent check.

Integrity gate (this item's pass criterion — figure trustworthiness): for every
order, (a) the seven components sum to the recorded T_e2e within the A5 tick
tolerance, (b) every component is non-negative, and (c) each elevator ride
clears its kinematic floor. Asserted over ALL orders of ALL 28 corpus scenarios.

Footnotes reflected in the figures:
  * "congestion not modeled" (D3, etc/plan_h0_verification.md §0.1): the walker
    speed is constant, so there is NO corridor-congestion component — the term
    is structurally zero and is deliberately absent (not drawn as a 0 band).
  * ev_wait: an *idle* car boards the rider on the hall-call tick, so ev_wait is
    exactly 0 and the door cycle lives inside `ride` (V-GP / V2 finding). The
    positive ev_wait seen at higher K is genuine contention for the two shared
    cars — the same signal as V-MONO ⑥ (W_EV rises with K).

Data: the 28-scenario modelling corpus x seed 42 (one seed suffices; the full
sweep is ~70 s at 28 scenarios, per the V-ALL39 budget).

CORPUS REGIME CHANGE (사용자 확정 2026-08-03, 2차): K500/K750/K1000 (11 files)
are held out of the modelling corpus for this study, so this script no longer
globs data/data1 for 39 files — it resolves the corpus through
analysis.scenario_tiers.scenario_paths("all") (primary 20 + extreme 8 = 28),
the single source of truth shared with the tier-aware analysis runners. The
old K1000_4 ≡ K1000_5 byte-duplicate caveat is moot here: both files are
outside the corpus entirely (duplicate detection itself lives in
analysis/vv_data_integrity.py).

Outputs (verification-run convention, plan §6):
    results/vv/decomp_by_k.csv     per-K component mean & p95 table
    results/vv/decomp_mean.png     mean stacked bar
    results/vv/decomp_p95.png      p95 stacked bar
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

from analysis.scenario_tiers import scenario_paths as _tier_scenario_paths
from analysis.verify_h0 import (
    FLOAT_TOL,
    STAIR_NODE_1F,
    _graph_and_kin,
    _tick,
    _timer_ticks,
    _walk_dist,
    _walk_ticks,
)
from simulation.run import run_baseline

ROOT = Path(__file__).resolve().parent.parent
SCENARIO_DIR = ROOT / "data" / "data1"
OUT_DIR = ROOT / "results" / "vv"
OUT_CSV = OUT_DIR / "decomp_by_k.csv"
OUT_MEAN_PNG = OUT_DIR / "decomp_mean.png"
OUT_P95_PNG = OUT_DIR / "decomp_p95.png"

SEED = 42

# stack order (bottom -> top), colours (Okabe-Ito, colour-blind safe)
COMPONENTS = ["cook", "rider_wait", "street", "walk", "ev_wait", "ride", "service"]
COMPONENT_LABELS = {
    "cook": "cook (ready-ord)",
    "rider_wait": "rider_wait (pool queue)",
    "street": "street (dist/v)",
    "walk": "walk (lobby->office)",
    "ev_wait": "ev_wait (hall call)",
    "ride": "ride (vertical up)",
    "service": "service (drop-off)",
}
COMPONENT_COLORS = {
    "cook": "#E69F00",
    "rider_wait": "#D55E00",
    "street": "#0072B2",
    "walk": "#56B4E9",
    "ev_wait": "#CC79A7",
    "ride": "#009E73",
    "service": "#F0E442",
}


def _k_group(stem: str) -> int:
    """Nominal K from a scenario stem, e.g. 'K1000_4' -> 1000."""
    return int(stem.split("_")[0][1:])


class _Ctx:
    """Precomputed per-result reconstruction context (graph, kinematics)."""

    def __init__(self, result: dict) -> None:
        self.res = result
        self.tick = _tick(result)
        cfg = result["config"]
        self.g, self.kin = _graph_and_kin(result)
        self.v_walk = cfg["rider_process"]["walk_speed_mps"]
        self.sps = cfg["vertical"]["stair_sec_per_floor"]
        self.door = self.kin.door_open_close_sec
        self.l1_stair = _walk_dist(self.g, "lobby_entry", STAIR_NODE_1F)


def decompose_order(rec: dict, ctx: _Ctx) -> dict:
    """Decompose one order's T_e2e into the seven additive components.

    Returns a dict with the seven component seconds plus bookkeeping:
    ``t_e2e``, ``residual`` (sum - recorded), ``ride_floor_slack`` (elevator
    only, else None) and ``vertical_mode``. Reconstruction mirrors A5
    (verify_h0.check_lobby_identity) restricted to the delivery/up leg: the
    first walk leg shares the creation tick (``-tick``), stairs are exact, and
    the elevator ride is the leftover of the measured up leg.
    """
    tick = ctx.tick
    f, office = rec["floor"], rec["office_id"]
    office_node = f"floor_{f}_office_{office}"

    cook = rec["ready_time_sec"] - rec["ord_time_abs_sec"]
    rider_wait = rec["rider_wait_sec"] or 0.0
    entry_lag = rec["entered_at_sec"] - rec["arrival_time_planned_sec"]
    street = rec["horizontal_time_s"] + entry_lag  # fold sub-tick entry lag in
    svc = _timer_ticks(rec["service_time_sec"], tick) * tick
    deliver = rec["delivered_at_sec"] - rec["entered_at_sec"]  # up leg span

    ride_floor_slack = None
    if rec["vertical_mode"] == "stairs":
        l2 = _walk_dist(ctx.g, f"floor_{f}_corr_{ctx.g.graph['corridor_mid_pos']}", office_node)
        w1 = _walk_ticks(ctx.l1_stair, ctx.v_walk, tick) * tick
        w2 = _walk_ticks(l2, ctx.v_walk, tick) * tick
        walk = (w1 - tick) + w2  # walk_to_vert shares the creation tick
        ev_wait = 0.0
        ride = _timer_ticks((f - 1) * ctx.sps, tick) * tick  # exact climb timer
    else:
        ev_ids = ctx.g.graph["ev_ids"]
        leg1 = min(_walk_dist(ctx.g, "lobby_entry", f"ev_{e}_1") for e in ev_ids)
        leg2 = min(_walk_dist(ctx.g, f"ev_{e}_{f}", office_node) for e in ev_ids)
        w1 = _walk_ticks(leg1, ctx.v_walk, tick) * tick
        w2 = _walk_ticks(leg2, ctx.v_walk, tick) * tick
        walk = (w1 - tick) + w2
        ev_wait = rec["ev_wait_up_sec"] or 0.0
        ride = deliver - walk - ev_wait - svc  # residual board->alight span
        ride_floor = ctx.kin.travel_time_sec(1, f) + ctx.door
        ride_floor_slack = ride - ride_floor

    comps = {
        "cook": cook,
        "rider_wait": rider_wait,
        "street": street,
        "walk": walk,
        "ev_wait": ev_wait,
        "ride": ride,
        "service": svc,
    }
    total = sum(comps.values())
    comps.update(
        ord_id=rec["ord_id"],
        vertical_mode=rec["vertical_mode"],
        t_e2e=rec["t_e2e_sec"],
        residual=total - rec["t_e2e_sec"],
        ride_floor_slack=ride_floor_slack,
    )
    return comps


def decompose_result(result: dict) -> tuple[list[dict], list[str]]:
    """Decompose every order of one run; return (rows, integrity failures).

    Failures (empty list == PASS): sum-vs-T_e2e residual above the tick
    tolerance, any negative component, or an elevator ride below its kinematic
    floor (allowance: one tick, A5 / verify_baseline #4 convention).
    """
    ctx = _Ctx(result)
    tick = ctx.tick
    rows, fails = [], []
    for rec in result["per_order"]:
        row = decompose_order(rec, ctx)
        rows.append(row)
        oid = row["ord_id"]
        if abs(row["residual"]) > tick + FLOAT_TOL:
            fails.append(
                f"ord {oid}: components sum {sum(row[c] for c in COMPONENTS):.3f} "
                f"!= T_e2e {row['t_e2e']:.3f} (residual {row['residual']:+.3f}s)"
            )
        for c in COMPONENTS:
            if row[c] < -FLOAT_TOL:
                fails.append(f"ord {oid}: component {c} negative ({row[c]:+.3f}s)")
        slack = row["ride_floor_slack"]
        if slack is not None and slack < -tick - FLOAT_TOL:
            fails.append(
                f"ord {oid}: elevator ride below kinematic floor "
                f"(slack {slack:+.3f}s, tolerance {tick}s)"
            )
    return rows, fails


# ----------------------------------------------------------------- aggregation


def build_k_table(by_k: dict[int, list[dict]]) -> list[dict]:
    """Per-K-group mean & p95 of each component (+ recorded T_e2e).

    Returns long rows: one per (K, stat). For the ``mean`` stat the component
    means sum to the T_e2e mean (exact partition); for ``p95`` they do not
    (percentiles are not additive) — this is expected and noted in the figure.
    """
    table = []
    for K in sorted(by_k):
        rows = by_k[K]
        arrs = {c: np.array([r[c] for r in rows]) for c in COMPONENTS}
        t_e2e = np.array([r["t_e2e"] for r in rows])
        for stat, fn in (("mean", np.mean), ("p95", lambda a: np.percentile(a, 95))):
            entry = {"K": K, "n_orders": len(rows), "stat": stat}
            for c in COMPONENTS:
                entry[c] = round(float(fn(arrs[c])), 3)
            entry["components_total"] = round(sum(entry[c] for c in COMPONENTS), 3)
            entry["t_e2e"] = round(float(fn(t_e2e)), 3)
            table.append(entry)
    return table


def write_csv(table: list[dict]) -> None:
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    fields = ["K", "n_orders", "stat", *COMPONENTS, "components_total", "t_e2e"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(table)


# --------------------------------------------------------------------- figures

_CAPTION = (
    "Delivery-time (T_e2e) decomposition, paper track (dynamic pool + scenario "
    "window + uniform profile), data/data1 39 scenarios x seed 42.\n"
    "Congestion not modeled (D3): walker speed is constant, so there is no "
    "corridor-congestion term.  ev_wait=0 for an idle car (door cycle sits in "
    "ride); positive ev_wait is genuine 2-car contention (cf. V-MONO ⑥)."
)


def _stacked_bar(table: list[dict], stat: str, out_path: Path, title: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = [r for r in table if r["stat"] == stat]
    rows.sort(key=lambda r: r["K"])
    ks = [f"K{r['K']}\n(n={r['n_orders']})" for r in rows]
    x = np.arange(len(rows))

    fig, ax = plt.subplots(figsize=(10, 6))
    bottom = np.zeros(len(rows))
    for c in COMPONENTS:
        vals = np.array([r[c] for r in rows])
        ax.bar(x, vals, bottom=bottom, width=0.62, label=COMPONENT_LABELS[c],
               color=COMPONENT_COLORS[c], edgecolor="white", linewidth=0.4)
        bottom += vals

    ax.set_xticks(x)
    ax.set_xticklabels(ks)
    ax.set_ylabel("seconds")
    ax.set_title(title)
    ax.legend(loc="upper left", fontsize=8, framealpha=0.9)
    ax.grid(axis="y", alpha=0.3)
    ax.margins(x=0.02)
    note = _CAPTION
    if stat == "p95":
        note += ("\nStacked component p95s do not sum to T_e2e p95 (percentiles "
                 "are not additive) — read each band on its own.")
    fig.text(0.01, -0.02, note, fontsize=7, va="top")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(out_path, dpi=130, bbox_inches="tight")
    plt.close(fig)


def make_figures(table: list[dict]) -> None:
    _stacked_bar(table, "mean", OUT_MEAN_PNG,
                 "T_e2e decomposition by K — mean per component")
    _stacked_bar(table, "p95", OUT_P95_PNG,
                 "T_e2e decomposition by K — 95th percentile per component")


# ------------------------------------------------------------------------ main


def run_all(seed: int = SEED) -> tuple[dict[int, list[dict]], float]:
    """Decompose every corpus scenario (28) at one seed; return (by_K, max|resid|)."""
    scenarios = _tier_scenario_paths("all", SCENARIO_DIR)
    assert len(scenarios) == 28, f"expected 28 corpus scenarios, found {len(scenarios)}"

    by_k: dict[int, list[dict]] = {}
    max_resid = 0.0
    for path in scenarios:
        result = run_baseline(scenario_path=path, rng_seed=seed, floor_profile="uniform")
        rows, fails = decompose_result(result)
        if fails:
            raise AssertionError(
                f"{path.stem}: decomposition integrity FAILED ({len(fails)}): "
                + "; ".join(fails[:5])
            )
        max_resid = max(max_resid, max(abs(r["residual"]) for r in rows))
        by_k.setdefault(_k_group(path.stem), []).extend(rows)
        print(f"[OK] {path.stem:<10} K={_k_group(path.stem):<5} "
              f"orders={len(rows)} max|resid|={max(abs(r['residual']) for r in rows):.2e}")
    return by_k, max_resid


def main() -> int:
    by_k, max_resid = run_all()
    tick = 1.0  # paper-track tick; reported alongside the residual
    print(f"\nPer-order residual gate: max|sum-T_e2e| = {max_resid:.3e}s "
          f"(tolerance {tick}s tick) -> PASS")

    table = build_k_table(by_k)
    write_csv(table)
    make_figures(table)

    print(f"\nwrote {OUT_CSV}")
    print(f"wrote {OUT_MEAN_PNG}")
    print(f"wrote {OUT_P95_PNG}")
    print("\nmean T_e2e decomposition by K (seconds):")
    hdr = "  K      n    " + "".join(f"{c:>11}" for c in COMPONENTS) + f"{'total':>9}{'t_e2e':>9}"
    print(hdr)
    for r in table:
        if r["stat"] != "mean":
            continue
        print(f"  {r['K']:<6} {r['n_orders']:<4} "
              + "".join(f"{r[c]:>11.2f}" for c in COMPONENTS)
              + f"{r['components_total']:>9.2f}{r['t_e2e']:>9.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
