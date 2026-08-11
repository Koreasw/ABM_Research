# H0 v2 / v2.1 검증 결과 집계 보고서 (verification_report_h0v2.md)

> **개정 2026-08-06 (v2.1 = R8 창·종료 재정의)**: W1~W8의 v2 판정은 §0~§7에
> **그대로 보존**한다(2026-08-04 시점의 기록). R8이 창·종료 규약을 바꾼 뒤 배터리를
> 전부 다시 돌린 결과는 **§8(V21 재검증)**에 있고, **현재 인용해야 할 정본 수치는
> §8**이다. §2 매트릭스의 수치는 legacy_margin 창에서 측정된 것이라 논문에 직접
> 인용하면 안 된다 — §8에 같은 게이트의 delivery 기준 재산출값이 있다.
>
> 작성: 2026-08-04, 세션(오퍼스)/high (`etc/plan_h0v2_verification.md` §4 W8 배정).
> v1 보고서(`archive/h0_v1/docs/verification_report_h0.md`) 양식을 승계한다.
> 본 문서는 **W1~W8의 신규 실험 없이** 완료된 산출물(검증계획서 §8 진행 로그 ·
> `results/vv/` CSV 10종 · `results/h0_stats/` · `analysis/h0_insights/`)을 집계·재인용한다.
> 논문 §7.1 "8-step Partial V&V" 절의 재료다.
>
> 정본 우선순위: **`results/` CSV > `etc/plan_h0v2_verification.md` §8 진행 로그 > 본 문서.**
>
> ⚠️ **v1 수치는 본 문서에 인용하지 않는다.** v1은 2 EV · 800 ㎡ · 복도 27 m ·
> 지하 없음 건물의 값이라 v2의 오라클이 될 수 없다(검증계획서 §7). v1과의 대조는
> `analysis/h0_insights/note_v1_v2_comparison.md` **한 곳에만** 두고, 그 문서의 v1 열도
> 논문 인용 대상이 아니다.

---

## 0. 검증 트랙 재확인 (본 문서 작성 세션, 2026-08-04)

- `.venv/bin/python -m pytest -q` : **437 passed / 3 skipped**
  (스킵 3건은 STAGE 3 미구현분 — `test_cost_model.py`·`test_locker.py`의 NPV/락커
  로직, 본 트랙과 무관. v1 트랙의 스킵 3건과 동일한 항목이다.)
- W1~W8에서 스위트가 **415 → 437**으로 늘었다(+22): W1 +9(A10~A12) · W2 +9(절대
  검산 골든패스) · W4a +3(EV 1대 축퇴 · 러시 ×2 seed).
- `results/vv/`·`results/h0_stats/` 산출물을 **세션이 재파싱해 독립 재계산**했다 —
  단계별 재검증 내역은 §2 "독립 재검증" 열, 불일치는 §3에 기록.

---

## 1. 요약

**검증 스코프**: 논문 본문 트랙(H0 v2 paper track) =
`BuildingHandoffModel(mode=H0, dynamic_pool=True, return_leg=False,
scenario_window=True, floor_profile="uniform", config=baseline_10f.yaml(v2))`,
**지상 10층 + 지하 2층 · 층당 ~1,200 ㎡ · 복도 34 m · EV 4대 교차배치 ·
상주 900명 · 보행자 7.5 /분** 빌딩, **28개 시나리오 코퍼스**(primary 20 + extreme 8;
K500·K750·K1000은 본 실험에서 보류 — 사용자 확정 2026-08-03 2차).
동결 경로(`regression_nobasement_10f.yaml` · `results/pre_basement/`)는 회귀 기준선
으로만 다룬다.

**전체 판정**: 게이트 **13개 중 PASS 12 / CAUTION 1 / PENDING 0** — **H0 v2 검증 완료**
(V2-VISUAL 사용자 육안 서명 2026-08-04로 마지막 PENDING이 닫혔다).

- **CAUTION 1건 = W5b(V2-FACE)** — deadline slack과 T_e2e 층별 기울기 두 하위 판정.
  v1도 같은 라벨이었으나 **근거가 완전히 바뀌었다**: v1의 CAUTION은 위반 14건이 전부
  K1000이라는 사실에 근거했는데 그 티어가 코퍼스 밖이 되어 **재현 불가**다. v2의
  판정은 **위반 0/15,600 · 최소 여유 12.58분**이라는 재산출값에 근거하며, 결론은 v1보다
  강하다 — **SLA·S_customer는 v2 코퍼스에서 판별력이 없다**(§4 ①).
- **W7 V2-VISUAL = PASS (2026-08-04 사용자 서명)** — 구 PENDING이 해소됐다. §3 기하
  6항목은 세션이 정적 렌더 2종으로 선판정(전건 기대 일치)했고, **§4 거동 8항목은
  사용자가 앱(`solara run simulation/app.py`)에서 K50_1·K200_1 각 1회 동적 관찰**해
  전건 PASS로 판정했다. 이상 거동·결함 관측 **0건**. 판정 원본은
  `etc/checklist_visual_h0v2.md` §5(메타데이터·항목별 표·종합 서명).
  K1000_1은 선택 항목이자 보류 티어라 미실시 — 판정에 영향 없음.
- 나머지 11건 PASS: 불변식 위반 0 · 방향성 위반 0 · 잔차 float-exact ·
  스냅샷 비트 동일.

> **이로써 H0 v2 검증 배터리가 닫혔다.** 남은 CAUTION 1건은 결함이 아니라 **해석상
> 유의사항**(SLA 무판별)이므로 Phase A 착수를 막지 않는다. 착수 전 남은 것은 문서
> 개정 ⓑ뿐이다(`etc/HANDOFF_v2.md` §4).

---

## 2. 검증 매트릭스

판정 표기: **PASS** / **CAUTION**(불변식 위반은 없으나 해석·설계 유의사항) /
**PENDING**(산출물 준비 완료, 실행·판정 미완).

