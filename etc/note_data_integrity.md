# V-DATA -- data/data1 integrity note

> Stage V6 of `archive/h0_v1/docs/plan_h0_verification.md` (§2 L7 table, V-DATA row).
> Reproduce: `.venv/bin/python -m analysis.vv_data_integrity` (source
> `analysis/vv_data_integrity.py`, CSV `results/vv/data_integrity.csv`).
> Scope = the 39 D6 scenario files in `data/data1` (`K*.json`); `STAGE3_*.json`
> is a separate track and out of scope here (same boundary `vv_all39.py`/
> `vv_face.py` use). No file under `data/` was modified to produce this note.

## 1. Duplicate check (39 files, all-pairs)

- **File-level md5** (raw bytes): exactly one duplicate pair —
  **`K1000_4` == `K1000_5`** (md5 `e9e356a713...`) — re-confirming plan
  §0.3 fact 2. No other pair among the remaining 37 files collides (all 37
  other md5 values are pairwise distinct).
- **ORDERS-content md5** (canonicalized `ORDERS` payload only, independent of
  `name`/`RIDERS`/`DIST` serialization): same single pair, **`K1000_4` ==
  `K1000_5`**, and no other pair. So the duplication is a genuine full-file
  clone (`K1000_4.json` and `K1000_5.json` are byte-identical), not merely a
  relabeled copy of the order set — there is no additional "same orders,
  different wrapper" duplicate hiding among the other 37 files.

Verdict: **PASS** (duplicate set == `{(K1000_4, K1000_5)}` exactly, both by
file bytes and by order content).

## 2. name <-> stem mapping table

Every scenario JSON's internal `name` field (`analysis/load_data.py`
`Scenario.name`, i.e. `raw["name"]`) does **not** match its filename stem
under `data/data1` — **39/39 mismatches**. The files were renamed to the
`K{n}_{i}` convention used by the experiment battery, but the JSON body still
carries the original internal label from an earlier `STAGE1_*` / `STAGE2_*` /
`TEST_K{n}_*` naming scheme. This is a naming-provenance fact, not evidence of
misfiled content (K declared inside each file matches the `K{n}` in its
stem in all 39 cases; see CSV `K_declared` column) — it is listed here so the
mismatch is visible and not silently assumed away.

| stem | internal `name` | K | file md5 (prefix) |
|---|---|---|---|
| K1000_1 | STAGE2_2 | 1000 | 9a0fb41a72 |
| K1000_2 | STAGE2_4 | 1000 | ae70cc5673 |
| K1000_3 | STAGE2_6 | 1000 | 8a3e311f4c |
| K1000_4 | STAGE2_TEST_1 | 1000 | e9e356a713 |
| K1000_5 | STAGE2_TEST_1 | 1000 | e9e356a713 |
| K100_1 | TEST_K100_1 | 100 | 2205741ccf |
| K100_2 | TEST_K100_2 | 100 | d8a523442d |
| K100_3 | STAGE1_1 | 100 | c0783c0f4a |
| K100_4 | STAGE1_2 | 100 | d09a147e42 |
| K100_5 | STAGE1_7 | 100 | b1c3a8bf14 |
| K100_6 | STAGE1_8 | 100 | df96d10f7a |
| K100_7 | STAGE1_13 | 100 | b69b87571c |
| K100_8 | STAGE1_14 | 100 | 4ae421c949 |
| K100_9 | STAGE1_TEST_3 | 100 | a4849e3092 |
| K200_1 | TEST_K200_1 | 200 | 0d1ca9e38a |
| K200_2 | TEST_K200_2 | 200 | ccca99f24f |
| K200_3 | STAGE1_3 | 200 | cb660e5600 |
| K200_4 | STAGE1_4 | 200 | f84b7f2488 |
| K200_5 | STAGE1_9 | 200 | 61fb9d73b2 |
| K200_6 | STAGE1_10 | 200 | eb9be72716 |
| K200_7 | STAGE1_15 | 200 | 0450e41860 |
| K200_8 | STAGE1_16 | 200 | dc181c1726 |
| K200_9 | STAGE1_TEST_2 | 200 | ff3ad4520f |
| K300_1 | STAGE1_5 | 300 | 244c0035fd |
| K300_2 | STAGE1_6 | 300 | 67398eb35b |
| K300_3 | STAGE1_11 | 300 | 4c0439cff9 |
| K300_4 | STAGE1_12 | 300 | ccb1916ac6 |
| K300_5 | STAGE1_17 | 300 | 7d3b5a286e |
| K300_6 | STAGE1_18 | 300 | 372de85a6d |
| K300_7 | STAGE1_TEST_1 | 300 | 1e7e466620 |
| K300_8 | STAGE2_TEST_3 | 300 | 1c4d0d64ff |
| K500_1 | STAGE2_1 | 500 | 3bcfc0498e |
| K500_2 | STAGE2_3 | 500 | b02303b291 |
| K500_3 | STAGE2_5 | 500 | 5f9c3934b4 |
| K500_4 | STAGE2_TEST_4 | 500 | 78e464d571 |
| K500_5 | STAGE2_TEST_5 | 500 | f597a4ec95 |
| K50_1 | TEST_K50_1 | 50 | 434cda7ac0 |
| K50_2 | TEST_K50_2 | 50 | 57ad8767c9 |
| K750_1 | STAGE2_TEST_6 | 750 | 7b4b7986f3 |

