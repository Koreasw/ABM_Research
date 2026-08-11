"""V-RIDER — 문서↔코드 라이더 배정 전수 일치 잠금 (plan §4 V-RIDER).

`etc/plan_rider_assignment_revision.md` §4 표의 V-RIDER 항목을 구현한다:
개정된 `etc/rider_type_assignment_inventory.md`(2026-07-11)의 **모든 수치·표·
불변식**을 프로덕션 코드(`analysis/rider_arrival_model.py`의 `type_priority`·
`delivery_cost_krw`·`compute_w_R_krw_per_h`, `simulation/rider_pool.py`의
`RiderPool`)와 그 재현 스크립트(`analysis/rider_assignment_tables.py`)에 대해
잠근다. 목적은 문서↔코드가 지금뿐 아니라 **앞으로도** 어긋나면 반드시
빨갛게 터지도록 하는 것 — 코드/스크립트/문서는 무수정, 불일치는 은폐하지 않고
크게 실패시킨다(plan §7 "코드가 진실").

각 테스트 docstring에 잠그는 문서 절을 명시한다. 무거운 부분(28개 시나리오
거리배열 적재 = cost_sets/rho_sets/assignment_map)은 module-scope fixture
`tables`에서 **딱 한 번** 계산해 전 테스트가 공유한다(plan 성능 예산).
"""

from __future__ import annotations

import re
import types
from pathlib import Path

import pytest

from analysis.load_data import Rider, load_scenario, pickup_drop_distance
from analysis.rider_arrival_model import delivery_cost_krw, type_priority
from analysis.scenario_tiers import is_excluded
from analysis.rider_assignment_tables import (
    RIDER_TYPES,
    assignment_map,
    build_t1,
    build_t2,
    build_t3,
    cost_sets,
    default_scenario_paths,
    rho_sets,
)
from simulation.rider_pool import RiderPool

ROOT = Path(__file__).resolve().parent.parent
DOC_PATH = ROOT / "etc" / "rider_type_assignment_inventory.md"


# ------------------------------------------------------------ shared fixture


@pytest.fixture(scope="module")
def tables() -> types.SimpleNamespace:
    """28개 시나리오 배정 산출물을 한 번만 계산해 공유 (plan 성능 예산).

    cost_sets / rho_sets / assignment_map(×38) 를 여기서 한 번 적재·계산하고,
    build_t1/t2/t3 표 문자열과 doc 원문, 파생 집계도 함께 담아 반환한다.
    """
    paths = default_scenario_paths()
    if not paths:
        pytest.skip("data1 scenarios not present")

    csets = cost_sets(paths)
    rsets = rho_sets(paths)
    amaps = [assignment_map(p) for p in paths]

    riders0 = load_scenario(paths[0]).riders
    speed = {r.type: r.speed_mps for r in riders0}

    # per-combo riders (fixed_cost is a scenario-invariant→riders proxy)
    riders_by_combo: dict[tuple, list[Rider]] = {}
    for p in paths:
        s = load_scenario(p)
        combo = tuple(round(next(r.fixed_cost for r in s.riders if r.type == t)) for t in RIDER_TYPES)
        riders_by_combo.setdefault(combo, s.riders)

    return types.SimpleNamespace(
        paths=paths,
        csets=csets,
        rsets=rsets,
        amaps=amaps,
        amap_by_stem={a["stem"]: a for a in amaps},
        riders_by_combo=riders_by_combo,
        speed=speed,
        t1=build_t1(csets),
        t2=build_t2(rsets),
        t3=build_t3(amaps),
        doc=DOC_PATH.read_text(),
        walk_first_total=sum(a["walk_first_count"] for a in amaps),
        full_walk_total=sum(a["full_stock_counts"]["WALK"] for a in amaps),
        total_orders=sum(a["K"] for a in amaps),
    )


# -------------------------------------------------------- markdown helpers


_SEP_RE = re.compile(r":?-+:?")


def _split_row(line: str) -> tuple[str, ...]:
    return tuple(c.strip() for c in line.strip().strip("|").split("|"))


def _parse_pipe_lines(lines: list[str]) -> list[tuple[str, ...]]:
    """Consecutive markdown-table rows (header+data), separator rows dropped."""
    rows: list[tuple[str, ...]] = []
    for ln in lines:
        s = ln.strip()
        if not s.startswith("|"):
            break
        cells = _split_row(s)
        if all(_SEP_RE.fullmatch(c) for c in cells):
            continue
        rows.append(cells)
    return rows


