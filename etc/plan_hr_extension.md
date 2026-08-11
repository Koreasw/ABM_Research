# HR 확장 계획 — H0 vs HR(로봇 릴레이 최소 모드) 용량 매개 평가

작성 2026-07-12. 사용자 승인된 연구 확장 제안(플랜 `h0-squishy-turing`)의 정식 계획서.
선행: `archive/h0_v1/docs/plan_h0_verification.md` V1~V8 완료(`archive/h0_v1/docs/verification_report_h0.md` PASS 16/CAUTION 1/PENDING 1).

> **지위 갱신 (2026-07-12, 4-모드 SCIE 확장 확정)**: 사용자 결정으로 연구 스코프가
> 2-암(H0 vs HR)에서 **4-모드 전체(H0/H1/H2/H3)** 로 확장되었다 — 정본 연구계획서 =
> `etc/research_plan_scie.md`, Phase별 상세 = `etc/scie_phase/`.
> - **R1a~R1c·R2a~R2d는 그대로 유효** — SCIE 계획의 **Phase A**로 승계된다
>   (풀어 쓴 상세: `etc/scie_phase/phase_A_robot_h1.md`; 규칙·코드 위치는 본 문서
>   §2~§4가 정본, 진행 로그는 본 문서 표와 phase_A 문서 양쪽에 동기 기록).
> - **R3(2-암 실험)·R4(경제층)는 실행하지 않는다** — 4-모드 통합 실험·경제층인
>   **Phase D**(`etc/scie_phase/phase_D_experiments_economics.md`)가 확장 대체한다.
> - §1 "논문 골격"(2-암 서사)·§5·§6도 research_plan_scie.md §2~§4(4-모드 RQ)로
>   대체되었다. §0 제약 중 "구현 소규모(2~3주)"는 4~5개월 로드맵으로 완화 확정.
> - R0 설계 동결 규칙 7건(§2)은 4-모드에서도 전부 유효(H1 기반 규칙이므로).

