# H0 수정 계획서 (plan_h0_revision.md) — H0 v2 개정

작성: 2026-08-03 (세션 Fable). 지위: **H0 v2 개정의 정본 실행 계획서**.
상위 정본은 `etc/research_plan_scie.md`(연구계획서)이며, 본 계획 승인 시
연구계획서 §1 결정 로그에 결정 #16~#22로 등재하고 §6 로드맵에 Phase R(개정)을
Phase A 앞에 삽입한다.

상태: **사용자 승인 완료 (2026-08-03)** — §8 확인 6건 + 추가 지시 2건(git 미사용,
R1·R2 = Fable 배정) 회신. 확정값은 §8 참조. 실행 진행 중(§9 로그).

---

## 목차

- §0. 개요 — 요구사항 7건과 반영 매핑
- §1. 설계 사양 (확정 제안값)
- §2. 아카이브 전략 (Step R0)
- §3. 코드 수정 단계 (Step R1~R5)
- §4. 검증 계획 (V2 게이트 — 기존 L1~L7 체계 승계)
- §5. 문서 수정 방안 (research_plan_scie / scie_phase / 신규·아카이브 목록)
- §6. 모델·effort 배정표
- §7. 리스크와 주의사항
- §8. 사용자 확인 대기 항목
- §9. 진행 로그

---

## §0. 개요 — 요구사항 7건과 반영 매핑

2026-08-03 사용자 지시 7건 + 3차 추가 지시 1건(요구 8)을 다음과 같이 반영한다.

| # | 요구사항 | 반영 위치 |
|---|---|---|
| (1) | EV 4대 확대, 복도 중앙 북측 2·남측 2 배치, 시각화 비겹침 | §1.2, §3 R1·R2, §1.5 |
| (2) | 수요 시나리오 1차 K50/K100/K200, 극단 K300 후행 (K500·K750·K1000 **본 실험에서 보류**, 2026-08-04 재확인) | §1.4, §3 R5 |
| (3) | H0 수정·검증 계획서 + scie_phase·연구계획서 수정 + v1 아카이브 분리 | §2, §4, §5 |
| (4) | 로봇 충전 B1→1F 이전, 대기 중 수시 충전, B1 구현 삭제 | §1.3, §3 R1·R3 |
| (5) | 층당 1,200㎡ 확장, 상주 100명/층, 12실/층 유지, 중복도 유지 | §1.1 |
| (6) | 시각화 모델 수정 | §1.5, §3 R4 |
| (7) | H0 관련 파일 전수 검토 (지시 목록 외 추가 식별분 포함) | §2.2 |
| **(8)** | **지하 2개층(B1·B2) 신설 — 사람 승하차 전용, EV 이용률 변화 목적. 사무공간 없음. 로봇 대기·충전은 1F 유지** (2026-08-03 3차 지시) | **§1.6, §3 R6** |

핵심 원칙 (레포 확립 관례 승계):

1. **v1 동결 후 개정** — 기존 H0(이하 "H0 v1")은 git 태그 + 아카이브 폴더로
   동결하고, 개정판(이하 "H0 v2")은 동일 파일을 인플레이스 수정하되 v1과
   섞이는 산출물·문서가 없도록 한다.
2. **테스트도 스펙** — 각 Step에서 코드와 테스트를 함께 개정하고 단계 경계마다
   전체 스위트 green을 유지한다(스냅샷 게이트만 §4 V2-SNAP에서 마지막에 교체).
3. **코드가 진실** — 문서 수치는 스크립트 자동 생성만 인용.
4. H0 v2 완료·검증 후에 Phase A(로봇+H1)에 착수한다. `plan_hr_extension.md`의
   Phase A 착수는 본 개정 완료 시점으로 순연.

---

## §1. 설계 사양 (확정 제안값)

> ⚠️ **2026-08-06 — 창(window)·종료(termination)는 이 문서 밖에서 개정됐다.**
> 본 계획서(R0~R7)는 **건물 기하와 자원**을 다루고, 시뮬레이션의 **초기 상태와
> 완료 조건**은 **R8**에서 다시 세웠다. 그래서 아래 §1.x에 남아 있는 "워밍업 1시간
> (`window_margin_sec` 3,600 s)"·"보행자가 다 빠질 때까지 돈다"류의 전제는
> **더 이상 논문 트랙의 동작이 아니다.**
>
> - 정본: **`etc/plan_h0v21_window.md`**(§1 실측 근거 · §2 설계 · §11 진행 로그)
> - 규약 요약: **`etc/HANDOFF_v2.md` §3.8** — 정책이 `legacy_margin` / `delivery`
>   **둘**이고, config에 키가 없으면 legacy(= 이 문서의 전제)로 동작한다
> - 재검증 결과: `etc/verification_report_h0v2.md` **§8**
>
> **기하·자원 사양(§1.1~§1.6)은 R8이 한 줄도 건드리지 않았으므로 그대로 유효하다.**
> 바뀐 것은 창·종료뿐이고, 그래서 육안 체크리스트도 기하 항목은 면제됐다.

### §1.1 건물 기하 — 층당 1,200㎡ 확장 (요구 5)

현행(`configs/baseline_10f.yaml`): ~800㎡/층(28.3m 풋프린트), 복도 27m,
12실/층(북6·남6, 위치 [3,7,11,15,19,23] 대칭), 상주 80명/층.

제안(v2):

| 항목 | v1 | v2 제안 | 근거 |
|---|---|---|---|
| 층면적 | ~800㎡ | **~1,200㎡** (풋프린트 ~34.6m 정방형) | 요구 5 |
| corridor_length_m | 27.0 | **34.0** | √1200≈34.6m 풋프린트에 내접 |
| 사무실 수 | 12 (북6·남6) | **12 (북6·남6, 동일)** | 요구 5 "12실/층 기존과 동일" |
| office_positions_m | [3,7,11,15,19,23]×2 | **[2,7,12,22,27,32]×2** (북·남 거울 대칭) | R1은 [4,9,14,19,24,29] 등간격이었으나 **2026-08-04 재배치**(§10 R7): 복도 중점 17m 거울 대칭 + 12~22m를 EV 서비스 코어로 비움 |
| 사무실 규모 | ~66㎡/실 | **~85㎡/실** (12×85=1,020 + 복도·코어 ~180) | 1,200㎡ 배분 |
| occupancy_per_floor | 80 | **100** | 요구 5 |
| 상주 합계 | 720 (2~10F) | **900** (9개 사무층 × 100) | — |
| pedestrian.arrival_rate_per_min | 6.0 | **7.5** | 1인당 트립율 0.5회/h 유지: 900×0.5/60 |
| floor_height_m / n_floors | 4.0 / 10 | 4.0 / 10 (유지) | 변경 지시 없음 |
| 중복도(양측 배치) | 유지 | **유지** | 요구 5 |

층수·층고·EV 카 용량(15인)은 변경 지시가 없으므로 유지한다.
5F용 `configs/baseline.yaml`은 v1 유산으로 아카이브 대상(§2)이며 v2에서는
`baseline_10f.yaml`(개정판)만 정본 config로 남긴다.

### §1.2 EV 4대 확대와 배치 (요구 1)

현행: EV1(사람 전용)·EV2(사람+로봇 공용) 2대가 복도 위치 [13,14]에 일렬 배치.
`simulation/model.py`가 ElevatorAgent 2대·`ev1_*`/`ev2_*` KPI 스키마를
하드코딩하고, `space.build_from_config`의 V-CFG 가드가 `people_evs=1`을 강제.

제안(v2):

| 항목 | 제안값 |
|---|---|
| 총 EV | **4대** (EV1~EV4) |
| 배치 | 복도 중앙부 **교차 배치(사용자 확정)**: **북측 EV1(전용, pos 16)·EV3(공용, pos 18) / 남측 EV2(전용, pos 16)·EV4(공용, pos 18)** — 북·남 각 전용1+공용1 |
| 공용 지정 | **EV1·EV2 사람 전용, EV3·EV4 로봇 공용 가능**(robot_accessible=True). H0에는 로봇이 없으므로 4대 모두 사람 서비스로 동작 동일 |
| 공용 변경 | config 키 `building.shared_ev_ids: [EV3, EV4]`로 **선언적 지정** — 추후 로봇 시나리오에서 공용 대수·대상 변경 가능(요구 1 단서) |
| 그래프 | EV 노드에 `side: north/south` 속성 신설. 복도 접속은 기존과 동일하게 해당 corridor position 노드에 연결(북·남 EV가 같은 pos를 공유해도 노드명이 달라 충돌 없음) |
| 검증 규칙 | EV-사무실 위치 중복 검사를 (position, side) 쌍 기준으로 개정. [2,7,12,22,27,32]와 [16,18]은 비중복(2026-08-04 재배치 후에도 유지). 추가로 **미터→복도 격자 인덱스 변환 검증**(§10 R7) |
| 시각화 | 북측 EV는 복도선 위(+y), 남측은 아래(−y)로 오프셋해 **겹치지 않게** 표시(§1.5) |