def _generated_rows(table_md: str) -> list[tuple[str, ...]]:
    return _parse_pipe_lines(table_md.splitlines())


def _doc_table_rows(doc: str, *must_contain: str) -> list[tuple[str, ...]]:
    """Locate the doc table whose header row contains all `must_contain`."""
    lines = doc.splitlines()
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s.startswith("|") and all(m in s for m in must_contain):
            return _parse_pipe_lines(lines[i:])
    raise AssertionError(f"doc table with header containing {must_contain!r} not found")


def _assert_rows_equal(doc_rows, gen_rows, tag: str) -> None:
    assert len(doc_rows) == len(gen_rows), (
        f"{tag}: row count doc={len(doc_rows)} vs generated={len(gen_rows)}"
    )
    for d, g in zip(doc_rows, gen_rows):
        assert d == g, f"{tag}: row diverged\n  doc={d}\n  gen={g}"


# =================================================================== §0 구조


def test_scenario_set_is_28_corpus_sorted(tables) -> None:
    """§0 서두 / 스크립트 §0: 모집단 = 28개 코퍼스, 자연정렬.

    모집단 변경(사용자 확정 2026-08-04): 구 38개(39 − K1000_5 중복)에서
    모델링 코퍼스 28개로 축소. K1000 계열이 통째로 빠졌으므로 "중복 K1000_5만
    제외" 규칙은 검사 대상이 아니라 **도달 불가**가 되었고, 그래서 아래는
    '중복 없음'이 아니라 '보류 K가 하나도 없음'을 잠근다.
    """
    stems = [p.stem for p in tables.paths]
    assert len(stems) == 28
    for stem in stems:
        assert not is_excluded(stem), stem
    assert "K1000_4" not in stems
    assert "K1000_5" not in stems
    # natural order: group by K then index
    key = lambda s: (int(s.split("_")[0][1:]), int(s.split("_")[1]))
    assert stems == sorted(stems, key=key)


def test_fixed_cost_8_combos_sum_to_28(tables) -> None:
    """§0.2: fixed_cost 고유 조합 8개, 시나리오 수 합계 28 (구 11개/38)."""
    assert len(tables.csets) == 8
    assert sum(c["n_scenarios"] for c in tables.csets) == 28


def test_rho_2_combos_sum_28_car_always_one(tables) -> None:
    """§0.3: ρ 고유 조합 2개, 합계 28, CAR의 ρ=1.0 전 조합 불변 (구 8개/38).

    ρ 다양성이 8 → 2로 줄어든 것은 데이터가 바뀌어서가 아니라 모집단에서
    K500 이상이 빠졌기 때문이다 — 코퍼스 28개 중 27개가 (0.2, 0.3, 1.0)이다.
    """
    assert len(tables.rsets) == 2
    assert sum(r["n_scenarios"] for r in tables.rsets) == 28
    assert all(r["rho"][RIDER_TYPES.index("CAR")] == 1.0 for r in tables.rsets)


# ============================================================ §2.1 완전지배


def test_bike_completely_dominates_car_all_combos(tables) -> None:
    """§2.1 불변 정리: BIKE가 CAR를 11개 조합 전부에서 완전지배.

    완전지배 정의(§2): slope_B ≤ slope_C AND intercept_B ≤ intercept_C.
    ⇒ D*(B,C) < 0 (D≥0 교차 없음). 임계 w_B/w_C ≤ speed_B/speed_C = 1.25,
    관측 최댓값 1.20. 문서가 인용한 1.25·1.20 도 함께 검증.
    """
    thr = tables.speed["BIKE"] / tables.speed["CAR"]
    assert thr == pytest.approx(1.25)

    max_ratio = 0.0
    for c in tables.csets:
        assert c["slope"]["BIKE"] <= c["slope"]["CAR"]
        assert c["intercept"]["BIKE"] <= c["intercept"]["CAR"]
        assert c["d_star_bc"] is not None and c["d_star_bc"] < 0, c["fixed_cost"]
        ratio = c["w_R"]["BIKE"] / c["w_R"]["CAR"]
        assert ratio <= thr, c["fixed_cost"]
        max_ratio = max(max_ratio, ratio)
    assert max_ratio == pytest.approx(1.20)

    # doc quotes the 1.25 threshold and the 1.20 observed max (§2.1)
    assert "1.25" in tables.doc
    assert "1.20" in tables.doc