> ## 🔴 지위 갱신 2 (2026-08-04, 문서 개정 ⓑ) — **먼저 읽을 것**
>
> 본 문서는 **v1 빌딩**(EV 2대 · 층당 800 ㎡ · 복도 27 m · 지하 없음 · 상주 800명 ·
> 보행자 6.0/분 · 모집단 38개)을 전제로 2026-07-12에 작성됐다. 그 뒤 **H0 v2 개정
> (R0~R7)과 검증(W1~W8)이 완료**되어 전제가 전부 바뀌었다
> (`etc/research_plan_scie.md` §1 **결정 #16~#22**, `etc/HANDOFF_v2.md`).
>
> **무엇이 유효하고 무엇이 아닌가**:
>
> | 구분 | 지위 |
> |---|---|
> | §2 R0 설계 동결 규칙 7건 | ✅ **유효** — 건물과 무관한 규칙이다. 단 **R0-1·R0-2의 "EV2"는 "공용 EV(EV3·EV4)"로**, **R0-5의 "B1F 충전 도크"는 폐기**로 읽는다(아래 각 행에 정정 표기) |
> | §3·§4의 **코드 위치(파일:줄)** | ⚠️ **2026-08-04 전량 재검증·갱신 완료.** v2 재작성으로 상당수가 이동했다 — 갱신 전 줄번호를 그대로 쓰면 엉뚱한 코드를 고친다 |
> | §0·§1·§8의 **실측 수치** | 🚫 **인용 금지** — v1 조건 측정값이다. v2 재산출값은 `etc/verification_report_h0v2.md`와 `analysis/h0_insights/note_v1_v2_comparison.md` |
> | §5 R3 · §6 R4 | ⚪ **미실행 확정** — Phase D가 대체(위 지위 갱신 1). 그 안의 시나리오 수·K 격자는 낡았으나 **고칠 대상이 아니라 폐기 대상**이다 |
>
> **v2에서 가장 자주 틀리는 3가지**: ①**공용 EV = EV3·EV4**(EV1·EV2는 사람 전용,
> 복도 16 m; 공용 뱅크는 18 m) ②**로봇은 지하에 가지 않는다**(B1·B2는 사람 승하차
> 전용) ③**코퍼스는 28개**(K500 이상은 보류 — "K500부터" 류의 임계 서술은 검정 불가).
> 풀어 쓴 v2 맥락은 `etc/scie_phase/phase_A_robot_h1.md` 상단이 정본이다.

## 진행 로그

| Stage | 항목 | 배정 | 산출물·핵심 수치 | 상태 |
|---|---|---|---|---|
| R0 | 설계 동결 | 세션 직접 | 본 문서 §2 (규칙 7건) | ✅ 2026-07-12 문서화 — 사용자 이의 시 개정 |
| R1a | 로봇 승객화 + EV 이종 정원 | — | — | ⬜ |
| R1b | HandoffRiderAgent + 디스패치 + model 배선 | — | — | ⬜ |
| R1c | KPI additive + run.py --mode | — | — | ⬜ |
| R2a | HR 골든패스 2케이스 | — | — | ⬜ |
| R2b | verify_hr.py B1~B11 + 테스트 | — | — | ⬜ |
| R2c | 단조성 5방향 + 극한 2케이스 | — | — | ⬜ |
| R2d | HR 전수 배터리 **28×3 = 84 run** | — | — | ⬜ |
| ~~R3~~ | ~~CRN 페어드 스윕 + 경계 매핑 + counterfactual~~ | — | **Phase D가 대체 — 미실행 확정** | ⚪ |
| ~~R4~~ | ~~costs.py NPV·break-even + figure + 보고서~~ | — | **Phase D가 대체 — 미실행 확정** | ⚪ |

**재개 가이드**: 다음 = R1a(오퍼스/high). **착수 전제인 H0 v2 검증은 2026-08-04 완료**
(게이트 13건 = PASS 12 / CAUTION 1 / PENDING 0). 각 단계 완료 시 이 표에 인플레이스 기록(산출물 경로·핵심 수치·독립 재검증 방법). H0 검증 계획의 관례(서브에이전트 위임 + 세션 독립 재검증 + 게이트 판정) 동일 적용.

---

## §0. 배경과 제약 (사용자 확정)

1. **로봇/핸드오프 서사 필수** — 단 기존 H1/H2/H3 설계를 그대로 따를 필요 없음.
2. **구현 예산 소규모** — 항목당 며칠~1주, 총 2~3주(추정 14.5~17 작업일).
3. **타겟 저널 SMPT 유지** — 검증 배터리를 방법론 기여로 전면 배치.

코드 실태(**2026-08-04 재확인**): H0 **v2**만 구현·검증 완료. RobotAgent/LockerAgent
스텁, control_system no-op(`control_system.py:54-56`), costs.py NPV 스텁,
model.py 비-H0 raise(**`model.py:114-117`** — 구 표기 109-112는 v2에서 이동).
그래프 zone(`lobby_handoff_counter`·`lobby_robot_pickup_zone`)·config `robot:` 블록·
`ElevatorAgent(shared_with_robot=…)` 플래그·`shared_ev_capacity_people_with_robot: 11`
키는 **전부 현존 확인**.

검증 발견 → 설계 근거(요약) — 🚫 **아래 수치는 v1 조건 측정값이라 인용 금지.
2026-08-04 v2 재판정을 병기한다**:

| # | v1 발견 (인용 금지) | v2 재판정 | 설계 함의 |
|---|---|---|---|
| ① | ev_wait이 K 지배 성분 · EV util **92~98%** 보행자 포화 → 병목 = 수직 용량 | **약화됐으나 유효**: 대당 가동률 **0.773(K50)→0.835(K300)**, 완화 폭이 K와 함께 축소(−15.2%→−10.5%) | 병목 = 수직 용량이라는 **결론은 유지**. 강도만 하향 |
| ② | 라이더 계단 처리 2F 89.6% → 5F 0.7% → 로봇 전환 시 **계단 손실** | **불변** — 수직수단 선택 상수가 v2에서 안 바뀌었다(`note_v1_v2_comparison.md`) | 계단 손실 가설 **그대로 유효** |
| ③ | SLA 판별력 없음(CAUTION) → 고객축 = p95 + deadline counterfactual | **더 강해짐**: v2 코퍼스 위반 **0/15,600**, 최소 여유 12.58분 | counterfactual 없이는 SLA로 모드를 못 가른다 |
| ④ | CRN 쌍대조 규약 → 페어드 설계 | ⚠️ **부분 철회**: `floor_seed` 고정 CRN의 분산 감소가 시나리오 대부분에서 1.0과 구별 불가 | 페어드 설계는 유지하되 **이득을 전제하지 말 것** |
| ⑤ | 층 프로파일 검증 완료 → 형태학 축 무료 | **유효** | — |
| ⑥ | 실행 예산 실측 → 계산 비제약 | **유효**(v2: run당 1.01~2.13 s, 84 run 135 s) | — |

**v2에서 새로 추가된 설계 제약 1건**: 로봇의 **T_e2e 단축 상한이 11.6~13.0%**다
(조리 64~68% + street 19~24%가 건물 무관). 대표 KPI를 T_e2e가 아니라
**T_lobby·W_EV·opex**에 두어야 하는 이유가 여기 있다.

## §1. 논문 골격

**HR = 구 H1의 최소화** (enum `H1_SYNC` 재사용, 논문 표기 "H1-minimal"):
라이더가 `lobby_handoff_counter`에서 로봇에 인계 후 즉시 퇴장 → 로봇이 **공용 EV
(EV3·EV4)** 로 상행 → 호실 인도(30s) → 1F 복귀. **제외(future work)**: H2 큐/포기,
H3 락커, 충전 사이클, 동일층 배칭.

**핵심 가설**: HR은 T_lobby를 줄이지만 ①계단 손실(2~5F 주문의 EV 수요 편입)
②**공용 EV 정원 잠식**(15→11) ③주문당 **공용 EV 호출 2회**로 수직 용량을 소모 →
K×층 프로파일 평면에서 개선/역전 경계를 매핑.
~~양면 외부성: **전용 EV1·EV2** 보행자 대기 개선 / **공용 EV3·EV4** 악화~~
🔴 **2026-08-11(결정 #31)**: 실측이 이 가설을 지지하지 않는다 — 보행자 대기의 모드 간
차이는 ±1~6 s로 주 지표의 1/1000이고 고부하에서는 부호가 H1에 유리하다. **수직 경합은
로봇 쪽에서 관측된다**: 로봇 EV 대기 배달당 왕복 60~75 s(`T_building_order` 임계 경로) +
`board_denied` 17→73→124. per-EV 보행자 분리는 **타당성 가드**로 존치.

> *2026-08-04: v2에서 공용이 **2대**가 되어 잠식 압력이 분산된다. 동시에 **공용이
> 2대라 "로봇이 어느 카를 부를지"라는 결정이 새로 생겼다** — v1(공용 1대)에는 없던
> 문제다(§3 R1a 참조).*

**RQ**: RQ1 경계 매핑(T_lobby·p95 T_e2e·**로봇 수직 경합** — 구 "보행자 EV 대기", 결정 #31) / RQ2 역전 메커니즘 분해
(계단 손실·slot 점유·호출 배증 — A5 분해 확장) / RQ3 로봇 대수·w_R break-even(폐형식) /
방법론: H0 A-게이트 + HR B-게이트 = 재사용 가능 replay-ABM V&V 템플릿.

framework 기여 재편: §8 기여 1(4-mode taxonomy — 서론/향후연구로 유지)·5(V&V)·6(재현성)
보존, 2·3·4는 2-암 범위로 축소 재기술 (R4c에서 framework 정합).

## §2. R0 설계 동결 — 확정 규칙 7건

| # | 규칙 | 근거 |
|---|---|---|
| R0-1 | **로봇 1대/카 상한** — 한 카에 로봇 2대 동승 불가(사람과는 혼승). *2026-08-04 정정: 대상 카는 **공용 EV3·EV4**이며 전용 EV1·EV2에는 로봇이 아예 못 탄다* | 이종 정원 규칙 단순화; `with_robot` 정원 키가 단수 정의 |
| R0-2 | **사람 정원 규칙**: 로봇 탑승 중 사람 ≤ 11 (`shared_ev_capacity_people_with_robot`), 로봇 미탑승 시 15. 로봇 탑승 허용 조건 = 현재 사람 수 ≤ 11 **and** 로봇 미탑승 | config 기존 키 소비(양쪽 다 현존 확인); audit assert **`model.py:541-571`**(`_audit_invariants`, 정원 assert는 569행) 동기 갱신 필수 — *구 표기 526-529는 v2에서 이동* |
| R0-3 | **핸드오프 시간 = N(60, 15²) 0-절단**, RNG 3-워드 스트림 `[0x686F6666('hoff'), rng_seed, ord_id]` — P3 스트림-패밀리 규약의 4번째 3-워드 패밀리 | `configs/modes/h1_sync.yaml` 기존 값; CRN 무교란(기존 도착·층·수단·보행자 스트림 불변) |
| R0-4 | **1주문/트립** (배칭 없음). *2026-08-06 실측 보강*: 코퍼스 28개 5,200주문의 **VOL max = 100 · mean 27.4 · p95 53**이고 `robot.capa = 100`이므로 **적재 거부는 정의상 0건**이다 — B-게이트에서 **정보행**으로만 다룬다. ⚠️ VOL은 **부피**이지 무게가 아니며(`data_ex.txt` `Order.volume`), **100에서 절단**된 것으로 보인다(정확히 100이 26건, 초과 0건) → "실측 최대에 맞췄다"는 서술은 이 사실과 함께 쓸 것. 이 상수가 실제로 구속력을 갖는 곳은 **Phase C의 락커 V_max 스윕**이다(V_max=50이면 5.96%, 70이면 1.94% 미수용) | 소규모 예산; future work |
| ~~R0-5~~ | ~~**충전 비활성**~~ → 🔴 **폐기 (결정 #26, 사용자 확정 2026-08-06).** 배터리·충전을 **모델링한다**: 용량 1,300 Wh · 주행 0.14 Wh/m · **비주행 전량** 1.0 Wh/min · 충전 13.0 Wh/min(20→80% 1h) · 20% 하향 돌파 시 **인도(DROP) 완료 후** 복귀·충전 → **40%에서 배차 재개**. `RobotState`에 **`CHARGING_BLOCKED`** 를 신설한다(`IDLE`의 기회 충전과 구분되는 것은 **배차 가능성**이다). idle 홈 = 1F `lobby_robot_pickup_zone`(결정 #19의 대기＝충전 통합은 **유효**하며, 그래서 "충전을 위해 이동"과 "대기 장소로 복귀"는 경로가 동일해 `return_reason` 태그로만 구분한다). 로봇은 여전히 **지하에 진입하지 않는다**(결정 #18). ⚠️ **점심 피크 창에서 20% 임계는 발화하지 않는 것이 정상**이다(종료 SOC 43~90%) — 이는 결함이 아니라 **결과**이며 "1.3 kWh급 로봇은 점심 피크 운영의 제약이 아니다"로 보고한다. 발화 경로는 ①합성 단위 테스트 ②**Phase E의 `soc_init` 스윕 {100,60,40,25}%** 뿐이다 | 사양·검산은 `scie_phase/review_phase_A_precheck.md` §3; 파라미터 정본은 `configs/baseline_10f.yaml` `robot.battery`(A0 신설) |
| R0-6 | **보행자 로봇 회피 α 미구현** (framework α_lobby_extra 등) — H0 보행자 행동 불변 | H0 비트 동일성 게이트 보전 |
| R0-7 | **연간 환산 규약(NPV)**: 시뮬레이션 창 = 점심피크 1식(scenario_window), 연간 = ×250 영업일. 로봇 연간 OPEX = 유지보수(CAPEX의 5%/y) + 전기료(`elec_krw_per_kwh` × 주행 에너지) | costs.py 구현 시 상수 1곳 문서화; 민감도 대상 |

## §3. R1 구현 상세 (5~6일)

> ⚠️ **개정 2026-08-06 (착수 전 점검 결정 14건 + Step A0 완료 반영).**
> 정본 흐름: 착수 전 점검 `scie_phase/review_phase_A_precheck.md` →
> 계획 `scie_phase/phase_A_robot_h1.md` §2 → **구현 로그
> `scie_phase/phase_A_implementation_log.md`**. 본 문서와 어긋나면 **그 셋이 우선**한다.
>
> **R1 앞에 R0a(= Step A0)가 신설됐다** — config 배선·`max_overrun_sec_robot`·보행자
> 감쇠. 2026-08-06 완료(스위트 441→480). 상세는 구현 로그 §A0.
>
> ⚠️ **파일:줄 표기가 R8 이후 다시 표류했다 (2026-08-06 전수 재검증).**
> 2026-08-04 검증분 중 `model.py` 항목이 전부 이동했다. **줄 번호 대신 심볼로 찾을 것** —
> A0가 또 밀었고 A1~A3이 더 밀 것이다.
>
> | 구 표기 | 2026-08-06 실측 | |
> |---|---|---|
> | `walker.py:51-133` GraphWalker | class at **51** | ✅ 유효 |
> | `elevator.py:13-17` 덕 타이핑 | **14-17** | ✅ 유효 |
> | `elevator.py:146-173` 보딩 루프(정원검사 155·159) | **155·159** | ✅ 유효 |
> | `control_system.py:54-56` 예비 훅 | **54-56** | ✅ 유효 |
> | `model.py:541-571` `_audit_invariants`(정원 assert 569) | **`_audit_invariants()`**, 정원 assert **687** | ❌ 표류 |
> | `model.py:329-336` `shared_with_robot` | **387** | ❌ 표류 |
> | `model.py:114-117` 모드 게이트 | **121-122** | ❌ 표류 |
> | `tests/test_agents.py:55-58` | **58-60** | ❌ 표류 |

**R1a 로봇 승객화 + EV 이종 정원 (2일)**
- `robot.py`: GraphWalker 믹스인(`walker.py:51-133` — **위치 불변 확인**, 호스트 요구 = graph/node/speed_mps)
  + 승객 프로토콜(`elevator.py:13-17` 덕 타이핑 — **위치 불변 확인**: ev_dest_floor/ev_wait_started_sec/kind="robot"/on_board/on_alight).
  **FSM — 개정 2026-08-06 (결정 4)**: 구 표기(IDLE→TO_COUNTER→HANDOFF→WAIT_EV_UP→
  RIDING_UP→TO_OFFICE→DROP→TO_EV→WAIT_EV_DOWN→RIDING_DOWN→TO_HOME→IDLE)는
  **`WAIT_RIDER`가 빠져 있고 `CHARGING_BLOCKED`가 없다.** 정본은 **8상태 + 직교 속성 2개**:
  `IDLE`(기회 충전·배차 가능) / `MOVING`(`leg`) / **`WAIT_RIDER`**(신설) / `HANDOFF` /
  `WAIT_EV`(`dir`) / `RIDING`(`dir`) / `DROP` / **`CHARGING_BLOCKED`**(신설, 배차 불가).
  속성 `return_reason ∈ {idle, low_soc}`가 "복귀"와 "충전하러 이동"의 유일한 실제
  차이다(경로가 동일하므로 상태를 나누지 않는다). 상세·근거는
  `scie_phase/phase_A_robot_h1.md` §2 A1 / 점검 §4.2.
- **배터리 서브시스템 (결정 #26 — R0-5 폐기)**: 파라미터 정본은 A0가 만든
  `robot.battery` 블록(`simulation/config_params.py`의 `RobotParams.battery`).
  **`RobotAgent`의 `soc_low_threshold`·`capa` 생성자 인자를 `RobotParams`로 교체할 것** —
  스텁의 자체 기본값을 남기면 정본이 이중화된다(구현 로그 §A0-⑤-6).
  소모 규약(결정 5): 주행 `0.14 Wh/m`, **비주행 전량**(대기·EV대기·**탑승**·인계·인도)
  `1.0 Wh/min`, 20% 트리거 경계는 **DROP 완료 시점**.
- **종료 조건**: `_carriers_settled()`의 H1 분기는 **`IDLE ∨ CHARGING_BLOCKED` ∧
  노드 == 로봇존**이다. "전원 IDLE"로 쓰면 마지막 배달 직후 SOC가 낮은 로봇 때문에
  run이 끝나지 않는다.
- **공용 EV 선택 (2026-08-04 전면 개정 — 구 "EV2 고정: `model.elevators[1]`" 지시는 오류다)**:
  v2에서 인덱스 1은 **사람 전용 EV2**다. 공용은 `shared_ev_ids: [EV3, EV4]`(선언적 config)이고,
  런타임 후보는 **`[ev for ev in model.elevators if ev.shared_with_robot]`** 로 얻는다
  (`ElevatorAgent`가 생성 시 플래그를 받는다 — `model.py:329-336`). **인덱스 하드코딩은
  R2 N-EV 일반화를 되돌리는 행위**이므로 금지.
  **공용이 2대가 되면서 "어느 카를 부를지"라는 새 결정이 생겼다**(v1은 공용 1대라 불필요했다).
  기본 규칙 = **기존 EV 선택 휴리스틱을 그대로 쓰되 후보를 공용 2대로 제한**. 이 경로는
  사람과 같은 배차 코드를 타므로 W5c에서 확인된 타이브레이크 쏠림(동점 시 `ev_id` 오름차순)이
  로봇에도 적용된다 — R2d에서 관찰 항목으로 기록할 것.
  전용 EV 방어 assert는 **EV1·EV2 양쪽**을 대상으로 한다(구 "EV1"만은 부족).
- `elevator.py:146-173` 보딩 FIFO 루프(`_door_cycle` 내, 정원 검사 155·159행) *(구 139-170)*:
  R0-1·R0-2 이종 규칙 + `robot_board_denied` 카운터(리스크 2 계측).
- `model.py:541-571` `_audit_invariants` 정원 assert 동기 갱신 *(구 526-529)*.
  H0 비트 동일성: 로봇 부재 시 산술 동일 → V5d가 게이트.
- **지하 방어**: 로봇 FSM의 목적층은 항상 ≥ 1F여야 한다(결정 #18). B-게이트 B3에
  "로봇 지하 진입 0건"을 넣는다 — H0의 A10-2에 대응하는 H1 판이다.

**R1b HandoffRiderAgent + 디스패치 + model 배선 (2~2.5일)**
- `HandoffRiderAgent` **별도 클래스**(external_rider.py FSM 원본): WALK_TO_COUNTER→WAIT_ROBOT→HANDOFF→WALK_TO_EXIT.
- **함정 1 (Mesa 정확 클래스 키잉)**: 생성자에서 `self.rider_cls` 결정 후
  `agents_of(ExternalRiderAgent)`를 전부 `agents_of(self.rider_cls)`로 치환 —
  R1b 첫 커밋에서 선행, 스모크에서 라이더 계수 비영 확인.
  ⚠️ **개소는 8개가 아니라 11개다** (2026-08-06 전수 재조사): `model.py` **6**
  (439·560·628·733·1003·1046) + **`visualize.py` 4**(260·279·433·533, **구판 누락**) +
  `building_manager.py` 1(43). `visualize.py`를 빠뜨리면 **앱에서 H1 라이더가 렌더링되지
  않는다.** 스모크에 **앱 렌더 경로를 포함**하고, **H0 화면이 치환 후에도 동일함을
  테스트로 고정**할 것 — H0에서는 `rider_cls == ExternalRiderAgent`이므로 동일해야 하며,
  이것이 `checklist_visual_h0v2.md` 서명을 R1b 이후에도 유효하게 만드는 근거다.
  H1 관찰은 **`checklist_visual_h1.md`** 가 별도로 맡는다(H0용은 존치, 사용자 확정 2026-08-06).
- **함정 2 (라이더 조기 퇴장)**: delivered 스탬프는 로봇 DROP 시 `customer.delivered_at_sec` 기록(주체 교체),
  `model.robot_leg_records`(ord_id 키: handoff_start/end·robot_id·robot_ev_wait_up/down·delivered·returned) 신설,
  run.py per_order = rider×robot 레코드 **ord_id 조인**(H0 필드 전부 보존, 신규 필드는 H0에서 None — additive 관례).
- `control_system.py:54-56` 예비 훅(`step()`의 `pass`)에 FCFS 디스패치 *(구 50-52)*
  (전 로봇 동일 idle 지점 → 최근접=FCFS 동치). tick 순서상 디스패치 1-tick 지연은
  골든패스 체인에 반영.
- 모드 게이트 해제(**`model.py:114-117`** H1_SYNC만) *(구 109-112)*, 종료 조건에
  "로봇 전원 IDLE 복귀" 추가, **`tests/test_agents.py:55-58`**
  (`test_non_h0_modes_not_implemented_yet`)는 H2/H3만 raise 기대로 수정 *(구 51-54)*.

**R1c KPI additive + run.py (1일)**
- **★ 측정 창 3층 분리 (2026-08-06 신설, 결정 14)** — R1c에서 가장 중요하다.
  ①**자원 점유 지표**(보행자 EV 대기·EV 가동률·재차 인원)는 **모드 불변 고정창
  `[첫 주문, 마지막 주문]`** ②**주문 단위 지표**(T_e2e·`T_building_order`·SLA)는
  **창 무관**(주문 집합) ③`utilization_delivery`는 **모드 내 진단 전용**.
  창 밖 드레인은 `drain_span_sec`·`drain_ev_boardings`·`drain_robot_trips`로 별도 보고.
  ~~**이 분리를 하지 않으면 양면 외부성 주장이 성립하지 않는다**~~
  🔴 **2026-08-11 근거 정정(결정 #31)**: ⓐ드레인은 **한산하지 않다**(피크보다 더 붐빈다 —
  배달이 주문보다 ~20분 늦어 백로그가 마지막 주문 직후 최대) ⓑ보행자 EV 대기는
  **헤드라인이 아니라 타당성 가드**다 ⓒ**함대 가동률의 분모는 고정창이 아니라
  `utilization_ops`**(`[첫 주문, 마지막 운반체 정착]`) — 고정창은 길이가 K와 무관해
  포화 후 천장에 붙는다(K200 0.735 / K300 0.738 → ops로는 0.905 / 0.932).
  **3층 분리 자체는 유효**하되 근거는 "외부성 주장"이 아니라 **자원 점유의 모드 불변
  슬라이스 확보**다.
- **`T_building_order` 신설**(인계 시작 → 인도 완료). **H0의 `T_lobby`와 진짜로 비교
  가능한 양은 이것**이다 — H1의 `T_lobby_rider`는 ρ>1 구간에서 로봇 대기로 발산한다.
- 보행자 EV 대기: 기존 `ped_done_log`(`kpi.py:146-154` — **위치 불변 확인**) 확장 —
  p95, **ev_id별 분리 4대 전량 + 전용(EV1·EV2)/공용(EV3·EV4) 그룹 집계**
  (🔴 **결정 #31**: 목적이 "양면 외부성 입증"에서 **타당성 가드**로 바뀌었다 —
  보행자가 공용 카를 회피하면 로봇이 빈 샤프트를 물려받아 이득이 과대평가된다),
  orderspan 필터(`_order_span` 재사용).
  ⚠️ **공용 4대 조합에서는 전용 집합이 공집합**이므로(결정 13) `ev_id`별 계측을
  **정본**으로 두고 그룹은 **파생**, 전용이 비면 **None**(additive 관례).
- **배터리 KPI** 신설: `soc_min_observed`·`n_charge_events`·`charge_blocked_sec`·종료 SOC.
  **`robot_evsel_stale`** 신설 — H0 실측(stale 52.95% / harm 상한 28.81 s)과 대조한다
  (로봇은 후보가 2대라 비율↓·건당 harm↑가 예상된다).
- 로봇 가동률: `_ev_busy_cum` 스냅샷 패턴 복제. `w_ev_mean_all_sec`은 kind=="robot" 제외 필터로 기존 의미 보존, robot 전용 필드 신설.
- `run.py --mode hr` passthrough. **동시에 `config` dict 주입 경로도 열 것** —
  `run_baseline`이 config *경로*만 받아 A0의 파라미터 변조 테스트가 모델을 직접
  구동해야 했고, Phase D의 sizing 스윕이 같은 문제에 부딪힌다(구현 로그 §A0-②-3).

**R1 게이트**: ①기존 **480** 테스트 green *(A0 완료 시점 실측. 구 표기 437·440은 표류값)* ②결정성 테스트 + **골든패스 2체계**
(`test_vv_golden_path.py` 그래프 유도 + `test_vv_golden_path_v2.py` 설계 사양 절대값) **비트
동일**(H0 무교란 증명) ③HR K50_1 audit 스모크 완주 ④**하위호환 잠금 3종 유지**
(`configs/regression_nobasement_10f.yaml` · `results/pre_basement/` ·
`test_h0_frozen_snapshot.py::test_nobasement_replay_matches_pre_basement_snapshot`) —
`model._draw_ground_floor()`가 종점 1F뿐일 때 **RNG를 소비하지 않는** 설계를 깨면 이
테스트는 영구히 통과 불가가 된다.

## §4. R2 검증 상세 (4~4.5일)

- **R2a HR 골든패스 2케이스** (0-tick 정확 일치): 단일 주문×idle 로봇 / 2주문×1로봇 경합.
  `test_vv_golden_path.py` 인프라(합성 시나리오 빌더·보행자 0·single7 프로파일·mode_seed 탐색) 재사용.
  수기 체인: entered → w(entry→counter)−1 → [디스패치 +1 tick + w_robot(pickup→counter)] → max 대기 → tt(60, sd=0) → 라이더 퇴장 ∥ 로봇 w(counter→**공용 EV 승강장(EV3 또는 EV4, 복도 18 m)**) → 보딩 → tt(door)+tt(move) → w(corr→office) → tt(30) = delivered. *2026-08-04: 구 표기 `ev_EV2_1`은 v2에서 **사람 전용** 카의 노드다 — 그대로 쓰면 로봇이 탈 수 없는 카를 손계산하게 된다.*
- **R2b `analysis/verify_hr.py` **B1~B11** + `tests/test_verify_hr.py`(음성 케이스 포함, test_verify_h0 24개 패턴):
  verify_h0의 CheckResult/_walk_ticks/_timer_ticks/_graph_and_kin import 재사용.
  *(2026-08-06: **B1~B9 → B1~B11**. 신설 **B10 배터리 보존**(SOC 단조성·0≤SOC≤100·
  `CHARGING_BLOCKED` 중 배차 0건·재개 시 SOC ≥ resume. 단 코퍼스에서 `n_charge_events==0`은
  **정상**이므로 그 부분은 정보행) · **B11 종료 상태**(전 로봇 `IDLE ∨ CHARGING_BLOCKED`
  ∧ 로봇존 · `delivered == K` **엄격** · `termination_reason == "delivery_complete"`;
  cap 종료는 게이트 FAIL이 아니라 **실행 실패**로 `max_overrun_sec_robot`을 올려 재실행).
  또한 B3의 전용 EV 게이트는 **공용 4대 조합에서 조건부 SKIP**(전용 집합이 공집합),
  W5c G2 균형은 **"사람 보딩만"으로 판정**한다.)*
  B1 보존 / B2 라이더 체인(entered<handoff_end≤exited) / **B3 로봇 보존**(**전용 EV1·EV2 로봇 보딩 0** *(구 "EV1")* · **로봇 지하 진입 0** — A10-2의 H1 판 · boards==alights · 종료 시 전원 IDLE · with-robot 사람정원 위반 0) / B4·B5 기구학·분해(로봇 속도 1.0 재유도 — HR 라이더 t_lobby = walk+wait_robot+handoff 정확 항등식) / B7 FCFS 배정 리플레이 / B8 윈도우 / B9 프로파일 GOF.
- **R2c 단조성 5방향** *(2026-08-06: 3 → 5)*: ①n_robots **1→3→5**(baseline 포함)
  ⇒ wait_robot↓ / ②K↑ ⇒ robot util·**공용 EV 보행자 대기**↑ / ③저K HR t_lobby < H0 페어드 /
  **④K↑ ⇒ 충전 이벤트↓·종료 SOC↓**(신설 — 포화 구간에서는 로봇이 IDLE이 되지 않아
  기회 충전이 일어나지 않는다) / **⑤공용 EV 2→3→4 ⇒ 로봇 EV 대기↓**(신설).
  + 극한 2케이스(로봇 1대·보행자×10).
  ⚠️ 저K 페어드 비교에서 **보행자를 0으로 두지 말 것** — 배경교통 0이면 동점 타이브레이크로 **EV3·EV4 승차가 0건**이 되어 로봇 이득이 과대평가된다(W5c 유효성 위협).
- **R2d 배터리**: `vv_all39` mode 파라미터화, HR **28×3 = 84 run** 완주 게이트 *(구 "38×3, 유효 38 = 39 − K1000_5"는 K500 이상 보류 전 기준. K1000_4≡K1000_5 중복 규약은 그 티어가 코퍼스 밖이라 **판정 대상이 아니다**)*. 코퍼스는 `analysis/scenario_tiers.py`가 정본 — `data/data1`을 직접 glob 해 39개를 세는 코드는 오류다.

## ~~§5. R3 실험 설계~~ ⚪ **미실행 확정 — Phase D가 대체**

> *2026-08-04: 아래는 2-암 시절 설계다. 시나리오 수(33)·K 격자({100,300,500})·부록
> (K750/K1000)이 전부 결정 #21 이전 기준이지만, **고칠 대상이 아니라 폐기 대상**이라
> 원문 그대로 둔다. 실제 실험 설계 정본 =
> `etc/scie_phase/phase_D_experiments_economics.md`(4모드 × 28 × 30 = 3,360 run).*

<details>
<summary>구 R3 설계 (이력 참고용)</summary>

- CRN 페어드 스윕: 2암 × 33 시나리오 × 30 seed (uniform 전량; bottom/top_heavy는 K∈{100,300,500}) + 부록 K750/K1000.
  전 런 verify 게이트 인라인. 페어드 CRN assert: 동일 seed에서 도착·층 스트림 per-order 일치.
- 경계 매핑: Δt_lobby·Δped W_EV(per-EV)·ΔT_e2e(p95) vs K×프로파일, 역전점 검출.
- 로봇 대수 {2,3} × K∈{100,300,500} (NPV 입력).
- deadline 강화 counterfactual: per_order 후처리(재실행 불요) + p95 보고.
- 산출: `results/hr/` CSV + `experiments/hr_sweep.py`.

</details>

## ~~§6. R4 경제층 + 집필 재료~~ ⚪ **미실행 확정 — Phase D가 대체**

> *2026-08-04: costs.py·NPV·break-even은 Phase D로 이관됐다(위 지위 갱신 1).
> 아래 폐형식 w* 유도는 **Phase D가 재사용할 재료**이므로 남긴다.*

- costs.py `building_npv`·`break_even_w_rider` 구현(framework §7.4 식, R0-7 환산 규약).
  w* 폐형식(w_R 선형, Revenue 소거): w* = (연금화 ΔCAPEX + Δ고정OPEX) / ΔT_lobby_연간.
  `tests/test_cost_model.py` skip 해제 + 수기 계산 테스트.
- Figure: HR vs H0 분해(vv_decomp 패턴)·경계 히트맵·2암 trade-off·w* 선도.
- `etc/verification_report_hr.md` + framework §6/§7/§8 정합.

## §7. 배정표

| Stage | 난이도 | 모델 | effort | 비고 |
|---|---|---|---|---|
| R1a | 중 | 오퍼스 | high | EV 보딩 루프는 H0 핵심 경로 — 비트 동일성 직결 |
| R1b | 중~상 | 오퍼스 | high | 함정 2건(Mesa 키잉·레코드 조인) 포함 |
| R1c | 하 | 소넷 | medium | additive KPI, 기존 패턴 복제 |
| R2a·R2b | 중 | 오퍼스 | medium + **오퍼스/max 리뷰 1회**(V1R 관례 — 게이트 설계 결함 조기 발견; 구 Fable 리뷰 대체) | B-게이트가 방법론 기여 본체 |
| R2c·R2d | 하 | 소넷 | low~medium | 러너 재사용 |
| R3 | 중 | 소넷 | medium | 스윕·집계, 해석은 세션(오퍼스) |
| R4 | 중 | 소넷 | medium | costs 폐형식 + figure; framework 정합은 오퍼스/medium |

Escalation 관례: 소넷 담당분에서 스펙 모호·게이트 실패 반복 시 오퍼스로, 설계 충돌 시 세션(오퍼스) 직접. 각 단계 완료 시 세션 독립 재검증 후 진행 로그 기록.

> **모델 정책 3차 개정 (2026-08-03)**: Fable 잔여 크레딧 0 — 본 계획서의 모든
> Fable 배정을 **오퍼스**로 이관하고, 구 Fable 담당 구간은 effort `max`
> (`low<medium<high<max`)를 적용한다. 정본은 `plan_h0_revision.md` §6.

## §8. 리스크와 절단

1. **HR 전패 가능성** — *2026-08-04 재판정: **약화됐으나 유효***. v1 근거였던 "EV2 92~98% 포화"는 인용 금지이고, v2 실측은 대당 가동률 **0.773(K50)→0.835(K300)**이다. EV를 2배로 늘렸는데도 완화 폭이 K와 함께 줄고(−15.2%→−10.5%) 가동률은 K와 함께 오르므로 **포화로 향한다는 구조는 유지**된다. **전용 EV1·EV2 개선**(양면 외부성)이 서사 구제; 저K·top_heavy 미우위 시 로봇 대수·핸드오프 60s 민감도. 역전이 빨라도 경계 매핑 기여 성립. 단 **T_e2e 단축 상한 11.6~13.0%**라 상금 자체가 작다는 점을 함께 서술할 것.
2. **탑승 거부 루프**(하행 로봇 vs 만원 카): 버그 아닌 측정 대상 — deny 카운터 + B-게이트 report-only 상한.
3. **CRN 부분 파손**(동적 풀 내생): 채널 분해 보고 + 풍부한 풀 robustness 1세트 — "실효 함대 확대" 서사.
4. SCAN 방향 위임(첫 탑승자=로봇이 방향 결정 가능): 정상 동작, 골든패스 수기 체인에 반영.

**절단 순서**(예산 초과 시): 프로파일 K 3점 축소(기반영) → 로봇 대수 스윕 폐지(w* 폐형식만) → 단조성 2방향 → counterfactual 단일값 → 부록 HR 생략.
**절단 금지**: H0 비트 동일성 게이트 · HR 골든패스 · B-게이트 배터리.

## §9. 산출물 경로

```
simulation/agents/robot.py             # R1a (스텁 → 구현)
simulation/agents/handoff_rider.py     # R1b (신규)
analysis/verify_hr.py                  # R2b B1~B11
tests/test_vv_golden_path_hr.py        # R2a
tests/test_verify_hr.py                # R2b
experiments/hr_sweep.py                # R3
results/hr/                            # R3 CSV (results/vv/와 분리)
etc/verification_report_hr.md          # R4
```