| Stage | 검증 ID | 목적 | 방법(도구·규모) | 핵심 수치 | 독립 재검증 | 판정 |
|---|---|---|---|---|---|---|
| W1 | **V2-AUD** | 사후 불변식 게이트를 v2 구조(4EV·지하)로 확장 | `analysis/verify_h0.py` A1~A9 → **A1~A12** + `model._audit_invariants()` 틱 assert | 코퍼스 표본 5종 × 3 seed = **15 run 전건 PASS**; A10 3분지(구조·라이더 미진입·EV rank 범위), A11 EV 선언 정합, A12는 구조상 SKIP | 스위트 424 passed(+9) · K50_1 골든 비트 일치 · `audit=True` 비트 동일 | **PASS** |
| W2 | **V2-GP** | 그래프와 **무관한** 손계산 절대값으로 빌더 교차검증 | `tests/test_vv_golden_path_v2.py` 신규 9건(기하·기구학·전여정 3층 구조) | d1 8.0 m · **d2 8.0 m · s2 8.0 m**(2026-08-04 재배치로 6.0→8.0 재산출) · 1F→7F **12.1 s** · **1F→B1 4.0 s · 1F→B2 5.7 s · B2→10F 20.1 s**(rank 규약이 물리량으로 드러나는 지점) | **뮤테이션 감도**(재배치 이전 기하에서 측정): 사무실 이동·층고 4.0→3.5 m 모두 적발. R7 재배치 후에는 상수를 손으로 재유도해 9건 재통과 | **PASS** |
| W3 | **V2-ALL28** | v2 최초 코퍼스 전수 실행 + 예산 산정 | `experiments/vv_all39.py` 2패스: 본 배터리 28×3=**84 run**(audit OFF) + **감사 스윕 28 run**(seed 42, audit ON) | **84/84 + 28/28 PASS**; A4 최소 slack **−0.048 s**(1-tick 내); A9 p<0.05 **0/112**; K50 1.00 s ~ K300 2.12 s/run, 84 run 134.3 s | CSV 재파싱: all_passed 전건 True · skipped 집합 {A12}만 · delivered==K 전건 | **PASS** |
| W4a | **V2-EXT** | 축퇴·포화 경계에서 v2 일반화가 성립하는가 | `tests/test_vv_extreme.py` 12 → **15건** (EV 1대 축퇴 1건 + 30 /분 러시 2 seed) | EV 1대: 완주 50/50 · KPI/`model_vars`/그래프 EV 키가 **정확히 EV1 하나** · util 0.999. 러시: 완주 200/200 · **4대 전부 util 0.996~0.999** · W_EV 84.70 s(기준선 36.11) | **뮤테이션 2건 적발**: `ev2_*` 리포터 잔재 주입 → 적발 / 러시 30→9 /분 → 포화 플로어 적발 | **PASS** |
| W4b | **V2-MONO** | 6개 인과 방향의 단조성 | `experiments/vv_monotonicity.py` 130 run·169.5 s | **6/6 PASS**. dir6 재산출 사다리 W_EV **22.11 → 34.72 → 41.74**(K50_1→K200_1→K300_4) | 저장 verdict 불신 — CSV 원시 평균에서 방향 재판정, 게이트 9행 전건 일치 | **PASS** |
| W5a | **V2-DECOMP** | T_e2e 7성분 가산성 + 논문 figure | `analysis/vv_decomp.py`, 28 시나리오 전 주문 | 주문 단위 잔차 **max 3.638e-12 s**(허용 1 tick) → float-exact. **`rider_wait` 전 구간 정확히 0** | CSV 재파싱 성분 직접 합산; **p95 행은 합이 성립하지 않음**(성분별 백분위수)을 명시 | **PASS** |
| W5b | **V2-FACE** | 통계적 상식 정합 4종 | `analysis/vv_face.py` 84 run·**15,600 주문** | ①stairs PASS(2F 91.4%→5F 이상 0) ②층 기울기 CAUTION(2·SE 초과 역전 0) ③slack **CAUTION — 위반 0/15,600 · 최소 12.58분** ④T_lobby PASS(4.09→4.66분 단조) | v1 보고서 대조로 **인용 불가 수치 2건 식별 후 코드 정정**(§3 ②③) | **CAUTION** |
| W5c | **V2-BAL** | 4EV 동점 타이브레이크 쏠림 감사 (신규) | **`analysis/vv_balance.py` 신규** 90 run·137.4 s | G1 EV별 boardings **max/min 1.004~1.125**(한계 1.5) · G2 북/남 **0.951~1.062**(밴드 0.8~1.25). 극단 티어도 1.019~1.104 | 원시 boardings에서 두 비율 재계산·재판정, FAIL 0건 | **PASS** |
| W5d | **V2-EVSEL** | designated-dispatch 단순화의 대가 정량화 | `analysis/vv_evsel.py` 30행 | stale **51.8%**(rider 60.7 / ped 49.7), harm **상한** mean 25.09 s · p95 73.68 · max 138.5 | `ALL` 행이 kind별 9 run 합과 정확히 일치, `stale_ratio` 재계산 편차 ≤4.95e-5 | **PASS** |
| W5e | **V2-DET / V2-VAR** | 재현성 + 30-seed 분산 구조 | `tests/test_vv_determinism.py` 7건 · `experiments/vv_variance.py` 180 run·303.0 s | DET **7 passed**. CI95 상대폭: t_e2e_mean **0.066~0.102%** · t_lobby 0.678~0.944% · w_ev **1.989~4.540%**. 채널비: 평균계 **0.394~1.217**, p95 **0.995~1.779** — 대부분 1.0과 구별 불가 | Phase E 전제를 세션이 직접 해석·**정정**(§4 ④) | **PASS** |
| W6 | **V2-TIER** | 보류 11개가 **어떤 경로로도** 산출물에 안 들어오는가 | `--tier {extreme,all,primary}` 3회 실제 실행 + CLI 반증 시도 | 8 / 28 / 20행, tier 열 정합, **보류 stem 0건**. `--tier excluded`는 argparse가 거부, 선택 가능 전 티어 합집합 ∩ 보류 = **공집합** | 소스 가드(23 passed)와 별개로 산출물을 직접 검사 | **PASS** |
| W6 | **V2-WIN** | 창 선택(D4)의 사후 정당화 | `experiments/vv_window_bias.py` 30 run·40.6 s | 구 고정 점심피크 창은 혼잡을 **과소평가** — W_EV **+37.8~+53.3%** · T_lobby +7.0~+12.1% · T_e2e는 +0.5~+1.0%만 | seed 평균 재계산: 12개 비교 중 11개 방향 일치, 예외 1건은 W5e 실측 노이즈 폭 내 | **PASS** |
| W7 | **V2-CMP** | 개정계획 §7 리스크 3의 정량 판정 | `analysis/h0_insights/note_v1_v2_comparison.md` 신규, 매칭 84쌍 | 시나리오 간 CV: T_e2e 7.7224→7.7300%(불변)·W_EV 12.75→**14.89%**(확대) → **대비 압축 미발현**. **로봇의 T_e2e 단축 상한 11.6~13.0%** | 핵심 비율 1건을 자체 검산으로 정정(§3 ①) | **PASS** |
| W7 | **V2-VISUAL** | v2 기하·거동 육안 확인 | `etc/checklist_visual_h0v2.md` §5(판정 원본) + 정적 렌더 2종 | §3 기하 6항목 세션 선판정 **전건 기대 일치**(지하 행에 회색 보행자만 = A10-2 육안 확인 포함) | §4 거동 8항목을 **사용자가 K50_1·K200_1에서 동적 관찰 → 전건 PASS**(2026-08-04 서명). 이상 관측 0건 | **PASS** |
| W8 | **V2-SNAP** | 최종 동결 스냅샷 무변화 확인 | 4종 × 2회 독립 재생성 + 구조 비교 | **2회 실행 상호 동일 · 동결본과도 동일**. (최초 W8에서는 "재동결 불필요"였고, R7 사무실 재배치 후 **재동결한 뒤 같은 검사를 다시 통과**했다) | **`cmp` 바이트 비교는 이 게이트에 부적합**하다는 사실을 확인(§3 ④) | **PASS** |
| W8 | **V2-DOC** | v1 상수·규약 잔재 소탕 | grep 13패턴 × 리포 전체(archive 제외) | **6곳 정정**(§3 ⑤) + R7 재배치 후 구 사무실 위치 **5곳 추가 소탕**(체크리스트·도면 HTML·방법론 v4·검증계획 §0.1·개정계획 §1). 잔존 hit는 전부 *부재를 단언하는 테스트* 또는 *의도적 이력 기록* | 소탕 후 재실행으로 0건 확인 | **PASS** |