def test_conditions_c2_c3(tables) -> None:
    """§2.2 조건 C2·C3 (관측 11개 조합 전부 성립).

    C2: w_W < w_B (service 동일 → intercept_W < intercept_B), 관측 최대비 0.864.
    C3: w_W/w_C > speed_W/speed_C = 0.3125, 관측 최솟값 0.45.
    """
    max_wb = max(c["w_R"]["WALK"] / c["w_R"]["BIKE"] for c in tables.csets)
    min_wc = min(c["w_R"]["WALK"] / c["w_R"]["CAR"] for c in tables.csets)
    thr_c3 = tables.speed["WALK"] / tables.speed["CAR"]

    assert max_wb < 1.0                       # C2: WALK 항상 BIKE보다 싼 인건비
    assert round(max_wb, 3) == 0.864
    for c in tables.csets:                    # C2 intercept form
        assert c["intercept"]["WALK"] < c["intercept"]["BIKE"], c["fixed_cost"]

    assert thr_c3 == pytest.approx(0.3125)
    assert min_wc > thr_c3                     # C3
    assert round(min_wc, 2) == 0.45

    assert "0.864" in tables.doc and "0.3125" in tables.doc and "0.45" in tables.doc


# ================================================= §3 3구간 강제 순위 구조


def test_three_regime_forced_ordering_all_combos(tables) -> None:
    """§0.2/§2.2/§3: 11개 조합 전부에서 3구간 순위가 강제됨.

    경계 D*(B,W)·D*(W,C) 를 ±1 m 로 넘나들며 `type_priority`가
      D<D*(B,W)          → [WALK, BIKE, CAR]
      D*(B,W)<D<D*(W,C)  → [BIKE, WALK, CAR]
      D>D*(W,C)          → [BIKE, CAR, WALK]
    를 정확히 반환하는지(경계 crisp) 전 조합 검증. 순서는 하드코딩이 아니라
    slope/intercept 로부터 코드가 도출한 것.
    """
    for c in tables.csets:
        combo = tuple(round(x) for x in c["fixed_cost"])
        riders = tables.riders_by_combo[combo]
        d_bw, d_wc = c["d_star_bw"], c["d_star_wc"]
        mid = (d_bw + d_wc) / 2.0
        assert type_priority(riders, d_bw - 1.0) == ["WALK", "BIKE", "CAR"], combo
        assert type_priority(riders, d_bw + 1.0) == ["BIKE", "WALK", "CAR"], combo
        assert type_priority(riders, mid) == ["BIKE", "WALK", "CAR"], combo
        assert type_priority(riders, d_wc - 1.0) == ["BIKE", "WALK", "CAR"], combo
        assert type_priority(riders, d_wc + 1.0) == ["BIKE", "CAR", "WALK"], combo
        assert type_priority(riders, d_wc * 2.0) == ["BIKE", "CAR", "WALK"], combo


def test_boundary_ranges(tables) -> None:
    """§2.2/§3/§0.2: 경계 범위 D*(B,W)∈[35,413], D*(W,C)∈[183,1212].

    조합별 극단값과 대표 조합 두 개의 정확한 float 도 검증:
    (5000,5000,5000)≈(52.9, 399.8), (9000,4000,5000)≈(412.7, 634.9).

    모집단 28개 반영(2026-08-04): D*(B,W) 상한이 794 → 413으로 내려갔다. 794 m를
    주던 (9000,3000,5000) 조합은 K1000 계열 전용이라 코퍼스 밖으로 나갔다.
    D*(W,C) 상한 1212 m는 (6000,3000,5000)=K300_7이 코퍼스 안이라 그대로다.
    """
    dbw = [c["d_star_bw"] for c in tables.csets]
    dwc = [c["d_star_wc"] for c in tables.csets]
    assert (min(round(x) for x in dbw), max(round(x) for x in dbw)) == (35, 413)
    assert (min(round(x) for x in dwc), max(round(x) for x in dwc)) == (183, 1212)

    by_combo = {tuple(round(x) for x in c["fixed_cost"]): c for c in tables.csets}
    c5 = by_combo[(5000, 5000, 5000)]
    assert round(c5["d_star_bw"], 1) == 52.9 and round(c5["d_star_wc"], 1) == 399.8
    c9 = by_combo[(9000, 4000, 5000)]
    assert round(c9["d_star_bw"], 1) == 412.7 and round(c9["d_star_wc"], 1) == 634.9
    # the old 794 m upper bound came from a K1000-only combo -- it must be gone
    assert (9000, 3000, 5000) not in by_combo

    # doc quotes the ranges verbatim (§2.2 line, §3 bullet)
    assert "35~413" in tables.doc and "183~1212" in tables.doc
    assert "[35, 413]" in tables.doc and "[183, 1212]" in tables.doc


