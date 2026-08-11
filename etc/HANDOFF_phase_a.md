# 작업 인수인계 — Phase A (H1 로봇 릴레이) 진행 중

> 작성 2026-08-06. **선행 인계 문서**: `etc/HANDOFF_v2.md`(H0 v2/v2.1 전체) —
> 건물·창·종료 규약 8가지는 **그쪽이 정본**이고 여기서 반복하지 않는다.
> 본 문서는 **Phase A만** 다룬다.

---

## §0. 30초 요약

- **H0는 끝났다.** v2.1 검증 게이트 15건 = **PASS 14 / CAUTION 1 / PENDING 0** — 사용자 육안 재서명이 **2026-08-07 PASS로 완료**(`checklist_visual_h0v2.md` §6).
- **Phase A는 A0~A6 완료(+A5-b 분모 정정, +A5-c 게이트 리뷰 반영), A7 남음.**
  스위트 **646 passed / 3 skipped**.
  H1_SYNC 모드가 열렸다 — `--mode hr`로 K50_1 완주(감사 ON), H0 비트 동일.
  A3로 **측정 창 3층·`T_building_order`·로봇/배터리 KPI·R1~R6 렌더**가,
  A4로 **HR 골든패스 2케이스(전 스탬프 0틱 일치)**가,
  A5로 **B-게이트 10개(`analysis/verify_hr.py`)**가 들어왔다 — 4개 수요 티어 전건 통과.
- 착수 전 3차 점검에서 **결정 14건**이 확정됐고 계획서 4종이 그에 맞춰 개정됐다.
  상위 결정은 `research_plan_scie.md` §1 **#26~#30**으로 등재.
  **2026-08-11 결정 #31 추가** — 보행자 EV 대기 격하 · 외부성 지표 교체 ·
  가동률 분모 정정(§3.7·§3.8).