---

## 3. 발견·수정 이력

W1~W8에서 **모델 결함은 0건**이었다. 아래는 전부 *게이트·문서·판정문·기하 사양*의
결함이며, 그중 ①②③은 **잘못된 수치를 논문에 실을 뻔한** 건, ⑥은 **잘못된 건물을
지을 뻔한** 건이다.

**① V2-CMP 초고의 비율 오용 (세션 자체 검산으로 정정)**
로봇의 T_e2e 단축 상한 근거로 `T_lobby / T_e2e`(15.4~18.6%)를 썼다. `T_lobby`는
라이더의 건물 내 **왕복** 체류라 하강·퇴장 구간이 `delivered` **이후**에 있고, T_e2e와
부분적으로만 겹친다. 분해 성분(walk+ev_wait+ride+service)으로 재계산한
**11.6~13.0%**가 옳다. 혼동하면 로봇 효과를 **최대 6 pp 과대평가**한다. 노트에 두
비율을 구분하는 절을 신설했다.

**② V2-FACE의 SLA 판정문이 v1 서사를 하드코딩**
판정문이 "117-run 배터리가 소수의 위반을 K1000에 집중해 발견"이라고 **출력**하고
있었다. v2는 84 run이고 K1000은 코퍼스 밖이라, 위반 0건을 세면서 "nonzero"라고
쓰는 자기모순 문장이 CSV·콘솔에 그대로 찍혔다. 판정문을 **측정값에서 파생**하도록
고쳤다.

**③ V2-FACE의 T_lobby 게이트가 v1 절대 앵커**
check 4가 "K50 ≈ 4.1분"을 **게이트**로 쓰고 있었다. 이 값은 2EV·800㎡·27 m·지하없음
건물의 값이고, v2는 복도 34 m(↑)와 EV 4대(↓)가 상쇄돼 근접하는 것이 **검증이 아니라
우연**이다. 절대 오라클은 이미 W2의 손계산 상수가 맡으므로, 게이트를 **"K가 커질 때
T_lobby가 감소하지 않는다"(2·SE 노이즈 허용)** 로 교체하고 4.1분은 이력 출력으로 강등.

**④ V2-SNAP에 바이트 비교를 쓰면 오판한다**
4종 스냅샷을 `cmp`로 비교하면 K100_1·K200_1·K300_4가 "다르다"고 나온다. 실제 차이는
`runtime_wall_sec`(벽시계 계측값, ±0.02 s)뿐이고 K50_1은 우연히 같은 값으로 반올림돼
"같다"고 나왔을 뿐이다. **모델 상태는 전부 동일**하다(`test_h0_frozen_snapshot.py`가
구조 비교를 쓰는 이유이며, 그 독스트링이 이미 경고하고 있었다). 미래에 md5로 확인하면
없는 회귀를 보고하게 된다.

**⑤ V2-DOC 소탕 6곳**
`research_plan_scie.md` 4곳(건물 정의 · EV1/EV2 용어 · 로봇 충전 도크 지하 1층 ·
보행자 6.0 /분 · W_EV 분리보고 · "EV 2대 경합"), `methodology_demand_to_floor_mapping_v4.md`
§5.4 건물 상수, `scie_phase/phase_A_robot_h1.md` Step A3의 "EV2만 잠식".
`building_10f_layout.html`의 "지하층 없음"은 `nBasements == 0` 분기의 정상 폴백이라
**소탕 대상이 아니다**(오탐).

**⑥ 사무실 배치의 기하 오류 2건 + 미터/인덱스 혼용 (사용자 지적 → R7)**
사용자가 사무실 위치 재조정을 제안하며 드러난 것: R1 배치 [4,9,14,19,24,29]는
①복도 중점·EV 뱅크 중심이 17.0인데 **사무실 열만 16.5 대칭**이었고 ②사무실 14·19 m가
EV 도어(16·18)에서 2 m·1 m라 **샤프트가 사무실 안**이었다. [2,7,12,22,27,32]로 재배치
(17.0 대칭 + 12~22 m를 EV 서비스 코어로 비움). 동시에 **`office_positions_m`이
미터이자 복도 노드 인덱스로 쓰이던 혼용**을 수정했다 — 오프그리드 값은 예외 없이
통과한 뒤 `add_edge`가 유령 노드를 만들어 **사무실이 복도에서 고립**되고 주문이
배달 불가가 됐다(범위 검증도 미터를 인덱스 상한과 비교). 상세·재검증은 개정계획 §9 R7.