# ============================================= §6/§8 WALK 1순위·재고여유 합계


def test_walk_first_and_full_stock_totals(tables) -> None:
    """§8 캡션 / §3 / §6.1: WALK 1순위 총합 87, 재고여유 WALK 총합 87.

    - walk_first(capa-무시 순수 비용 1순위 WALK) 합 == 87 == 전 5,200 의 1.7%.
    - full_stock(capa 필터 후 1순위 WALK) 합 == 87.
    - 각 시나리오 full_stock 3종 합 == 그 시나리오 K (전수).
    - 문서 캡션이 인용한 87·"87/5,200"·"1.7%" 도 계산값과 일치.

    모집단 28개에서 두 합계가 **같아졌다**(구 38개에서는 417 vs 411). capa 필터는
    VOL>70인 주문에서만 WALK를 깎는데 코퍼스에 그런 주문이 없어서다. 부등식이
    아니라 '차이 = capa에 걸린 건수'라는 관계를 잠근다 — 등호를 하드코딩하면
    데이터가 바뀔 때 의미를 잃는다.
    """
    assert tables.total_orders == 5200
    assert tables.walk_first_total == 87
    assert tables.full_walk_total == 87
    # capa 필터는 깎기만 한다(늘릴 수 없다). 28개 코퍼스에선 깎을 게 0건이라 등호.
    assert tables.walk_first_total >= tables.full_walk_total

    for a in tables.amaps:
        assert sum(a["full_stock_counts"].values()) == a["K"], a["stem"]

    doc = tables.doc
    assert f"28개 합계는 **{tables.walk_first_total}**" in doc
    assert f"WALK 열의 28개 합계는 **{tables.full_walk_total}**" in doc
    assert f"{tables.walk_first_total}/{tables.total_orders:,}" in doc  # "87/5,200"
    pct = round(tables.walk_first_total / tables.total_orders * 100.0, 1)
    assert pct == 1.7 and f"{pct}%" in doc


# ================================================== §2.2 tie-break (합성)


def test_tie_break_is_type_name_alphabetical() -> None:
    """§2.2 경계 tie-break: 비용 동률 시 type명 사전순 (BIKE < CAR < WALK).

    D=200 m 에서 세 라이더 비용이 정확히 200.0 KRW 로 교차하도록 합성
    (w_R=3600 고정, speed/service 로 (200,200) 통과). 입력 순서를
    역알파벳(WALK, CAR, BIKE)으로 넣어도 `type_priority`는 정렬-by-name 을
    반환해야 한다. D=100 에서는 순수 비용순([WALK,CAR,BIKE], 비알파벳)이라
    tie-break 가 오직 동률에서만 작동함을 대조로 확인.
    """
    # w_R = fixed_cost + var_cost*throughput = 3600 (throughput 기본 50)
    # cost(D) = (3600/3600)*(D/speed + service); (200,200) 통과 → service=200-200/speed
    walk = Rider("WALK", 1.0, 200, 0.0, 3600.0, 0.0, 1)    # cost(200)=200/1+0   =200
    car = Rider("CAR", 2.0, 200, 0.0, 3600.0, 100.0, 1)    # cost(200)=200/2+100 =200
    bike = Rider("BIKE", 4.0, 200, 0.0, 3600.0, 150.0, 1)  # cost(200)=200/4+150 =200
    riders = [walk, car, bike]  # 역알파벳 입력 순서

    costs = {r.type: delivery_cost_krw(r, 200.0) for r in riders}
    assert costs["WALK"] == costs["CAR"] == costs["BIKE"] == 200.0  # 정확 동률

    assert type_priority(riders, 200.0) == ["BIKE", "CAR", "WALK"]  # 사전순
    assert type_priority(riders, 200.0) == sorted(r.type for r in riders)
    # 동률이 아닌 곳에선 순수 비용순(비알파벳)이라 tie-break 개입 없음
    assert type_priority(riders, 100.0) == ["WALK", "CAR", "BIKE"]


