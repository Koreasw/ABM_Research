"""V2-BAL — EV load-balance audit (Stage W5c, etc/plan_h0v2_verification.md §4).

    .venv/bin/python -m analysis.vv_balance

WHY THIS EXISTS
---------------
`ControlSystemAgent.choose_elevator` is `min(evs, key=_estimate_wait)` over
`sorted(elevators, key=ev_id)`, so **every tie goes to the lowest ev_id**. The
estimate is

    |position_floor - rank(from_floor)| * per_floor_sec
  + door_open_close_sec * pending_stop_count
  + remaining door timer

which is exactly 0 for an idle car standing at the calling floor. With four
idle cars at the lobby, all four estimates are 0 and **EV1 wins every time**.

At 2 EVs (v1) that was worth at most one idle car. At 4 (v2, R1/R2) it can
idle three, which would (a) inflate rider EV waits against a fleet that is
nominally twice as large, and (b) bias every H1~H3 comparison, because the
robot-shareable cars are EV3/EV4 — if people systematically avoid them, the
robot inherits an artificially free shaft and its measured benefit is
overstated. That second point is a threat to the *paper's* validity, not just
to a KPI, which is why this audit is a gate rather than a footnote.

GATES (plan §4 W5c)
-------------------
Over the **primary tier** (20 scenarios x 3 seeds):

  G1  max/min of per-EV `n_boardings` <= 1.5
  G2  north-bank/south-bank boarding-sum ratio in [0.8, 1.25]

G2's band is symmetric by construction (1/1.25 = 0.8): a 25% surplus on either
bank fails identically, so the check does not silently privilege one side.
Bank membership is read from the run's own `ev_sides` config, never hard-coded
to "EV1+EV3 = north" — the fleet is declarative (plan §1.2) and an audit that
re-hard-codes it would pass a mis-wired building.

The extreme tier (K300, 8 scenarios) is measured and written too, but marked
`gate=False`. It is not part of the plan's pass criterion; it is here because
"does balance survive the heaviest demand in the corpus?" is the question the
gate would ask next, and the runs cost ~50 s.

LOW-LOAD PROBE (plan §4 W5c, "저부하 특이 확인 필수")
----------------------------------------------------
A corpus mean cannot see the tie-break at all. Under the standard 7.5 /min
pedestrian stream the cars are almost never simultaneously idle, so ties are
rare and the ratio looks healthy no matter how the tie is broken. The regime
where the tie-break IS the dispatch policy is a near-empty building, and it is
invisible in the battery.

So the probe runs a **10-order truncation** of K50_1 (orders 0..9, with the
DIST matrix sliced consistently at the pickup/drop index pairs) at two
pedestrian levels:

  ped 7.5 /min  — realistic low order load; cars still stirred by background
  ped 0   /min  — no background traffic at all: every hall call meets four
                  cars whose estimates can genuinely tie

and reports the per-EV split of **rider** hall calls (`boarding_log` carries
`kind`, so rider boardings are separable from pedestrian ones — the corpus
metric `n_boardings` pools both and would drown 10 riders in ~1,400
pedestrians). These rows are diagnostics, not gates: with no background
traffic and 10 orders, an idle-car monopoly costs nobody any waiting time, so
failing a run on it would be measuring an artefact. What matters is whether the
monopoly is total (a policy that never rotates) or partial (a policy that
self-corrects as cars drift off the lobby), and that is what the probe prints.

OUTPUT
------
  results/vv/ev_balance.csv   one row per (scope, scenario, seed) with per-EV
                              boardings, the two ratios, and the verdict.

Exit code 0 iff every gated row passes. A FAIL here is a **dispatch design
finding**, not a broken run: the fix would be a tie-break that rotates (e.g.
round-robin on equal estimates, or a small position-dependent epsilon), and it
would change every frozen snapshot, so it is a decision, not a patch.
"""

from __future__ import annotations

import csv
import json
import time
from collections import Counter
from pathlib import Path