구현상 핵심은 `model.py`의 **N-EV 일반화**다: ElevatorAgent 리스트·KPI
리포터(`ev1_*`~`ev4_*`)·`control_system.choose_elevator` 스캔·
`add_lobby_handoff_zones`의 로비-EV 배선(`ev_EV1_1`~`ev_EV4_1`)을 config 주도로
생성하고, V-CFG 가드는 "config의 EV 선언과 모델 인스턴스·그래프 노드·KPI
스키마의 상호 정합"을 검사하는 형태로 재작성한다.

### §1.3 로봇 충전 1F 이전 + B1 삭제 (요구 4)

현행: 대기 = 1F `lobby_robot_pickup_zone`, 충전 = B1 `b1f_charging`
(SOC < 임계 20%일 때만 B1 복귀). EV 운행 범위와 그래프 floor_labels에 B1 포함.

제안(v2):

1. **B1 전면 삭제**: `space.py` floor_labels에서 (-1, "B1") 제거,
   `b1f_charging` 노드·간선 제거, `floor_of`의 B1 규칙 제거, EV 운행 범위
   1F~10F로 축소, `elevator_physics`의 음수층 높이 처리 제거,
   `visualize.py`의 B1 행 제거. 잔존 참조는 grep 전수 감사(§4 V2-DOC).
2. **대기공간 = 충전공간 통합**: `lobby_robot_pickup_zone`에
   `charging: true` 속성을 부여해 1F 로비의 로봇 존이 대기·픽업·충전을 겸한다
   (별도 도크 노드 없는 단순안 — 사용자 확정 2026-08-03).
3. **수시 충전(opportunistic charging)**: RobotAgent 상태기계에서 "SOC 임계
   미달 → 충전소 이동" 로직을 제거하고, **IDLE(로비 대기) 중 SOC < 100이면
   자동 충전**으로 대체. 별도 CHARGING 상태·이동이 사라지므로 상태기계 단순화.
   `building_manager.charging_policy` 기본값 `off_peak` → `opportunistic`.
4. H0에는 로봇이 활동하지 않으므로 본 변경의 동작 검증은 그래프·상태기계
   단위테스트 수준으로 하고, 시뮬레이션 수준 검증은 Phase A(H1)에서 수행함을
   `phase_A_robot_h1.md`에 명기한다.

### §1.4 수요 시나리오 티어 (요구 2)

보유 데이터(`data/data1/`): K50 **2개**, K100 9개, K200 9개, K300 8개,
K500 5개, K750 1개, K1000 5개 = 39개. 이 중 **K500·K750·K1000 11개는 본 실험에서
보류**되어 모델링 코퍼스는 **28개**다.

| 티어 | 시나리오 | 개수 | 용도 |
|---|---|---|---|
| **1차(primary)** | K50, K100, K200 | 20 | 기본 결과 분석·본문 보고 |
| **극단(extreme)** | K300 | 8 | 1차 분석 완료 후 극단 케이스 분석 |
| **보류(excluded)** | K500, K750, K1000 | 11 | **본 실험에서 우선 보류** — 사용자 확정 2026-08-04. 코드 동작은 완전 배제와 동일하나 영구 폐기는 아니다(재개 시 배터리 기대 개수·인용 모집단 동시 수정 필요) |

> **개정 이력 — 2026-08-03 2차 확정**: 최초 확정은 extreme=K300+K500(13),
> hold=K750+K1000(6, 후행 분석 여지)이었으나, 사용자가 **K500·K750·K1000을
> 보류**로 재확정했다. 따라서 ①`hold` 티어 자체가 소멸하고 ②extreme은 K300
> 단독(8개)이 되며 ③**모델링 코퍼스는 39 → 28개**로 축소된다.
> **가장 큰 규약 변경**: 종전 "검증 배터리는 회귀 감지 목적상 39개 전수 유지"가
> **더 이상 성립하지 않는다** — 본 실험이 돌리지 않는 수요를 회귀 감시할 이유가
> 없으므로 배터리도 28개만 돌린다(보류가 풀리면 이 규약도 함께 되돌린다).
> `analysis/scenario_tiers.py`가 배터리의 정본이 되고, `data/data1`를 직접 glob
> 해 39를 세던 스크립트는 전부 오류다.

구현(R5 완료): 티어 정의는 **`configs/scenario_tiers.yaml`**(데이터) + 로더
**`analysis/scenario_tiers.py`**(코드)로 분리했다. `scenario_loader.py`에 얹지
않은 이유는 그 모듈이 리플레이·배차 타임라인 구성을 담당해 "loader"의 의미가
달라지기 때문. `h0_baseline_stats`·`h0_descriptive`가 `--tier` 인자를 받고
산출 테이블에 `tier` 열을 남긴다. **검증 배터리도 동일한 28개 코퍼스**를 쓴다
(2차 확정 반영 — 본 실험이 안 쓰는 수요를 배터리만 유지할 이유가 없다).

**무결성 제외는 소멸**: `h0_descriptive`가 R5 이전부터 걸어 온 `K1000_5`
(= `K1000_4` 바이트 중복) 필터는 K1000 자체가 코퍼스 밖이 되면서 **무의미**해졌다.
R5 시점에는 "티어 ≠ 무결성 제외"로 직교 유지했으나, 2차 확정 후에는 제외 규칙
하나로 흡수된다.

주의: K50은 표본이 2개뿐이므로 1차 분석의 통계 보고는 K100·K200 중심으로 하고
K50은 저수요 참조점으로 병기한다(§7 리스크 2).

### §1.5 시각화 사양 (요구 1·6)

`simulation/visualize.py`(649줄)·`app.py`(solara)·`etc/building_10f_layout.html` 대상.

1. **복도 축 확장**: x축 0~34m, 사무실 틱 [2,7,12,22,27,32](2026-08-04 재배치).
2. **EV 4대 비겹침 배치**: EV 샤프트 4열. 샤프트 상단 라벨 EV1~EV4, 카 상태색·
   방향 화살표는 기존 문법 유지. 로비 행의 EV 대기열 표기는 4열로 확장.
   *(R4 구현 시 정정 — 초안의 "북측 +y / 남측 −y 오프셋"은 단면도에서 성립하지
   않는다: y축이 층 번호이고 샤프트는 전 층을 세로로 관통하므로 샤프트에는 단일
   y가 없다. 사무실(±0.3층)과 달리 상하 분리가 불가능하다. **실제 구현은 x축
   오프셋**(북 −0.45 m / 남 +0.45 m)으로 좌우 분리하고, 측면은 라벨 `EV1·N`
   형식과 홀큐 배지 방향(북=좌·남=우)으로 표기한다. 결과 x = 15.55/16.45/
   17.55/18.45로 4열이 상호 배타 — `test_four_ev_shafts_do_not_overlap`이 고정.)*
3. **B1 행 삭제**: y축을 1F~10F로 축소, `b1f_charging` 아이콘 제거.
4. **1F 로비 충전 표기**: `lobby_robot_pickup_zone`에 충전 겸용 아이콘(⚡)을
   병기(H0에는 로봇 미등장이나 레이아웃 정합 유지, Phase A부터 활용).
5. **`etc/building_10f_layout.html` v2 재생성**: 신규 기하(1,200㎡·34m 복도·
   EV 북2/남2·1F 충전)를 반영해 새로 작성, v1은 아카이브.
6. **`checklist_visual_h0.md` → v2 개정**: EV 4대 비겹침·B1 부재·복도 축·
   충전 표기 항목을 추가한 `checklist_visual_h0v2.md` 신규 작성(§4 V2-VISUAL의
   수동 확인 체크리스트로 사용).


### §1.6 지하 2개층(B1·B2) 신설 — 요구 8 (사용자 지시 2026-08-03 3차)

> **위치 주의**: 이 절은 §1.3("B1 전면 삭제")을 **부분 번복**한다. 삭제됐던 것은
> *로봇 충전용* B1이고, 여기서 새로 만드는 것은 *사람 전용* B1·B2다. §1.3의
> "로봇 대기=충전=1F 로비존" 결론은 **그대로 유효**하다 — 로봇은 지하에 내려가지
> 않는다. 두 절이 모순처럼 보이면 이 문단을 기준으로 읽을 것.

#### 배경과 목적

사용자 지시: "지하1층·지하2층을 새로 만든다. 용도는 로봇과 무관하며, 건물
이용자가 EV로 지하에서도 타고 내리게 해서 **EV 이용률 변화**를 보기 위함이다.
지하에 사무공간은 없다. 로봇의 대기·충전은 H0 v2대로 1F 로비다."