# ============================== §0.2·§0.3·§8 문서표 ↔ 스크립트 산출 잠금


def test_doc_table_0_2_matches_generator(tables) -> None:
    """§0.2 fixed_cost 조합표(D* 2열 + 3구간 순위 3열) == build_t1(cost_sets).

    수기 숫자 부패(hand-written-number rot) 회귀 방지: 문서 표 셀을 파싱해
    스크립트가 코드에서 새로 생성한 표와 전수 대조.
    """
    doc_rows = _doc_table_rows(tables.doc, "0<D<D*(B,W)")
    _assert_rows_equal(doc_rows, _generated_rows(tables.t1), "§0.2")


def test_doc_table_0_3_matches_generator(tables) -> None:
    """§0.3 ρ 조합표 == build_t2(rho_sets)."""
    doc_rows = _doc_table_rows(tables.doc, "ρ (B,W,C)", "시나리오 수")
    _assert_rows_equal(doc_rows, _generated_rows(tables.t2), "§0.3")


def test_doc_table_8_matches_generator(tables) -> None:
    """§8 검증표(28행: stem·D*·D분포·VOL·재고여유·fallback·WALK 1순위) == build_t3.

    28개 전수 셀 일치(plan §4 "전수 일치"). 한 셀이라도 어긋나면 해당 행을
    찍어 실패한다.
    """
    doc_rows = _doc_table_rows(tables.doc, "재고여유 배정")
    gen_rows = _generated_rows(tables.t3)
    assert len(doc_rows) == 1 + 28, f"§8 rows={len(doc_rows)} (header+28 expected)"
    _assert_rows_equal(doc_rows, gen_rows, "§8")


# ============================ §5/§10 RiderPool ↔ assignment_map 정합성


def test_riderpool_matches_assignment_map_bike_exhaust(tables) -> None:
    """§5/§10: `RiderPool.try_dispatch` 재고로직이 assignment_map 의미와 일치.

    K300_7(fallback 다양성 有)에서 주문 전수를 흘려:
      - 전 type 재고 충분 → try_dispatch = capa필터 후 `type_priority`[0]
        (assignment_map full_stock 배정과 동일).
      - free['BIKE']=0 로 직접 소진 → try_dispatch = 우선순위상 첫 free type
        = 첫 비-BIKE eligible type (assignment_map bike_exhausted fallback 동일).
    집계도 §8 표(K300_7 재고여유 배정 / BIKE소진 fallback)와 전수 일치.
    """
    path = next(p for p in tables.paths if p.stem == "K300_7")
    scenario = load_scenario(path)
    riders = scenario.riders
    dist = pickup_drop_distance(path)
    amap = tables.amap_by_stem["K300_7"]

    full = RiderPool(riders)
    full.free = {t: 10**9 for t in full.free}          # 무한 재고
    exh = RiderPool(riders)
    exh.free = {"BIKE": 0, "WALK": 10**9, "CAR": 10**9}  # BIKE 소진 직접 설정

    full_counts = {t: 0 for t in RIDER_TYPES}
    fb_counts = {"WALK": 0, "CAR": 0}
    for i, order in enumerate(scenario.orders):
        o = types.SimpleNamespace(vol=order.vol, dist_m=float(dist[i]))
        eligible = [r for r in riders if r.capa >= o.vol]
        expected_full = type_priority(eligible, o.dist_m)[0]
        expected_fb = next(t for t in type_priority(eligible, o.dist_m) if t != "BIKE")

        t_full, _ = full.try_dispatch(o)
        t_exh, _ = exh.try_dispatch(o)
        assert t_full == expected_full
        assert t_exh == expected_fb
        full_counts[t_full] += 1
        fb_counts[t_exh] += 1

    assert full_counts == amap["full_stock_counts"]
    assert fb_counts == amap["bike_exhausted_fallback_counts"]
