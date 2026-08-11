# cycle_charts — 에이전트 1-사이클 차트

각 에이전트 클래스의 FSM을 "한 번의 사이클"로 펼쳐 **상태 · 소요시간 · 공간경로 ·
결정근거**를 하나의 자립 HTML로 렌더한다. run 산출물이 필요 없다 — 코드와 config만
읽는다.

```bash
cd /home/sw/Research/abm_new
.venv/bin/python -m cycle_charts.build --list          # 등록된 slug
.venv/bin/python -m cycle_charts.build                 # 전부 → cycle_charts/out/
.venv/bin/python -m cycle_charts.build --agent robot_h1
.venv/bin/python -m cycle_charts.build --check         # 쓰지 않고 검증만
```

현재 등록:

| slug | 대상 | 기준 |
|---|---|---|
| `rider_h0` | `external_rider.py` · 12상태 | H0 v2.1 동결. **`robot_h1`의 대조군** |
| `robot_h1` | `robot.py` · 8상태 | Phase A Step A1 구현 |

## 두 차트를 왜 나란히 두는가

두 FSM을 **로봇 규약**(direction을 상태 이름이 아니라 직교 속성으로)으로 정규화하면
정확히 이렇게 떨어진다:

```
라이더(정규화) = MOVING · WAIT_EV · RIDING · DROP · IDLE          5상태
로봇          = 라이더 + WAIT_RIDER · HANDOFF · CHARGING_BLOCKED  8상태
leg           = 로봇에만 TO_COUNTER / 라이더에만 계단 2종
```

**추가된 3상태가 H1이 H0에 더한 전부다.** 이것이 두 차트를 같은 대표 케이스(5F 주문 ·
사무실 평균 거리 · 큐잉 0)와 같은 팔레트 국면으로 묶어 둔 이유다 — 차집합이 눈에
보여야 한다. 비교가 성립하려면 규약도 공유해야 해서, `riding = 승차 도어 1회 + 주행`
(하차 도어는 세지 않는다)을 양쪽 기하가 똑같이 쓴다.

실측 대조(큐잉 0 하한):

| | 라이더 H0 | 로봇 H1 |
|---|---|---|
| 사이클 | **182.5 s** | **159.8 s** |
| 수평 보행 | 44 m @ 1.2 m/s | 47 m @ 1.0 m/s |
| 최대 단일 구간 | SERVICE 120 s (66%) | HANDOFF 60 s (38%) |
| 큐잉 구간 | 2 (`WAIT_EV` ×2) | 3 (+ `WAIT_RIDER`) |

## 왜 `analysis/`가 아닌가

`analysis/`는 **`results/`를 소비하는 사후 분석**이다. 이쪽은 반대로 **코드와 config
자체를 소비**한다. 한 번도 run을 돌리지 않은 상태에서도 렌더되며, 그래야 Step 구현
직후·검증 이전에 설계를 눈으로 확인할 수 있다. 섞으면 `analysis/`의 "results를
읽는다"는 불변식이 깨진다.

예외가 하나 있다. 라이더의 **서비스 시간만은 config가 아니라 시나리오의 `RIDERS`
표**에서 온다(`model.service_time_for`). 시나리오 JSON은 run 산출물이 아니라 **입력
데이터**라서 위 불변식은 유지된다. `geometry.DEFAULT_SCENARIO`(K50_1)를 읽되 파일이
없으면 config 폴백(`rider_process.service_time_sec`)으로 조용히 물러서므로,
데이터 없이도 `--check`는 돈다.

## 세 개의 층

| 파일 | 역할 | 모르는 것 |
|---|---|---|
| `spec.py` | 순수 데이터 구조 | 렌더러도 시뮬레이터도 모른다 |
| `geometry.py` | config + 건물 그래프에서 **살아 있는 상수** 산출 | 차트를 모른다 |
| `render.py` | spec → HTML/SVG | 사이클의 의미를 모른다. 배치만 안다 |
| `specs/<agent>.py` | 위 셋을 엮어 한 장의 차트를 정의 | — |

## 설계 규칙 세 가지

**1. 숫자를 스펙에 적지 않는다.** 전부 `geometry.py`가 계산한다. 이 모듈이 존재하는
이유는 구체적이다 — `etc/HANDOFF_phase_a.md` §A4의 로봇 기하 상수가 실제 그래프와
**1 m 어긋나 있었다**(EV 노드 → 복도 노드 스텁이 누락). 문서에 적힌 상수는 조용히
늙지만, 그래프에서 계산한 상수는 config가 바뀌면 같이 바뀐다.

