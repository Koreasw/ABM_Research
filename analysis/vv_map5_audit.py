"""V-MAP5 + V-VAC — frozen v5 floor-mapping audit (etc/plan_h0_verification.md §2 L7,
Stage V6; both items re-scoped 2026-07-10 to the frozen-regression-path audit — v5 is no
longer the paper track, see §0.1 D5 and §0.3 fact 3).

    .venv/bin/python -m analysis.vv_map5_audit

V-MAP5 (task A): the paper track's floor/office assignment now comes from
`simulation/floor_demand.py` categorical profiles, audited by verify_h0.py's A9. v5
(`analysis/map_floor_v5.py` + the committed `data/floor_mapping/*_v5.json` pair per
scenario) survives only as the frozen distance-band regression path. This script re-audits
that the frozen v5 artifacts are internally consistent and, wherever comparable, still
reproduce the frozen v4 rule exactly — across the 28-scenario modelling corpus:

CORPUS REGIME CHANGE (사용자 확정 2026-08-03, 2차): K500/K750/K1000 (11 files) are
held out of the modelling corpus for this study, so both tasks below iterate
analysis.scenario_tiers.scenario_paths("all") (primary 20 + extreme 8 = 28) rather than
globbing data/data1 for 39 files. The frozen v5/v4 JSON artifacts for the excluded files
still exist on disk; they are simply no longer audited, because nothing downstream may
use them.

  1. anchor recompute match — the v5 JSON's `parameters.building_coord` equals an
     independently recomputed mean(DLV_LAT), mean(DLV_LON) over the scenario's K orders
     (recomputed here with `statistics.fmean`, not by importing
     `map_floor_v5.demand_centroid` — an independent implementation of the same rule).
  2. anchor inside bbox — the anchor lat/lon lies within [min, max] of the scenario's own
     DLV_LAT / DLV_LON envelope.
  3. floor-distribution sum — sum(floor_distribution_2_to_10) == K (no order dropped or
     double-counted across the 9 office floors).
  4. v4 regression — v5's per-order (floor, office_id) is bit-identical to an independent
     recomputation of the frozen v4 rule (`assign_floor(d_i)` + `Random(42).randrange(12)`
     row-order, imported unchanged from `analysis/map_floor_v4.py` — the anchor-independent
     half of the v4->v5 change per map_floor_v5.py's own docstring). Only K50_1 and K50_2
     have a v4 basis for comparison: K50_1 has a committed `*_floor_mapping_v4.json` (used
     by `tests/test_map_floor_v5.py`), K50_2 does not (fresh coverage here, no v4 JSON is
     written — the v4 rule is recomputed in-memory only). The remaining 37 scenarios were
     never mapped under v4 at all, so check 4 is N/A there (not a gap: v5 replaced v4
     wholesale before those scenarios were ever run through v4).

V-VAC (task B): frozen-v5-only vacant-floor bookkeeping — obsolete on the paper track
(floor is now an independent categorical draw, decoupled from city distance; see
`etc/note_vacant_floors.md` header and plan §0.3 fact 3). This task only tallies the
`floor_distribution_2_to_10` / `vacant_floors` fields already recorded in the frozen v5
JSON files (no re-simulation, no profile sampling) so the frozen regression path's
long-standing high-floor-vacancy observation is quantified and attributed to the
distance-band mechanism rather than left as an anecdote. (The v1-era headline figure
"19/39 scenarios" was measured over the old 39-file glob; over the 28-file corpus the
count is re-derived from this script's own output — do not quote the old number.)
"""

from __future__ import annotations

import csv
import json
import random
import statistics
from collections import Counter
from pathlib import Path

from analysis.load_data import Scenario, load_scenario
from analysis.map_floor_v4 import N_OFFICES, OFFICE_SEED, assign_floor
from analysis.scenario_tiers import scenario_paths as _tier_scenario_paths

ROOT = Path(__file__).resolve().parent.parent
SCENARIO_DIR = ROOT / "data" / "data1"
MAPPING_DIR = ROOT / "data" / "floor_mapping"
OUT_DIR = ROOT / "results" / "vv"

V4_REGRESSION_SCENARIOS = ("K50_1", "K50_2")
ANCHOR_TOL = 1e-9  # exact-recompute float tolerance (same arithmetic, different code path)
HIGH_FLOOR_MIN = 7  # floors >= this count as "high floor" for the V-VAC concentration read


# --------------------------------------------------------------- task A: V-MAP5

