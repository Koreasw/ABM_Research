# 작업 인수인계 v2 (HANDOFF_v2.md)

작성: 2026-08-04. **이 문서가 현행 인계 정본이다.** 구 `etc/HANDOFF.md`는 2026-08-03
시점(리포 RED 상태)에서 출발한 판본이라 상태 기술이 낡았다 — 이력으로만 참고할 것.

**목적 2가지**: ①지금까지 무엇이 끝났고 어떤 규약이 확정됐는지 ②남은 단계마다
**무엇을 새로 구현해야 하는지**를 파일 단위로 지정한다.

---

## §0. 30초 요약

| | |
|---|---|
| 리포 상태 | **green — 440 passed / 3 skipped / 0 failed** (R8-e 재동결 후) |
| 구현 | H0 v2 개정 **R0~R7 완료** (4EV·1,200㎡·지하 2개층·로봇 1F 충전·**사무실 [2,7,12,22,27,32]**) |
| 검증 | **W1~W8(v2) 완료 + V21 재검증(v2.1) 완료** — V21 게이트 15개 중 **PASS 14 / CAUTION 1 / PENDING 0**(2026-08-07 육안 재서명 완료로 마감). 집계: `etc/verification_report_h0v2.md` **§8이 인용 정본**(§0~§7은 legacy 창 시절 기록) |
| 다음 | ~~V2-VISUAL 서명 · 문서 개정 ⓐ·ⓑ~~ **✅** → **R8 창·종료 재정의 0~8단계 ✅ 완료**(2026-08-06) → **▶ Phase A 착수** (`plan_hr_extension.md` R1a = `scie_phase/phase_A_robot_h1.md` Step A1) |
| 미결 결정 | **1건** — H3의 `delivered` 정의(사물함 투입 권장 vs 고객 수령). Phase D까지 이월 가능 |
| **대기 중 사용자 액션** | **없음.** V21-W7 육안 재서명 4항목이 **2026-08-07 PASS로 완료**됐다(`etc/checklist_visual_h0v2.md` **§6**) — 논문 V&V 절의 마지막 빈칸이 채워졌다 |
| 모델 정책 | **Fable 미사용** — 판단 구간은 오퍼스 `max` |
| git | **미사용** (커밋·태그 금지, 사용자 지시) |

**정본 문서 4종** (`etc/`, 이 순서로 읽을 것):
1. `plan_h0_revision.md` — 개정 계획서 (§1 설계 · §3 R0~R6 · §9 진행 로그)
2. `plan_h0v2_verification.md` — 검증 계획서 (§3 L1~L7 · §4 W1~W8 · §8 진행 로그)
3. **`plan_h0v21_window.md`** — **R8 창·종료 재정의 계획서** (§1 실측 근거 · §2 설계 ·
   §7 재검증 배터리 · §8 모델·effort 배정 · §11 진행 로그). **창·종료 규약의 정본**
4. `HANDOFF_r8_step78.md` — R8 7·8단계 실행 지시서. **2026-08-06 전 항목 완료** —
   이력으로만 참고할 것(§3.8이 그 결과를 규약으로 승격했다)