즉 이 변경의 **종속변수는 EV 이용률(util)·대기(W_EV)**이고, 독립변수는 "수직
운행 범위가 10개층에서 12개층으로 늘고 지상 종점이 3개로 분산되는 것"이다.
R2에서 관측된 v1→v2의 util 급락(0.92~0.93 → 0.71~0.74, §9 R2 행)이 EV 4대
확대로 인한 탈포화였는데, 지하층은 **같은 4대에 수직 이동거리를 되돌려 주는**
반대 방향 압력이다 — §7 리스크 3(모드 간 대비 약화)의 완화 수단이기도 하다.

#### 확정 사양

| 항목 | 값 | 비고 |
|---|---|---|
| 지하층 수 | **2개층 (B1, B2)** | config `building.n_basements: 2` |
| 층 라벨(정수) | B1 = **−1**, B2 = **−2** | 0층은 존재하지 않음(한국 관례). v1의 B1 규약을 그대로 승계·일반화 |
| 노드 명명 | `floor_B1_center`, `floor_B2_center`, `ev_{EVID}_B1`, `ev_{EVID}_B2` | v1 명명 승계 |
| 용도 | **승하차 전용** — 사무실·복도 노드 **0개** | 지하에 `office`/`corridor` 타입 노드를 만들지 않는다 |
| 지하 내부 보행 | `floor_B{n}_center` ↔ 각 EV 노드 4.0 m (지상 비사무층과 동일 규칙) | 기존 `build_building_graph`의 "사무층이 아닌 층" 분기를 그대로 탄다 |
| 층고 | **4.0 m 동일** | B1 = −4 m, B2 = −8 m. `floor_height_m` 단일 상수 유지(주차층 별도 층고는 도입하지 않음 — kinematics 단일 상수 가정을 깨지 않기 위함) |
| EV 운행 범위 | **4대 전부 B2~10F (12개 정차층)** | 사용자 확정. 대칭이 유지되므로 V2-BAL(EV 균형) 게이트 무변경 |
| 로봇 | **지하 미사용** | 대기·충전은 1F 로비존(§1.3). 로봇 목적지 집합에 지하를 넣지 않는다. H0에는 로봇이 없으므로 실동작 검증은 Phase A |
| 라이더 | **지하 미사용** | 진입은 `lobby_entry`(1F), 목적지는 사무층. 지하 계단도 없음(계단은 사무층 한정) |
| 보행자 지상측 종점 | **1F 0.50 / B1 0.30 / B2 0.20** | config `pedestrian.ground_split`. 사용자 확정(권장안 채택) |
| 보행자 총량 | **7.5명/분 유지 — 재분배** | 사용자 확정. 상주 900명 × 0.5트립/h 캘리브레이션(§1.1)을 깨지 않는다. util 변화는 "인원 증가"가 아니라 **이동거리·정차층 증가**에서만 나온다 |

#### 층 랭크(rank) 규약 — 이 변경의 유일한 비자명 부분

층 라벨에 0이 없어서 `|라벨 차|`가 물리적 층수 차와 **어긋난다**(1F↔B1은 라벨 차
2, 실제 1개층). SCAN의 최근접 정차 선택과 대기시간 추정이 이 값을 쓰므로 그대로
두면 지하가 걸린 경우에만 배차가 미묘하게 틀린다. 따라서:

```
rank(f) = f      (f >= 1)        # 1F=1 ... 10F=10  — 지상은 라벨과 동일
rank(f) = f + 1  (f <= -1)       # B1=0, B2=-1
```

- rank는 **연속 정수**이고 물리적 높이에 대해 **순증가**한다 → 방향 판정
  (`a > b`)은 라벨로 해도 결과가 같지만, **거리(`abs`)·보간에는 반드시 rank**를 쓴다.
- 적용 지점 3곳: ①`ElevatorAgent._decide_next`의 최근접 정차 선택
  ②`ElevatorAgent.step`의 `position_floor` 보간 ③`ControlSystemAgent._estimate_wait`.
- `ElevatorKinematics.floor_height_between`은 v1 규약 복원:
  `height(f) = (f−1)·h if f≥1 else f·h` → 1F↔B1 = 4 m, 1F↔B2 = 8 m.
- **`position_floor`의 의미가 "라벨"에서 "rank"로 바뀐다**(KPI `ev{i}_floor`,
  시각화 y축). 지상층에서는 rank == 라벨이라 **기존 값은 한 자리도 변하지 않고**,
  지하일 때만 0/−1이 나온다. 시각화는 y틱 라벨을 B2·B1·1..10으로 매핑한다.

#### 하위 호환(회귀 안전장치)

`n_basements: 0`이면 **v2(지하 없음)와 비트 동일**해야 한다. 그러려면 보행자
지상 종점 추첨이 지하가 없을 때 **RNG를 소비하지 않아야** 한다(추첨을 건너뛰고
1F 고정). 이 성질을 테스트로 고정한다 — 지하층 도입이 기존 결과를 흔들지
않았음을 증명하는 유일한 수단이다.

#### 결과 영향 (예상 — W-게이트에서 정량 확인)

- 동결 스냅샷 4종(K50_1·K100_1·K200_1·K300_4)은 **반드시 깨진다.** 보행자
  종점 분포가 바뀌어 EV 점유가 달라지고, 라이더의 EV 대기가 그 영향을 받는다.
  → §4 V2-SNAP에서 재동결(W8). 이는 결함이 아니라 **설계 변경의 정상 귀결**이다.
- 기대 방향: EV util ↑, W_EV ↑, T_e2e ↑(라이더는 지하를 안 쓰지만 **혼잡을 통해**
  간접 영향). 방향이 반대로 나오면 배차·rank 구현 결함을 의심할 것.


---

## §2. 아카이브 전략 (Step R0)

### §2.1 방식

(사용자 확정 2026-08-03: **git 미사용** — 커밋·태그를 만들지 않는다. v1 복원
계획 없음. 기존 H0 검토가 필요하면 아카이브 폴더에서 해당 내용을 찾아 열람한다.
따라서 아카이브 폴더가 **v1의 유일한 기록**이며, tar.gz 스냅샷의 완전성이 곧
복원성이다.)

1. **아카이브 폴더**: `abm_new/archive/h0_v1/` 신설.
   - `docs/` — v1 전용 문서 **이동**(아래 A군).
   - `analysis_outputs/` — v1 분석 산출물 **이동**(아래 B군).
   - `code_snapshot_h0v1.tar.gz` — simulation/·analysis/·experiments/·tests/·
     configs/ 스냅샷(사용자 요구 "코드도 별도 폴더 보관" 충족; git 태그 없음
     → 이것이 v1 코드의 유일 스냅샷이므로 생성 후 목록·무결성 확인 필수).
   - `MANIFEST.md` — 보관물 목록·처분(이동/사본/유지)·사유·열람 방법 기록.
2. **정본 문서는 이동하지 않음**: `research_plan_scie.md`·`scie_phase/`는 연구
   트랙 연속성을 위해 **사본만 아카이브**하고 원본을 인플레이스 개정(§5).
3. 이동 후 **경로 참조 grep 감사**: 테스트·README·문서가 이동된 경로를
   참조하지 않는지 전수 확인(스위트 green으로 게이트).
4. R0 시점의 **미커밋 git 작업트리는 그대로 둔다**(git 미사용 지시). 이후
   커밋 여부는 사용자 재량.

### §2.2 대상 파일 전수 목록 (요구 7 — 지시 목록 + 추가 식별분)

**A군 — v1 문서 (archive/h0_v1/docs/로 이동)**

사용자 지시 목록: `building_10f_layout.html`, `checklist_visual_h0.md`,
`plan_h0_verification.md`, `verification_report_h0.md`, `extension_suggestion.md`.

추가 식별분(전수 검토 결과): `plan_abm_baseline_h0.md`,
`log_abm_baseline_h0_implementation.md`, `tutorial_abm_h0.md`,
`guide_h0_visualization.md`, `demand_mapping.md`,
`methodology_demand_to_floor_mapping.md`(v1~v4 4종),
`plan_3d_demand_integration.md`, `plan_demand_mapping_profile.md`,
`plan_floor_mapping_v6.md`, `plan_rider_assignment_revision.md`,
`plan_rider_pool_dynamic.md`, `plan_travel_time_functions.md`,
`rider_type_assignment.md`, `rider_type_assignment_inventory.md`,
`note_data_integrity.md`, `note_kpiwin_convention.md`, `note_vacant_floors.md`,
`note_vvar_interpretation.md`, `glittery-coalescing-eagle.md`,
`etc/html/`(렌더 HTML 12종), `etc/old/`(STAGE1·2 유산).

이 중 **방법론·노트류(demand/floor mapping, rider 배정, travel time, note_* 4종)는
v2에서도 유효한 내용이 많다** — 건물 기하와 무관한 수요→층 매핑·라이더 규약은
그대로 승계되므로, "이동"이 아니라 "사본 아카이브 + 원본 유지"로 분류한다.
최종 이동/유지 분류표는 R0 실행 시 파일별로 확정해 MANIFEST에 기록한다.