def check_anchor_recompute(scenario: Scenario, v5_fm: dict) -> tuple[bool, float, float]:
    """Independent recompute of mean(DLV_LAT), mean(DLV_LON) vs the recorded anchor."""
    lat_mean = statistics.fmean(o.dlv_lat for o in scenario.orders)
    lon_mean = statistics.fmean(o.dlv_lon for o in scenario.orders)
    coord = v5_fm["parameters"]["building_coord"]
    d_lat = abs(coord["lat"] - lat_mean)
    d_lon = abs(coord["lon"] - lon_mean)
    return (d_lat <= ANCHOR_TOL and d_lon <= ANCHOR_TOL), d_lat, d_lon


def check_anchor_in_bbox(scenario: Scenario, v5_fm: dict) -> bool:
    lats = [o.dlv_lat for o in scenario.orders]
    lons = [o.dlv_lon for o in scenario.orders]
    coord = v5_fm["parameters"]["building_coord"]
    return (min(lats) <= coord["lat"] <= max(lats)) and (min(lons) <= coord["lon"] <= max(lons))


def check_sum_floor_eq_k(scenario: Scenario, v5_fm: dict) -> tuple[bool, int]:
    total = sum(v5_fm["floor_distribution_2_to_10"])
    return total == scenario.K, total


def recompute_v4_assignment(scenario: Scenario) -> dict[int, tuple[int, int]]:
    """Independent in-memory recomputation of the frozen v4 rule (no file I/O)."""
    d = [float(scenario.dist[i][scenario.K + i]) for i in range(scenario.K)]
    floors = [assign_floor(di) for di in d]
    rng = random.Random(OFFICE_SEED)
    offices = [rng.randrange(N_OFFICES) for _ in range(scenario.K)]
    return {order.ord_id: (floors[i], offices[i]) for i, order in enumerate(scenario.orders)}


def check_v4_regression(scenario: Scenario, v5_fm: dict) -> tuple[bool, list[int]]:
    expected = recompute_v4_assignment(scenario)
    got = {o["ord_id"]: (o["floor"], o["office_id"]) for o in v5_fm["orders"]}
    mismatches = [oid for oid in expected if expected[oid] != got.get(oid)]
    return len(mismatches) == 0, mismatches


def run_map5_audit() -> list[dict]:
    scenario_paths = _tier_scenario_paths("all", SCENARIO_DIR)
    assert len(scenario_paths) == 28, (
        f"expected 28 corpus scenarios, found {len(scenario_paths)}"
    )

    rows = []
    for path in scenario_paths:
        stem = path.stem
        fm_path = MAPPING_DIR / f"{stem}_floor_mapping_v5.json"
        if not fm_path.exists():
            rows.append({
                "scenario": stem, "K": None,
                "check1_anchor_recompute": "MISSING_V5_JSON",
                "check2_anchor_in_bbox": "MISSING_V5_JSON",
                "check3_sum_floor_eq_k": "MISSING_V5_JSON",
                "check4_v4_regression": "MISSING_V5_JSON",
                "overall": "FAIL",
                "detail": f"{fm_path} not found",
            })
            continue

        scenario = load_scenario(path)
        v5_fm = json.loads(fm_path.read_text())

        ok1, d_lat, d_lon = check_anchor_recompute(scenario, v5_fm)
        ok2 = check_anchor_in_bbox(scenario, v5_fm)
        ok3, total = check_sum_floor_eq_k(scenario, v5_fm)

        if stem in V4_REGRESSION_SCENARIOS:
            ok4, mismatches = check_v4_regression(scenario, v5_fm)
            check4_str = "PASS" if ok4 else f"FAIL ({len(mismatches)} mismatches: {mismatches[:5]}...)"
            check4_pass = ok4
        else:
            check4_str = "N/A"
            check4_pass = True  # N/A does not fail the overall gate

        overall = "PASS" if (ok1 and ok2 and ok3 and check4_pass) else "FAIL"
        rows.append({
            "scenario": stem,
            "K": scenario.K,
            "check1_anchor_recompute": "PASS" if ok1 else f"FAIL (d_lat={d_lat:.3e}, d_lon={d_lon:.3e})",
            "check2_anchor_in_bbox": "PASS" if ok2 else "FAIL",
            "check3_sum_floor_eq_k": "PASS" if ok3 else f"FAIL (sum={total}, K={scenario.K})",
            "check4_v4_regression": check4_str,
            "overall": overall,
            "detail": "",
        })
    return rows


# --------------------------------------------------------------- task B: V-VAC