그래프는 `model.py`와 **동일한 경로**로 만든다(`build_from_config` +
`add_lobby_handoff_zones`). 지름길을 쓰면 차트가 재는 건물이 시뮬레이터가 도는
건물과 달라진다.

**2. 이름은 코드에서 import한다.** 상태·leg·버킷 이름을 문자열로 적지 말고
`RobotState` / `RobotLeg` / `REPORT_BUCKETS`에서 가져온다. 개명이 렌더 시점에
예외로 터져야지, 그림을 눈으로 보고 발견해서는 안 된다.

**3. 번호는 한 곳에서만 매긴다.** 표의 행 · 리본의 세그먼트 · 도면의 마커가 모두
같은 `Step` 객체에서 나온다. 손으로 세 번 적던 시절의 주된 오류원을 구조로 없앤 것.

**4. 상태는 전수로 덮는다.** `CycleSpec.covers_states`에 그 에이전트의 FSM 상태
**전부**를 코드에서 뽑아 넣으면, 빠뜨린 상태와 지어낸 상태가 둘 다 렌더 시점 예외가
된다. 로봇에게는 `REPORT_BUCKETS` 대조가 그 역할을 하지만 **라이더에게는 버킷
상당물이 없어서**(12상태 raw) 이쪽이 유일한 방어다. Enum이 아닌 대문자 클래스 상수로
FSM을 적은 에이전트는 `spec.state_names(cls)`가 자동으로 긁어온다 — 소문자
메타데이터(`kind = "rider"`)는 걸러진다.

**5. 구현 전에 그린 차트는 그렇게 표시한다.** `CycleSpec.provenance`의 `pending=True`가
파선 배지로 렌더된다. "이미 도는 것"과 "아직 코드가 없는 것"이 같은 무게로 읽히면 안
된다. `pending` 차트는 그 Step의 **수용 기준** 노릇을 하므로, 코드가 생기는 순간
스펙이 그것을 import해서 자기 자신과 대조하고 통과하면 `pending`을 내린다.

### 지금 잡히는 드리프트

```
버킷 추가/개명 → 팔레트와 REPORT_BUCKETS가 어긋난다: ['staging']
유령 마커      → 도면 마커 '99'에 대응하는 단계가 없다
미정의 버킷    → 단계 1(IDLE)의 버킷 'nope'이 팔레트에 없다
상태 누락      → 차트가 빠뜨린 상태: ['SERVICE']
유령 상태      → 코드에 없는 상태를 그렸다: ['EXITED']
기하 이중정의  → 리본 합계 159.8 s와 geometry.cycle_sec 160.3 s가 어긋난다
```

마지막 항목이 라이더 차트 때문에 생겼다. 사이클 총 소요가 **스펙의 리본 합계**와
**`geometry.cycle_sec`** 두 곳에 존재하게 되었기 때문인데(후자는 두 에이전트를 나란히
놓고 빼기 위해 필요하다), `robot_h1.build()`가 렌더 시점에 둘을 대조해 묶어둔다.

## 새 에이전트 추가하기

1. `geometry.py`에 그 에이전트의 상수를 **계산**으로 추가한다
   (`RobotCycleGeometry`가 본보기 — 전 필드가 config/그래프 유래이고, 파생값은
   `@property`로 두어 중간 계산이 저장되지 않게 한다).
2. `specs/<agent>.py`에 `build() -> CycleSpec`을 쓴다.
3. `specs/__init__.py`의 `REGISTRY`에 등록한다.

`specs/`에 raw HTML을 끼워 넣고 싶어지면 그건 spec 어휘가 부족하다는 신호다.
`spec.py`를 넓히고 `render.py`를 고쳐라 — 한 스펙에서 예외를 내주면 다음 에이전트가
그 예외를 복사한다.

다음 후보(각각 자기 FSM이 있다):

| slug 후보 | 대상 | 상태 | 메모 |
|---|---|---|---|
| `handoff_rider_h1` | `handoff_rider.py` | 5 (설계) | **다음.** 아래 §"보류 중" 참조 |
| `pedestrian` | `pedestrian.py` | 4 | 배경 부하. EV 경합의 반대편 |
| `elevator` | `elevator.py` | 3 + `direction` | 사이클이 아니라 SCAN 루프라 도면 어휘를 넓혀야 한다 |
| `customer` | `customer.py` | **없음** | `step()`이 `pass`. 리본이 아니라 주문 타임라인이 맞다 |

`building_manager` · `control_system` · `locker`는 후보가 아니다. 앞의 둘은 상태가 아니라
누산기·무상태이고, 락커는 `try_dock`/`pickup`이 아직 `NotImplementedError`라 H3(Phase C)
전에는 그릴 것이 없다. 상태도 에이전트가 아니라 **칸 단위**라 리본이 아니라 점유 격자가
맞는 형식이다.

