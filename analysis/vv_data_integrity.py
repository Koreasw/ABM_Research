"""V-DATA -- data integrity checks over the modelling corpus
(etc/plan_h0_verification.md §2 L7 table, Stage V6 of the H0 verification
plan).

    .venv/bin/python -m analysis.vv_data_integrity

Scope (plan D6, updated 사용자 확정 2026-08-03 2차): the 28 scenario JSON files
of the modelling corpus (K50 x2, K100 x9, K200 x9, K300 x8), resolved via
analysis.scenario_tiers.scenario_paths("all") rather than a raw data/data1
glob. K500/K750/K1000 (11 files) are now held out from the
corpus -- see analysis/scenario_tiers.py -- and are no longer read by this
script. STAGE3_*.json is a separate track and is deliberately excluded (same
D6 boundary vv_all39.py and vv_face.py use).

Three checks, each report-only (this script never mutates data/):

  1. duplicate detection
     a. file-level: md5 of the raw file bytes, all-pairs comparison.
        §0.3 fact 2 states K1000_4 == K1000_5 (md5-identical) within the old
        39-file corpus -- that pair is now outside the corpus entirely, so
        this check now expects *no* duplicate pair among the 28 files
        (re-confirmed empirically, not assumed -- see check_file_duplicates).
        The duplicate-detection logic itself is unchanged and generic: it
        would still catch any other colliding pair, including a future
        addition to the corpus.
     b. content-level: even where the file bytes differ (different `name`
        field, RIDERS/DIST re-serialization, etc.), the ORDERS payload could
        still be a byte-for-byte copy. Canonicalized via
        json.dumps(scenario["ORDERS"], sort_keys=True) -> md5, compared
        all-pairs across the 28 files (independent of the file-level md5 in
        1a, so this also re-derives the 1a duplicate from the orders side and
        would catch any order-content clone that used a different DIST/RIDERS
        block).

  2. name <-> stem mapping table
     Every scenario JSON's internal top-level "name" field vs. its filename
     stem (analysis/load_data.py Scenario.name, i.e. raw["name"]). Any
     mismatch is listed (expected to be common here: files were renamed from
     an internal STAGE1/STAGE2/TEST_* naming scheme to the K{n}_{i} scheme
     used under data/data1, but the JSON body was not rewritten).

  3. VOL <= max(capa) over every order in every scenario
     RIDERS row = [type, speed_mps, capa, var_cost, fixed_cost,
     service_time_sec, available_number] (analysis/load_data.py docstring).
     ORDERS row's VOL (index 7) is the parcel volume; capa is the rider's
     carrying capacity. An order is deliverable at all only if some rider
     type's capa >= VOL (analysis/rider_assignment_tables.py L238-243 already
     encodes and enforces this per-order eligibility check as
     `r.capa >= order.vol`, raising ValueError otherwise -- this script is an
     independent, read-only re-confirmation across all 39 files, using the
     coarser scenario-level max(capa) bound the plan text asks for).

Outputs (plan §6 results/vv/ convention):
  - results/vv/data_integrity.csv  -- one row per scenario file (md5, name,
    stem, name==stem, K, n_orders, min/max VOL, max capa, vol_over_capa_count)
  - stdout PASS/FAIL table for the three checks

No existing file is read destructively and nothing under data/ is written.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from analysis.scenario_tiers import scenario_paths as _tier_scenario_paths

ROOT = Path(__file__).resolve().parent.parent
SCENARIO_DIR = ROOT / "data" / "data1"
OUT_DIR = ROOT / "results" / "vv"
OUT_CSV = OUT_DIR / "data_integrity.csv"


def _scenario_files() -> list[Path]:
    """The 28 D6 scenario files -- the modelling corpus (tier 'all'), STAGE3_*
    and the held-out K500/K750/K1000 files never included."""
    return _tier_scenario_paths("all", data_dir=SCENARIO_DIR)


def _md5_bytes(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def _md5_text(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------- collection

def collect_rows() -> tuple[list[dict], dict[str, bytes], dict[str, dict]]:
    """Read all 28 files once; return per-file rows + raw bytes + parsed JSON
    (raw bytes/JSON returned separately so the duplicate checks below don't
    re-read from disk)."""
    files = _scenario_files()
    assert len(files) == 28, f"expected 28 D6 scenario files, found {len(files)}"

    raw_bytes: dict[str, bytes] = {}
    raw_json: dict[str, dict] = {}
    rows: list[dict] = []

    for path in files:
        stem = path.stem
        data = path.read_bytes()
        raw_bytes[stem] = data
        obj = json.loads(data)
        raw_json[stem] = obj

        file_md5 = _md5_bytes(data)
        orders_md5 = _md5_text(json.dumps(obj["ORDERS"], sort_keys=True))

        internal_name = str(obj["name"])
        name_matches_stem = internal_name == stem

        orders = obj["ORDERS"]
        riders = obj["RIDERS"]
        vols = [int(o[7]) for o in orders]
        capas = [int(r[2]) for r in riders]
        max_capa = max(capas) if capas else None
        vol_over_capa = (
            [int(o[0]) for o in orders if max_capa is not None and int(o[7]) > max_capa]
            if max_capa is not None
            else []
        )

        rows.append(
            {
                "stem": stem,
                "file_md5": file_md5,
                "orders_md5": orders_md5,
                "internal_name": internal_name,
                "name_matches_stem": name_matches_stem,
                "K_declared": int(obj["K"]),
                "n_orders": len(orders),
                "vol_min": min(vols) if vols else None,
                "vol_max": max(vols) if vols else None,
                "max_capa": max_capa,
                "vol_over_capa_count": len(vol_over_capa),
                "vol_over_capa_ord_ids": ";".join(str(x) for x in vol_over_capa),
            }
        )

    return rows, raw_bytes, raw_json


# --------------------------------------------------------------- check 1: duplicates

def check_file_duplicates(rows: list[dict]) -> tuple[list[tuple[str, str]], str]:
    by_md5: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        by_md5[r["file_md5"]].append(r["stem"])

    pairs: list[tuple[str, str]] = []
    for stems in by_md5.values():
        if len(stems) > 1:
            stems_sorted = sorted(stems)
            for i in range(len(stems_sorted)):
                for j in range(i + 1, len(stems_sorted)):
                    pairs.append((stems_sorted[i], stems_sorted[j]))

    # K1000_4 == K1000_5 (the old duplicate pair) is outside the 28-scenario
    # corpus now -- expect no duplicate at all. Asserted explicitly rather
    # than assumed: if the corpus ever regains a colliding pair, this must
    # go red, not silently pass.
    expected: list[tuple[str, str]] = []
    verdict = "PASS" if pairs == expected else "FAIL"
    return pairs, verdict


def check_orders_content_duplicates(rows: list[dict]) -> tuple[list[tuple[str, str]], str]:
    by_orders_md5: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        by_orders_md5[r["orders_md5"]].append(r["stem"])

    pairs: list[tuple[str, str]] = []
    for stems in by_orders_md5.values():
        if len(stems) > 1:
            stems_sorted = sorted(stems)
            for i in range(len(stems_sorted)):
                for j in range(i + 1, len(stems_sorted)):
                    pairs.append((stems_sorted[i], stems_sorted[j]))

    # Same reasoning as check_file_duplicates: no duplicate expected in the
    # 28-scenario corpus.
    expected: list[tuple[str, str]] = []
    verdict = "PASS" if pairs == expected else "FAIL"
    return pairs, verdict


# --------------------------------------------------------------- check 2: name<->stem

def check_name_stem_mismatches(rows: list[dict]) -> tuple[list[dict], str]:
    mismatches = [
        {"stem": r["stem"], "internal_name": r["internal_name"]}
        for r in rows
        if not r["name_matches_stem"]
    ]
    # Not a data-corruption signal by itself (see docstring) -- report-only,
    # "PASS" here means the check ran and every file was inspected, not that
    # mismatches are absent.
    return mismatches, "PASS"


# --------------------------------------------------------------- check 3: VOL<=max(capa)

def check_vol_le_max_capa(rows: list[dict]) -> tuple[list[dict], str]:
    violations = [
        {
            "stem": r["stem"],
            "max_capa": r["max_capa"],
            "vol_max": r["vol_max"],
            "vol_over_capa_count": r["vol_over_capa_count"],
            "vol_over_capa_ord_ids": r["vol_over_capa_ord_ids"],
        }
        for r in rows
        if r["vol_over_capa_count"] > 0
    ]
    verdict = "PASS" if not violations else "FAIL"
    return violations, verdict


# --------------------------------------------------------------- CSV IO

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


# --------------------------------------------------------------- main

def main() -> int:
    print("V-DATA: reading 39 D6 scenario files from data/data1 ...")
    rows, _raw_bytes, _raw_json = collect_rows()
    print(f"  read {len(rows)} files")

    _write_csv(OUT_CSV, rows)

    file_dup_pairs, file_dup_verdict = check_file_duplicates(rows)
    orders_dup_pairs, orders_dup_verdict = check_orders_content_duplicates(rows)
    name_mismatches, name_verdict = check_name_stem_mismatches(rows)
    vol_violations, vol_verdict = check_vol_le_max_capa(rows)

    print("\n" + "=" * 78)
    print("V-DATA -- data integrity checks (data/data1, 39 files, D6 scope)")
    print("=" * 78)

    print(f"\n[1a] file-level md5 duplicates: {file_dup_verdict}")
    if file_dup_pairs:
        for a, b in file_dup_pairs:
            print(f"    DUP: {a} == {b} (md5 identical)")
    else:
        print("    (none found)")

    print(f"\n[1b] ORDERS-content duplicates (md5 differs, order payload identical): {orders_dup_verdict}")
    if orders_dup_pairs:
        for a, b in orders_dup_pairs:
            print(f"    DUP: {a} == {b} (ORDERS payload identical)")
    else:
        print("    (none found)")

    print(f"\n[2] name<->stem mapping: {name_verdict} (report-only; see CSV/note for full 39-row table)")
    print(f"    mismatches: {len(name_mismatches)} / {len(rows)}")
    for m in name_mismatches:
        print(f"    {m['stem']:<10} internal name = {m['internal_name']}")

    print(f"\n[3] VOL <= max(capa) over every order: {vol_verdict}")
    print(f"    violations: {len(vol_violations)} / {len(rows)} files")
    for v in vol_violations:
        print(
            f"    {v['stem']:<10} max_capa={v['max_capa']} vol_max={v['vol_max']} "
            f"over_capa_count={v['vol_over_capa_count']} ord_ids={v['vol_over_capa_ord_ids']}"
        )

    print("\n" + "-" * 78)
    print(f"wrote {OUT_CSV}  ({len(rows)} rows)")

    overall = {file_dup_verdict, orders_dup_verdict, vol_verdict}
    print(
        f"\noverall: file_dup={file_dup_verdict} orders_dup={orders_dup_verdict} "
        f"name_stem={name_verdict}(report-only) vol_le_capa={vol_verdict}"
    )
    return 1 if "FAIL" in overall else 0


if __name__ == "__main__":
    raise SystemExit(main())