def run_vac_summary(map5_rows: list[dict]) -> dict:
    """Vacant-floor bookkeeping under the frozen v5 assignment, all 28 corpus scenarios."""
    per_scenario = []
    for path in _tier_scenario_paths("all", SCENARIO_DIR):
        stem = path.stem
        fm_path = MAPPING_DIR / f"{stem}_floor_mapping_v5.json"
        v5_fm = json.loads(fm_path.read_text())
        k = v5_fm["K"]
        dist = v5_fm["floor_distribution_2_to_10"]
        vacant = v5_fm["vacant_floors"]
        per_scenario.append({
            "scenario": stem,
            "K": k,
            "n_vacant_floors": len(vacant),
            "vacant_floors": vacant,
            "n_high_floor_vacant": sum(1 for f in vacant if f >= HIGH_FLOOR_MIN),
        })

    n_scenarios = len(per_scenario)
    n_with_vacancy = sum(1 for r in per_scenario if r["n_vacant_floors"] > 0)
    total_vacant_slots = sum(r["n_vacant_floors"] for r in per_scenario)

    floor_vacancy_counts: Counter[int] = Counter()
    for r in per_scenario:
        for f in r["vacant_floors"]:
            floor_vacancy_counts[f] += 1
    n_high_floor_vacant_slots = sum(c for f, c in floor_vacancy_counts.items() if f >= HIGH_FLOOR_MIN)
    high_floor_share = (n_high_floor_vacant_slots / total_vacant_slots) if total_vacant_slots else None

    ks_with = [r["K"] for r in per_scenario if r["n_vacant_floors"] > 0]
    ks_without = [r["K"] for r in per_scenario if r["n_vacant_floors"] == 0]
    mean_k_with = statistics.fmean(ks_with) if ks_with else None
    mean_k_without = statistics.fmean(ks_without) if ks_without else None

    return {
        "per_scenario": per_scenario,
        "n_scenarios": n_scenarios,
        "n_with_vacancy": n_with_vacancy,
        "total_vacant_slots": total_vacant_slots,
        "floor_vacancy_counts": dict(sorted(floor_vacancy_counts.items())),
        "n_high_floor_vacant_slots": n_high_floor_vacant_slots,
        "high_floor_share": high_floor_share,
        "mean_k_with_vacancy": mean_k_with,
        "mean_k_without_vacancy": mean_k_without,
    }


# --------------------------------------------------------------- IO / main

def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    print("V-MAP5: auditing 39 frozen data/floor_mapping/*_v5.json artifacts...")
    map5_rows = run_map5_audit()
    _write_csv(OUT_DIR / "map5_audit.csv", map5_rows)

    print(f"\n{'scenario':<10}{'K':>6}  {'anchor_recompute':<20}{'anchor_in_bbox':<16}"
          f"{'sum==K':<12}{'v4_regression':<40}{'overall':<8}")
    print("-" * 112)
    for r in map5_rows:
        print(f"{r['scenario']:<10}{str(r['K']):>6}  {r['check1_anchor_recompute']:<20}"
              f"{r['check2_anchor_in_bbox']:<16}{r['check3_sum_floor_eq_k']:<12}"
              f"{r['check4_v4_regression']:<40}{r['overall']:<8}")

    n_pass = sum(1 for r in map5_rows if r["overall"] == "PASS")
    n_fail = len(map5_rows) - n_pass
    print(f"\nV-MAP5: {n_pass}/{len(map5_rows)} PASS, {n_fail} FAIL")
    print(f"wrote {OUT_DIR / 'map5_audit.csv'}")

    print("\nV-VAC: frozen-v5 vacant-floor characterization (39 scenarios)...")
    vac = run_vac_summary(map5_rows)
    vac_rows = vac["per_scenario"]
    _write_csv(OUT_DIR / "vac_summary.csv", vac_rows)

    print(f"\n{'scenario':<10}{'K':>6}{'n_vacant':>10}  {'vacant_floors':<20}{'n_high_floor_vacant':>20}")
    for r in vac_rows:
        print(f"{r['scenario']:<10}{r['K']:>6}{r['n_vacant_floors']:>10}  "
              f"{str(r['vacant_floors']):<20}{r['n_high_floor_vacant']:>20}")

    print(f"\nscenarios with >=1 vacant floor: {vac['n_with_vacancy']}/{vac['n_scenarios']}")
    print(f"total vacant floor-slots (sum over scenarios): {vac['total_vacant_slots']}")
    print(f"floor -> vacancy count across scenarios: {vac['floor_vacancy_counts']}")
    print(f"high-floor (>={HIGH_FLOOR_MIN}F) share of vacant slots: {vac['high_floor_share']}")
    print(f"mean K | vacancy present: {vac['mean_k_with_vacancy']}")
    print(f"mean K | no vacancy: {vac['mean_k_without_vacancy']}")
    print(f"wrote {OUT_DIR / 'vac_summary.csv'}")

    return 1 if n_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