**⑦ 극한 테스트가 주장을 검사하지 못하고 있었다 (R7 재실행에서 발견)**
`test_extreme_all_pedestrians_to_deepest_basement`이 "B2 전량 부하가 더 무겁다"를
**총 가동률**로 판정했다. 가동률은 0.78 근처에서 포화해 부하 증가에 거의 반응하지
않는다 — 6 seed 중 5회만 방향이 맞고 seed 42는 **0.11%로 뒤집혔다**. 지표를
**승객 운행 층수 합**(6/6에서 +22.6~30.0%)과 **B2 승차 발생 여부**로 교체했다.
재배치가 결함을 만든 게 아니라 **원래 취약하던 게이트를 드러냈다.**

**⑧ 체크리스트의 가동률이 R6 이전 값**
`checklist_visual_h0v2.md` §4가 "가동률 0.71~0.74"로 안내하고 있었는데 이는 **지하
도입 전** 값이다. 지하 왕복이 EV 부하를 되돌려 현재는 **0.773~0.835**다. 그대로 두면
사용자가 "배지가 안 보이는 게 정상"이라 오판한다 — 실측값으로 갱신했다.

---

## 4. CAUTION·실험 설계 반영 사항

**① SLA·S_customer는 v2 코퍼스에서 판별력이 없다** (W5b, CAUTION의 실질)
위반 **0/15,600**, 최소 여유 **12.58분**, p5 **19.75분**. 1차 티어에서는 v1도 0이었다.
deadline을 조이거나 부하를 올리지 않으면 이 KPI로 H0 **구성 간** 차이조차 못 본다.
→ 논문 KPI 세트에서 제외하거나 재설계할 것.

**② 대표 KPI를 T_e2e에서 건물 내 지표로 옮길 것** (W7 V2-CMP)
T_e2e의 **64~68%가 `cook`, 19~24%가 `street`** 로 둘 다 건물·모드와 무관하다. 로봇이
배달구간 건물 내 여정을 전부 없애도 평균 T_e2e 단축 상한은 **11.6~13.0%**다.
→ 대표 지표는 **T_lobby · W_EV · 라이더 인건비(opex)**, T_e2e는 부차 지표로 그 비율이
작은 이유와 함께 보고. 상한을 인용할 때 §3 ①의 두 비율 구분을 지킬 것.

**③ 저부하 EV 쏠림 — Phase A 유효성 위협** (W5c)
코퍼스에서는 균형이 통과한다(max/min 1.125 ≤ 1.5). 그러나 배경교통이 0인 저부하에서는
동점이 항상 ev_id 오름차순으로 풀려 **EV3·EV4 승차가 정확히 0건**이 된다(3 seed 전부).
로봇 공용차가 하필 그 둘이라, **저부하 감도 케이스에서 로봇 이득이 과대평가**된다.
→ dispatch 수정은 불요(게이트 통과)지만 Phase A 실험 설계에 **명시적 유효성 위협**으로
등재할 것.

**④ Phase E 전제 — CRN은 평균계에만 유효** (W5e)
**정정 2026-08-04 (재배치 후 재측정)**: 이전 판본은 "`floor_seed` 고정 CRN이 평균계
KPI 분산의 30~65%를 제거한다"고 적었으나, 재측정하니 채널비
(= Var(floor 고정)/Var(전체))가 **평균계 0.394~1.217**, **p95 0.995~1.779**로 흩어졌다.
n=30에서 분산비의 표본분포는 대략 F(29,29)(95% 범위 ≈ [0.48, 2.09])이므로 **대부분의
값이 1.0과 통계적으로 구별되지 않는다.** 명확히 감소한 것은 K300_4뿐이다
(t_lobby 0.394 · w_ev 0.504 · t_e2e 0.512).

→ **Phase E 전제는 "CRN이 이득을 준다"가 아니라 "이득 여부를 시나리오별로 확인한
뒤 쓴다"로 바꿔야 한다.** 30 seed는 채널 분해를 결론지을 만큼의 검정력이 없다.

변하지 않은 결론: 30 seed면 **평균계 CI95가 ≤1%**(t_e2e_mean 0.066~0.102%)이므로
모드 간 대비가 1%를 넘으면 분해 가능하고, **w_ev_mean은 저수요(K50)에서 ±4.5%**라
저수요 EV 대기 비교는 seed를 늘리거나 지표를 바꿔야 한다.

**⑤ designated-dispatch의 대가가 v1의 2~4배** (W5d)
stale 51.8% · harm 상한 평균 25.09 s. 차가 2→4대로 늘어 "선택 시점 argmin"과 "등록
시점 argmin"이 어긋날 여지가 **구조적으로** 커졌다. 다만 harm은 보수적 상한이고
t_e2e ~1,550 s 대비 **1.6% 수준**이라 단순화는 여전히 방어 가능 —
논문의 단순화 방어 절에 **재산출값으로** 쓸 것.

**⑥ 라이더 풀은 병목이 아니다** (W5a)
`rider_wait`가 코퍼스 전 구간에서 **정확히 0**이다(V2-MONO dir4의 high(orig)=0.0과 정합).
→ 논문에서 동적 라이더 풀을 제약으로 서술하면 안 된다.

**⑦ 극단 티어의 역할 재정의** (W7)
개정계획 §7은 "극단 티어가 차별화의 핵심"이라 했으나 상한이 K1000→K300으로 내려왔다.
K300에서도 가동률은 아직 **상승 중**(0.835)이므로, 차별화가 더 필요하면 K를 올리는
것보다 **보행자 부하를 올리는 편이 싸다**(W4a 실측: 30 /분이면 4대 전부 0.992~0.998).

---

## 5. 확정 규약 (사용자 결정, 재론 금지)

| 날짜 | 결정 |
|---|---|
| 08-03 | EV 4대 교차배치, 공용은 EV3·EV4 (`shared_ev_ids`로 선언적 변경 가능) |
| 08-03 | 건물 확장: 1,200 ㎡ · 100명/층 · 보행자 7.5 /분 · 복도 34 m |
| 08-03 | 로봇 충전 B1 → **1F 로비존 통합**, 대기 중 수시 충전 |
| 08-03 | **K500·K750·K1000 미사용** → 코퍼스 28개 |
| 08-03 | **지하 2개층 신설** — 사람 승하차 전용 |
| 08-03 | 보행자 지상 종점 **1F 0.50 / B1 0.30 / B2 0.20**, 총량 7.5 /분 **재분배** |
| 08-03 | V2-SNAP 동결 범위 = **K50_1 · K100_1 · K200_1 · K300_4** |
| 08-03 | V2-VAR seed 수 = **30** |
| 08-04 | K500+ 지위 = "영구 제외"가 아니라 **"본 실험에서 우선 보류"** |
| 08-04 | 라이더 배정 인용 모집단 **38 → 28개 재산출** |
| — | **git 미사용** (커밋·태그 금지) · **Fable 미사용**(판단 구간은 오퍼스 `max`) |