**B군 — v1 분석 산출물 (archive/h0_v1/analysis_outputs/로 이동)**

`analysis/h0_insights/`(S0~S3 진단 일체), `results/h0_stats/`, `results/vv/`,
`results/figures/`, `paper/figures/`·`paper/tables/` 중 H0 산출물,
`experiments/results/` 중 H0 실행분. v2 산출물은 동일 경로에 새로 생성되므로
이동으로 혼입을 차단한다.

**C군 — 인플레이스 개정 (아카이브에 사본 보관)**

`research_plan_scie.md`, `scie_phase/`(7종), `plan_hr_extension.md`,
`proposal_hr_extension.md`, `configs/`(baseline_10f.yaml 등),
시뮬레이션·분석·테스트 코드 전체(§3에서 수정).

**D군 — v1 종결 유산 (이동만, v2 재작성 없음)**

`configs/baseline.yaml`(5F 프로파일 — v2는 10F 단일), `analysis/map_v3.py`·
`map_floor_v4.py` 등 superseded 스크립트(단, import 의존 확인 후).

### §2.3 스냅샷 게이트 처리

`tests/test_h0_frozen_snapshot.py`의 골든 스냅샷은 v1 수치이므로 개정 착수와
동시에 깨진다. R0에서 골든 파일을 아카이브로 **복사**하고, 본 게이트는
§4 V2-SNAP까지 일시 `xfail`(사유 명기) 처리 후 v2 수치로 재동결한다.
그 외 스위트는 각 Step에서 즉시 green 복구가 원칙.

---

## §3. 코드 수정 단계 (Step R1~R5)

각 Step은 "코드 + 해당 테스트 개정 + 전체 스위트 green"을 완료 조건으로 한다.
현행 스위트 374 collected (371 passed / 3 skipped) 기준.

**R1. 공간·설정 개정** — `space.py`, `configs/baseline_10f.yaml`
- §1.1 기하(34m 복도·position 재배치·occupancy 100), §1.2 EV 4대 그래프
  (side 속성, ev_corridor_positions_m 4원소 + ev_sides 신설),
  §1.3 B1 삭제·로비 충전 속성.
- `build_from_config`의 V-CFG 가드 재작성(§1.2), `add_lobby_handoff_zones`의
  EV 배선 4대 일반화.
- 영향 테스트: test_space, test_cfg_people_evs(개명·재작성), test_travel_time_v4 등.

**R2. 모델 N-EV 일반화** — `model.py`, `agents/elevator.py`,
`agents/control_system.py`, `kpi.py`, `vertical_transport.py`
- ElevatorAgent 4대 config 주도 생성, KPI 리포터 `ev{i}_*` 동적 생성,
  dispatch 휴리스틱 4대 스캔(북/남 대칭 타이브레이크 규칙 명시),
  로비 EV 대기열 4열.
- 영향 테스트: test_agents, test_elevator_scan, test_live_kpi, test_kpi_window,
  test_h0_endtoend, test_vv_* 다수.

**R3. 충전 정책 개정** — `agents/robot.py`, `agents/building_manager.py`
- §1.3 opportunistic 충전 상태기계, B1 복귀 로직 삭제, charging_policy 기본값
  교체. (H0 비활성 — 단위테스트 수준 검증, Phase A에서 시뮬레이션 검증.)

**R4. 시각화 v2** — `visualize.py`, `app.py`, `etc/building_10f_layout.html`(신규),
`checklist_visual_h0v2.md`(신규)
- §1.5 전 항목. 영향 테스트: test_visualize, test_plot_baseline.

**R5. 분석 파이프라인 티어링** — `analysis/scenario_loader.py`,
`h0_baseline_stats.py`, `experiments/h0_descriptive.py`, `vv_all39.py` 등
- §1.4 티어 상수·러너 인자화. 배터리·분석 모두 28개 코퍼스, 분석 산출물은
  1차 티어(20개) 우선 생성. 영향 테스트: test_scenario_loader 등.


**R6. 지하 2개층 신설 (§1.6, 요구 8)** — `space.py`, `elevator_physics.py`,
`agents/elevator.py`, `agents/control_system.py`, `agents/pedestrian.py`,
`model.py`, `visualize.py`, `configs/baseline_10f.yaml`, `analysis/verify_h0.py`

R1~R5 완료 후 착수하는 **기하 재개정** 단계다. 하위 단계:

| Sub | 내용 | 게이트 |
|---|---|---|
| R6a | `space.py`: `n_basements` 파라미터, 층 라벨 B1/B2 생성, `floor_label`/`floor_rank` 헬퍼 공개, `floor_of`의 B-라벨 파싱 복원, EV 정차층에 지하 포함 | `test_space` 확장 green |
| R6b | `elevator_physics.floor_height_between` 음수층 복원 + `elevator.py`·`control_system.py`의 거리·보간을 rank 기반으로 교체 | `test_elevator_physics`·`test_elevator_scan` green |
| R6c | `model.py`·`pedestrian.py`: `ground_split` 추첨, 지하 노드 이름 처리, `n_basements: 0` 시 RNG 미소비 | 비트 동일성(지하 0 ⇒ v2와 완전 일치) |
| R6d | `visualize.py`: y축을 rank로 확장(B2·B1 행), 틱 라벨 매핑, 지하는 사무실·복도 미표기 | `test_visualize` 확장 green |
| R6e | `verify_h0.py`: **A10 반전**(지하 부재 → 지하 정합), config·문서 정합 | A1~A12 전건 PASS |

**A10 반전 상세**(§4 표도 같이 개정): 구 A10은 "전 주문의 방문 노드·EV 정차층에
floor ≤ 0 이 0건"이었다. 지하가 생겼으므로 다음으로 대체한다.

- A10-1 **지하 구조 정합**: 지하층에 `office`·`corridor` 타입 노드가 0개이고,
  각 지하층의 노드는 `floor_center` 1개 + EV 정차 노드 N개뿐이다.
- A10-2 **라이더·로봇 지하 미진입**: 전 주문의 라이더 방문 노드에 floor ≤ 0 이
  **0건**(라이더는 지하를 쓰지 않는다는 §1.6 사양의 런타임 확인). 로봇도 동일.
- A10-3 **EV 운행 범위**: 각 EV의 정차층 집합 ⊆ {−2, −1, 1..10}이고, 지하
  정차가 발생했다면 그 승객은 **전원 `kind == "pedestrian"`**이다.

**순서 의존**: R6은 R1~R5 완료 상태를 전제한다. R6c가 RNG 스트림을 건드리므로
**R6 완료 후 스냅샷 4종을 재동결**해야 하며(§4 V2-SNAP), 그때까지 스냅샷 게이트는
새 수치로 갱신한다. 검증 배터리(W1~W8)는 **R6 완료 후에 착수**한다 — 지하 없는
기하로 배터리를 돌리면 전량 재실행이 되기 때문이다.

순서 의존: R0 → R1 → R2 → (R3·R4·R5 병렬 가능) → **R6** → §4 검증.

**R1·R2 게이트 주의(R0에서 확인된 결합)**: config를 4EV·신기하로 전환하는 순간
V-CFG 가드와 model.py의 2EV 하드코딩이 동시에 깨지고, B1 삭제도 model·visualize
계열 테스트에 즉시 파급된다. 따라서 **전체 스위트 green 판정은 R2 완료 시점에
통합 적용**하고, R1 경계에서는 space 계층 테스트(test_space 등) green +
빌더 일반화 완료만 게이트한다. 두 Step은 같은 세션에서 연속 수행하되
커밋 단위(변경 기록)는 분리해 파손 원인 추적성을 유지한다.

---## §4. 검증 계획 (V2 게이트)

`plan_h0_verification.md`(v1)의 레이어 체계 L1~L7을 승계한다. 본 절이 골격이며,
실행 직전 상세 계획서 `plan_h0v2_verification.md`를 신규 작성해 항목·합격 기준을
동결한다(요구 3 "기존과 같은 방법으로 검증").