Note the `K1000_4`/`K1000_5` duplicate pair shares the identical internal name
`STAGE2_TEST_1` too (consistent with being a full byte-for-byte clone, §1).

Verdict: **PASS** (check ran to completion over all 39 files; "PASS" here
means the mismatch inventory above is complete, not that mismatches are
absent — see §4 footnote for how this should be described in the design
matrix).

## 3. VOL <= max(capa) (full census, every order in every file)

`RIDERS` row = `[type, speed_mps, capa, var_cost, fixed_cost,
service_time_sec, available_number]`; `ORDERS` row's `VOL` (index 7) is the
parcel volume an order needs carried. An order is deliverable by *some* rider
type only if that type's `capa >= VOL`
(`analysis/rider_assignment_tables.py` L238-243 already enforces this
per-order eligibility filter and raises if none qualify). This check
independently re-confirms, across all 39 files, that no order's `VOL` exceeds
even the largest available `capa`.

All 39 files carry the identical rider fleet: `capa = [100 (BIKE), 70 (WALK),
200 (CAR)]`, so `max(capa) = 200` everywhere. Observed `VOL` ranges per file
span roughly 5-100 (see CSV `vol_min`/`vol_max` columns); the largest `VOL`
seen anywhere in the 39 files is 100, well under the 200 ceiling.

Verdict: **PASS** -- `vol_over_capa_count == 0` in all 39 files (0 violating
orders total).

## 4. Design-matrix footnote (draft)

> Of the 5 `data/data1` scenario files at nominal K=1000, `K1000_4.json` and
> `K1000_5.json` are byte-identical (md5-identical, confirmed by full
> all-pairs md5 and independently by an ORDERS-payload-only hash; no other
> pair among the 39 D6 files collides at either level). **Proposed** (pending
> user decision, plan §5 item 3): exclude `K1000_5` from the design matrix,
> leaving 4 distinct K1000 scenarios (39 files total, 38 distinct order
> sets) -- **not yet finalized**. Every scenario's internal `name` field predates the
> `K{n}_{i}` filename convention (a `STAGE1_*`/`STAGE2_*`/`TEST_K{n}_*`
> label) and disagrees with the file stem for all 39 files; this is a
> naming-provenance artifact only, not a content mismatch (`K` declared
> inside each file matches its filename's `K{n}` in every case). Every
> order's `VOL` is within the fleet's maximum `capa` (200, CAR) in all 39
> files (0/? violations across the full order census) -- no order is
> structurally undeliverable by the available rider fleet.

Reproduction figures for this footnote: duplicate pair count = 1
(`K1000_4`==`K1000_5`, both file- and content-level), name/stem mismatches =
39/39 (all provenance-only, K-consistent), VOL>max(capa) violations = 0/13,450
orders across all 39 files (see `results/vv/data_integrity.csv` for the exact
per-file counts backing every number above).

**Decision status**: the K1000 duplicate exclusion is a **proposal only**
per plan §5 item 3 ("K1000 중복 쌍 처리 -- 제안: K1000_5 제외"); this note
does not finalize it. Until the user decides, both `K1000_4.json` and
`K1000_5.json` remain part of the 39-file D6 set used by other verification
stages (`vv_all39.py`, `vv_face.py`, etc., which already flag this duplicate
in their own docstrings/comments without excluding it).