---

## 6. 논문 §7.1 "8-step Partial V&V" 대응표

| # | Framework §7.1 단계 | 대응 결과 | 비고 |
|---|---|---|---|
| 1 | Partial calibration | V-RIDER(v1 완료·기하 무관 승계) | 인용 모집단만 28개로 재산출(계획서 §6-3) |
| 2 | Face validity | **W5b V2-FACE(CAUTION)** + **W7 V2-VISUAL(PASS, 2026-08-04 서명)** | 전문가 인터뷰 미실시 — 통계적 상식 정합 + 육안 체크리스트로 대체. 이 대체 방식 자체는 논문 한계 절에 명시 |
| 3 | Extreme-value test | **W4a V2-EXT(PASS)** | v2 신규 2케이스(EV 1대 축퇴 · 30 /분 러시) 포함. 로봇/락커 극한은 H1~H3 미구현이라 범위 밖 |
| 4 | Sanity test (단조성) | **W4b V2-MONO(PASS)** | 6/6, K↑ 사다리 K50_1→K200_1→K300_4로 재구성 |
| 5 | G/G/c docking | (미실시) | H2 큐잉존 자체가 미구현 — 범위 밖 |
| 6 | Replay-driven lower bound | **W1 V2-AUD(A4) + W2 V2-GP + W3 V2-ALL28** | A4 최소 slack −0.048 s(1-tick 내), 28 시나리오 전수 |
| 7 | Travel time decomposition | **W5a V2-DECOMP + A5** | 잔차 3.638e-12 s, figure 2종 산출 |
| 8 | Rider arrival face validity | (본 트랙 범위 밖) | STAGE1 산출물을 입력으로만 소비 |
| — | Replication (30 seed, CRN) | **W5e V2-VAR + V2-DET** | §4 ④의 채널 분해가 Phase E의 CRN 전략 근거 |
| — | (v2 신규) 부하 균형 | **W5c V2-BAL** | 4EV 고유 위험. v1에는 대응 항목이 없다 |
| — | (v2 신규) 창 편향 | **W6 V2-WIN** | D4 사후 정당화 |
| — | (v2 신규) v1 대비 | **W7 V2-CMP** | 개정계획 §7 리스크 3 판정 |

---

## 7. 산출물 색인 (재현 경로)

```
etc/plan_h0v2_verification.md          # 정본 진행 로그(W1~W8) — 본 문서의 1차 소스
etc/plan_h0_revision.md                # 개정 계획서(R0~R6)
etc/checklist_visual_h0v2.md           # V2-VISUAL 체크리스트 + §5 판정 원본 (PASS, 2026-08-04 서명)
analysis/h0_insights/note_v1_v2_comparison.md   # W7 V2-CMP (v1 대조는 여기에만)

results/vv/all39_battery.csv           # W3  (112행)
results/vv/monotonicity.csv            # W4b (10행)
results/vv/decomp_by_k.csv + decomp_{mean,p95}.png   # W5a
results/vv/face_{stairs_by_floor,te2e_by_floor,slack,tlobby_by_k}.csv
                       + face_slack_hist.png        # W5b
results/vv/ev_balance.csv              # W5c (90행)
results/vv/evsel_stale.csv             # W5d (30행)
results/vv/variance_{30seed,summary}.csv            # W5e
results/vv/window_bias.csv             # W6  (60행, V21에서 축 재정의)
results/vv/warmup_bias.csv             # V21-NEW (182행)
results/vv/window_compare.csv          # V21-NEW (64행)
results/h0_stats/{scenario_traits,h0_kpi_by_scenario}.csv   # W6·W7 (1차 티어)
results/figures/h0v2_cross_{K50_1,K200_1_rush}.png  # W7 정적 렌더
results/baseline_h0_{K50_1,K100_1,K200_1,K300_4}_uniform_s42.json   # W8 동결 4종
results/pre_basement/*.json            # 지하 도입 이전 골든 (하위호환 잠금)
archive/h0_v2_frozen/                  # R8 이전(v2) 동결본 — 읽기 전용, 구·신 대조의 유일한 출처
```

재현:

```bash
.venv/bin/python -m pytest -q                       # 440 passed / 3 skipped
.venv/bin/python -m experiments.vv_all39            # W3 (+ W1 감사 스윕)
.venv/bin/python -m experiments.vv_monotonicity     # W4b
.venv/bin/python -m analysis.vv_decomp              # W5a
.venv/bin/python -m analysis.vv_face                # W5b
.venv/bin/python -m analysis.vv_balance             # W5c
.venv/bin/python -m analysis.vv_evsel               # W5d
.venv/bin/python -m experiments.vv_variance         # W5e
.venv/bin/python -m experiments.vv_window_bias      # W6 WIN (legacy_margin ↔ delivery)
.venv/bin/python -m experiments.vv_warmup_bias      # V21-NEW 워밍업 머리 스윕
.venv/bin/python -m experiments.vv_window_compare   # V21-NEW 4창 비교
.venv/bin/python -m experiments.h0_descriptive --tier primary   # W6·W7
.venv/bin/python -m analysis.h0_baseline_stats --tier primary   # 주 지표 = utilization_delivery
```

---

## 8. V21 재검증 — R8 창·종료 재정의 이후 (2026-08-06)

> 배정: `etc/plan_h0v21_window.md` §8.2 / 실행 지시: `etc/HANDOFF_r8_step78.md` §3.
> **여기부터가 논문 인용 정본이다.** §2의 v2 수치는 `legacy_margin` 창에서 나온
> 것이라 창 정의가 다르다.

### 8.1 비교가 왜 CI 판정인가

워밍업 길이가 바뀌면 `ped_rng`(seed+1)의 틱 정렬이 달라져 **같은 시드도 다른 보행자
실현**을 낳는다. 구·신 비트 동일성은 **원리적으로 불가능**하므로, KPI를 세 그룹으로
사전 선언하고 각각 다른 판정을 걸었다(사후 해석 금지).