| 게이트 | 내용 (v1 대응) | v2 특이사항 |
|---|---|---|
| V2-GP | 골든 패스 손계산 (L1 V-GP) | 신규 기하(34m·pos 재배치)로 **수기 재유도**. 4EV 대기 모형 반영, 대표 시나리오 1건 전 구간 수계산 대조 |
| V2-AUD | 동적 경로 불변식 감사 (L2 V-AUD) | 4EV 불변식 추가: EV별 큐 보존, 라이더-EV 배정 정합, 북/남 EV 노드 혼입 금지, **지하 2개층 정합(A10 반전 — §3 R6e)** |
| V2-EXT/CONV | 극한·수렴 배터리 (L3) | 수요 0, EV 1대 강제 축소, 900명 러시 극한 추가 |
| V2-MONO | K 단조성 (L4) | K50→K300 28개 전수(회귀 감지), 보고는 티어별. K↑ 사다리는 K50_1→K200_1→K300_4 |
| V2-FACE/EVSEL | face validity·EV 선택 분포 (L5) | **EV 4대 이용 분포의 북/남·좌/우 균형** 신규 점검(대칭 배치 → 균등 기대) |
| V2-VISUAL | 시각화 감사 (L5 V-VISUAL) | `checklist_visual_h0v2.md` 전 항목 + 스냅샷 이미지 육안 확인(비겹침·B1 부재·충전 표기) — 세션 확인 1회 |
| V2-DET/VAR | 결정성·CRN·분산 (L6) | 시드 규약 유지 확인, v1 대비 분산 구조 변화 기록 |
| V2-DATA/CFG | 데이터 정합·config 가드 (L7) | 신규 V-CFG 가드(4EV 정합) 동작 확인, 티어 정의 정합 |
| V2-SNAP | 동결 스냅샷 재수립 | 28개 배터리 재실행 → 골든 스냅샷 4종(K50_1·K100_1·K200_1·K300_4) 확정. **세션 독립 재검증**(비트 동일성 2회 실행) |
| V2-DOC | 문서 정합 grep 감사 | "2대/EV2까지", "800㎡", "80명", "720명", "27m" 잔존 참조 전수 소탕. **"지하 없음/no basement" 문구는 이제 반대로 소탕 대상**(§1.6로 B1·B2 신설) |

게이트 순서: R1~R5 완료·전체 pytest green → V2-GP~V2-DATA 배터리 →
V2-SNAP 동결 → V2-DOC → **`verification_report_h0v2.md` 작성**(v1 보고서 양식
승계: 게이트별 결과·수치·재현 명령). 보고서의 세션(오퍼스) 독립 재검증
(전체 pytest·비트 동일성·grep 감사)을 통과해야 H0 v2 완료로 선언하고
연구계획서 진행 로그에 등재한다.

**v1 대비 결과 비교 노트**: 검증과 별도로, v1(2EV·800㎡) vs v2(4EV·1,200㎡)의
주요 KPI(EV 대기·리드타임) 변화를 1차 티어에서 요약해 `h0_insights` v2에
수록한다. EV 수송력 2배 확대가 H0의 혼잡 병목을 완화하므로, 이후 모드 비교
연구 서사에서 극단 케이스(K300)의 역할이 커질 수 있음을 기록(§7 리스크 3).

---

## §5. 문서 수정 방안 (요구 3)

### §5.1 신규 작성

| 문서 | 내용 | 시점 |
|---|---|---|
| `etc/plan_h0_revision.md` | 본 문서 | 완료 |
| `etc/plan_h0v2_verification.md` | §4 골격의 상세화(항목·합격 기준·배정) | R5 완료 전 |
| `etc/checklist_visual_h0v2.md` | 시각화 체크리스트 v2 (§1.5-6) | R4 |
| `etc/verification_report_h0v2.md` | V2 게이트 결과 보고서 | V2 완료 시 |
| `analysis/h0_insights/` v2 재생성 | 1차 티어 20개 기준 S0~S3 재진단 + v1 대비 비교 노트 | V2-SNAP 후 |
| `etc/building_10f_layout.html` v2 | 신규 기하 레이아웃 | R4 |

### §5.2 인플레이스 개정 (사본 아카이브 후)

> **실행 순서 주의**: ⓐ(`research_plan_scie.md`+`phase_A`)를 먼저 돌려
> 결정 #16~#22와 phase_A 설계 결론을 확정한 뒤, ⓑ가 그것을 나머지 문서에
> 전파한다. 순서를 뒤집으면 ⓑ가 미확정 전제로 작업해 재작업이 생긴다.
> (ⓐ의 배정은 2026-08-03 3차 정책으로 **Fable → 오퍼스/max**로 교체됐다. §6 참조.)

**`research_plan_scie.md`** (정본 — ⓐ **오퍼스/max**, 구 Fable/high 배정 대체):
- §1 결정 로그에 결정 #16~#22 등재: ①EV 4대 교차 배치(북: EV1 전용+EV3 공용 /
  남: EV2 전용+EV4 공용) ②EV3·4 공용 예약(config `shared_ev_ids`로 변경 가능)
  ③1,200㎡·100명/층·보행자 7.5명/분 ④충전 1F 대기존 통합·opportunistic·B1 삭제
  ⑤K 티어(1차 K50/100/200, 극단 K300; **K500·K750·K1000 보류** — 2026-08-04 확인)
  ⑥v1 아카이브(이동, git 미사용, archive/h0_v1이 유일 기록)·v2 재검증
  ⑦Phase A 순연.
- §5 완료 자산 수치(테스트 수·시나리오 수) 갱신, §6 로드맵에 **Phase R(H0 v2
  개정, 본 계획)** 삽입 + 기간 재조정, §8.1 design matrix의 K 수준을 티어
  구조로 개정, §12 배정표에 §6 표 반입 + 진행 로그 갱신.

**`scie_phase/`** (7종):
- `phase_A_robot_h1.md` (**ⓐ 오퍼스/max**): 로봇 충전 B1 참조 → 1F opportunistic
  전면 개정, EV 공용을 EV3·EV4 2대 기준으로 개정(공용 2대 = 로봇 직렬화 해소,
  §0 "카당 1대라 직렬화·EV2 병목 1순위" 주장 재유도), 착수 전제 "H0 v2 검증
  완료" 명기. **필수 3건**: ①L89 `model.elevators[1]` 지시 — v2에서 그 인덱스는
  사람 전용 EV2이므로 공용(EV3/EV4) 기준으로 정정 ②§0 진단 기준선 표는 2EV
  실측이라 **테스트 오라클로 무효** — R2 관찰(util 0.92→0.71)에 비추어 재산출
  또는 "V2 재측정 전까지 판정 근거 사용 금지"로 강등 ③"EV 무릎(잠식할 여유
  없음)" 주장의 참·거짓 재판정.
- `README.md` (ⓑ 오퍼스): Phase R 추가, 실행 순서·상태 갱신.
- `phase_B~F` (ⓑ 오퍼스): 건물 상수(800㎡·80명·EV 2대)·B1 참조 grep 소탕,
  design matrix K 티어 반영(특히 phase_D 실험·phase_E 민감도의 시나리오 목록).
  단 phase_B의 G/G/c 서버 수 c는 **로봇 대수**라 EV 확대와 무관 — 무변경 확인만.

**`plan_hr_extension.md` / `proposal_hr_extension.md`**: 로봇 대수·충전 설계가
§1.3과 충돌하는 부분(B1 충전 왕복, charging_policy) 개정. R1a~R2d 스텝 정의
중 공간 그래프 전제 갱신.

### §5.3 아카이브 이동

§2.2 A·B·D군. 이동/유지 최종 분류는 R0에서 MANIFEST로 확정.

---

## §6. 모델·effort 배정표

연구계획서 §12 관례 준수: 각 Step을 배정 모델 서브에이전트로 위임 → 세션에서
핵심 게이트 독립 재검증 → 단계 경계 전체 스위트 green → 본 문서 §9 진행 로그
기록. Escalation: 같은 테스트 2회 실패 시 모델/effort 1단계 상향, 설계 충돌 시
세션 직접 개입.

> **모델 정책 (2026-08-03, 사용자 지시 3차 개정 — 현행)**: **Fable 전면 미사용.**
> 남은 Fable 크레딧이 0이 되어(사용자 확인 2026-08-03) 2차 개정이 남겨 두었던
> 예외 1건(문서 개정 ⓐ 2개 파일)마저 소멸했다. Fable이 담당하던 난도·판단
> 구간은 전부 **오퍼스 + 최고 effort(`max`)**로 처리한다. 세션 = 오퍼스.
>
> effort 사다리: `low < medium < high < max`. 기존에 "Fable 대체이므로 high로
> 상향"이라고 적힌 구간 중 **원래 Fable 배정이던 것은 `max`**로 다시 올리고,
> 처음부터 오퍼스 배정이던 구간의 effort는 그대로 둔다(난도가 변한 게 아니라
> 담당 모델만 바뀐 것이므로).
>
> R0~R3(완료분)의 `세션(Fable)` 표기는 **실행 이력 기록이므로 보존**한다 —
> 배정 지시가 아니라 "그때 실제로 그 모델이 했다"는 사실 기록이다.
> §6.1의 Fable 예산 산정은 그래서 **효력을 잃었다**(기록으로만 보존).

### §6.1 문서 개정 Fable 예산 산정 (실측 기반) — ⚠️ **효력 없음 (2026-08-03 3차)**

> 아래 산정은 Fable 잔여 크레딧 $6.51을 전제로 한 것이다. **크레딧이 0이 되어
> 문서 개정 ⓐ·ⓑ 모두 오퍼스/max로 이관**됐으므로 배정 근거로 쓰지 말 것.
> 산정 방법론(토큰 실측식·캐시 단가 반영)은 이후 다른 예산 판단에 재사용할 수
> 있어 삭제하지 않고 남긴다.