### 보류 중 — `handoff_rider_h1`

사용자 판단으로 **나중에 만든다**(2026-08-07). 막힌 것은 없고 재료도 다 있다:

- `simulation/agents/handoff_rider.py` — **Step A2가 같은 날 신설했다.** 상태는
  `state_names()` 확인 결과 아래 예상과 정확히 일치하는 5개다. 따라서 이 차트는
  `pending`이 **아니라** 보통의 `Provenance("구현 기준", ...)`으로 만들면 된다.
- `geometry.handoff_rider_geometry()` — **구현 완료**. 입구↔카운터 7 m, 인계
  N(60, 15²), 그리고 대조군 둘(`h0`·`robot`)을 통째로 들고 있어
  `saved_sec` · `saved_pct` · `system_sec`가 파생된다.
- `spec.Provenance(pending=True)` — **구현 완료**. 이 차트를 위해 만들었지만 A2가
  먼저 도착해 쓸 자리가 없어졌다. 장치는 남겨둔다 — 구현보다 스펙이 먼저 오는
  다음 Step에서 쓴다.

실측해 둔 대조(큐잉 0):

```
라이더 H0  182.5 s  →  라이더 H1  71.7 s   (−60.7%, w_R이 곱해지는 양)
                       + 로봇     159.8 s
시스템 총 행위시간  182.5 → 231.5 s (+49.0 s)
```

**시스템은 더 많은 시간을 쓰는데 사람은 61% 덜 머문다** — 논문의 양면 외부성 주장이
이 한 줄이다. 라이더가 1F를 벗어나지 않으므로 라이더발 EV 편도가 2 → 0이 되고,
그 부하는 사라지지 않고 로봇에게 이전되면서 사람 정원을 15 → 11로 줄인다.

만들 때: 상태는 `WALK_TO_COUNTER · WAIT_ROBOT · HANDOFF · WALK_TO_EXIT · EXITED` 5개.
`WAIT_ROBOT`은 로봇의 `WAIT_RIDER`와 **맞물린다** — 한 주문에서 둘 중 하나만 양수다.

## 출력

`cycle_charts/out/<slug>.html`. Artifact로 그대로 발행 가능한 형태다 —
`<!doctype>`/`<html>`/`<head>`/`<body>` 없이 `<title>` + `<style>` + 본문만 내고,
외부 자산을 하나도 참조하지 않는다(CSP가 막는다).

한글은 **시스템 폰트 스택**으로 받는다. CJK 웹폰트를 data URI로 인라인하면 수 MB고,
CDN 링크는 CSP에 막혀 조용히 폴백된다.

테마는 토큰 단위다. `prefers-color-scheme`가 OS 설정을 나르고 뷰어의 토글이 루트에
`data-theme`를 찍으며, 그것이 **양방향으로** 미디어 쿼리를 이겨야 한다 — 그래서
팔레트를 세 번 선언한다.

## 아직 안 한 것

- `tests/`에 pytest 커버리지가 없다. `--check`가 같은 검증을 하지만 CI 훅은 아니다.
  스위트에 넣으면 `HANDOFF_phase_a.md` §6이 추적하는 **스위트 수(503)가 바뀌므로**
  의도적으로 보류했다.
- `rider_h0`의 대표 카는 **무부하 타이브레이크**의 결과다(모든 카가 1F·pending 0이면
  `_estimate_wait`이 전부 0으로 같아지고 `ev_id` 오름차순 `min`이 EV1을 준다). 부하가
  걸리면 달라지는 값이라 "대표"이지 "고정"이 아니다. `geometry.rider_geometry()`가
  휴리스틱을 재구현하지 않고 정렬 규칙만 쓰는 이유이며, 대신 그 재구현 회피가
  **`choose_elevator`가 바뀌어도 이 차트는 조용히 옛 규칙을 그린다**는 뜻이기도 하다.
- `rider_h0`의 리본 서비스 시간은 config 폴백(120 s)이다. 실제는 타입별
  BIKE/WALK 120 · CAR 180이고 차트 노트가 그 범위를 밝히지만, **리본의 폭은 한 값만
  쓴다** — 타입 혼합을 폭으로 표현할 어휘가 아직 없다.
- 도면 좌표는 손으로 잡는다. 축척이 아니라 다이어그램 좌표이고 실제 거리는
  치수선으로 밝힌다. 층·샤프트·레인 구조만 실물과 일치시킨다.