| 그룹 | KPI | 합격 기준 | 결과 |
|---|---|---|---|
| **I. 불변이어야 함** | T_e2e mean/p95, T_lobby, W_EV, rider_wait, `delivered`, SLA율 | 구·신 30시드 **CI95 겹침** | **15/15 겹침** + `delivered` **112/112 run 완전 일치** |
| **II. 구조적으로 변해야 함** | ticks, wall_span, `utilization`(full), ped n_spawned, termination_reason | 방향 사전 선언 일치 | **6항목 전건 일치**(R8-e) — ticks −29.2~−40.5% |
| **III. 정의상 불변** | `utilization_orderspan`, opex(라이더 체류 중만 적산) | 통계적 동일 | Welch \|t\| **0.90~1.96 < 2** (n=5) |

**그룹 I 판정 원표** (`experiments/vv_variance` 30시드, 구 = `archive/h0_v2_frozen/vv/`):

| 시나리오 | KPI | 구 mean ± CI95 | 신 mean ± CI95 | Δ | 겹침 |
|---|---|---|---|---|---|
| K50_1 | T_e2e mean | 1586.347 ± 1.622 | 1586.503 ± 1.607 | +0.0% | ✅ |
| K50_1 | T_lobby mean | 241.491 ± 2.281 | 240.715 ± 1.649 | −0.3% | ✅ |
| K50_1 | W_EV mean | 23.318 ± 1.059 | 23.119 ± 0.761 | −0.9% | ✅ |
| K200_1 | T_e2e mean | 1601.167 ± 1.238 | 1600.815 ± 1.404 | −0.0% | ✅ |
| K200_1 | T_lobby mean | 264.198 ± 2.021 | 262.704 ± 2.087 | −0.6% | ✅ |
| K200_1 | W_EV mean | 35.594 ± 0.924 | 34.888 ± 0.870 | −2.0% | ✅ |
| K300_4 | T_e2e mean | 1548.813 ± 1.028 | 1547.851 ± 1.098 | −0.1% | ✅ |
| K300_4 | T_lobby mean | 277.229 ± 1.879 | 275.798 ± 1.902 | −0.5% | ✅ |
| K300_4 | W_EV mean | 42.184 ± 0.839 | 41.480 ± 0.842 | −1.7% | ✅ |

(p95 3건·rider_wait 3건 포함 15/15. `rider_wait`는 구·신 모두 **정확히 0** — 라이더
풀은 여전히 병목이 아니다.)

### 8.2 V21 검증 매트릭스

| # | 항목 | 도구·규모 | 핵심 수치 (delivery 기준) | 판정 |
|---|---|---|---|---|
| W1 | **V21-AUD** | `verify_h0.py` **A1~A14** + 감사 스윕 28 run | **A1~A14 전건 PASS, A12만 SKIP**(결과 JSON이 큐 길이만 기록 — 구조상). 신설 A13 warm-up adequacy · A14 termination reason이 살아 있음 | **PASS** |
| W2 | **V21-GP** | `test_vv_golden_path{,_v2}.py` | **14 passed.** 손계산 상수 그대로(그래프 조회로 대체하지 않음) | **PASS** |
| W3 | **V21-ALL28** | `vv_all39.py` 28×3=84 run + 감사 28 | **84/84 + 28/28 PASS.** A4 최소 slack **−0.367 s**(허용 1 tick, 구 −0.048 s) · A9 p<0.05 **0/112** · 84 run 102.6 s | **PASS** |
| W4a | **V21-EXT** | `test_vv_extreme.py` 15건 | **15 passed.** 드레인 예산은 R8-d 재실측치(`RUSH_OVERRUN_SEC` 7200, `SATURATING_PED_RATE` 30/분) 그대로 유효 | **PASS** |
| W4b | **V21-MONO** | `vv_monotonicity.py` 130 run·132.5 s | **6/6 PASS.** dir6 사다리 W_EV **23.85 → 35.78 → 42.25**. dir5 fallback 감소는 `gate=False` 정보행(기지) | **PASS** |
| W5a | **V21-DECOMP** | `vv_decomp.py` 28 시나리오 전 주문 | 주문 단위 잔차 **max 3.638e-12 s** — 구본과 **동일 자릿수 유지**. `rider_wait` 전 구간 0 | **PASS** |
| W5b | **V21-FACE** | `vv_face.py` 84 run·15,600 주문 | ①stairs PASS ②층 기울기 CAUTION ③slack **CAUTION — 위반 0/15,600 · 최소 12.27분**(구 12.58) ④T_lobby PASS(4.12→4.63분 단조) | **CAUTION**(구와 동일 성격) |
| W5c | **V21-BAL** | `vv_balance.py` 90 run·105.9 s | G1 EV별 boardings **max/min 1.177**(한계 1.5, 최악 K100_4) · G2 북/남 **0.924~1.066**(밴드 0.8~1.25) | **PASS** |
| W5d | **V21-EVSEL** | `vv_evsel.py` 30행 | stale **52.95%**(rider 62.78 / ped 49.40), harm 상한 mean **28.81 s** · p95 79.07 · max 123.61. 절단 이벤트는 89행이 이미 걸러낸다 | **PASS** |
| W5e | **V21-DET/VAR** | `vv_variance.py` 180 run·230.3 s | **그룹 I 15/15 CI95 겹침**(§8.1). CI95 상대폭 t_e2e_mean **0.071~0.101%** · t_lobby 0.685~0.794% · w_ev **2.030~3.292%** | **PASS** |
| W6 | **V21-TIER** | `--tier {primary,extreme,all}` 3회 실행 | 행수 **20 / 8 / 28**, `--tier all`의 `tier` 열이 시나리오별 실제 티어(primary 20 + extreme 8), **보류 11개 0건 유입** | **PASS** |
| W6 | **V21-WIN** | `vv_window_bias.py` **축 재정의** 30 run·43.8 s | 아래 §8.3 | **PASS** |
| — | **V21-NEW/WARMUP** | `vv_warmup_bias.py` 112 run·171.9 s | 아래 §8.4 | **PASS** |
| — | **V21-NEW/WINCMP** | `vv_window_compare.py` 12 run·18.4 s | 아래 §8.5 | **PASS** |
| W7 | **V21-VISUAL** | `etc/checklist_visual_h0v2.md` **§6** | 기하 6항목 면제(R8은 기하 무변경) · 거동 2항목 + 신규 2항목을 **사용자가 K50_1에서 동적 관찰 → 전건 PASS**(2026-08-07 서명). 이상 관측 0건 | **PASS** |
| W8 | **V21-SNAP** | 동결 픽스처 7종 × 2회 재생성 + 구조 비교 | **7/7 — 2회 실행 상호 동일 · 디스크 동결본과도 동일**(volatile `runtime_wall_sec` 제외, NaN 동치). `baseline_h0_K50_1.json`은 static+legacy 픽스처라 delivery config에서 재생 불가 → 의도적 제외 | **PASS** |
| W8 | **V21-DOC** | grep 소탕 + 본 문서 §8 신설 + 8단계 문서 8종 | 아래 §8.7 | **PASS** |