import numpy as np

from analysis.scenario_tiers import scenario_paths as _tier_scenario_paths
from simulation.kpi import summarize
from simulation.model import BuildingHandoffModel, HandoffMode
from simulation.space import load_config

ROOT = Path(__file__).resolve().parent.parent
SCENARIO_DIR = ROOT / "data" / "data1"
BASE_CONFIG = ROOT / "configs" / "baseline_10f.yaml"
OUT_CSV = ROOT / "results" / "vv" / "ev_balance.csv"

SEEDS = [42, 7, 2026]              # same seed set as the W3 battery / V2-FACE

MAX_MIN_RATIO_MAX = 1.5            # G1
BANK_RATIO_BAND = (0.8, 1.25)      # G2 (symmetric: 1/1.25 == 0.8)

PROBE_N_ORDERS = 10                # "주문 10건 이하 synthetic"
PROBE_SCENARIO = "K50_1"
PROBE_PED_RATES = [7.5, 0.0]

FIELDNAMES = [
    "scope", "scenario", "seed", "ped_rate_per_min", "n_orders",
    "ev_ids", "boardings", "rider_boardings", "robot_boardings",
    "max_min_ratio", "north_sum", "south_sum", "bank_ratio",
    "top_ev", "top_ev_rider_share", "gate", "verdict", "note",
]


# --------------------------------------------------------------------- runs

def _run(config: dict, scenario_path: Path, seed: int) -> BuildingHandoffModel:
    """Paper track, mirroring simulation.run.run_baseline's profile-mode call.

    The model is built here rather than through run_baseline because the probe
    needs `elevator.boarding_log` (for the rider/pedestrian split), which the
    run_baseline payload does not carry. Every other argument is identical, and
    the boarding totals below are read back out of `summarize()` so the gated
    metric is literally the KPI the plan names.
    """
    model = BuildingHandoffModel(
        mode=HandoffMode.H0_DIRECT, config=config, scenario_path=scenario_path,
        dynamic_pool=True, return_leg=False, scenario_window=True,
        rng_seed=seed, floor_profile="uniform",
    )
    model.run_to_completion()
    return model


def _cfg(**overrides) -> dict:
    """baseline_10f config with dotted overrides (same helper shape as the tests)."""
    cfg = load_config(BASE_CONFIG)
    for dotted, val in overrides.items():
        d = cfg
        *parents, leaf = dotted.split(".")
        for p in parents:
            d = d[p]
        d[leaf] = val
    return cfg


def truncate_scenario(src: Path, dst: Path, n_orders: int) -> Path:
    """First `n_orders` orders of `src`, with DIST sliced to match.

    DIST is (2K x 2K) with pickup nodes 0..K-1 and drop nodes K..2K-1, indexed
    positionally (analysis.load_data.pickup_drop_distance). Truncating orders
    without re-slicing both index blocks would silently pair order i with a
    stranger's drop node, so the submatrix is taken over
    [0..n-1] + [K..K+n-1] on both axes.
    """
    raw = json.loads(src.read_text())
    k = int(raw["K"])
    if n_orders > k:
        raise ValueError(f"cannot truncate {src.stem} (K={k}) to {n_orders} orders")
    idx = list(range(n_orders)) + list(range(k, k + n_orders))
    dist = np.asarray(raw["DIST"], dtype=float)
    raw["K"] = n_orders
    raw["ORDERS"] = raw["ORDERS"][:n_orders]
    raw["DIST"] = dist[np.ix_(idx, idx)].tolist()
    raw["name"] = f"{raw['name']}_first{n_orders}"
    dst.write_text(json.dumps(raw))
    return dst


# ----------------------------------------------------------------- measures

def bank_of(config: dict) -> dict[str, str]:
    """{ev_id: 'north'|'south'} from the run's own declarative fleet config."""
    b = config["building"]
    return {f"EV{i + 1}": side for i, side in enumerate(b["ev_sides"])}