단가: Fable 5 = 입력 $10 / 출력 $50 per MTok, 오퍼스 5 = $5 / $25.
캐시 읽기 ≈ 입력가 ×0.1, 캐시 쓰기 ×1.25(5분 TTL).
토큰량은 문서 실측(한글 음절 ×1.4 + 그 외 ×0.28):

| 문서군 | 실측 토큰 | 배정 |
|---|---|---|
| `research_plan_scie.md` | ~25.4K | **Fable** |
| `phase_A_robot_h1.md` | ~8.3K | **Fable** |
| `plan_h0_revision.md`(참조 입력) | ~11.2K | (Fable 세션 입력) |
| `scie_phase/README` + `phase_B~F` | ~28.0K | 오퍼스 |
| `plan_hr_extension` + `proposal_hr_extension` | ~8.4K | 오퍼스 |

**Fable 세션 추정(2건)**: 로드 컨텍스트 ~55K → 캐시 쓰기 $0.69 + 캐시 읽기
(25턴×40K) $1.00 + 비캐시 $0.15 = **입력 ~$1.84**. 출력은 가시 편집 ~14K +
사고 ~45K = 59K × $50/M = **~$2.95**. **합계 ≈ $4.8 (한도 $6.51 대비 74%)**.

**전량 Fable 시나리오는 초과**: 전체 문서 ~70K 로드·50턴이면 입력 ~$5.0 +
출력(가시 25K + 사고 75K) ~$5.0 = **~$10.0**로 한도의 1.5배. `phase_B`
1건만 추가해도 ~$6.9로 초과하므로 2건이 예산 내 최대 범위다.

**초과 방지 장치**: ①Fable 세션은 위 2개 파일만 편집(그 외 전부 스코프 밖)
②effort는 `high`(사고 토큰 폭증 방지 — `max` 금지) ③이미 읽은 파일 재독 금지
④세션 종료 시 실제 사용량을 §9 로그에 기록해 추정 대비 오차 확인.

