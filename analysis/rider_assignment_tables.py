"""Rider-assignment tables — reproducible source for the doc revision.

Regenerates every table that `etc/rider_type_assignment_inventory.md` §0/§8
needs, by calling the production cost/priority functions in
`analysis.rider_arrival_model` (`compute_w_R_krw_per_h`, `delivery_cost_krw`,
`type_priority`) against the real `data/data1/K*.json` scenarios — never by
re-implementing the cost formula. See `etc/plan_rider_assignment_revision.md`
§3 for the spec this module fulfils, and §0/§1 for the fact pattern it is
meant to replace ("hand-written numbers must not survive in the doc").

Scenario set: the modelling corpus resolved through `analysis.scenario_tiers`
(`scenario_paths("all")`) — **28 scenarios** (primary K50/K100/K200 = 20 +
extreme K300 = 8).

POPULATION CHANGE, 사용자 확정 2026-08-04: this used to run over 38 scenarios
(all 39 data1 files minus the `K1000_5` md5 duplicate of `K1000_4`) on the
grounds that rider-type assignment is a property of the city distance data
rather than of the building. The user chose instead to align the cited
population with the modelling corpus, so K500/K750/K1000 are no longer counted
here. Two consequences to keep in mind when reading the tables:
  * every headline number moved (order total, WALK-first count and share, the
    per-scenario row count), so quoting a figure from a pre-2026-08-04 draft
    against a current table will mismatch — regenerate rather than reconcile;
  * the `K1000_5` duplicate is moot: both K1000 files are outside the corpus,
    so no de-duplication step is needed at all any more.

Distance-regime sampling convention (plan §3, "concrete distances, never
hard-coded orderings"): for a combo with crossovers D*(BIKE,WALK) and
D*(WALK,CAR), the three priority regimes are sampled at
  near = max(D*(BIKE,WALK) / 2, 1.0)                    -- literal D -> 0 regime
  mid  = (D*(BIKE,WALK) + D*(WALK,CAR)) / 2              -- between the crossovers
  far  = D*(WALK,CAR) * 2                                -- literal D -> inf regime
`type_priority` is called at each of these three points; nothing about the
ordering is hard-coded. Note: for combos where D*(BIKE,WALK) is tiny relative
to real order distances (e.g. (5000,5000,5000): D*(BIKE,WALK)~53m), the
"near" sample below correctly reports the literal WALK-before-BIKE regime,
even though that sliver is practically negligible in the real distance
distribution (min real distances start around 180m) — callers who want the
"practically relevant" ordering for such combos should look at `mid_priority`
instead of `near_priority`.

CLI:
    python -m analysis.rider_assignment_tables
    python -m analysis.rider_assignment_tables --throughput 60 --json out.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np

from analysis.load_data import Rider, Scenario, load_scenario, pickup_drop_distance
from analysis.scenario_tiers import scenario_paths as _tier_scenario_paths
from analysis.rider_arrival_model import (
    compute_w_R_krw_per_h,
    delivery_cost_krw,
    type_priority,
)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SCENARIO_DIR = ROOT / "data" / "data1"
RIDER_TYPES = ("BIKE", "WALK", "CAR")

# Kept for provenance only: K1000_5.json is an md5-identical duplicate of
# K1000_4.json (etc/plan_rider_assignment_revision.md §0). It no longer does any
# filtering work — both files are outside the 28-scenario corpus — but naming it
# here documents why the old population was 38 rather than 39.
EXCLUDED_DUPLICATES = frozenset({"K1000_5.json"})

_STEM_RE = re.compile(r"^K(\d+)_(\d+)$")


def _natural_key(stem: str) -> tuple[int, int]:
    """Sort key for scenario stems 'K<K>_<idx>': group by K, then index."""
    m = _STEM_RE.match(stem)
    if not m:
        raise ValueError(f"scenario stem does not match K<K>_<idx>: {stem!r}")
    return (int(m.group(1)), int(m.group(2)))


def default_scenario_paths() -> list[Path]:
    """The 28-scenario modelling corpus, in natural K order.

    Resolved through `analysis.scenario_tiers` so this module cannot drift from
    the tier definition (사용자 확정 2026-08-04 — see the module docstring for
    why the population moved from 38 to 28). Only the sort order is applied
    here: `scenario_paths` returns lexicographic order, in which K100_* sorts
    before K50_*, whereas every table in the doc is read in ascending K.
    """
    paths = _tier_scenario_paths("all", DEFAULT_SCENARIO_DIR)
    return sorted(paths, key=lambda p: _natural_key(p.stem))


def _resolve_paths(scenario_paths: list[str | Path] | None) -> list[Path]:
    if scenario_paths is None:
        return default_scenario_paths()
    return [Path(p) for p in scenario_paths]


def _fixed_cost_tuple(riders: list[Rider]) -> tuple[float, float, float]:
    by_type = {r.type: r.fixed_cost for r in riders}
    return tuple(by_type[t] for t in RIDER_TYPES)


def _rho_tuple(scenario: Scenario) -> tuple[float, float, float]:
    by_type = {r.type: round(r.available_number / scenario.K, 1) for r in scenario.riders}
    return tuple(by_type[t] for t in RIDER_TYPES)


def _slope_intercept(
    riders: list[Rider], throughput: float
) -> tuple[dict[str, float], dict[str, float]]:
    """Derive slope/intercept per type FROM delivery_cost_krw, not re-implemented.

    intercept_t = delivery_cost_krw(r, 0.0); slope_t = delivery_cost_krw(r, 1.0) -
    delivery_cost_krw(r, 0.0) (plan §3 instruction; algebra documented in
    etc/rider_type_assignment_inventory.md §1-2).
    """
    intercept = {r.type: delivery_cost_krw(r, 0.0, throughput) for r in riders}
    slope = {
        r.type: delivery_cost_krw(r, 1.0, throughput) - delivery_cost_krw(r, 0.0, throughput)
        for r in riders
    }
    return slope, intercept


def _crossover(slope: dict[str, float], intercept: dict[str, float], a: str, b: str) -> float | None:
    """D*(a,b) = (intercept_b - intercept_a) / (slope_a - slope_b).

    None if the slopes are equal (no finite crossover). A non-positive value
    means the crossover is not reached at any D >= 0, i.e. one type
    completely dominates the other (etc/rider_type_assignment_inventory.md §2).
    """
    denom = slope[a] - slope[b]
    if denom == 0:
        return None
    return (intercept[b] - intercept[a]) / denom


def cost_sets(
    scenario_paths: list[str | Path] | None = None, throughput: float = 50.0
) -> list[dict]:
    """Group scenarios by fixed_cost tuple; derive costs/crossovers/priorities.

    Returns one dict per unique (BIKE, WALK, CAR) fixed_cost combo, sorted by
    fixed_cost tuple ascending. Each dict:
      fixed_cost, w_R, slope, intercept        -- per-type (dicts keyed by RIDER_TYPES)
      d_star_bw, d_star_wc, d_star_bc           -- D*(BIKE,WALK)/D*(WALK,CAR)/D*(BIKE,CAR)
      near_d/mid_d/far_d, near_priority/mid_priority/far_priority
      n_scenarios, stems
    """
    paths = _resolve_paths(scenario_paths)
    combo_stems: dict[tuple[float, float, float], list[str]] = {}
    combo_riders: dict[tuple[float, float, float], list[Rider]] = {}
    for p in paths:
        scenario = load_scenario(p)
        combo = _fixed_cost_tuple(scenario.riders)
        combo_stems.setdefault(combo, []).append(p.stem)
        combo_riders.setdefault(combo, scenario.riders)

    results: list[dict] = []
    for combo in sorted(combo_stems):
        riders = combo_riders[combo]
        stems = combo_stems[combo]
        slope, intercept = _slope_intercept(riders, throughput)
        w_R = {r.type: compute_w_R_krw_per_h(r, throughput) for r in riders}

        d_bw = _crossover(slope, intercept, "BIKE", "WALK")
        d_wc = _crossover(slope, intercept, "WALK", "CAR")
        d_bc = _crossover(slope, intercept, "BIKE", "CAR")

        near_d = max((d_bw or 0.0) / 2.0, 1.0)
        far_d = (d_wc or 0.0) * 2.0
        if d_bw is not None and d_wc is not None:
            mid_d = (d_bw + d_wc) / 2.0
        else:
            mid_d = max(near_d, 1.0)

        results.append(
            {
                "fixed_cost": combo,
                "w_R": w_R,
                "slope": slope,
                "intercept": intercept,
                "d_star_bw": d_bw,
                "d_star_wc": d_wc,
                "d_star_bc": d_bc,
                "near_d": near_d,
                "mid_d": mid_d,
                "far_d": far_d,
                "near_priority": type_priority(riders, near_d, throughput),
                "mid_priority": type_priority(riders, mid_d, throughput),
                "far_priority": type_priority(riders, far_d, throughput),
                "n_scenarios": len(stems),
                "stems": sorted(stems, key=_natural_key),
            }
        )
    return results


def rho_sets(scenario_paths: list[str | Path] | None = None) -> list[dict]:
    """Group scenarios by rho tuple = (available_number/K per type, 1dp).

    Returns one dict per unique rho combo, sorted by rho tuple ascending:
      rho, n_scenarios, stems
    """
    paths = _resolve_paths(scenario_paths)
    groups: dict[tuple[float, float, float], list[str]] = {}
    for p in paths:
        scenario = load_scenario(p)
        rho = _rho_tuple(scenario)
        groups.setdefault(rho, []).append(p.stem)

    return [
        {"rho": rho, "n_scenarios": len(stems), "stems": sorted(stems, key=_natural_key)}
        for rho, stems in sorted(groups.items())
    ]


def assignment_map(scenario_path: str | Path, throughput: float = 50.0) -> dict:
    """Per-scenario §8 row: fixed_cost/rho context, crossovers, dist stats,
    full-stock assignment counts, BIKE-exhausted fallback counts, WALK-first count.

    "Full-stock" = infinite supply: for each order, filter riders to
    capa >= vol, then take type_priority(...)[0] (cheapest eligible type).
    "BIKE-exhausted fallback" = for each order, the first type in the
    eligible priority list that is not BIKE (what the order would fall back
    to if BIKE stock were 0). "walk_first_count" is the capa-AGNOSTIC pure
    cost priority-1 count (type_priority over all 3 types, no capa filter) --
    deliberately not full_stock_counts["WALK"], since the capa filter would
    undercount orders where WALK is cheapest by distance alone but
    capa-ineligible (VOL > 70); this is the statistic plan §1.3-③ reports as
    417/12,450 (3.3%). Raises ValueError if some order's VOL exceeds every
    rider type's capa (matches
    analysis.rider_arrival_model._sample_rider_type_for_order convention).
    """
    path = Path(scenario_path)
    scenario = load_scenario(path)
    riders = scenario.riders
    slope, intercept = _slope_intercept(riders, throughput)
    d_bw = _crossover(slope, intercept, "BIKE", "WALK")
    d_wc = _crossover(slope, intercept, "WALK", "CAR")

    dist_m = pickup_drop_distance(path)

    full_stock_counts = {t: 0 for t in RIDER_TYPES}
    fallback_counts = {t: 0 for t in RIDER_TYPES}
    walk_first_count = 0

    for i, order in enumerate(scenario.orders):
        d = float(dist_m[i])
        eligible = [r for r in riders if r.capa >= order.vol]
        if not eligible:
            raise ValueError(
                f"{path.stem}: ord_id={order.ord_id} VOL={order.vol} exceeds every "
                f"rider type's capa (max={max(r.capa for r in riders)})"
            )
        prio = type_priority(eligible, d, throughput)
        full_stock_counts[prio[0]] += 1
        fallback = next((t for t in prio if t != "BIKE"), None)
        if fallback is not None:
            fallback_counts[fallback] += 1
        # Pure cost priority-1, capa-agnostic (etc/rider_type_assignment_inventory.md
        # §3: "capa·재고를 무시한 순수 비용순 정렬"). This is a DIFFERENT statistic from
        # full_stock_counts["WALK"] above: full_stock_counts already applies the capa
        # filter (VOL <= 70), so it undercounts orders where WALK is the cheapest type
        # by pure distance-cost but is capa-ineligible for that order. This unrestricted
        # count is the "WALK 1순위" figure plan §1.3-③ quotes (417/12,450, 3.3%).
        if type_priority(riders, d, throughput)[0] == "WALK":
            walk_first_count += 1

    return {
        "stem": path.stem,
        "K": scenario.K,
        "fixed_cost": _fixed_cost_tuple(riders),
        "rho": _rho_tuple(scenario),
        "d_star_bw": d_bw,
        "d_star_wc": d_wc,
        "dist_min": float(dist_m.min()),
        "dist_median": float(np.median(dist_m)),
        "dist_max": float(dist_m.max()),
        "vol_max": max(o.vol for o in scenario.orders),
        "full_stock_counts": full_stock_counts,
        "bike_exhausted_fallback_counts": {t: fallback_counts[t] for t in ("WALK", "CAR")},
        "walk_first_count": walk_first_count,
    }


# --------------------------------------------------------------- formatting


def _fmt_tuple(t: tuple[float, float, float], decimals: int = 0) -> str:
    if decimals == 0:
        return "(" + ", ".join(str(int(round(x))) for x in t) + ")"
    return "(" + ", ".join(f"{x:.{decimals}f}" for x in t) + ")"


def _fmt_d(x: float | None) -> str:
    return "n/a" if x is None else str(int(round(x)))


def _fmt_priority(prio: list[str]) -> str:
    return "→".join(prio)  # "->" arrow, matches doc style


def _fmt_counts(counts: dict[str, int], types: tuple[str, ...] = RIDER_TYPES) -> str:
    parts = [f"{t} {counts[t]}" for t in types if counts.get(t, 0) > 0]
    return ", ".join(parts) if parts else "-"


def _fmt_fallback(counts: dict[str, int]) -> str:
    parts = [f"{t} {counts[t]}" for t in ("WALK", "CAR") if counts.get(t, 0) > 0]
    return " / ".join(parts) if parts else "-"


def _markdown_table(headers: list[str], aligns: list[str], rows: list[list[str]]) -> str:
    """aligns: 'l' or 'r' per column."""
    sep = "|" + "|".join(("---:" if a == "r" else "---") for a in aligns) + "|"
    lines = ["| " + " | ".join(headers) + " |", sep]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def build_t1(csets: list[dict]) -> str:
    """T1: fixed_cost combo table, all three distance regimes (plan §1.2 / doc §0.2).

    Columns cover the full three-regime structure (doc §3): near (0<D<D*(B,W)),
    mid (D*(B,W)<D<D*(W,C)), far (D>=D*(W,C)) -- not just near/far -- so the
    table is interval-precise per combo and the uniform-structure claim
    (WALK->BIKE->CAR / BIKE->WALK->CAR / BIKE->CAR->WALK for all 11 combos) is
    directly machine-checkable from the printed rows.
    """
    ordered = sorted(csets, key=lambda d: (-d["n_scenarios"], d["fixed_cost"]))
    headers = [
        "fixed_cost (B,W,C)",
        "D*(B,W)",
        "D*(W,C)",
        "0<D<D*(B,W)",
        "D*(B,W)<D<D*(W,C)",
        "D≥D*(W,C)",
        "시나리오 수",
    ]
    aligns = ["l", "r", "r", "l", "l", "l", "r"]
    rows = []
    for c in ordered:
        rows.append(
            [
                _fmt_tuple(c["fixed_cost"]),
                _fmt_d(c["d_star_bw"]),
                _fmt_d(c["d_star_wc"]),
                _fmt_priority(c["near_priority"]),
                _fmt_priority(c["mid_priority"]),
                _fmt_priority(c["far_priority"]),
                str(c["n_scenarios"]),
            ]
        )
    return _markdown_table(headers, aligns, rows)


def build_t2(rsets: list[dict]) -> str:
    """T2: rho combo table."""
    ordered = sorted(rsets, key=lambda d: (-d["n_scenarios"], d["rho"]))
    headers = ["ρ (B,W,C)", "시나리오 수", "시나리오"]
    aligns = ["l", "r", "l"]
    rows = []
    for r in ordered:
        rows.append(
            [
                _fmt_tuple(r["rho"], decimals=1),
                str(r["n_scenarios"]),
                ", ".join(r["stems"]),
            ]
        )
    return _markdown_table(headers, aligns, rows)


def build_t3(amaps: list[dict]) -> str:
    """T3: per-scenario §8 row table, sorted by stem natural order."""
    ordered = sorted(amaps, key=lambda d: _natural_key(d["stem"]))
    headers = [
        "시나리오",
        "K",
        "fixed_cost (B,W,C)",
        "ρ (B,W,C)",
        "D*(B,W)",
        "D*(W,C)",
        "D[min/med/max] (m)",
        "VOL max",
        "재고여유 배정",
        "BIKE소진 fallback",
        "WALK 1순위",
    ]
    aligns = ["l", "r", "l", "l", "r", "r", "l", "r", "l", "l", "r"]
    rows = []
    for a in ordered:
        rows.append(
            [
                a["stem"],
                str(a["K"]),
                _fmt_tuple(a["fixed_cost"]),
                _fmt_tuple(a["rho"], decimals=1),
                _fmt_d(a["d_star_bw"]),
                _fmt_d(a["d_star_wc"]),
                f"{a['dist_min']:.0f}/{a['dist_median']:.0f}/{a['dist_max']:.0f}",
                str(a["vol_max"]),
                _fmt_counts(a["full_stock_counts"]),
                _fmt_fallback(a["bike_exhausted_fallback_counts"]),
                str(a["walk_first_count"]),
            ]
        )
    return _markdown_table(headers, aligns, rows)


# ------------------------------------------------------------------------ CLI


def _json_default(o: object) -> object:
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, tuple):
        return list(o)
    raise TypeError(f"not JSON serializable: {type(o)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate rider-assignment tables (etc/rider_type_assignment_inventory.md "
        "§0/§8) from the data1 scenarios via analysis.rider_arrival_model."
    )
    parser.add_argument("--throughput", type=float, default=50.0, help="orders/h/rider (default 50.0)")
    parser.add_argument("--json", default=None, help="also write combined JSON dict to this path")
    args = parser.parse_args(argv)

    paths = default_scenario_paths()
    csets = cost_sets(paths, throughput=args.throughput)
    rsets = rho_sets(paths)
    amaps = [assignment_map(p, throughput=args.throughput) for p in paths]

    print(f"## T1 -- fixed_cost combos (n={len(csets)}, throughput={args.throughput})\n")
    print(build_t1(csets))
    print(f"\n## T2 -- rho combos (n={len(rsets)})\n")
    print(build_t2(rsets))
    print(f"\n## T3 -- per-scenario assignment map (n={len(amaps)})\n")
    print(build_t3(amaps))

    if args.json:
        payload = {"cost_sets": csets, "rho_sets": rsets, "assignment_map": amaps}
        Path(args.json).write_text(json.dumps(payload, indent=2, default=_json_default))

    return 0


if __name__ == "__main__":
    sys.exit(main())