def measure(model: BuildingHandoffModel, config: dict) -> dict:
    """Per-EV boardings (gated metric) + the rider-only split (probe metric).

    A5 (결정 13 후속): the gated metric counts PEOPLE only. G1/G2 ask whether the
    building serves its occupants evenly across the two banks, and a robot is
    not an occupant — in a robot mode it boards only the shared cars by
    construction, so pooling it in would make the gate fail for the one reason
    it is not allowed to judge: that the design puts robots on EV3/EV4. In H0
    there are no robot boardings, so every historical W5c number is unchanged
    and this is a no-op on the frozen corpus.
    """
    kpi = summarize(model)["elevator"]
    ev_ids = sorted(kpi)
    boardings = {
        e: sum(
            n for kind, n in kpi[e]["n_boardings_by_kind"].items() if kind != "robot"
        )
        for e in ev_ids
    }
    robot = {
        ev.ev_id: sum(1 for b in ev.boarding_log if b["kind"] == "robot")
        for ev in model.elevators
    }
    rider = {
        ev.ev_id: sum(1 for b in ev.boarding_log if b["kind"] == "rider")
        for ev in model.elevators
    }

    lo, hi = min(boardings.values()), max(boardings.values())
    max_min = (hi / lo) if lo else float("inf")

    banks = bank_of(config)
    north = sum(v for e, v in boardings.items() if banks[e] == "north")
    south = sum(v for e, v in boardings.items() if banks[e] == "south")
    bank_ratio = (north / south) if south else float("inf")

    total_rider = sum(rider.values())
    top_ev, top_n = Counter(rider).most_common(1)[0] if total_rider else ("-", 0)
    return {
        "ev_ids": "|".join(ev_ids),
        "boardings": "|".join(str(boardings[e]) for e in ev_ids),
        "rider_boardings": "|".join(str(rider.get(e, 0)) for e in ev_ids),
        # information column: robot boardings are excluded from every gate above
        # but must stay visible, because "the shared cars carry N robot trips"
        # is the mechanism the balance numbers are being read against
        "robot_boardings": "|".join(str(robot.get(e, 0)) for e in ev_ids),
        "max_min_ratio": max_min,
        "north_sum": north,
        "south_sum": south,
        "bank_ratio": bank_ratio,
        "top_ev": top_ev,
        "top_ev_rider_share": (top_n / total_rider) if total_rider else None,
    }


def judge(row: dict) -> str:
    lo, hi = BANK_RATIO_BAND
    g1 = row["max_min_ratio"] <= MAX_MIN_RATIO_MAX
    g2 = lo <= row["bank_ratio"] <= hi
    if g1 and g2:
        return "PASS"
    return "FAIL:" + ",".join(n for n, ok in (("G1", g1), ("G2", g2)) if not ok)


# ------------------------------------------------------------------ sweeps

def corpus_sweep() -> list[dict]:
    """Primary tier (gated) + extreme tier (reported) x SEEDS."""
    rows: list[dict] = []
    config = _cfg()
    primary = {p.stem for p in _tier_scenario_paths("primary", SCENARIO_DIR)}
    scenarios = _tier_scenario_paths("all", SCENARIO_DIR)
    assert len(scenarios) == 28, f"expected 28 corpus scenarios, got {len(scenarios)}"
    assert len(primary) == 20, f"expected 20 primary scenarios, got {len(primary)}"

    for path in scenarios:
        gated = path.stem in primary
        for seed in SEEDS:
            model = _run(config, path, seed)
            row = {
                "scope": "primary" if gated else "extreme",
                "scenario": path.stem, "seed": seed,
                "ped_rate_per_min": config["pedestrian"]["arrival_rate_per_min"],
                "n_orders": model.K,
                **measure(model, config),
            }
            row["gate"] = gated
            row["verdict"] = judge(row) if gated else "info"
            row["note"] = ""
            rows.append(row)
            print(f"[{row['scope']:<7}] {path.stem:<8} seed={seed:<5} "
                  f"boardings={row['boardings']:<24} "
                  f"max/min={row['max_min_ratio']:.3f} "
                  f"N/S={row['bank_ratio']:.3f} -> {row['verdict']}")
    return rows