**`cmp`/`md5sum` 금지는 여전히 유효하다** — `runtime_wall_sec`가 벽시계라 항상
"다르다"가 나온다(§3 ④). W8 구조 비교는 volatile 키 제외 + NaN 동치로 한다.

### 8.3 V21-WIN — 비교 축이 바뀌었다

구 축(`scenario_window` False ↔ True)은 **실행 불가**하다: delivery config에 명시적
`scenario_window=False`를 주면 ValueError로 거부된다(명시적 모순은 조용히 덮지 않는
설계). 새 축은 **`window_policy` legacy_margin ↔ delivery**다.

> ⚠️ **구 결론 "고정 점심창이 혼잡을 W_EV +37.8~53.3% 과소평가"는 폐기한다.**
> 그 문장은 폐기된 축(고정창 ↔ 데이터 유도창)에 대한 것이라 새 축으로 옮길 수 없다.

| 그룹 | 지표 | K50_1 | K200_1 | K300_4 | 판정 |
|---|---|---|---|---|---|
| I | T_e2e mean | +0.1% | +0.1% | −0.0% | 일치 |
| I | T_lobby mean | +0.7% | +1.0% | −0.2% | 일치 |
| I | W_EV mean | +4.3% | +4.2% | +0.6% | Welch \|t\| 0.16~0.68 → 일치 |
| II | ticks | **−40.1%** | **−36.6%** | **−29.2%** | 사전 선언대로 감소 |
| II | `utilization`(full) | +4.3% | +7.4% | +5.8% | 사전 선언대로 상승 |
| II | 보행자 생성 수 | −39.4% | −35.6% | −28.4% | run이 짧아진 만큼 |
| III | `utilization_orderspan` | +1.3% | +1.9% | +1.2% | Welch \|t\| 0.90~1.96 → 동일 |

**정직하게 남겨 두는 관찰 1건**: 그룹 III의 부호가 3 시나리오 전부 **양(+)**이다.
n=5에서는 \|t\| < 2라 통계적으로 분리되지 않지만, 우연이라기엔 부호가 일관된다.
30시드 그룹 I 판정(§8.1)이 W_EV에서 오히려 **음(−)의 Δ**를 주므로 계통 편향으로
보긴 어렵고, 시드 5개의 표본 효과로 판단한다. **논문에 `utilization_orderspan`의
정책 간 차이를 주장하지 말 것** — 이 표는 그 주장을 지지하지 않는다.

### 8.4 V21-NEW/WARMUP — 워밍업 600 s의 근거

`warmup_sec` ∈ {0, 300, 600, 900, 1800, 3600, 7200} × 8시드 × 2시나리오 = **112 run**.
delivery 정책에서는 꼬리가 주문 데이터에 고정되므로 **머리만 움직인다**(스크립트가
`ped_end` 불변을 매 실행 자체 검사: K100_1 52,100 s · K300_4 52,196 s 전 수준 동일).

| | head=0 | 300 | 600 | 900 | 1800 | 3600 | 7200 | max z |
|---|---|---|---|---|---|---|---|---|
| K100_1 W_EV (s) | 26.55 | 27.19 | 27.31 | 26.88 | 27.56 | 27.05 | 26.70 | 0.80 |
| K100_1 `util_delivery` | 0.840 | 0.850 | 0.856 | 0.850 | 0.844 | 0.845 | 0.846 | 1.73 |
| K300_4 W_EV (s) | 41.34 | 42.43 | 42.45 | 41.59 | 43.88 | 41.96 | 42.34 | **2.58** |
| K300_4 `util_delivery` | 0.902 | 0.900 | 0.901 | 0.897 | 0.899 | 0.898 | 0.898 | 0.49 |

**결론: 단조 추세 없음.** 최대 이탈은 K300_4 W_EV의 head=1800(z=2.58)인데 사다리
중간의 **비단조 융기**라 워밍업 효과가 아니라 시드 잡음이다(head=3600·7200에서 다시
내려온다). 배달 KPI는 head=0에서조차 나머지와 구별되지 않는다 — 주문 구간이 완화시간의
10배 이상이라 초기 200~300초가 평균에 묻히기 때문이다.

**A13 임계값의 사후 확인** (`util_at_first_order / utilization_delivery`):

| head (s) | 0 | 300 | 600 | 900 | 1800 | 3600 | 7200 |
|---|---|---|---|---|---|---|---|
| 비율(K100_1) | **0.0000** | 0.817 | 0.751 | 0.951 | 0.838 | 0.946 | 0.866 |
| 비율(K300_4) | **0.0000** | 0.773 | 0.714 | 0.901 | 0.786 | 0.889 | 0.816 |

냉각 건물은 **정확히 0.000**(보행자가 없으니 EV가 안 움직인다), 데워진 건물은 0.71~0.95.
`WARMUP_RATIO_FLOOR = 0.35`가 두 모집단 사이에 놓인다 — 거짓 FAIL 여지 없이 진짜 실패
(워밍업 누락·배경 스트림 정지)만 잡는다.

### 8.5 V21-NEW/WINCMP — 이용률 왜곡의 출처

같은 run 안에서 4개 창을 정확히 계산한다(종료를 앞당기는 것은 **엄격한 prefix**이므로
재시뮬레이션 없이 가능하다). legacy_margin 드레인올 팔, 4시나리오 × 3시드 = 12 run.

| 시나리오 | 꼬리 합계 | ped_end 가드 | `peds==0` | full | to_ped_end | to_rider_exit | delivery | orderspan |
|---|---|---|---|---|---|---|---|---|
| K50_1 | 1,254 s | 1,203 | **51** | 0.7748 | 0.7766 | 0.7785 | 0.8242 | 0.8253 |
| K100_1 | 792 s | 750 | **42** | 0.7973 | 0.7981 | 0.8036 | 0.8593 | 0.8603 |
| K200_1 | 1,025 s | 967 | **57** | 0.8256 | 0.8278 | 0.8344 | 0.9092 | 0.9088 |
| K300_4 | 160 s | 114 | **46** | 0.8406 | 0.8418 | 0.8413 | 0.9105 | 0.9120 |

**귀속(%p)**:

| 시나리오 | `peds==0` 조건 | ped_end 가드 | **워밍업 머리** | orderspan 잔차 |
|---|---|---|---|---|
| K50_1 | 0.182 | 0.192 | **4.566** | 0.116 |
| K100_1 | 0.082 | 0.543 | **5.574** | 0.103 |
| K200_1 | 0.220 | 0.652 | **7.486** | −0.041 |
| K300_4 | 0.121 | −0.054 | **6.920** | 0.145 |

**워밍업 머리가 4.6~7.5 %p로 지배적이고, 없애자고 했던 `peds==0` 조건은 0.08~0.22 %p뿐이다.**
그래서 R8은 "루프를 언제 멈추나"를 고치는 데 그치지 않고 **주 지표를 `utilization_delivery`로
승격**했다. orderspan 잔차가 ±0.15 %p인 것은 **올바른 값이 이미 `utilization_orderspan`으로
계산되고 있었고, 문제는 `utilization`이 주 지표 자리에 있었던 것**임을 뜻한다.

### 8.6 논문 재료 수치 (delivery 기준, 동결 픽스처)

| 픽스처 | ticks | `utilization`(진단) | **`utilization_delivery`(주 지표)** | `utilization_orderspan` | 재차 인원 4대 합 | 종료 시 건물 내 보행자 |
|---|---|---|---|---|---|---|
| K50_1 uniform | 6,318 | 0.8157 | **0.8339** | 0.8324 | 2.97 | 15 |
| K100_1 uniform | 6,965 | 0.8520 | **0.8718** | 0.8725 | 3.28 | 5 |
| K200_1 uniform | 6,857 | 0.8954 | **0.9196** | 0.9203 | 4.15 | 7 |
| K300_4 uniform | 7,678 | 0.8858 | **0.9065** | 0.9071 | 4.77 | 1 |
| K50_1 bottom_heavy | 6,327 | 0.8236 | **0.8426** | 0.8413 | 2.88 | 15 |
| K50_1 top_heavy | 6,311 | 0.8443 | **0.8655** | 0.8646 | 3.03 | 13 |
| K50_1 v5 매핑 | 6,393 | 0.8150 | **0.8329** | 0.8295 | 2.89 | 12 |

전 픽스처 `termination_reason == delivery_complete`, `delivered == K`.

**논문에 반드시 붙일 각주 4가지**

1. **`utilization`은 적재율이 아니다.** DOORS+MOVING+호출 있는 IDLE의 **시간 비율**이다.
   같은 run에서 평균 재차 인원은 **4대 합계 2.88~4.77명 / 정원 60석(15인승 × 4대) =
   4.8~8.0%**다. 시간가동률 85%를 적재율 85%로 읽으면 정반대 결론이 나온다.
   `mean_passengers_delivery`를 항상 병기할 것.
2. **주 지표는 `utilization_delivery`**(창 = [첫 주문, 마지막 라이더 퇴장]).
   `utilization`(전 구간)은 워밍업 머리를 분모에 포함하므로 **진단용으로 강등**했다.
   `run.py` 콘솔·`plot_baseline.py`·`visualize.py`·`h0_baseline_stats.py` 표시 경로는
   2026-08-06에 전환 완료(legacy 경로에서는 자동으로 full-window로 폴백).
3. **초반 10% 주문은 워밍업과 무관하게 낙관적이다.** head=7,200 s에서도 W_EV 17.0 vs
   전체 22.8이다. 초기화 편향이 아니라 **점심 피크 주문 램프**이며(§8.4가 head 무관함을
   보인다), 그래서 A13-④는 게이트가 아니라 정보행이다. "모델 아티팩트가 아니다"를
   본문에 써야 방어된다.
4. **보행자 KPI는 절단된다.** 종료 시점에 건물 안에 있던 보행자는 `ped_done_log`에
   들어가지 않아 `ev_wait_mean`이 미세하게 하향 편향된다. 규모는 위 표의
   `n_in_building_at_end`(1~15명, K50_1에서 15/808 = **1.9%**)이고 30/분 배경에서는
   ~60명이다. 보행자 대기를 인용하면 절단 편향을 명시할 것.

### 8.7 V21-DOC 소탕 결과

grep 대상: `A1~A12`(→A1~A14) · `437`(→440) · `utilization`(주 지표 강등) ·
`ped_end`(더는 종료 조건 아님) · "보행자 전원 완료"(계약 변경).

정정한 것은 **현재 상태를 단언하는 문장**뿐이다 — `plan_h0_revision.md` §9 ·
`plan_h0v2_verification.md` §12의 **날짜가 붙은 진행 로그 행은 그대로 둔다**.
그것들은 "그 시점에 그러했다"는 기록이고, 사후에 고치면 이력이 사라진다.

> ⚠️ **grep은 의미 반전을 못 잡는다**(V2-DOC 교훈). 서사 판정은 8단계 문서 개정이
> 담당했다 — 문서 8종의 개정 내역은 `etc/HANDOFF_v2.md` §4의 R8 행 참조.

### 8.8 V21 전체 판정

**게이트 15개 중 PASS 14 / CAUTION 1 / PENDING 0 — H0 v2.1 검증 완료**
(V21-VISUAL 사용자 육안 재서명 2026-08-07로 마지막 PENDING이 닫혔다).

- **CAUTION 1건 = W5b V21-FACE** — 성격이 v2와 동일하다(SLA 무판별: 위반 0/15,600,
  최소 여유 12.27분). 창 재정의와 무관하며 §4 ①의 결론이 그대로 유효하다.
- **W7 V21-VISUAL = PASS (2026-08-07 사용자 서명)** — 구 PENDING이 해소됐다. 판정
  원본은 `etc/checklist_visual_h0v2.md` §6. 기하 6항목은 면제(R8이 기하를 안
  건드렸다). 재관찰 4항목(ⓐ 종료 직후 화면 · ⓑ 배경 지속 생성 · ⓒ 논문 트랙 창 ·
  ⓓ FloorDemandPanel) 전건 기대 일치, K50_1 완주 관찰. K200_1은 선택 항목이라
  미실시 — 판정 무영향. 관찰에 쓰인 앱은 같은 날 `simulation/app.py`의 모델 생성을
  세션별로 바꾼 판본이며, 렌더러·모델 로직은 무변경이라 기하·거동 판정에 영향이 없다.
- **모델 결함 0건.** R8 전 구간에서 코드가 잡아낸 진짜 결함은 R8-c의 A6/A11 정책
  무지 1건뿐이고, 그것도 게이트 결함이지 모델 결함이 아니다.