| Step | 내용 | 난이도 | 모델 | effort | 비고 |
|---|---|---|---|---|---|
| R0 | 아카이브 이동·tar.gz 스냅샷, MANIFEST, 경로 grep 감사 | 하 | (완료: 세션 Fable) | — | ✅ 실행 이력 |
| R1 | space/configs 기하·4EV·B1 삭제 | 상 | (완료: 세션 Fable) | high | ✅ 실행 이력 |
| R2 | model/kpi/dispatch N-EV 일반화 | 상 | (완료: 세션 Fable) | high | ✅ 실행 이력 |
| R3 | 충전 opportunistic·B1 로직 삭제 | 하~중 | (완료: R1·R2에 접힘) | — | ✅ 실행 이력 |
| R4 | 시각화 v2 (visualize/app/layout.html/체크리스트) | 중 | **오퍼스** | **high** ↑ | 비겹침 기하·로비 4열 재배치 판단 — Fable 대체로 effort 상향 |
| R5 | 분석 티어링·러너 갱신 | 하~중 | 소넷 | medium | 상수·인자화 중심 |
| **R6** | **지하 2개층 신설(§1.6)** | 상 | **오퍼스** | **max** | rank 규약이 배차·KPI·시각화에 동시 파급 — 침묵 오류 위험 구간(라벨/rank 혼용). 3차 모델 정책 적용 |
| V2 계획서 | plan_h0v2_verification.md 상세화 | 중 | 오퍼스 | **high** ↑ | ✅ 2026-08-03 완료. 구 "오퍼스 medium + Fable 리뷰"를 오퍼스 high 단독 + 세션 재검토로 대체 |
| V2-GP | 골든 패스 수기 재유도 | 중~상 | **오퍼스** | **high** | 수기 계산 — 상위 모델 원칙 |
| V2-AUD | 불변식 감사(4EV 규칙 추가) | 중 | 오퍼스 | medium | v1 감사 코드 확장 |
| V2-EXT/MONO/DET | 배터리 재실행 3종 | 하 | 소넷 | low~medium | 러너 재사용 |
| V2-FACE/EVSEL | face validity·EV 분포 | 하~중 | 소넷 | medium | 해석은 세션(오퍼스) |
| V2-VISUAL | 시각화 감사 | 하 | 소넷 medium + 세션 육안 확인 1회 | — | 체크리스트 v2 기준 |
| V2-SNAP | 스냅샷 재동결 | 하 | 소넷 medium + **세션 독립 재검증** | — | 비트 동일성 2회 |
| V2-DOC·보고서 | grep 소탕 + verification_report_h0v2 | 중 | 오퍼스 | high | 최종 정합 패스는 세션(오퍼스) |
| 문서 개정 ⓐ | **`research_plan_scie.md` + `phase_A_robot_h1.md`** | 상 | **오퍼스** | **max** | 구 Fable 배정 → 3차 정책으로 오퍼스/max 이관(§6.1 예산 산정 실효). 침묵 오류 집중 구간: 확정 규약 폐기(결정 #19), `elevators[1]` 함정, 진단 기준선 오라클 무효화, EV 무릎 주장 반전, 메커니즘 4채널·§10 리스크 재유도 |
| 문서 개정 ⓑ | `scie_phase/README`+`phase_B~F`, `hr_extension` 2종 | 중 | **오퍼스** | **high** | ⓐ에서 확정된 결정을 전파(상수·참조 정합). 처음부터 오퍼스 배정이라 effort 유지 |

예상 규모: 실작업 1.5~2.5주 상당(v1 검증 6일 실적 대비, 구현 개정이 추가되나
검증 인프라 재사용).

---

## §7. 리스크와 주의사항

1. **테스트 대량 파손**: R1·R2에서 374개 중 space/model/kpi/visualize 계열
   상당수가 깨진다. green 게이트는 §3의 R1·R2 통합 규칙을 따르고, 스냅샷
   게이트만 예외적으로 xfail 유지(§2.3). 변경 기록은 Step별로 분리해 파손 원인
   추적성을 유지한다.
2. **K50 표본 2개**: 1차 티어 통계에서 K50은 대표성이 없다. 보고는 K100·K200
   중심, K50은 저수요 참조점으로 병기(§1.4).
3. **연구 서사 영향**: EV 2→4대(수송력 2배)는 혼잡 병목을 완화해 H0 기준선의
   대기시간을 크게 낮출 수 있다. 보행자 부하 +25%(720→900명)로 일부 상쇄되나,
   모드 간 차이가 축소되면 극단 티어가 차별화의 핵심이 된다. **2026-08-03 2차
   확정으로 K500 이상이 제외되면서 이 리스크가 커졌다** — 수요 상한이 K300
   (주문률 ~38%/h)이므로, EV 4대 확대와 겹쳐 모드 간 대비가 약해질 여지가 있다.
   V2-CMP(v1 대비 비교)에서 반드시 정량 확인하고 연구계획서 §10에 반영할 것.
   v1 대비 비교 노트(§4 말미)로 정량 확인 후 연구계획서 §10 리스크에 반영.
4. **v1 기록의 단일성**: git 미사용 확정이므로 `archive/h0_v1/`(특히 tar.gz
   스냅샷)이 v1의 유일한 기록이다. R0에서 스냅샷 생성 직후 목록 대조로 완전성을
   확인하고, 이후 아카이브 폴더를 수정하지 않는다(읽기 전용 취급).
5. **아카이브 경로 파손**: 문서 이동 시 README·테스트·문서 상호 링크가 깨질 수
   있다. R0 grep 감사로 게이트(§2.1-4).
6. **Phase A 문서와의 정합**: `plan_hr_extension.md`의 R1a~R2d는 2EV·B1 전제로
   작성되어 있어 §5.2 개정 전 착수 금지.

---

## §8. 사용자 확정 사항 (2026-08-03 회신 — 재론 금지)

| # | 항목 | 확정값 |
|---|---|---|
| 1 | 복도 길이·사무실 위치 | 34m, **[2,7,12,22,27,32]**, 북6·남6 동일 배분 (R1의 [4,9,14,19,24,29]를 2026-08-04 재배치 — §10 R7) |
| 2 | EV 북/남 구성 | **교차 배치**: 북측 EV1(전용)+EV3(공용) / 남측 EV2(전용)+EV4(공용) |
| 3 | K750·K1000 지위 | ~~보류(분석 제외, 배터리 포함)~~ → **2026-08-03 2차 확정으로 K500과 함께 코퍼스 밖**(배터리에서도 제외). **2026-08-04 표현 정정**: 지위는 "영구 제외"가 아니라 **"본 실험에서 우선 보류"** — 코드 동작은 동일 |
| 4 | 아카이브 방식 | **이동**(archive/h0_v1/ + tar.gz 코드 스냅샷) |
| 5 | 보행자 부하 | 7.5명/분 (1인당 트립율 유지 스케일) |
| 6 | 충전 공간 | 대기존 통합(별도 도크 노드 없음) |
| 8 | **지하 2개층** (3차 지시) | **B1·B2 신설, 사람 승하차 전용(사무공간 없음), EV 4대 전부 B2~10F, 보행자 지상 종점 1F 0.50/B1 0.30/B2 0.20, 총량 7.5명/분 재분배, 로봇은 1F 대기·충전 유지** — §1.6 |
| 7 | git | **미사용** — 커밋·태그 없음. v1 복원 계획 없음, 검토는 아카이브 폴더 열람으로 |
| 9 | R1·R2 배정 | **세션(Fable) high** (최대 난관 구간) — 실행 완료. 이후 단계는 §6 모델 정책 변경(Fable 미사용, 오퍼스 대체+effort 상향) 적용 |

---

## §9. 진행 로그 (인플레이스 기록)

| Step | 배정 | 산출물·핵심 수치 | 독립 재검증 | 상태 |
|---|---|---|---|---|
| 계획서 작성 | 세션(Fable) | 본 문서 | — | ✅ 2026-08-03 |
| 사용자 승인(§8) | 사용자 | 확정 8건(§8 표) — 교차 배치·git 미사용·R1/R2 Fable 반영 | — | ✅ 2026-08-03 |
| R0 아카이브 | 세션(Fable) | `archive/h0_v1/` 신설: 전체 tar.gz 스냅샷(372 엔트리, gzip 무결성 OK) + docs 21건·html/·old/ 이동 + h0_insights·h0_stats·vv·figures·paper 도면 이동 + baseline.yaml(5F)·map_v3.py 이동 + MANIFEST. 테스트 픽스처 JSON 7건은 results/ 잔류(MANIFEST 기록). 살아있는 문서의 이동 문서 인용 → 아카이브 경로 갱신(재생성형 산출물 경로는 V2-DOC로 이월) | 전체 스위트 **371 passed / 3 skipped** (v1 기준선과 동일) | ✅ 2026-08-03 |
| R1 공간·설정 | 세션(Fable) high | `space.py` 전면 재작성: B1 삭제(1..10F), EV 4대 교차 배치(side 속성·`ev_ids`·`shared_ev_ids` 선언적 메타), (pos,side) 쌍 중복 검사, `corridor_mid_pos` 메타 신설, 로비 로봇존 `charging=True`, V-CFG 가드를 "선언→그래프→모델→KPI 정합 by construction"으로 재작성. `baseline_10f.yaml` v2(34m·[4,9,14,19,24,29]·100명/층·ped 7.5). `test_space.py` 재작성(30건)·`test_cfg_ev_fleet.py` 신설 9건(구 test_cfg_people_evs 삭제) | R2와 통합 게이트(§3 규칙) | ✅ 2026-08-03 |
| R2 N-EV 일반화 | 세션(Fable) high | `model.py` EV 선언 기반 생성 + `ev{i}_*` 리포터 동적 생성, `external_rider` 계단노드 `corr_{mid}` 파라미터화, `visualize` 4샤프트 북(−0.45)/남(+0.45) 오프셋 비겹침·계단기둥·EV차트 동적화, `elevator_physics` B1 제거, `verify_h0`·`verify_baseline`·`vv_decomp` EV 일반화, 테스트 전수 개정, **픽스처 JSON 7건 v2 재생성**(§2.3 xfail 대신 즉시 재동결 — V2-SNAP에서 39종 배터리 후 공식 확정) | **전체 스위트 373 passed / 3 skipped** + 비트 동일성(2회 실행 ≡ + 픽스처 일치) + ruff 오류 v1 동등(전체 128→115). A1~A9 감사가 v2 산출물에서 전부 PASS. 관찰: K50_1 EV util 0.92~0.93(2EV) → **0.71~0.74(4EV)**, 탑승 354/367/372/340 균형, order-span이 일관되게 더 바쁜 창(4EV 탈포화), check#4 slack −0.04s(1틱 허용 내, v1 +0.14s) — v1 대비 비교 노트(§4 말미) 소재 | ✅ 2026-08-03 |
| R3 충전 개정 | 세션(Fable) (R1·R2에 접힘) | `charging_policy` 기본값 `opportunistic`, `RobotState.CHARGING` 제거(IDLE 중 수시 충전 설계 주석 명문화), B1 복귀 로직 부재 확인 — 로봇은 스텁이므로 시뮬레이션 수준 검증은 Phase A | 스위트 green에 포함 | ✅ 2026-08-03 |
| R4 시각화 v2 | 세션(오퍼스) high | `visualize.py`: EV 4열 라벨 `EV{i}·N/S` **2행 엇갈림 배치**(9×5 figure에서 4개 한 행은 겹침), 홀큐 배지를 **측면 기준 바깥쪽**(북=좌·남=우)으로 이동(구 "최내측만 좌측" 규칙은 4열에서 배지 충돌), 로비 로봇존 `⚡ robot` 마커(그래프 `charging` 플래그 판독 — 하드코딩 아님), 로봇존 x좌표 신설, 계단기둥·로비 좌표를 복도 길이에서 유도. `app.py` 독스트링 v2 갱신. **`etc/building_10f_layout.html` v2 재생성**(층별 평면도 + EV 4대 수직단면, 자체완결 HTML/SVG, 다크모드 대응, 18.5KB — v1 46KB 대비 축소). **`etc/checklist_visual_h0v2.md` 신규**(§3 v2 기하 6항목 + §4 v1 거동 8항목 승계 + 부록 A 헤드리스 렌더 절차 + 부록 B 자동테스트 중복 항목 명시) | `tests/test_visualize.py` **+4건**(비겹침·측면 오프셋·B1 부재·복도축/충전마커/라벨) → 10 passed. R4 범위 6개 파일 **68 passed**. **9×5(앱 실제 크기) PNG 육안 확인 완료**: EV 4열 분리·라벨 2행·B1 행 없음·x축 0–34·⚡ 1F·사무실 6열(4/9/14/19/24/29)·계단 33m. **HTML은 node + DOM 스텁으로 헤드리스 실행 검증**(문법 아닌 실동작): 층 버튼 10개(B1 없음), 3F 평면=EV 4개+사무실 12개, 1F 로비=존 6종 전부+⚡+EV 4개+사무실 0개, 단면=1F~10F만·B1 문자열 0건. `simulation/` 잔존 v1 상수 grep 0건 | ✅ 2026-08-03 |
| R5 분석 티어링 | 소넷 medium (서브에이전트, R4와 병렬) | **`configs/scenario_tiers.yaml` 신규**(티어 정의 단일 출처) + **`analysis/scenario_tiers.py` 신규** 로더(`k_levels`/`k_of`/`tier_of_k`/`tier_of_scenario`/`scenario_paths`/`scenario_stems`, `TIER_CHOICES`로 CLI choices 제공). `experiments/h0_descriptive.py`·`analysis/h0_baseline_stats.py`에 `--tier {primary,extreme,hold,all}` 배선(기본 `primary`), 산출 테이블에 **`tier` 열 추가**(어느 코퍼스 산출물인지 하류에서 식별 가능). `h0_baseline_stats`의 구 하드코딩 `assert len(traits)==38` → 티어 열 검증으로 교체, figure의 고정 7-K 순회를 `_present_k_order`로 대체(티어가 K를 빼도 KeyError 안 남). `tests/test_scenario_tiers.py` 신규 16건 | **세션 독립 재검증 완료**: ①전체 스위트 **393 passed / 3 skipped**(2회 실행 동일) ②티어 분할 직접 계산 — primary 20·extreme 13·hold 6 = **39, 전 파일 정확히 1개 티어**(미포함 0) ③**검증 배터리 불변 확인** — `vv_*` 8종의 `scenario_tiers` 참조 **0건**, 5개 스크립트 모두 `glob("K*.json")`+`== 39` 유지 ④비트 동일성 — R2 골든 픽스처와 `per_order`·`kpi_summary`·`model_vars` 완전 일치 ⑤ruff 20→10(잔여는 Solara PascalCase N802·printf UP031 등 기존 관례) | ✅ 2026-08-03 (⚠️ **일부 후속 무효화**: 같은 날 2차 확정으로 `hold` 티어 소멸·배터리 39→28 전환 — §1.4 개정 이력 참조. 위 재검증 ②③은 당시 규약 기준 기록) |
| R4·R5 통합 | 세션(오퍼스) | zip `strict=` 명시 정리(EV↔측면·K↔색상은 길이 일치가 계약이므로 `strict=True`; **`zip(spans, spans[1:])`는 의도적 부등 길이라 `strict=False`** — 일괄 `--fix`였다면 테스트가 깨졌을 지점), import 정렬, `visualize.py` 독스트링 v1 잔재(0..27 m·"two EV shafts") 제거 | 정리 후 전체 스위트 재실행 **393 passed / 3 skipped** | ✅ 2026-08-03 |
| V2 검증계획서 | 세션(오퍼스)/high | **`etc/plan_h0v2_verification.md` 신규**. 핵심 설계: ①§0에서 "R0~R5가 이미 자동 게이트로 잠근 것"과 "v2에서 아직 검증 안 된 것"을 분리해 중복 검증 제거 ②§2에서 v1 게이트 17종을 **승계/재실행/폐기/신규**로 전건 분류(V-RIDER·V-DATA·V-KPIWIN·V-CFG는 재실행 불요로 확정) ③**V2-GP를 절대 검산으로 재설계** — 기존 골든패스는 기대값을 같은 그래프에서 유도하므로 그래프가 틀리면 양쪽이 함께 틀림, 따라서 설계 사양만으로 손계산한 절대 초값을 상수로 고정 ④**A10~A12 신규 불변식**(지하층 부재·EV 선언 정합·홀콜 배타성) ⑤**V2-BAL 신규 게이트** — 유휴 EV 4대 동점 시 최소 ev_id 쏠림 위험, max/min ≤ 1.5 ⑥V2-SNAP을 W8 마지막에 배치(중간 동결 시 재동결 반복) ⑦V2-DOC의 한계(의미 반전은 grep 불가 → 문서 개정 ⓐ 담당) 명시 | **세션 자체 검산 완료**: L1 예시 손계산 6종을 그래프 실측과 대조해 전건 일치(8.0 m·6.0 m·24.0 m·12.1000 s·6.25 m·corr_17·office_2=14m 북). 인용 테스트 건수 전수 확인 중 `test_space` 36→**30 정정**(2개 문서 반영) | ✅ 2026-08-03 |
| V2-SNAP·보고서 | — | — | — | ⬜ |
| K500/750/1000 제외 전파 | 세션(오퍼스) | HANDOFF §3 잔여분 완료: `vv_decomp`·`vv_face`·`vv_map5_audit`을 `scenario_tiers.scenario_paths("all")` 참조로 전환(39→28), 대표 삼중항 K1000_1→**K50_1·K200_1·K300_4**(5개 파일), `h0_descriptive`의 `hold` 티어·`EXCLUDED={K1000_5}` 제거, `h0_baseline_stats`의 K500/K1000 하드코딩 주석(fig2 "K≥500 현상" 주장 포함) 정리, `test_scenario_tiers.py` 전면 재작성(16→23건, 배터리 가드 **반전**) | **전체 스위트 402 passed / 3 skipped (0 failed)** + 코퍼스 분할 직접 검산 20/8/28/11 + **비트 동일성**(K50_1 `kpi_summary`·`per_order` 골든 일치 — 시나리오 선택만 건드렸으므로 시뮬레이션 불변) | ✅ 2026-08-03 |
| 모델 정책 3차 | 사용자 | **Fable 크레딧 0 → 전 배정 오퍼스/max 이관.** `plan_h0_revision`(§5.2·§6·§6.1 효력상실 표기·§9), `plan_h0v2_verification` §5, `research_plan_scie` §12, `scie_phase/{README,phase_B,C,F}`, `plan_hr_extension`, `proposal_hr_extension` 갱신. 진행 로그의 `세션(Fable)` 표기는 실행 이력이라 보존 | 잔존 Fable **배정** 0건(정책 문구·이력만 잔존) | ✅ 2026-08-03 |
| **R6 지하 2개층** | 세션(오퍼스)/max | §1.6 전건 구현. `space.py` `n_basements`(기본 2)·`floor_label`/`floor_rank` 공개·`floor_of` B라벨 파싱·B1/B2 노드(floor_center+EV 정차만), `elevator_physics` 음수층 높이(1F↔B1=4 m), `elevator.py`·`control_system.py`·`model.py`(evsel)의 거리·보간을 **rank 기반**으로 교체, `model.py` `_ground_split`/`_draw_ground_floor`(1F .50/B1 .30/B2 .20), `pedestrian.py` 지하 종점, `visualize.py` rank y축+B2·B1 행+지하 띠, config `n_basements`·`ground_split`, `configs/regression_nobasement_10f.yaml` 신설, `results/pre_basement/` 4종 보존. 문서: 검증계획서 **A10 반전**(A10-1~3)·V2-DOC 소탕 대상 정정·극한 2케이스 추가, 체크리스트 ③ 반전, `building_10f_layout.html` 지하 반영 | **전체 스위트 415 passed / 3 skipped** + **A1~A9 전건 PASS**(신 기하) + 2회 실행 비트 동일 + **`n_basements: 0` ⇒ 지하 도입 이전과 비트 동일**(`test_nobasement_replay_matches_pre_basement_snapshot`) + 스냅샷 4종 재동결 + PNG 육안 확인(B2 홀큐·지하 사무실 0) + HTML 헤드리스 검증(층버튼 B1·B2, 단면 B2~10F, ⚡ 1F 유지) | ✅ 2026-08-03 |
| 라이더 인용 모집단 38→28 | 세션(오퍼스) | 사용자 확정 2026-08-04(검증계획서 §6-3 (a) 채택). `rider_assignment_tables.py`를 `scenario_tiers` 참조로 전환, `rider_type_assignment_inventory.md` §0.2·§0.3·§8 표 재생성 + 산문 갱신, 파스-락 테스트 13건 갱신, `research_plan_scie` §C2 "39개·13,450건"→**28개·5,200건**, `phase_A_robot_h1` 38개/114run→28개/84run. 이동 수치: 주문 12,450→**5,200**, WALK 1순위 417(3.3%)→**87(1.7%)**, fixed_cost 조합 11→**8**, ρ 조합 8→**2**, D*(B,W) 상한 794→**413 m** | 전체 스위트 **415 passed / 0 failed** + 시뮬레이션 결과 **불변**(K50_1 골든 비트 일치 — 인용 통계만 바뀌고 모델은 안 건드렸음을 확인) | ✅ 2026-08-04 |
| K500+ 지위 표현 정정 | 사용자 | "영구 제외(재론 금지)" → **"본 실험에서 우선 보류"**. 코드 동작은 동일(어느 경로로도 미실행)하되 재개 여지를 남기고, 재개 시 동시 수정 대상(티어 승격·배터리 기대 28·인용 모집단)을 명시. 코드·config·테스트 13개 + 계획서 3종 문구 교체 | 스위트 green 유지, 코퍼스 20/8/28/11 불변 | ✅ 2026-08-04 |
| **R7 사무실 재배치 + 미터/격자 결함** | 세션(오퍼스)/high | **사용자 확정 2026-08-04**: `office_positions_m` **[4,9,14,19,24,29] → [2,7,12,22,27,32]**(×2). 근거는 R1 배치의 기하 결함 2건 — ①복도 중점·EV 뱅크 중심은 17.0인데 사무실 열만 **16.5 대칭** ②사무실 14·19 m가 EV 도어(16·18)에서 2 m·1 m라 **샤프트가 사무실 안**. 새 배치는 17.0 거울 대칭(2+32=7+27=12+22=34) + **12~22 m를 EV 서비스 코어로 비움** + 끝여백 2/2 대칭. **동반 결함 수정**: `office_positions_m`/`ev_corridor_positions_m`이 **미터이자 동시에 복도 노드 인덱스**로 쓰여 1 m 격자·정수에서만 성립했다 — 오프그리드 값은 예외 없이 통과한 뒤 `add_edge`가 유령 노드(`corr_2.5`)를 만들어 **사무실이 복도에서 고립**되고 주문이 배달 불가가 됐다(범위 검증도 미터를 인덱스 상한과 비교). `build_building_graph`에 `grid_index()` 명시 변환 + 미터 범위·격자 정합 검증 신설. 재생성: 골든 스냅샷 4종·프로파일 픽스처 3종·v5 매핑 픽스처·`pre_basement/` 4종·`results/vv/` 전량·`h0_stats/` | **①리팩터 선검증**: 결함 수정만 넣고 위치는 현행 유지 → K50_1 `per_order`·`model_vars`·`kpi_summary` **비트 동일**(행동 보존 증명) ②오프그리드·범위밖 4종 **빌드 거부 확인**(음성 테스트 3건 신설) ③**손계산 재산출**: office_2 14→12 m이므로 d2 6.0→**8.0 m**, s2 6.0→**8.0 m**(d1·s1·중점·수직 상수 불변) — 그래프 조회 없이 사양에서 재유도 ④**전체 스위트 437 passed / 3 skipped** ⑤KPI 영향 실측: T_lobby **+0.23~+4.72%**, T_e2e **+0.11~+0.41%** | ✅ 2026-08-04 |
| 문서 개정 ⓐ | **오퍼스/max** (구 Fable/high — 크레딧 소진으로 2026-08-03 3차 이관) | — | — | ⬜ |
| 문서 개정 ⓑ | 오퍼스/high | — | — | ⬜ ⓐ 완료 후 착수 |