def low_load_probe(tmpdir: Path) -> list[dict]:
    """10-order truncation at two pedestrian levels — diagnostic, never gated."""
    rows: list[dict] = []
    src = SCENARIO_DIR / f"{PROBE_SCENARIO}.json"
    scen = truncate_scenario(
        src, tmpdir / f"{PROBE_SCENARIO}_first{PROBE_N_ORDERS}.json", PROBE_N_ORDERS)

    for rate in PROBE_PED_RATES:
        config = _cfg(**{"pedestrian.arrival_rate_per_min": rate})
        for seed in SEEDS:
            model = _run(config, scen, seed)
            row = {
                "scope": "low_load_probe",
                "scenario": f"{PROBE_SCENARIO}_first{PROBE_N_ORDERS}", "seed": seed,
                "ped_rate_per_min": rate, "n_orders": model.K,
                **measure(model, config),
            }
            row["gate"] = False
            row["verdict"] = "info"
            row["note"] = ("no background traffic — pure tie-break regime"
                           if rate == 0.0 else "background traffic stirs the cars")
            rows.append(row)
            share = row["top_ev_rider_share"]
            print(f"[probe  ] ped={rate:<5} seed={seed:<5} "
                  f"rider_boardings={row['rider_boardings']:<16} "
                  f"top={row['top_ev']} share="
                  f"{'n/a' if share is None else f'{share:.0%}'}")
    return rows


# ------------------------------------------------------------------ report

def write_csv(rows: list[dict]) -> None:
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES)
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    import tempfile

    t0 = time.perf_counter()
    print("=== corpus sweep (primary gated, extreme reported) ===")
    rows = corpus_sweep()

    print("\n=== low-load probe (10 orders, diagnostic) ===")
    with tempfile.TemporaryDirectory(prefix="vv_bal_") as tmp:
        rows += low_load_probe(Path(tmp))

    write_csv(rows)

    gated = [r for r in rows if r["gate"]]
    failed = [r for r in gated if r["verdict"] != "PASS"]
    ratios = [r["max_min_ratio"] for r in gated]
    banks = [r["bank_ratio"] for r in gated]
    probe = [r for r in rows if r["scope"] == "low_load_probe"]

    print("\n" + "=" * 72)
    print(f"V2-BAL: {len(rows)} runs, wall={time.perf_counter() - t0:.1f}s")
    print(f"gated rows (primary x {len(SEEDS)} seeds): {len(gated)}")
    print(f"  G1 max/min boardings : max {max(ratios):.3f} "
          f"(limit {MAX_MIN_RATIO_MAX}) — worst {gated[ratios.index(max(ratios))]['scenario']}")
    print(f"  G2 north/south ratio : {min(banks):.3f} .. {max(banks):.3f} "
          f"(band {BANK_RATIO_BAND[0]}..{BANK_RATIO_BAND[1]})")
    for rate in PROBE_PED_RATES:
        sub = [r for r in probe if r["ped_rate_per_min"] == rate]
        shares = [r["top_ev_rider_share"] for r in sub if r["top_ev_rider_share"]]
        tops = Counter(r["top_ev"] for r in sub)
        print(f"  probe ped={rate:<5} top-EV rider share "
              f"{min(shares):.0%}..{max(shares):.0%}, busiest car {dict(tops)}")
    print(f"\nwrote {OUT_CSV} ({len(rows)} rows)")
    print("OVERALL:", "PASS" if not failed else f"FAIL ({len(failed)} rows)")
    for r in failed:
        print(f"  {r['scenario']} seed={r['seed']}: {r['verdict']} "
              f"max/min={r['max_min_ratio']:.3f} N/S={r['bank_ratio']:.3f}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