5. `research_plan_scie.md` — 상위 연구계획서 (4-모드 H0~H3, Phase A~F, 결정 #1~#25)

⚠️ **R8 이후 H0 v2 수치는 코드로 재생성되지 않는다** — 워밍업 길이가 바뀌면 보행자
RNG 정렬이 달라져 같은 시드라도 결과가 달라지기 때문이다. v2 결과의 유일한 기록은
`archive/h0_v2_frozen/`(읽기 전용, MANIFEST 참조).

---

## §1. 이 프로젝트

스마트 빌딩 로비 핸드오프 **4-모드(H0~H3) ABM**으로 로봇 배달 vs 사람 배달을
비교하는 SCIE 논문 연구 (target: *Simulation Modelling Practice and Theory*).
지금은 **H0(라이더 직접 배달, 로봇 없음) 베이스라인의 v2 개정을 끝내고 검증
배터리를 절반쯤 돌린** 상태다. H0 v2 검증이 끝나야 Phase A(로봇+H1)에 착수한다.

건물: **지하 2층 + 지상 10층**, 층당 ~1,200㎡, 34 m 중복도, 12실/층(복도 **2·7·12·22·27·32 m**, 12~22 m는 EV 서비스 코어), 상주 100명/층
(900명), **EV 4대 교차배치**(북 EV1 전용+EV3 공용 / 남 EV2 전용+EV4 공용, 전 대수
B2~10F 운행), 보행자 7.5명/분.

---

## §2. 완료된 것

### 2.1 H0 v2 개정 (R0~R6)

| Step | 내용 |
|---|---|
| R0 | v1 동결·아카이브 (`archive/h0_v1/` — tar.gz 스냅샷 + 문서 이동. **git 미사용이라 이게 v1의 유일한 기록**) |
| R1 | `space.py` 전면 재작성 — 34 m 복도, EV 4대 교차배치, (pos,side) 중복 검사 |
| R2 | `model.py` N-EV 일반화 — EV 대수 하드코딩 제거, KPI 리포터 동적 생성 |
| R3 | 로봇 충전을 1F 로비존과 통합(대기＝충전, opportunistic). `RobotState.CHARGING` 제거 |
| R4 | 시각화 v2 — 4샤프트 비겹침, `building_10f_layout.html` 재생성, 체크리스트 |
| R5 | 수요 시나리오 티어링 (`configs/scenario_tiers.yaml` + `analysis/scenario_tiers.py`) |
| **R6** | **지하 2개층(B1·B2) 신설** — 아래 §3.1 참조 |
| **R7** | **사무실 재배치 [4,9,14,19,24,29] → [2,7,12,22,27,32]** + 미터/격자 혼용 결함 수정 — 아래 §3.7 참조 |

### 2.2 검증 (W1~W3)

| Stage | 산출물 | 결과 |
|---|---|---|
| **W1 V2-AUD** | `verify_h0.py` A1~A9 → **A1~A12** + `model._audit_invariants()` 확장 (**R8에서 A13·A14 추가 → 현재 A1~A14**, §3.8) | 코퍼스 표본 15 run 전건 PASS |
| **W2 V2-GP** | `tests/test_vv_golden_path_v2.py` 신규 9건 (설계 사양 손계산 절대값) | 뮤테이션 감도 확인 완료 |
| **W3 V2-ALL28** | `results/vv/all39_battery.csv` (112행) | **배터리 84/84 + 감사 28/28 PASS** |
| **W4a V2-EXT** | `tests/test_vv_extreme.py` 12건 → **15건** (EV 1대 축퇴 + 30/min 러시 ×2 seed) | 뮤테이션 2건 적발 확인 |
| **W4b V2-MONO** | `results/vv/monotonicity.csv` (10행, 130 run·169.5 s) | **6방향 전건 PASS**, 코드 수정 0 |
| **W5a V2-DECOMP** | `decomp_by_k.csv` + PNG 2종 | 주문 단위 잔차 **3.6e-12 s** |
| **W5b V2-FACE** | CSV 4종 + 히스토그램 (84 run·15,600 주문) | stairs PASS · slope CAUTION · **slack CAUTION(위반 0/15,600)** · tlobby PASS |
| **W5c V2-BAL** | **`analysis/vv_balance.py` 신규** + `ev_balance.csv` (90행) | **G1 1.125 / G2 0.951~1.062 → PASS**, dispatch 수정 불요 |
| **W5d V2-EVSEL** | `evsel_stale.csv` (30행) | stale **51.8%** · harm 상한 평균 **25.09 s** (v1의 2배·4배) |
| **W5e V2-DET/VAR** | `variance_30seed.csv`·`variance_summary.csv` | DET 7 passed · 30-seed CI95 평균계 ≤1% |
| **W6 V2-TIER/WIN** | `window_bias.csv` + 티어 3종 실행 검증 | 보류 11개 **0건 유입** · 창 편향 W_EV +38~53% |
| **W7 V2-CMP** | **`analysis/h0_insights/note_v1_v2_comparison.md` 신규** | 리스크 3 **미발현** · 로봇 T_e2e 단축 상한 **11.6~13.0%** |
| **W7 V2-VISUAL** | `results/figures/h0v2_cross_*.png` 2종 + `checklist_visual_h0v2.md` §5 | 기하 6항목 선판정 일치 · 거동 8항목 사용자 동적 관찰 → **전건 PASS(2026-08-04 서명)** |
| **W8** | **`etc/verification_report_h0v2.md` 신규** | 스냅샷 4종 무변화 · grep 6곳 정정 · **모델 결함 0건** |

### 2.3 사용자 확정 결정 (재론 불필요)

| 날짜 | 결정 |
|---|---|
| 08-03 | EV 4대 교차배치, 공용은 EV3·EV4 (`shared_ev_ids`로 선언적 변경 가능) |
| 08-03 | 건물 확장: 1,200㎡ · 100명/층 · 보행자 7.5명/분 · 복도 34 m |
| 08-03 | 로봇 충전 B1 → **1F 로비존 통합**, 대기 중 수시 충전 |
| 08-03 | **K500·K750·K1000 미사용** → 코퍼스 28개 |
| 08-03 | **Fable 전면 미사용** (크레딧 0) → 구 Fable 배정 구간은 오퍼스 `max` |
| 08-03 | **지하 2개층 신설** — 사람 승하차 전용, EV 이용률 변화 목적 |
| 08-03 | 보행자 지상 종점 **1F 0.50 / B1 0.30 / B2 0.20**, 총량 7.5명/분 **재분배** |
| 08-04 | K500+ 지위 = **"영구 제외"가 아니라 "본 실험에서 우선 보류"** |
| 08-04 | 라이더 배정 인용 모집단 **38 → 28개 재산출** |

---

## §3. 이어받는 사람이 반드시 알아야 할 규약 8가지

여기를 건너뛰면 **정상 동작을 결함으로 판정하거나, 결함을 정상으로 통과시킨다.**

### 3.1 층 rank 규약 (§1.6) — 가장 사고 나기 쉬운 곳

층 라벨에 **0이 없다**(B2=−2, B1=−1, 1F=1). 그래서 `|라벨 차|`가 물리적 층수와
어긋난다 — 1F↔B1은 라벨 차 2지만 실제 1개층이다.

```python
space.floor_rank(f) = f if f >= 1 else f + 1     # B2=-1, B1=0, 1F=1
```

- **거리·보간에는 반드시 rank**, 순서 비교는 라벨로 해도 된다(rank가 라벨에 대해
  순증가라 비교 결과가 같다).
- 적용 지점 5곳: `elevator._decide_next`(최근접 정차), `elevator.step`
  (`position_floor` 보간), `control_system._estimate_wait`,
  `model._evsel_on_register`, `elevator_physics.floor_height_between`.
- **`position_floor`(KPI `ev{i}_floor`, 시각화 y축)의 단위가 rank다.** 지상층은
  rank == 라벨이라 기존 값이 하나도 안 변했고, 지하일 때만 0/−1이 나온다.

### 3.2 지하층의 성격

**사람 승하차 전용**이다. 사무실·복도 노드 0개, `floor_center` 1 + EV 정차 4개뿐.
**로봇은 지하에 안 간다** — 대기＝충전은 1F 로비존(§1.3)이고, §1.6이 그걸 바꾸지
않았다. 개정계획 §1.3의 "B1 전면 삭제"는 *로봇 충전용* B1을 지운 것이고 §1.6이
만든 건 *사람 전용* B1·B2다. 두 절이 모순처럼 보이면 **§1.6이 기준**.

### 3.3 A10 불변식은 반전됐다

구 A10 = "지하층 부재(floor ≤ 0이 0건, `ev{i}_floor` ≥ 1.0)". 지금은:

- **A10-1** 지하 구조 정합 (사무실·복도 0개)
- **A10-2** 라이더·로봇 지하 미진입 (주문 floor ≤ 0이 0건)
- **A10-3** EV 운행범위 ⊆ [1−n_basements, n_floors] (**rank 단위**)

**구 문구를 그대로 구현하면 정상 동작을 결함으로 판정한다.**

### 3.4 A12는 항상 SKIPPED로 보고된다

결과 JSON은 큐 **길이**만 기록해서 "두 카에 각 1명"과 "1명이 2중 등록"이
구분되지 않는다. 실제 게이트는 `model._audit_invariants()`의 틱 단위 assert이므로
**`--audit` 없이 돈 리포트를 A12 통과로 읽으면 안 된다.** 조용히 PASS시키지 않고
SKIP으로 남긴 이유가 이것이다. 배터리는 감사 스윕(seed 42, 28 run)으로 메운다.

### 3.5 골든패스 테스트는 2개이고 둘 다 필요하다

- `test_vv_golden_path.py` — 기대값을 **그래프에서 유도**. 타이밍 결함을 잡는다.
- `test_vv_golden_path_v2.py` — 설계 사양 **손계산 절대값 상수**. *잘못 지어진
  건물*을 잡는다.

그래프에서 유도하면 건물이 틀려도 기대값이 같이 틀려서 통과한다. **v2의 상수를
그래프 조회로 바꾸는 순간 그 모듈은 존재 이유를 잃는다.**

### 3.6 하위호환 잠금 3종 — 지우지 말 것

- `configs/regression_nobasement_10f.yaml` (동결 회귀 경로, `n_basements: 0`)
- `results/pre_basement/*.json` (지하 도입 **이전** 골든 4종)
- `tests/test_h0_frozen_snapshot.py::test_nobasement_replay_matches_pre_basement_snapshot`

**왜 중요한가**: 지하 신설은 rank 리팩터로 EV 배차·대기추정·위치 시계열을 전부
건드렸다. `results/baseline_h0_*`(현행)은 **의도적으로 재동결**됐으므로 "결과가
바뀌었다"를 못 잡는다. 지하를 끈 경로가 옛 스냅샷과 비트 동일하다는 사실만이
**"건물이 바뀐 것이지 모델이 바뀐 게 아니다"**를 증명한다. 그래서
`model._draw_ground_floor()`는 종점이 1F뿐이면 **RNG를 소비하지 않는다** — 이
설계를 깨면 저 테스트는 영구히 통과 불가가 된다.

부수 규약: **`n_basements` 기본값은 0**이다(`build_from_config`·`model` 양쪽).
config는 한 run의 건물을 완전히 기술하는 문서이므로, 키를 언급하지 않은 파일이
층을 얻어서는 안 된다. `build_building_graph()` 시그니처 기본값만 2다("현재 건물").

### 3.7 복도 위치는 미터이고, 격자 위에만 놓을 수 있다 (R7, 2026-08-04)

`office_positions_m` = **[2, 7, 12, 22, 27, 32]** (×2, 북·남 거울). 두 겹 대칭이다:
북/남이 서로 마주보고, 여섯 위치가 **복도 중점 17.0 m 기준 거울 대칭**이다
(2+32 = 7+27 = 12+22 = 34). **12~22 m는 비워 둔 EV 서비스 코어**로, 뱅크가 16·18에
있다. 구 배치 [4,9,14,19,24,29]는 16.5 대칭이라 중점과 어긋났고 사무실이 EV 도어에서
1~2 m였다(샤프트가 사무실 안).

**여기서 가장 사고 나기 쉬운 것**: 복도는 `corridor_resolution_m`(기본 1 m) 간격의
**이산 노드 사슬**(`floor_{f}_corr_{i}`)이고, `i`는 **인덱스이지 미터가 아니다.**
R7 이전에는 미터 값을 노드 이름에 그대로 넣어서 1 m 격자·정수에서만 우연히 맞았다.
그래서 `2.5` 같은 값을 주면 **예외 없이 빌드되고**, `add_edge`가 유령 노드
`corr_2.5`를 만들어 **사무실이 복도에서 고립**되고 주문이 전부 배달 불가가 됐다.
지금은 `build_building_graph`의 `grid_index()`가 미터→인덱스를 명시 변환하고
**범위(미터)·격자 정합을 빌드 시점에 거부**한다. 반미터 배치를 하려면
`corridor_resolution_m`을 먼저 낮춰야 한다.

`corridor_mid_pos`(그래프 키)는 **인덱스**다 — 미터로 읽지 말 것.

### 3.8 창(window)·종료(termination) 규약 (R8, 2026-08-06) — **정책이 둘이다**

`simulation.window_policy` config 키가 **두 개의 서로 다른 계약**을 가른다.
키가 **없으면 `legacy_margin`** — 즉 R8 이전 동작이 코드 기본값으로 보존된다.

| | `legacy_margin` (기본값·구 동작) | `delivery` (`configs/baseline_10f.yaml`) |
|---|---|---|
| clock_start | `min(ORD) − window_margin_sec` (3,600 s) | **`min(ORD) − warmup_sec` (600 s)** |
| 보행자 생성 종료 | `ped_end = max(ORD) + margin` | **컷오프 없음** (`ped_end = cap`) |
| cap | `ped_end + max_overrun` | **`max(ORD) + max_overrun`** (7,200 s 필수) |
| 종료 | drain-all (전 주문 배달 **+ 건물 내 보행자 0**) | **전 주문 배달 + 라이더 전원 건물 밖** |
| `termination_reason` | `drain_all` | `delivery_complete` (`cap`이면 결함) |

**어느 config가 어느 정책인지**: `baseline_10f.yaml` = delivery(논문 트랙) /
`regression_nobasement_10f.yaml` = **legacy_margin — 한 글자도 건드리지 말 것**
(§3.6의 `pre_basement` 잠금이 이 경로로 재현된다).

#### 사고 나기 쉬운 5가지

1. **구·신 비트 동일성 비교는 원리적으로 불가능하다.** 워밍업 길이가 바뀌면
   `ped_rng`(seed+1)의 틱 정렬이 달라져 **같은 시드도 다른 보행자 실현**을 낳는다.
   비교는 **30시드 CI**로만 한다(`experiments/vv_variance.py`, 판정 결과는
   `verification_report_h0v2.md` §8.1).
2. **종료 시점에 건물이 비어 있지 않은 것이 정상이다.** 배경 보행자 1~15명과
   EV 승객이 남는다(`n_in_building_at_end`). 그래서 R8-d에서 **"완료" 단언을
   "보존" 단언으로** 바꿨다 — `boards == alights` → `boards − alights == 종료 시점
   탑승 인원`. 두 진술은 drain_all에서 **동치**이므로 legacy 경로는 무영향이다.
3. **`scenario_window`는 `legacy_margin` 전용 스위치다.** 기본값이 센티널
   `None`(정책이 결정)이고, delivery config에 **명시적** `False`를 주면 ValueError다.
   가드를 명시적 모순에만 건 이유: 기본값 `False`에 의존하던 호출부가 35곳이라
   무조건 raise 하면 56건이 죽는다.
4. **주 지표는 `utilization`이 아니라 `utilization_delivery`다.** 전자는 워밍업
   머리를 분모에 넣어 4.6~7.5 %p 낮게 나온다(§8.5 귀속표). 표시 경로
   (`run.py`·`plot_baseline.py`·`visualize.py`·`h0_baseline_stats.py`)는
   2026-08-06 전환 완료 — legacy 경로에서는 자동으로 full-window로 폴백한다.
   그리고 **시간가동률은 적재율이 아니다**(재차 인원 4대 합 2.9~4.8명 / 정원 60석).
5. **60명/분 배경은 이제 종료하지 않는다.** 컷오프를 없앤 결과 **EV 용량을 넘는
   부하는 영원히 배출되지 않는다**(건물 내 보행자 3,614 → 10,072명 발산, overrun
   7,200·28,800 s 양쪽 cap 트립). 그래서 극단 테스트의 무거운 팔이 **30/분**
   (`SATURATING_PED_RATE`)이다. 이건 결함이 아니라 **모델의 적용 범위**이고,
   논문 한계 절에 써야 한다(결정 #25).

**게이트는 A1~A12 → A1~A14**로 늘었다. 신설 **A13**(warm-up adequacy, 임계
`WARMUP_RATIO_FLOOR = 0.35` — 분포로 확정, 평균으로 잡으면 거짓 FAIL) ·
**A14**(termination reason). 기존 **A1·A6·A8·A11은 정책 분기**를 갖는다.

---

## §4. 남은 단계별 필요한 추가 구현

각 항목: **이미 있는 것 / 새로 만들 것 / 합격 기준**. 배정은 검증계획서 §5.

### ~~W4a — V2-EXT~~ ✅ **완료 2026-08-04**

`tests/test_vv_extreme.py` **12건 → 15건**. 신규 2케이스(계획대로 코드 수정 0건):

1. **`test_extreme_single_ev_fleet`** — EV 1대 축퇴. 차를 이름 짓는 **전 계층**을
   정확 집합으로 잠갔다(`graph["ev_ids"]` / `model.elevators` / `kpi_summary`
   키 / **`model_vars`의 `ev\d+_` 계열**). 마지막 항목이 핵심이다 — v1 잔재
   `ev2_*`가 새면 KPI 키 개수 검사는 통과하지만 이건 적발한다.
   실측: 완주 50/50, EV1 util 0.999, W_EV 90.8 s, A1~A12 PASS.
2. **`test_extreme_pedestrian_rush_saturation`** (seed 42·7) — 보행자 30/min,
   K200_1. 4대 전부 util **0.996~0.999**(기준선 0.817~0.878), W_EV **84.70 s
   vs 36.11 s**, 완주 200/200, A1~A12 PASS.

**드레인 예산 — 구 판본의 ≥600 s 안내는 근거가 아니라 짐작이었다.** 실측하니
overrun **150 s→cap, 180 s→완주**이고, 라이더는 `ped_end`보다 **726 s 먼저**
끝난다. 즉 cap을 트립시키는 건 배달이 아니라 **배경 보행자 배출**이다. 상수는
실측 180 s의 ×5인 **900 s**(`RUSH_OVERRUN_SEC`)로 고정했다.

### ~~W4b — V2-MONO~~ ✅ **완료 2026-08-04**

`results/vv/monotonicity.csv` 재생성(10행, 130 run, **169.5 s**). **6방향 전건
PASS**, 코드 수정 0건. dir6 재산출값 = W_EV **22.11 → 34.72 → 41.74**
(K50_1→K200_1→K300_4). dir5의 fallback 감소(21.0→14.9)는 `gate=False` 정보행이며
모듈 독스트링이 예고한 기지 현상이 v2에서도 재현된 것 — **결함 아님**.

### ~~W5 — 분석 5종~~ ✅ **완료 2026-08-04**

수치·판정은 검증계획서 §8의 W5a~W5e 행이 정본이다. **다음 단계에서 반드시 들고
갈 결론 4가지**만 여기 남긴다.

1. **`rider_wait`가 코퍼스 전 구간에서 정확히 0이다** (W5a). 시나리오 자체 재고에서
   동적 라이더 풀이 **한 번도 병목이 아니다** — 논문에서 풀을 제약으로 서술하면 안 된다.
2. **SLA는 v2 코퍼스에서 판별력이 없다** (W5b). 위반 **0/15,600**, 최소 slack
   12.58분. v1의 CAUTION은 위반 14건이 전부 K1000이었는데 그 티어가 코퍼스 밖이라
   **v2에서는 오히려 더 강한 결론**이 됐다. `deadline` 강화나 부하 상향 없이는
   SLA·S_customer로 H0 구성을 구분할 수 없다.
3. **EV 균형은 통과했지만 타이브레이크 쏠림은 실재한다** (W5c). 코퍼스에서는
   max/min 1.125(한계 1.5)로 여유 통과 → **dispatch 수정 불요**. 그러나 배경교통이
   0인 저부하에서는 **EV3·EV4 승차가 정확히 0건**이다(동점이 항상 ev_id 오름차순).
   로봇 공용차가 하필 EV3·EV4라 **Phase A의 저부하 감도 케이스에서 로봇 이득이
   과대평가될 수 있다** — 유효성 위협으로 등재됨.
4. **분산 구조** (W5e). 평균계 KPI는 30 seed에서 CI95 ≤1%, **`floor_seed` 고정
   CRN의 이득은 시나리오별로 확인해야 한다** — 채널비가 평균계 0.394~1.217,
   p95 0.995~1.779로 흩어져 **대부분 1.0과 통계적으로 구별되지 않는다**(n=30에서
   분산비는 F(29,29), 95% 범위 ≈ [0.48, 2.09]). 명확히 감소한 것은 K300_4뿐.
   구 판본의 "분산 30~65% 제거"는 **철회**됐다(2026-08-04 재측정). Phase E는
   "CRN이 이득을 준다"가 아니라 "이득 여부를 먼저 확인한다"를 전제로 할 것.

부수 코드 변경 2건(둘 다 v1 잔재 제거): `vv_face.py`의 slack 판정문을 측정값
파생으로 교체, T_lobby 게이트를 **v1의 4.1분 절대 앵커 → K 방향 게이트**로 교체.
`analysis/vv_balance.py` 신규 + `CORPUS_SCRIPTS` 가드 등재.

### W6 — V2-TIER · V2-WIN · 소넷 low~medium

**있는 것**: `tests/test_scenario_tiers.py` 23건, `experiments/vv_window_bias.py`.
**새로 만들 것**: **없음.** 다만 `--tier primary/extreme/all` 각각을 **실제로
실행**해 산출 CSV의 `tier` 열·행수(20/8/28)와 **보류 11개가 어떤 경로로도 산출물에
안 들어옴**을 확인하는 절차가 필요하다(테스트는 소스 레벨 가드만 본다).

### ~~W6~~ ✅ **완료 2026-08-04**

`--tier {extreme,all,primary}`를 실제로 3회 돌려 8/28/20행·`tier` 열·**보류 11개
0건 유입**을 확인했고, `--tier excluded`가 argparse에서 거부됨까지 반증 시도로
확인했다. **유의점**: `--tier all`이어도 `tier` 열에는 문자열 `all`이 아니라
시나리오별 실제 티어가 찍힌다 — `all`을 기대하면 오판한다.
V2-WIN은 구 고정 창이 혼잡을 **과소평가**함을 확정(W_EV +37.8~53.3%).

### ~~W7~~ — V2-CMP ✅ / **V2-VISUAL ✅ PASS (2026-08-04 사용자 서명)**

**V2-CMP 완료**: `analysis/h0_insights/note_v1_v2_comparison.md`.
리스크 3은 **우려한 형태로 미발현**(시나리오 간 CV 불변~확대). 대신 **더 중요한
제약 발견 — 로봇의 T_e2e 단축 상한이 11.6~13.0%**다(cook 64~68% + street 19~24%가
건물 무관). 상세는 그 문서와 검증보고서 §4 ②.

**V2-VISUAL — 완료. 이것으로 H0 v2 검증 배터리가 전부 닫혔다.**

- 세션이 §3 기하 6항목을 정적 렌더 2종(`results/figures/h0v2_cross_{K50_1,
  K200_1_rush}.png`)으로 선판정해 **전건 기대 일치**를 확인했고,
- **사용자가 앱에서 §4 거동 8항목을 K50_1·K200_1 각 1회 동적 관찰 → 전건 PASS**
  (2026-08-04 서명). 이상 거동·결함 관측 **0건**. K1000_1은 선택 항목이자 보류
  티어라 미실시 — 판정에 영향 없음.
- **판정 원본 = `etc/checklist_visual_h0v2.md` §5**(실행 메타데이터 · 항목별 표 ·
  종합 판정 서명). 검증보고서 §1·§2 W7 행·§5 목록에 반영 완료.

### ~~W8~~ ✅ **완료 2026-08-04**

1. **V2-SNAP**: 4종 × 2회 재생성이 상호·동결본과 전부 동일 → **재동결 불필요**.
   ⚠️ **`cmp`/`md5sum`으로 확인하지 말 것** — `runtime_wall_sec`(벽시계 계측) 때문에
   "다르다"고 나온다. volatile 키 제외 + NaN 동치 처리한 **구조 비교**가 옳다.
2. **V2-DOC**: 6곳 정정 완료(§3 ⑤ of 검증보고서). `building_10f_layout.html`의
   "지하층 없음"은 `nBasements == 0` 분기 폴백이라 **오탐**.
3. **`etc/verification_report_h0v2.md` 작성 완료** — 논문 §7.1의 재료.

### ~~문서 개정 ⓐ~~ ✅ **완료 2026-08-04** (오퍼스/max)

`research_plan_scie.md` + `etc/scie_phase/phase_A_robot_h1.md` 개정 완료. 전체
스위트 **437 passed / 3 skipped** 재확인.

**한 것**:
- **결정 #16~#22 등재**(`research_plan_scie.md` §1) — 빌딩 규모 / EV 4대 교차배치 /
  지하 2개층 / 로봇 충전 1F 통합 / 보행자 7.5·종점 재분배 / 코퍼스 28개 / Fable 미사용.
  동시에 **v1 계승 규약 5건의 지위를 재판정**해 표로 명시(#2·#4후단·#5 폐기, #3 moot).
- **phase_A 침묵 오류 3건 정정**:
  ① `model.elevators[1]` → **`[ev for ev in model.elevators if ev.shared_with_robot]`**
     (이미 있는 배선. `ElevatorAgent(shared_with_robot=…)`, `model.py` 329~336행).
     **공용이 2대라 "어느 카를 고를지" 규칙이 새로 필요하다** — 구판(공용 1대 전제)에
     없던 결정이라 기본 규칙(휴리스틱 유지 + 후보를 공용 2대로 제한)을 명시해 뒀다.
  ② §0 진단 기준선 표 → **오라클 무효 배너 + "v2 재판정" 열 신설**. 표를 지우지 않은
     이유는 정성 예측이 살아 있어서다. 절대값은 전부 인용 금지 표시.
  ③ "EV 무릎" **재판정 = "약화됐으나 유효"**. 가동률 **0.773(K50) → 0.835(K300)**,
     완화 폭 **−15.2% → −10.5%**(⚠️ 이 문서 구판이 적어 둔 −15.1%/−10.4%는 오기 —
     정본은 `note_v1_v2_comparison.md` §② 표).
- **연쇄 정정**(구판 인계 메모가 3건으로 잡았으나 실제로는 더 많았다): 배터리 38×3 →
  **28×3**, design matrix 3,960 → **3,360 run**, 30-seed CI 근거 **v2 재측정값으로 교체**,
  프로파일 축 대표 K {100,300,500} → **{100,200,300}**, A-게이트 A1~A9 → **A1~A12**,
  테스트 368 → **437**, W_EV "EV1/EV2 분리" → **전용/공용 분리**, Fable 리뷰 배정 →
  **오퍼스 max**, `configs/scenario_tiers.yaml` 주석의 주문률(구 800명 분모) 정정.
- **v2 판별력 한계 4건**을 `research_plan_scie.md` §7에 상설 배너로 이식
  (rider_wait≡0 · SLA 무판별 · 저부하 타이브레이크 쏠림 · T_e2e 단축 상한 11.6~13.0%).

**ⓐ 수행 중 새로 드러난 것**: A5의 **deny 상한 캘리브레이션 절차가 바뀌어야 한다**.
구 절차는 v1 진단의 노출 분포(K500 2.0% / K1000 13.9%)를 상한 근거로 삼았는데 그
티어가 코퍼스 밖이라 **근거가 통째로 사라졌다**. 대신 A1에서 H0 v2 코퍼스의 "공용 EV
사람 ≥12명 tick 비율"을 먼저 재측정하도록 절차를 고쳐 뒀다(H0 모델만으로 가능).
연관해서 **저부하 사각지대가 v1보다 넓어졌다** — K500+가 빠져 배터리가 정원 잠식
경로를 아예 못 밟을 수 있으므로, A1의 인위적 만차 단위 테스트가 유일 실행 경로일 수
있다. 대안은 보행자 30/분 러시(W4a 실측 포화).

### ~~문서 개정 ⓑ~~ ✅ **완료 2026-08-04** (오퍼스/high)

대상 9종: `scie_phase/README` + `phase_B~F` 5종 + `plan_hr_extension.md` +
`proposal_hr_extension.md`. 편집 후 스위트 **437 passed / 3 skipped** 재확인.

**전 문서 공통 정정**: 배터리 38×3 → **28×3(84 run)** · 본문 스윕 3,960 → **3,360** ·
프로파일/대조 격자 K{100,300,500} → **{100,200,300}** · 공용 EV = **EV3·EV4** ·
Fable 배정 → **오퍼스**(D·E는 정책 배너 자체가 없어 신설).

**ⓑ에서 새로 드러난 것 — ⓐ 시점에 몰랐던 3건**:

1. **🔴 진단 산출물 경로가 통째로 깨져 있었다.** 5개 문서가
   `analysis/h0_insights/note_h0_demand_insights.md`·`tables/*.csv`를 정본으로
   가리키는데, **R0 아카이브 때 이동**해 그 경로에 없다(현 위치
   `archive/h0_v1/analysis_outputs/h0_insights/`). 현 `analysis/h0_insights/`에는
   W7의 `note_v1_v2_comparison.md` **하나뿐**이다. 전 문서 경로 정정 + 읽기 전용 표기.
2. **`plan_hr_extension.md`의 코드 위치가 대부분 이동해 있었다** — 전량 재검증:
   `model.py` 모드 raise 109-112 → **114-117**, audit assert 526-529 → **541-571**
   (정원 assert 569), `elevator.py` 보딩 루프 139-170 → **146-173**,
   `control_system.py` 훅 50-52 → **54-56**, `test_agents.py` 51-54 → **55-58**.
   **이동 안 한 것도 확인**했다(`walker.py:51-133`, `elevator.py:13-17`,
   `kpi.py:146-154`) — 표기에 "위치 불변 확인"을 남겼다.
3. **Phase B의 burst 표본 권고가 실행 불가였다.** "고 Ca² 시나리오(예: **K1000_1**)를
   반드시 포함"인데 그 티어가 코퍼스 밖이다. v2 대체 표본 = **K200_9**(원시 CV² 2.26,
   코퍼스 최대). 단 Allen–Cunneen에 들어가는 것은 *건물 도착* Ca²이고 **그 값은 아직
   v2로 재산출되지 않았다** — B5 착수 시 최우선 재측정 항목으로 등재했다.

**연쇄로 손본 서사 3건**: ①Phase D의 **K 3구간 서사**(K≤200 / K300~500 / K1000)는
상단 2/3가 코퍼스 밖이라 **폐기하고 v2 실측으로 다시 긋도록** 지시 — 대안 축은
가동률 곡선 또는 배경교통. ②**부록 스트레스 트랙(D2) 보류** — 대신 한계 거동은
**보행자 30/분 러시**로 탐침(W4a 실측 포화). ③Phase E·F에 **CRN 이득 전제 철회**와
**T_e2e 단축 상한 11.6~13.0%** 를 리스크/한계 항목으로 등재.

### ~~R8 — 창·종료 재정의~~ ✅ **완료 2026-08-06** (세션 오퍼스)

정본 계획서 `etc/plan_h0v21_window.md`(§11 진행 로그에 R8-0~g 단계별 기록),
실행 지시서 `etc/HANDOFF_r8_step78.md`. 규약 요약은 **§3.8**.

| 단계 | 내용 | 게이트 |
|---|---|---|
| R8-0~g | 창·종료 스위치 · KPI 가산 17종 · 게이트 A13/A14 · 테스트 개정 · 정책 전환 · 재동결 · 수요 프로파일 가시성 | **440 passed / 3 skipped** · `pre_basement` 2건 green 유지 |
| **7단계 V21 재검증** | 배터리 전건 재실행 + 구·신 대조 | **그룹 I CI95 15/15 겹침**(30시드) · `delivered` 112/112 run 일치 · A1~A14 전건 PASS · 배터리 84/84 + 감사 28/28 · 단조성 6/6 · 균형 max/min 1.177 · 잔차 3.638e-12 · 동결 픽스처 7/7 구조 동일 |
| **8단계 문서 개정** | 이 문서 §0·§3.8·§4·§6, `verification_report_h0v2.md` **§8 신설**, `checklist_visual_h0v2.md` **§6 신설**, `plan_h0_revision.md`·`plan_h0v2_verification.md`·`research_plan_scie.md`(결정 #23~#25)·`phase_A/B/C`·`note_kpiwin_convention.md` | 표시 경로 4곳 주 지표 전환 + 회귀 테스트 신설 |

**신설 산출물 3종**: `experiments/vv_warmup_bias.py`(워밍업 600 s의 근거, 112 run) ·
`experiments/vv_window_compare.py`(이용률 왜곡 귀속, 12 run) ·
`experiments/vv_window_bias.py` **축 재정의**(legacy_margin ↔ delivery).
셋 다 `tests/test_scenario_tiers.py`의 **SUBSET_SCRIPTS 가드에 등재**했다 —
지시서는 CORPUS_SCRIPTS를 지정했지만 그 가드는 `== 28` 코퍼스 카운트 단언을
요구하고 세 스크립트 모두 대표 부분집합을 쓰므로, 실제로 보호가 되는 쪽에 넣었다.

**남은 사용자 액션**: 없음. `checklist_visual_h0v2.md` **§6** 육안 재서명(4항목)이
**2026-08-07 PASS**로 완료됐다.

### 다음 — **Phase A 착수**

전제 조건이 전부 충족됐다: H0 v2 검증 완료 + **V21 재검증 완료**(PASS 14 /
CAUTION 1 / PENDING 0 — 육안 재서명 2026-08-07 완료) · 문서 개정 ⓐ·ⓑ·R8 8단계 완료 ·
스위트 **440 green** · 미결 결정 1건(H3 `delivered`, Phase D까지 이월 가능).
시작점 = `plan_hr_extension.md` **R1a**(오퍼스/high) = `phase_A_robot_h1.md` **Step A1**.
두 문서는 같은 Step을 각각 "코드 위치 중심"과 "처음 보는 사람용 풀이"로 쓴 것이며,
**빌딩·수요·자원 상수는 결정 #16~#22가 항상 우선**한다.
- **Phase A**: 로봇 승객화 + EV 이종 정원(15인 → 로봇 탑승 시 11인). 착수 전제는
  **H0 v2 검증 완료**다.

---

## §5. 실행 예산 (W3 실측, 2026-08-04)

| 항목 | 실측 |
|---|---|
| run당 wall | K50 **1.01 s** · K100 **1.23 s** · K200 **1.66 s** · K300 **2.13 s** |
| 배터리 84 run | **135.3 s (2.3분)** |
| 30-seed CRN (840 run) | **≈23분** |
| 감사 모드 오버헤드 | **×1.09** (최대 ×1.13) — 상시 ON으로 돌려도 부담 없음 |
| verify_h0 1회 | K50 0.05 s ~ K300 0.25 s |

---

## §6. 파일 지도

```
etc/
  HANDOFF_v2.md                  ← 이 문서 (현행 정본)
  HANDOFF.md                     ← 구판 (이력 참고용)
  plan_h0_revision.md            개정 계획서 (§1 설계·§3 R0~R6·§9 로그)
  plan_h0v2_verification.md      검증 계획서 (§3 L1~L7·§4 W1~W8·§8 로그)
  plan_h0v21_window.md           ★ R8 창·종료 재정의 계획서 (§1 실측·§2 설계·§11 로그)
  HANDOFF_r8_step78.md           R8 7·8단계 실행 지시서 (완료 — 이력)
  note_kpiwin_convention.md      창 3+1종 + 주 지표 = utilization_delivery
  research_plan_scie.md          상위 연구계획서 (결정 #1~#25)
  scie_phase/                    Phase A~F 실행 계획서 + README
  checklist_visual_h0v2.md       육안 체크리스트 (§5 v2 서명 ✅ / §6 R8 재서명 ✅ 2026-08-07)
  building_10f_layout.html       레이아웃 도면 (지하 + 설계 가중치 토글)
  verification_report_h0v2.md    ✅ 집계 보고서 — **§8 V21이 인용 정본**

simulation/    space.py(rank 헬퍼) model.py elevator_physics.py
               agents/{elevator,control_system,pedestrian,...}.py
               visualize.py app.py run.py kpi.py
analysis/      verify_h0.py(A1~A14) scenario_tiers.py vv_*.py
               vv_balance.py ✅ W5c 신규
               h0_insights/note_v1_v2_comparison.md ✅ W7 신규
experiments/   vv_all39.py(28 코퍼스+감사 스윕) vv_monotonicity.py
               vv_variance.py vv_window_bias.py h0_descriptive.py
configs/       baseline_10f.yaml  scenario_tiers.yaml
               regression_nobasement_10f.yaml (동결 회귀 경로)
results/       baseline_h0_*.json(현행 골든) pre_basement/(지하 이전 골든)
               vv/     all39_battery · monotonicity · decomp_by_k · face_*(4)
                       ev_balance · evsel_stale · variance_*(2) · window_bias
                       + decomp_{mean,p95}.png · face_slack_hist.png
               h0_stats/  scenario_traits · h0_kpi_by_scenario (1차 티어 고정)
               figures/   h0v2_cross_{K50_1,K200_1_rush}.png (V2-VISUAL용)
archive/h0_v1/       v1 유일 기록 — **읽기 전용, 수정 금지**
archive/h0_v2_frozen/  ★ R8 이전(v2) 동결본 115파일/54MB — **읽기 전용.**
                       워밍업이 바뀌어 v2 수치는 코드로 재생성되지 않으므로
                       이것이 유일한 기록이다(MANIFEST.md 참조). 구·신 대조는
                       전부 여기서 — 특히 `vv/variance_summary.csv`가 그룹 I 판정의
                       구 팔이다
```

**W1~W8 산출물은 전부 생성됐다.** v1 판본은 `archive/h0_v1/analysis_outputs/`에
있고 **V2-CMP 노트에서만** 대조 목적으로 읽는다.

⚠️ `results/h0_stats/`는 **1차 티어(20 시나리오·60 run) 상태로 고정**해 뒀다 —
티어 모듈이 규정한 분석·보고 기본값이고, `h0_baseline_stats.py`가 `tier` 열로
정합을 검사하기 때문이다. `--tier all`로 덮어썼다면 primary로 되돌릴 것.

---

## §7. 지켜야 할 방침

- **git 미사용.** 커밋·태그 금지(사용자 명시 지시). 리포 이동은 파일 복사로 하고,
  이 문서와 `archive/h0_v1/`을 **반드시 통째로** 옮길 것.
- **Fable 미사용.** 판단 구간은 오퍼스 `max`(사다리 `low<medium<high<max`).
  진행 로그의 `세션(Fable)` 표기는 **실행 이력**이라 고치지 말 것.
- **레포 관례**: 각 Step을 배정 모델로 수행 → 세션에서 핵심 게이트(전체 pytest,
  비트 동일성, grep 감사) **독립 재검증** → 단계 경계마다 전체 스위트 green →
  계획서 진행 로그에 인플레이스 기록. 같은 실패 2회 반복 시 모델/effort 1단계 상향.
- **"코드가 진실"** — 문서 수치는 스크립트 자동 생성만 인용한다.
- **v1 실측 수치 인용 금지**: 2EV·800㎡·지하 없음 시절 값이라 지금 오라클이 될 수
  없다. 특히 v1의 SLA CAUTION(K1000 전량)은 재현 불가.

---

## §8. 메모리는 자동으로 안 따라온다

`~/.claude/projects/-home-sw-Research-abm-new/memory/`:

```
MEMORY.md                        인덱스
project-state-abm-2026-08.md     최신 상태 (이 문서와 짝)
project-state-abm-2026-07.md     그 이전 이력
model-policy-no-fable.md         Fable 미사용 방침
workflow-model-effort-stages.md  단계별 배정·검증 관례
```

다른 컴퓨터에서는 비어 있는 상태로 시작한다. 함께 복사하면 결정 배경까지 이어받고,
복사하지 않아도 **이 문서만으로 작업 재개는 가능**하도록 작성했다.