- **가장 큰 전제 변화 3가지**:
  1. **배터리·충전을 모델링한다**(결정 #26) — 설계 동결 R0-5 "충전 비활성"은 **폐기**.
  2. **로봇 5대는 K50 전용 크기다.** K200·K300은 어떤 스윕 조합으로도 정상 상태에 들지 않는다.
     **포화는 결함이 아니라 결과**이며, 게이트가 아니라 지표로 표현한다.
  3. **Phase 실행 순서가 `A → B → D1 → C → D2 → E → F`로 바뀌었다**(결정 #30).

**다음에 할 일 = Step A7** (§4). A5 게이트 리뷰는 **2026-08-11 실행·반영 완료**(§A5-c).
A6 단조성 5방향·극한 2케이스도 **2026-08-11 완료** — 4/5방향 PASS·1방향(④) TIE,
방향 ②·③은 각 1건씩 FAIL이나 원인 분석 완료(코드 미수정, 상세는 구현 로그 §A6).

---

## §1. 문서 지도 — 어디를 봐야 하나

정본 우선순위가 **역전돼 있는 곳이 있으니** 이 표를 먼저 볼 것.

| 문서 | 역할 | 주의 |
|---|---|---|
| `NEXT_SESSION.md` | **세션 재개용 포인터**(첫 5분에 읽을 것만) | **정본이 아니다.** 충돌하면 본 문서가 이긴다. 진행되면 갱신·삭제 |
| `scie_phase/review_phase_A_precheck.md` | **착수 전 점검(1~3차) + 결정 14건** | **§11.3이 ρ·수요 수치의 정본.** §2.1·§9.2.1의 표는 λ 정의 오류로 **폐기**됐다 |
| `scie_phase/phase_A_robot_h1.md` | Phase A 계획(무엇을 만드나) | 2026-08-06 개정 완료 |
| `scie_phase/phase_A_implementation_log.md` | **구현 로그(계획이 왜 틀렸나)** | Step 완료 시마다 절을 추가한다. **⑤ 이월 항목을 다음 Step 착수 전에 읽을 것** |
| `plan_hr_extension.md` | 원 실행 계획(R0 설계 동결·코드 위치) | **줄 번호는 신뢰하지 말 것** — R8·A0·A1이 계속 밀었다. 심볼로 찾는다 |
| `research_plan_scie.md` §1 | 사용자 확정 결정 #1~**#31** | 재론 금지. **#31이 #29의 근거와 W_EV 정의를 부분 대체**하고, **#22는 Fable 재사용 가능으로 개정**됐다 |
| `checklist_visual_h0v2.md` | **H0 전용** 육안 체크리스트 | 존치. §5 v2 서명·**§6 R8 재서명 모두 완료**(2026-08-07) |
| `checklist_visual_h1.md` | **H1 전용** 육안 체크리스트(신설) | §0의 렌더 요구 R1~R7 **전건 충족(A3)** — 이제 §1 실행이 가능하다. 서명은 A7 이후 |
| `verification_report_h0v2.md` | H0 검증 정본 | **§8(V21)이 인용 정본.** §2의 v2 수치는 창 정의가 달라 논문 인용 금지 |

---

## §2. 완료된 것

### 2.1 Step A0 — Phase A 인프라 (2026-08-06)

**왜 신설됐나**: 3차 점검에서 위험 순위가 뒤집혔다. A1의 로봇 코드는 H0에서 생성조차
되지 않지만, config 배선·보행자 감쇠·cap 분리는 **H0 실행 경로를 직접 건드린다.**

- `simulation/config_params.py` **신설** — `RobotParams`·`BatteryParams`·`HandoffParams`·`PedDecay`.
  **전 블록 선택적**(동결 회귀 config가 이 블록들을 갖고 있지 않다).
- `configs/baseline_10f.yaml` — `robot.n_robots` **3→5**, `robot.battery`·`handoff` 신설,
  `simulation.max_overrun_sec_robot: 32400`, `simulation.ped_decay`.
- 보행자 감쇠 = `_ped_rate_at()` + `_spawn_pedestrians` 1줄.
- `space.py` 로봇존 capacity **2→5**.
- `configs/modes/*.yaml` 4종에 **미사용** 헤더(어떤 코드도 읽지 않는다).

스위트 441 → **480**. 상세: 구현 로그 §A0.

### 2.2 Step A1 — 로봇 승객화 + 이종 정원 + 배터리 + FSM (2026-08-06)

- `simulation/agents/robot.py` **스텁 → 전체 구현**: `RobotState` 8상태 + `RobotLeg` 5레그
  + `REPORT_BUCKETS` 7버킷. 승객 프로토콜, `GraphWalker` 재사용(**새 이동 코드 0줄**),
  배터리 계정, `assign()`/`notify_rider_ready()` API.
- `elevator.py` 이종 정원: `can_board`·`_capacity_violated`·**`robot_board_denied`**.
- `control_system.choose_elevator(..., candidates=)` — 기본 None이 A1 이전과 동일.
- `model._audit_invariants` 이종화(로봇 ≤1대 · 전용카 탑승 0 · 사람 정원 분기).

스위트 480 → **503**. 상세: 구현 로그 §A1.

### 2.3 Step A2 — 핸드오프 라이더 + FCFS 배차 + 모델 배선 (2026-08-07)

- `simulation/agents/handoff_rider.py` **신설**: `HandoffRiderAgent` 4상태
  (WALK_TO_COUNTER → WAIT_ROBOT → HANDOFF → WALK_TO_EXIT) + `draw_handoff_sec()`
  (R0-3 `'hoff'` 3-워드 스트림, `max(x,0)` 절단 — 주문별 독립 Generator라 배차 순서가
  바뀌어도 draw가 이동하지 않는다).
- **함정 1 해소**: 라이더 조회 11개소를 `model.rider_cls`로 치환 + **생성 2개소도** 치환.
  `visualize.py`는 `ExternalRiderAgent` import 자체를 삭제.
- **함정 2 해소**: `model.robot_leg_records`(ord_id 키) — 로봇이 `assign`에서 개시해
  `_finish_trip`에서 발행. 라이더 레코드와 **ord_id 조인**으로 주문 타임라인 완성.
- `control_system`: `request_robot`·`robot_for`·`release_robot`·`_dispatch_robots`(FCFS).
- `model`: 로봇 함대 생성(H0은 빈 리스트) · 모드 게이트 **H1_SYNC만** 개방 ·
  `_carriers_settled()` H1 분기 · 틱 순서에 로봇 · 상태 frozenset에 H1 상태 3종.
- `run.py`: `--mode {h0,hr}` + 출력 파일명 접두사에 모드(`baseline_hr_*`).

스위트 503 → **530**. 상세·발견·이월: 구현 로그 §A2.

### 2.4 Step A3 — KPI + 측정 창 3층 + 실행기 (2026-08-11)

- **측정 창 3층**(§3.7) — `kpi._fixed_window()` = `[min ORD_TIME, max ORD_TIME]`.
  실측 확인: 같은 시나리오·seed에서 **H0와 H1의 고정창이 완전히 동일**하고
  배달창은 다르다(5,718 s vs 5,589 s). 층 계약은 `simulation.windows`로 산출물에 박힌다.
- **`T_building_order` 신설** = 라이더 입장 → 인도 완료(양 모드 정의 동일).
  인계 후 구간은 `t_order_post_handoff_sec`로 분리. **어느 쪽을 논문에 쓸지는 미정**(§5-3).
- EV별 `*_by_kind_fixed`(rider/pedestrian/**robot**)가 **정본**, 전용/공용 그룹은
  **파생**(전용 공집합이면 `None`). ⚠️ 함대 가동률은 **A5-b에서 `utilization_ops`로
  정정**됐다(결정 #31 · §3.7) — `utilization_fixed`는 존치하되 인용본이 아니다.
- 🔴 **2026-08-11 F2 교정(인적 규칙)** — EV별 **전창** 필드도 같은 규약으로 통일했다:
  ① `w_ev_mean_sec`·`w_ev_p95_sec`는 **사람만**(로봇 탑승 제외, `building.w_ev_mean_all_sec`
  와 동일 규칙). ② 전창 `n_boardings_by_kind`·`w_ev_*_by_kind_sec`에 **로봇 모드에서만**
  `robot` 키를 추가(H0 스키마 불변). `n_boardings`는 카 부하 계수라 종전대로 전 탑승이며,
  이제 by_kind 합과 정확히 일치한다. 수치 영향: H1 K50_1 s42에서 EV3
  `w_ev_mean_sec` 29.46→**25.37 s**, EV4 24.35→**23.36 s**(H0 산출물은 비트 동일).
- **`robot` KPI 섹션**(로봇 모드에서만 방출): 가동률(고정창)·7버킷 점유·배터리·
  `robot_board_denied`·`evsel_stale_ratio`·`n_requests_unserved_at_end`.
- `drain_span_sec`·`drain_deliveries`·`drain_ev_boardings`·`drain_robot_trips`.
- `run.py`: **`config` dict 주입** + `n_robots` 오버라이드(Phase D 스윕 준비) + 모드별 배너.
- `visualize.py`: **R1~R6 전건**(◆ 로봇 마커·버킷/SOC 라벨·카운터 노드·사이드바
  로봇 블록·공용/전용 표기). R7은 A2에서 완료.

스위트 530 → **565**. 상세·발견·이월: 구현 로그 §A3.

### 2.5 문서

계획서 4종 개정(`phase_A_robot_h1` · `plan_hr_extension` · `phase_D_experiments_economics` ·
`research_plan_scie`) + 신설 2종(구현 로그 · H1 체크리스트).

---

## §3. Phase A에서 반드시 알아야 할 규약 8가지

`HANDOFF_v2.md` §3의 H0 규약 8가지에 더해, **Phase A 고유의 것**만 적는다.

### 3.1 로봇 FSM은 8상태 + 직교 속성이다 (결정 4)

사용자가 제안한 9상태를 그대로 쓰면 **분할(partition)이 아니다** — "고객에게 이동"이
"EV 앞 대기"와 "EV 탑승"을 포함해 체류시간이 중복 계상되고 B4·B5 항등식이 닫히지 않는다.
또 **인계(HANDOFF)와 라이더 대기(WAIT_RIDER)가 누락**돼 있었다.

```
IDLE / MOVING(leg) / WAIT_RIDER / HANDOFF / WAIT_EV(dir) / RIDING(dir) / DROP / CHARGING_BLOCKED
```
속성: `leg`(5종) · `direction`(±1) · `return_reason ∈ {idle, low_soc}` · `is_charging`(파생).

**`CHARGING_BLOCKED`와 `IDLE`의 차이는 충전 여부가 아니라 배차 가능성이다.**
둘 다 충전한다(결정 #19의 대기＝충전 통합). 이 구분이 없으면 "40%까지 충전 후 재투입"을
표현할 수 없다.

**보고·논문 그림은 7버킷**(`REPORT_BUCKETS`)으로 집계한다. 새 상태를 추가하면
버킷 누락이 즉시 예외가 되고 테스트가 전 상태 커버를 강제한다.

### 3.2 종료 조건은 "전원 IDLE"이 아니다

```
H1 완료 = 전 주문 배달 ∧ 라이더 전원 건물 밖
        ∧ 로봇 전원 로봇존에 (IDLE ∨ CHARGING_BLOCKED)
```
`CHARGING_BLOCKED`를 빼면 마지막 배달 직후 SOC가 낮은 로봇 때문에 **run이 끝나지 않는다.**
구현은 `model.py` `_carriers_settled()`의 H1 분기다(A2에서 채웠다).

### 3.3 EV는 걷기 **전에** 한 번만 고른다

라이더(`external_rider.py`)와 동일하다. 도착 시 다시 고르면 **로봇만 라이더보다 똑똑해져**
W5d가 재는 designated-dispatch 대가(stale 52.95% · harm ≤28.81 s)의 비교가 깨진다.
로봇은 후보만 공용 카로 제한한다(`candidates=`), 휴리스틱과 타이브레이크는 동일하다.

### 3.4 `WAIT_EV`는 **0틱**일 수 있다

유휴 EV가 같은 층에 서 있으면 hall call이 등록된 그 틱 안에 곧바로 태운다.
**A4 수기 체인에서 상행 EV 대기를 양수로 가정하면 틀린다.**
상태 관측 테스트는 틱 경계가 아니라 **서브스텝마다** 샘플링해야 한다.

### 3.5 배터리 임계는 코퍼스에서 발화하지 않는다 — 그게 정상이다

1,300 Wh에 배달 1건이 ~9~10 Wh다. 점심 피크 run은 **SOC 43~90%**로 끝난다.
이것은 결함이 아니라 **결과**이며 "1.3 kWh급 로봇은 점심 피크 운영의 제약이 아니다"로
보고한다. 발화 경로는 ①`tests/test_a1_robot.py`의 합성 케이스 ②**Phase E `soc_init` 스윕**뿐이다.

⚠️ 실효 충전 속도는 명판보다 느리다: 20→40%가 명판 20분인데 **실제 21.7분**이다
(도킹 중에도 대기 소모 1.0 Wh/min이 흘러 순 충전 12.0 Wh/min). 논문 각주 필요.

### 3.6 포화는 게이트가 아니라 지표로 표현한다

실측 건물 도착률 기준 ρ(baseline 5대·공용 2대):
**K50 0.50 ✅ / K100 0.97 ⚠️ / K200 2.03 ❌ / K300 3.26 ❌**
격자 최대(9대·공용4대)에서도 **K200 0.96 / K300 1.52**다.

- `delivered == K`는 **엄격하게 유지**한다.
- cap 종료는 **게이트 FAIL이 아니라 실행 실패** → `max_overrun_sec_robot`을 올려 재실행.
- 포화의 기록은 `robot_queue_wait_p95` · `T_building_order_p95` · `drain_span_sec`.

⚠️ **파생 함정**: H0에서 판별력이 없던 SLA가 H1에서 대량 위반으로 돌아설 수 있다.
"H1이 SLA에 판별력을 되살렸다"로 읽으면 안 된다 — **함대 규모 미달의 신호**다.

### 3.7 측정 창은 4개다 (결정 #29 + **#31 정정**)

> 🔴 **2026-08-11 사용자 확정(결정 #31)** — 구 판본을 읽었다면 두 가지가 바뀌었다:
> 1. **함대 가동률의 분모는 고정창이 아니라 `utilization_ops`**다.
> 2. **보행자 EV 대기는 헤드라인 KPI가 아니라 타당성 가드로 격하**됐고,
>    외부성 자리에는 **로봇 EV 대기 · `board_denied`**가 들어왔다(§3.8).
>    구 판본의 "한산한 드레인에 희석된다"는 근거도 **실측과 반대**였다.

| 층 | 창 | 무엇을 재나 | 왜 그 창인가 |
|---|---|---|---|
| ① | **고정창** `[첫 주문, 마지막 주문]` | 자원 점유(EV 가동률·재차·보행자 EV 대기) | 양 끝이 **시나리오 파일**에서만 오므로 모드·함대·seed에 불변. **모드 간** 비교의 유일한 apples-to-apples 슬라이스 |
| ② | **창 없음** | 주문 단위(T_e2e · `T_building_order` · SLA) | 주문 집합이 모집단이다 |
| ③-a | **ops 창** `[첫 주문, 마지막 운반체 정착]` | **함대 가동률(인용본)** | ↓ |
| ③-b | 배달창·orderspan | 진단 전용 | **모드 내에서만.** 오른쪽 끝이 시뮬레이션에서 온다 |

**왜 가동률만 창이 다른가**: 고정창의 *길이*는 K와 무관하게 ~3,500 s로 일정하다 —
주문이 늘면 점심 피크는 **길어지지 않고 촘촘해진다.** 그래서 고정창은
`5대 × 3,500 s`짜리 **고정 크기 상자**이고, 함대가 그 안에서 포화하면 비율은 함대가
아니라 창이 정하는 천장에 붙는다(K200 **0.735** / K300 **0.738**, 그 사이 일감은 +48%).
K300에서는 **로봇 작업의 82 %가 고정창 밖**이다. `ops` 창으로는 0.905 / 0.932로 갈린다.
`utilization_full`을 쓰지 않는 이유는 그 분모에 **워밍업 600 s**가 들어 있어서다 —
주문이 없는 구간이라 로봇이 일할 방법이 없다. **가동률에는 지킬 모드 간 비교가 없다**
(H0에 함대가 없다). ops 창은 H0에서 **기존 `delivery_window`와 정확히 일치**한다.

창 밖 드레인은 `drain_*`로 별도 보고 — "로봇 배달이 피크 부하를 피크 이후로 이연시킨다"가
그 자체로 발견이다. ⚠️ 드레인은 **한산하지 않다**: 배달이 주문보다 ~20분 늦어 백로그는
마지막 주문 직후에 최대이고, 실측 EV 대기도 드레인이 피크보다 높다(K300_4 공용 카 H0:
창 안 29.84 s vs 드레인 39.28 s).

### 3.8 외부성은 보행자가 아니라 로봇에서 관측된다 (결정 #31)

착수 당시 계획은 "로봇이 공용 EV3·EV4를 잠식해 **재실자**가 손해를 본다"였다.
A5-b 실측이 그것을 지지하지 않는다:

| Δ = H1 − H0 | K50_1 | K200_1 | K300_4 |
|---|---|---|---|
| T_lobby(라이더 체류, **원가 반영**) | −163.8 s | +2,473.2 s | +4,779.7 s |
| 로비 원가 | −18,990원 | +1,282,210원 | +3,955,522원 |
| **보행자 EV 대기** | **+0.92 s** | **−3.86 s** | **−5.75 s** |

보행자 대기는 주 지표의 **1/1000**이고 고부하에서 **부호가 H1에 유리**하며, 애초에
**OPEX에 계상되지 않는다**(`lobby_cost`는 라이더 체류만).

- **보행자 EV 대기의 역할 = 타당성 가드.** 보행자가 공용 카를 회피하면 로봇이 **빈
  샤프트를 물려받아** 이득이 과대평가된다 — W5c가 원래 지키던 것이 이것이다.
  EV별 분리 계측은 그 목적으로 **존치**한다. 부수적으로 "로봇 릴레이는 재실자의
  승강기 서비스를 악화시키지 않는다"는 **음성 결과 한 줄**로 보고한다.
- **본 지표 = 로봇의 EV 대기 + `board_denied`.** 편도 31.8~37.6 s × 왕복 =
  **배달당 60~75 s**가 `T_building_order`의 **임계 경로 위**에 있고, `board_denied`는
  K50 17 → K200 73 → K300 124로 는다. 건물 수직교통이 공유 자원이라는 사실이 실제로
  무는 대상은 **보행자가 아니라 로봇**이다.

⚠️ **A6 단조성 ②·D1 RQ1의 문구가 여기 걸려 있다** — "공용 EV 보행자 대기 ↑"를
게이트로 삼으면 정상 모델이 FAIL한다.

---

## §4. 남은 작업

### Step A2 — 핸드오프 라이더 + FCFS 배차 + 모델 배선 ✅ **완료 2026-08-07**

구현 상세·발견·이월은 `scie_phase/phase_A_implementation_log.md` **Step A2**가 정본.
게이트 2건 PASS: `--mode hr --audit` K50_1 완주(6,311틱·50/50 배달) + H0 비트 동일성.

**A3~A4가 반드시 알아야 할 것 3가지**:
- **배차 지연 0틱 · 인계 지연 1틱**은 서로 다른 사실이다. `_inject_riders`가
  `control.step`보다 앞이라 라이더는 입장한 틱에 배차되고, 로봇은 라이더보다 **먼저**
  step하므로 `notify_rider_ready`는 다음 틱에 반영된다.
- **틱 순서 로봇 → 라이더를 바꾸지 말 것.** 뒤집으면 A1이 문서로 남긴 1틱 지연이
  사라져 A4 수기 체인이 무효가 된다.
- **H1의 `T_lobby`는 H0와 다른 양이다**(인계 대기 포함, ρ>1에서 발산). 진짜 비교
  대상은 A3가 신설할 `T_building_order`.

### Step A3 — KPI + 측정 창 3층 + 실행기 ✅ **완료 2026-08-11**

구현 상세·발견·이월은 `scie_phase/phase_A_implementation_log.md` **Step A3**가 정본.
스위트 530 → 565, H0 동결 게이트 전건 통과.

**A4~A7이 반드시 알아야 할 것 4가지**:
- **`T_building_order`는 입장 기준**(라이더 입장 → 인도 완료)이고 로봇 대기를 **포함한다**.
  계획서 괄호의 "인계 시작 → 인도 완료"는 `t_order_post_handoff_sec`로 따로 있다.
  **논문 인용본은 아직 미정**(§5-3).
- **고정창은 배달을 다 담지 않는다.** K50_1에서 50건 중 26건이 창 밖(드레인)에서
  배달된다 — 자원 점유 창이라 옳지만, 그림 캡션에 "창 = 주문 발생 구간"을 반드시 쓴다.
- **로봇 stale은 후보군 2대 기준**이다. H0의 52.95 %(4대 기준)와 나란히 쓰려면
  `n_candidates`를 같이 인용해야 한다.
- **보행자 재배치가 1차 신호다**(구현 로그 §A3-②-1). K50_1에서 공용→전용으로 탑승
  28건이 이동했고 전용 카 대기는 오히려 **늘었다**. 단일 seed·ρ=0.50이므로 부호 주장 금지.
  **ρ≈2(K200_1)에서는 격차가 뚜렷하다** — 공용 EV 가동률 96.4/94.8 % vs 전용 85.5/86.5 %,
  보행자 대기 29.81 s vs 25.30 s. **양면 외부성 판정은 고부하 구간에서** 해야 한다.

### Step A4 — HR 골든패스 2케이스 ✅ **완료 2026-08-11**

`tests/test_vv_golden_path_hr.py` **7건**. 케이스 ①(주문 1 × 유휴 함대)·②(주문 2 × 로봇 1대)
모두 **전 스탬프 0틱 일치**. 상세는 구현 로그 **§A4**가 정본.

**A5~A7이 반드시 알아야 할 것 3가지**:
- **틱 문법은 "누가 경로를 계획했는가"에 달려 있다**(구현 로그 §A4-②-1).
  같은 틱의 앞선 액터가 계획하면 도착 = `T + w − 1`, 자기 step의 지나간 분기나
  **뒤선** 액터(EV는 로봇 뒤에 step)가 계획하면 `T + w`다. B4·B5가 이걸 섞으면
  전 주문에 1틱 잔차가 남는다.
- **`office_positions_m`은 office_id 순서가 아니다** — office_1이 7 m, office_6이 2 m.
  기하 검산에서 `enumerate(..., start=1)`로 id를 붙이면 조용히 틀린다.
- **틱 순서는 이제 테스트로 강제된다.** 로봇→라이더를 뒤집으면 골든패스 7건 중 5건 FAIL.

**로봇 기하 상수** (R7 재배치 이후, A4에서 그래프로 재확인):
홈→카운터 **5 m** · 카운터→공용 EV 승강장 **7 m** · 1F EV→홈 **4 m** ·
EV(18 m)→사무실 = **1 m(EV 지선) + |18 − pos| + 3 m(사무실 지선)**,
복도거리 `[4, 6, 9, 11, 14, 16]` m(평균 10.0). 로봇 속도 **1.0 m/s**(사람 1.2의 0.833배).

### Step A5 — B-게이트 B1~B11 ✅ **완료 2026-08-11** (리뷰 반영 = A5-c)

`analysis/verify_hr.py` **10 게이트**(B1~B5·B7~B11 — **계획에 B6은 없다**, ②-5) +
`tests/test_verify_hr.py` **42건**. 상세는 구현 로그 **§A5**가 정본.

```bash
.venv/bin/python -m simulation.run --scenario data/data1/K50_1.json \
    --floor-profile uniform --mode hr --out results/baseline_hr_K50_1_uniform_s42.json
.venv/bin/python -m analysis.verify_hr results/baseline_hr_K50_1_uniform_s42.json
```

> 🔴 **A5-c(게이트 독립 리뷰, 2026-08-11)**: 리뷰가 **게이트를 통과시켜서는 안 될 것을
> 통과시키는 결함 9건**을 잡았다 — 그중 **B7의 추이성 붕괴**(동률 도착에서 FCFS 위반이
> 통과), **None 가드 누락 5개소**(게이트 전체가 크래시해 나머지 판정이 사라짐),
> **B11이 정상 run을 FAIL**(정책 리터럴), **자기 정합성을 보존으로 착각**(주문을
> 전부에서 지우면 10/10 PASS)이 핵심이다. 테스트도 스스로를 속이고 있었다
> (`_assert_only_failure`가 "only"를 안 봤고, 크래시 단언이 항진명제였다).
> **전부 수정·회귀 고정 완료. 상세는 구현 로그 §A5-c.**
>
> ⚠️ **A7 착수 시 우선 처리**: 리뷰가 H0 A-게이트 대비 **누락 8건**을 실측으로 보고했다.
> 특히 **주문 결과(`t_e2e`·SLA)와 워밍업 적정성이 무게이트**다 — `t_e2e = 1.0 s`로
> 바꿔도, `warmup` 블록을 삭제해도 전건 PASS다. 구현 로그 §A5-c-④ 표가 정본.

**A6·A7이 반드시 알아야 할 것 4가지**:
- ⚠️ **A6 단조성 ②의 함대 부하는 `utilization_ops`로 판정할 것**(A5-b, 사용자 지적).
  고정창 가동률은 K200 0.735 / K300 0.738로 **판별력을 잃는다** — 고정창의 *길이*가
  K와 무관하게 ~3,500 s로 일정해서(피크는 길어지지 않고 촘촘해진다) 고정 크기 상자가
  되기 때문이다. K300에서는 **로봇 작업의 82 %가 창 밖**이다.
  `utilization_ops` = `[첫 주문, 마지막 운반체 정착]`은 0.428 / 0.905 / 0.932로 갈리고,
  `utilization_full`과 달리 분모에 워밍업 600 s를 넣지 않는다. H0에서는 이 정의가
  **기존 `delivery_window`와 일치**한다.
- **게이트는 포화를 판정하지 않는다.** 대기 p95가 136 s(K50)에서 9,533 s(K300)로
  70배가 돼도 10/10 PASS다. 포화는 전부 보고행(`robot_queue_wait_p95` ·
  `T_building_order_p95` · `drain_span_sec`).
- **cap 종료는 게이트 FAIL이 아니라 실행 실패**다(B11이 그렇게 말한다).
  K300_4는 uniform·seed 42에서 **16,338틱**에 cap 없이 완주했다.
- **B7은 같은 틱 도착 쌍을 판정하지 않는다**(힙 시퀀스가 산출물에 없다). K200에서 6쌍.

### Step A6 — 단조성 **5방향** + 극한 2케이스 ✅ **완료 2026-08-11**

①로봇 **1→3→5** ⇒ 로봇 대기↓ ②K↑ ⇒ **`utilization_ops`↑ · 로봇 EV 대기·`board_denied`↑**
③저부하 HR < H0 **④K↑ ⇒ 충전 이벤트↓·종료 SOC↓** **⑤공용 EV 2→3→4 ⇒ 로봇 대기↓**.

⚠️ **②의 문구가 결정 #31로 바뀌었다**(§3.8). 구판은 "가동률·**공용 EV 보행자 대기**↑"였는데
ⓐ가동률을 **고정창**으로 재면 K200 0.735 / K300 0.738로 FLAT이라 정상 모델이 FAIL하고
ⓑ보행자 대기는 실측이 **K↑에서 오히려 감소**한다(H1 30.08 → 29.73). 둘 다
`utilization_ops`와 **로봇 측** 경합 지표로 교체됐다.

**실측 결과** (10 seed 평균, `experiments/vv_monotonicity_hr.py` + `results/vv/monotonicity_hr.csv`):
①**PASS**(로봇 1→3→5: 2,866.7→219.8→20.3 s) ②**FAIL**(`utilization_ops`·`board_denied`는
3/3 PASS이나 로봇 EV 대기가 K200→K300에서 41.1→35.1 s로 반전 — 원인은 게이트 결함이
아니라 K300의 긴 드레인이 배경 보행자 감쇠 구간을 K200보다 훨씬 깊이 파고들어 런 전체
풀링 평균을 희석하기 때문; decay-이전 구간만 비교하면 41.2→41.5 s로 방향이 회복된다)
③**FAIL**(K50_1 페어드: H0 181.1 s vs HR 188.0 s — §2 A6 사전 경고대로 저부하 순이득이
얇아 음수로 뒤집혔다. K50_2는 반대 부호(−4.5%)라 "마진이 얇다"는 판정 자체가 실증됨)
④**TIE**(충전 이벤트 0→0→0→0, §3.5 정본 기대대로; 종료 SOC는 3/3 PASS로 99.9→59.1%)
⑤**PASS**(공용 EV 2→3→4: 41.1→34.7→31.9 s). 극한 2케이스(로봇 1대 포화 K100_1·보행자
×10 K50_1) 모두 프로덕션 기본 cap 안에서 완주, `verify_hr` 10/10 PASS. ②·③의 FAIL은
코드·게이트를 고쳐 지우지 않았다 — 원인 분석은 구현 로그 **§A6**이 정본.

### Step A7 — `max_overrun` 실측 확정 + 전수 배터리 (소넷 / medium, ~1일)

**선행**: K300_4를 **43,200 s cap**으로 1 run 돌려 드레인 실측 → **×1.3**으로
`max_overrun_sec_robot` 확정(현 32,400은 추정치). R8-d의 `RUSH_OVERRUN_SEC` 관례.
그 뒤 28×3 = **84 run** 전수 B1~B11 PASS. 관측 3항목(deny의 K 의존 · 로봇 공용 EV
직렬화 · 저층 배달 부호) + **병목 이전 지점**(§3.6).

---

## §5. 사용자 액션 대기 1건

| # | 항목 | 상태 |
|---|---|---|
| 1 | ~~**H0 V21-VISUAL 재서명** — `checklist_visual_h0v2.md` §6, K50_1 1회 4항목~~ | ✅ **2026-08-07 PASS 서명 완료.** K50_1 완주 관찰, 4항목 전건 기대 일치 |
| 2 | **H1 육안 서명** — `checklist_visual_h1.md` 15항목 | A7 이후 |
| 5 | ~~**보행자 EV 대기의 격하 여부**~~ | ✅ **2026-08-11 격하 확정 = 결정 #31.** §3.8 신설, 문서 6종 정합 완료 |
| 4 | ~~**A5 게이트 독립 리뷰 1회**~~ | ✅ **2026-08-11 실행 완료**(오퍼스 `max`, 5/7 앵글). 결함 9건 + 테스트 취약점 2건 적발·수정, 회귀 15건 추가. 누락 8건은 A7로 이월 |
| 3 | **`T_building_order` 논문 인용본 선택** — ⓐ`t_building_order_sec`(라이더 입장 → 인도, 로봇 대기 **포함**, H0 `T_lobby`와 같은 구간) ⓑ`t_order_post_handoff_sec`(인계 시작 → 인도). **코드는 이미 둘 다 낸다** | **Phase F 집필 전까지. 지금 결정 불필요** |

**앱 구동**:
```bash
SOLARA_KERNEL_CULL_TIMEOUT=30s SOLARA_ASSETS_PROXY=True \
  .venv/bin/solara run simulation/app.py --host 0.0.0.0 --port 8765
```
원격은 SSH 터널(`ssh -L 8765:localhost:8765 …`). 2026-08-06 확인: 자산 전부 로컬 200 서빙.

⚠️ **`SOLARA_KERNEL_CULL_TIMEOUT`을 빼지 말 것.** 기본값은 24h다. 소켓이 한 번 끊기면
(SSH 터널 blip 등) 그 커널이 24시간 살아남고, 그 안의 mesa 재생 스레드도 계속 돈다 —
`ModelController`의 루프는 `playing`/`running`만 보고 페이지 연결은 보지 않기 때문이다.
사용자가 리프레시하면 새 커널의 렌더 트리와 고아가 충돌해 `force_update()`가
`reacton/core.py`의 `assert widget.model_id in _get_widgets_dict()`에서 터지고,
`ModelController.step()`이 이 예외를 `error_message`로 삼켜 **재생 루프가 죽는다**(=
"중간에 멈추고 refresh만 뜬다"). 2026-08-07 실측: 단일 커널 7.2 ticks/s → 리프레시 후
1.6 ticks/s + `AssertionError` 2건, 고아 커널을 닫으면 **0건**으로 완전 해소.

⚠️ 관련 구조 제약: **모델을 모듈 레벨에 두지 말 것.** solara는 앱 스크립트를 서버당
1회만 실행해 캐시하므로 모듈 레벨 객체는 전 세션이 공유한다. `simulation/app.py`는
`make_model()` + `Page`의 `use_memo`로 세션별 모델을 만든다(2026-08-07). 회귀 가드 =
`tests/test_visualize.py::test_app_builds_solara_page`.

**성능 참고**: 렌더 1회가 1.3~1.7초(플롯 8종 PNG ~900ms + 단면도 265ms +
datacollector 데이터프레임 8회 재생성 162ms)인데 `play_interval=300`이라 실효
**7.2 ticks/s** — K50_1 완주(6,318틱)에 약 15분 걸린다. 급하면 사이드바
**Render Interval** 슬라이더를 올린다(스텝 자체는 0.12ms/틱로 사실상 공짜).

---

## §6. 현재 상태 재현·확인

```bash
cd /home/sw/Research/abm_new
.venv/bin/python -m pytest -q                 # 646 passed / 3 skipped
.venv/bin/python -m pytest tests/test_a0_config_wiring.py tests/test_a0_ped_decay.py -q   # 39
.venv/bin/python -m pytest tests/test_a1_robot.py -q                                       # 23
.venv/bin/python -m pytest tests/test_a2_handoff.py -q                                     # 26
.venv/bin/python -m pytest tests/test_a3_kpi.py tests/test_a3_visual.py -q                 # 35
.venv/bin/python -m pytest tests/test_vv_golden_path_hr.py -q                              # 7
.venv/bin/python -m pytest tests/test_verify_hr.py -q                                      # 59
.venv/bin/python -m pytest tests/test_vv_extreme_hr.py -q                                  # 2 (A6 극한)
```

**A6 단조성 5방향 재실행**(~5분, 180 run):
```bash
.venv/bin/python -m experiments.vv_monotonicity_hr
# writes results/vv/monotonicity_hr.csv — 상세는 구현 로그 §A6
```

**H1 스모크(A2 게이트)**:
```bash
.venv/bin/python -m simulation.run --scenario data/data1/K50_1.json \
    --floor-profile uniform --mode hr --audit
# mode=h1_sync ... K=50 delivered=50 ticks=6311
```

**H0 무교란 확인(Step 완료 시마다)**:
```bash
.venv/bin/python -m pytest tests/test_h0_frozen_snapshot.py tests/test_vv_determinism.py \
    tests/test_vv_golden_path.py tests/test_vv_golden_path_v2.py tests/test_vv_extreme.py -q
```

**스위트 수 이력**: v2.1 서명 시점 437 → A0 착수 시점 **441**(계획서의 "440"은 표류값)
→ A0 후 **480** → A1 후 **503** → A2 후 **530** → A3 후 **565** → A4 후 **572**
→ A5 후 **614** → A5-b 후 **619** → A5-c 후 **634** → Fable F1~F9 리뷰 반영 후 **644**
→ A6 후 **646**(`tests/test_vv_extreme_hr.py` 2건 신설; 단조성 5방향은 pytest 래퍼가
없다 — H0의 `vv_monotonicity.py`와 동일 관행, `experiments/vv_monotonicity_hr.py`로
별도 재실행).

---

## §7. 아직 손대지 않은 이월 항목

구현 로그 §A0-⑤ · §A1-⑤ · §A2-⑤ · **§A3-⑤**가 정본. 요약:

| # | 항목 | 대상 |
|---|---|---|
| 1 | ~~`run.py`에 **`config` dict 주입 경로**~~ | ✅ A3 완료(`n_robots` 오버라이드도 함께) |
| 2 | 신규 검증은 **보행자 0 · 주문 1~2건 · EV 1대** 축퇴 설정에서 먼저 돌릴 것 | 전 Step |
| 3 | 기준선·오라클은 `results/`와 **`analysis/*_insights/` 양쪽**을 뒤질 것 | 전 Step |
| 4 | 비트 동일성 비교는 `json.dumps(..., default=str)`로 **NaN 동치화** | 전 Step |
| 5 | `analysis/h0v21_stats.py:606` `ROBOT_FLEET_SIZES`에 **7·9 누락**, `:968` 주석 "n_robots = 3" | A6/A7 또는 Phase D |
| 6 | 주문 조작 합성 케이스는 **`dataclasses.replace()`**(`DispatchOrder`는 frozen) | A2·A4 |
| 7 | 충전 실효 21.7분(명판 20분)을 B10 정보행 + 논문 각주로 | A5 · Phase F |
| 8 | 고정창이 **배달 절반을 창 밖에 남긴다**(K50 26/50) — 그림 캡션에 창 정의 명시 | A5(B8) · Phase F |
| 9 | **보행자 재배치**(공용→전용 탑승 이동)를 관측 항목으로 등재 | A7 · D1 |
| 10 | `drain_span_sec`·`robot_wait_p95`를 **B-게이트 판정식에 편입** | A5 |
| 11 | 로봇 stale은 **후보군 2대 기준** — `n_candidates`와 함께 인용 | A7 · Phase F |
| 12 | **deny 상한 캘리브레이션** — H0 v2 "공용 EV 사람 ≥12명 tick 비율"이 필요(현 `_ev_pax_cum`은 누적합이라 비율 불가) | A7 |
| 13 | **B4는 EV 대기를 관측값으로 받는다** — hall call ↔ 탑승 정합은 어느 게이트도 안 본다 | A7 |
| 14 | B7이 **같은 틱 도착 쌍을 미판정**(힙 시퀀스 부재). 판정하려면 `arrival_seq`를 레코드에. ※A5-c에서 **그룹 경계는 판정하도록 수정**됨 — 남은 것은 그룹 *내부*뿐 | A7 · D1 |
| 15 | **A5-c 리뷰가 보고한 H0 대비 누락 8건** — 특히 ⓐ주문 결과(`t_e2e`·SLA) 하한 ⓑ워밍업 적정성(A13)이 **무게이트**다. 구현 로그 §A5-c-④가 정본 | **A7 우선** |

---

## §8. Phase A 이후 (결정 #30 — 순서가 바뀌었다)

```
A(H1) → B(H2) → D1(3모드 실험 + sizing 스윕) → C(H3) → D2(H3 편입 + 락커) → E → F
```

- **D1**: 3모드 × 28 × 30 = 2,520 run + 로봇 {5,7,9} × 공용 EV {2,3,4} sizing 스윕.
  공용 3대는 **`{EV2,EV3,EV4}`** 하나만(기하는 대칭이나 `ev_id` 타이브레이크가 비대칭).
- **참조 arm**(K200 16대 · K300 25대, 60 run): RQ3 대조점 **이자**
  **Phase B G/G/c 대조의 주 재료**(ρ<1 전제를 만족하는 유일한 두터운 표본).
- **D2**: H3만 840 run 추가. **D1 재실행 불요** — CRN이 seed 재사용으로 성립한다.
- 파일명·라벨은 유지한다(상호참조 보호).
