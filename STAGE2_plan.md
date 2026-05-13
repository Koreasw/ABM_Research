# STAGE 2 실행 계획서 — 빌딩 환경 모델링

> 한국 표준 소형 사무 빌딩 (5F × 500 m²) 의 networkx 기반 공간 모델 구축.
> Framework `research_framework_handoff.md` §5 의 구현 단계.
> 본 문서는 *착수 전 합의된 설계 결정* 과 *구현 절차* 의 reference 이다.

---

## 1. 목표 (한 줄)

5F × 500 m² 빌딩의 공간을 networkx MultiDiGraph 로 표현하여,
**"B1F 충전소 → EV2 → 3F 사무실 04호" 같은 경로/거리 query + EV 자원 경합 모델링** 이 가능하도록 한다.

이 그래프는 STAGE 3 의 8-agent ABM 이 공유하는 **공통 spatial layer** 가 된다.

---

## 2. 빌딩 사양 (framework §5 정합)

| 항목 | 값 | 근거 |
|---|---|---|
| 층 구조 | B1F ~ 5F (총 6 level) | 1F 로비 + 2F~5F 사무 + B1F 서비스 |
| 층당 면적 | 500 m² (≈ 150평) | 한국 PMO 중소형 표준 |
| Footprint | 22 m × 23 m (거의 정사각) | 500 m² 자연 형상 |
| 층고 | 3.6 m | 한국 사무 표준 |
| 복도 길이 | 20 m (편도, 중앙 single-loaded) | 23m footprint 내 |
| 복도 폭 | 2 m | 한국 사무 표준 |
| 사무실 수/층 | **7개** (positions 1, 4, 7, 10, 13, 16, 19 m) | 20m / 3m 균등 간격 |
| 사람 전용 EV | 1대 (EV1, 수용 10명) | 5F 자율설치 |
| 공용 EV | 1대 (EV2, 수용 10명 / 6명 with robot) | 핸드오프 실험 필수 |
| 총 EV | 2대 | 5F 의무 X (< 6F, < 2,000 m²) |
| 전체 점유 | ~280 인 (56인/층 × 5) | 1인당 9 m² |

---

## 3. 확정된 설계 결정 (4개)

| # | 결정 | 사유 |
|---|---|---|
| **D1** | Corridor 해상도 = **1 m** discrete | 혼잡 모델링 정밀도 (밀도 > θ 시 감속) |
| **D2** | 사무실 분기 위치 = **uniform 3m spacing** at corridor[1, 4, 7, 10, 13, 16, 19] | 균등 분포로 face validity ↑ |
| **D3** | ElevatorKinematics = **별도 `elevator_physics.py`** | 단일 책임 + ElevatorAgent (STAGE 3) import 명확 |
| **D4** | 정적 빌딩 평면도 **포함** (`visualize_space.py`) | Paper §5 figure 즉시 산출 |

---

## 4. 산출물 (3개 파일)

| 파일 | 역할 | 우선순위 |
|---|---|---|
| `simulation/space.py` | networkx MultiDiGraph + 경로 query API | ★ 핵심 |
| `simulation/elevator_physics.py` | EV 가감속·도어 물리 모델 (D3) | ★ 핵심 |
| `simulation/visualize_space.py` | 정적 빌딩 평면도 figure (D4) | ★ 핵심 |

테스트 산출물:
- `tests/test_space.py` (≈15 tests)
- `tests/test_elevator_physics.py` (기존 skip stub → 실제 테스트 5개로 교체)
- `tests/test_visualize_space.py` (≈3 tests, 출력 파일 존재·크기 검증)

---

## 5. 그래프 아키텍처

### 5.1 노드 인벤토리 (5F baseline ≈ 153 노드)

| 노드 타입 | 명명 규칙 | 5F 수 | 용도 |
|---|---|---|---|
| `floor_center` | `floor_{F}_center` (F = B1, 1, 2, 3, 4, 5) | **6** | EV 도착 hub |
| `corridor` | `floor_{F}_corr_{P}` (P = 0..19, 1m 간격, D1) | **80** (2F~5F × 20 positions) | 1m discretized 보행 위치 |
| `office` | `floor_{F}_office_{N}` (F=2..5, N=0..6) | **28** (7 × 4 office 층) | 고객 인도 endpoint (D2) |
| `elevator` | `ev_EV1_{F}`, `ev_EV2_{F}` (F = B1, 1..5) | **12** (2 EV × 6 floor) | EV 호출/하차 노드 |
| `lobby_zone` | `lobby_entry`, `lobby_handoff_counter`, `lobby_queue_zone`, `lobby_locker_bank`, `lobby_robot_pickup_zone`, `lobby_direct_corridor` | **6** | 1F 6종 핸드오프 zone |
| `support` | `b1f_charging`, `b1f_waiting` | **2** | B1F 서비스 zone |
| `floor_corridor` | `floor_1_corr_{P}` | **20** | 1F 로비 통로 (zone 간 연결) |
| **합계** | | **~154** | (이전 800m²/100m 사양 578개 대비 4배 축소) |

### 5.2 엣지 인벤토리 (5F baseline ≈ 240 엣지)

| 엣지 타입 | 속성 | 5F 수 |
|---|---|---|
| `walk` corridor 내부 | `{distance_m: 1.0, max_speed_mps}` | 5층 × 19 = **95** |
| `walk` office↔corridor 분기 | `{distance_m: 3.0}` | 4층 × 7 = **28** |
| `walk` floor_center↔corridor[10] | `{distance_m: 3.0}` | **6** |
| `walk` floor_center↔ev_node | `{distance_m: 4.0}` | 2 EV × 6 floor = **12** |
| `walk` lobby zone 간 인접 | `{distance_m: 1~5}` | ~15 |
| `ev` (EV1·EV2 별 floor 쌍) | `{from_floor, to_floor, ev_id}` | 2 × C(6, 2) = **30** |
| `handoff` (mode-specific) | `{service_time_dist}` | ~6 |
| `walk` b1f_charging↔ev | `{distance_m: 4.0}` | **2** |
| **합계** | | **~240** |

### 5.3 거리 attribute 결정 규칙

```
corridor[i] ↔ corridor[i+1]            : 1.0 m  (D1)
floor_center ↔ corridor[10]            : 3.0 m  (복도 중앙 진입)
office_{N} ↔ corridor[pos[N]]          : 3.0 m  (사무실 분기, D2)
  where pos = [1, 4, 7, 10, 13, 16, 19]
floor_center ↔ ev_EVx_floor            : 4.0 m
b1f_charging ↔ ev_EV2_B1               : 4.0 m
b1f_waiting ↔ ev_EV2_B1                : 4.0 m
ev_EV{id}_floor_i ↔ ev_EV{id}_floor_j  : ElevatorKinematics.travel_time_sec() 동적
```

---

## 6. API 명세

### 6.1 `simulation/space.py`

```python
def build_building_graph(
    n_floors: int = 5,
    n_offices_per_floor: int = 7,
    office_positions_m: list[int] = (1, 4, 7, 10, 13, 16, 19),  # D2
    corridor_length_m: float = 20.0,
    corridor_resolution_m: float = 1.0,                          # D1
    floor_height_m: float = 3.6,
    n_people_only_evs: int = 1,
    n_shared_evs: int = 1,
) -> nx.MultiDiGraph:
    """5F Korean 소형 사무 빌딩 baseline. 정적 그래프 (자원 상태는 Agent 가 관리).
    
    노드 attribute:
      - type: 'floor_center' | 'corridor' | 'office' | 'elevator' |
              'lobby_zone' | 'support'
      - floor: int | str  (-1 for B1F, 1-5 for above)
      - position_m: float (corridor 노드용)
      - ev_id: 'EV1' | 'EV2' (elevator 노드용)
      - robot_accessible: bool (EV1=False, EV2=True)
    """


def add_lobby_handoff_zones(
    g: nx.MultiDiGraph,
    n_locker_compartments: int = 4,
    queue_capacity: int = 8,
) -> nx.MultiDiGraph:
    """1F 로비에 6종 핸드오프 zone 추가."""


# Query API
def shortest_walk_path(g, source: str, target: str,
                       robot: bool = False) -> tuple[list[str], float]:
    """walk 엣지만 사용 + robot 이면 EV1 비통과 제약. 반환: (경로, 총거리_m)."""

def floor_of(node: str) -> int | None:
    """노드명에서 층 번호 추출 (B1F → -1, None for lobby_zone)."""

def offices_on_floor(g, floor: int) -> list[str]:
    """해당 층의 office 노드 목록 (CustomerAgent 배정용)."""

def elevator_nodes(g, ev_id: str | None = None) -> dict[str, list[str]]:
    """{ev_id: [floor_node, ...]} 매핑. ev_id=None 이면 모든 EV."""

def corridor_density(g, node: str, agent_positions: dict) -> float:
    """해당 corridor 노드 주변 ±2m 안의 agent 밀도 (혼잡 감속 계산용)."""
```

### 6.2 `simulation/elevator_physics.py` (D3)

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class ElevatorKinematics:
    """EV 가감속·도어 물리 모델 (framework §5.3).
    
    Default 값: 가속 1.0 m/s², 최고 속도 2.5 m/s, 도어 4초, 층고 3.6 m.
    """
    accel_mps2: float = 1.0
    max_speed_mps: float = 2.5
    door_open_close_sec: float = 4.0
    floor_height_m: float = 3.6

    def travel_time_sec(self, from_floor: int, to_floor: int) -> float:
        """가감속·도어 포함 순수 이동시간 (큐잉 대기 제외).
        
        구현:
          dH = |to - from| × floor_height
          ascent_dist = v_max² / (2·a) = 3.125 m
          단순거리 (dH < 2·ascent_dist):
            t = 2 × sqrt(dH / a)
          v_max 도달 후 정속:
            t = 2·(v_max/a) + (dH - 2·ascent_dist) / v_max
          총 = t + door_open_close_sec
        """

    def floor_distance_m(self, from_floor: int, to_floor: int) -> float:
        """수직 이동거리만 (B1F → 5F 는 6층 차이 × 3.6m = 21.6m)."""
```

### 6.3 `simulation/visualize_space.py` (D4)

```python
def draw_building_section(
    g: nx.MultiDiGraph,
    out_path: Path,
    figsize: tuple[float, float] = (12, 8),
) -> None:
    """5F 빌딩 측면도 (vertical section view):
    - X축: 가로 방향 (복도 + offices)
    - Y축: 층 (B1F ~ 5F)
    - EV1, EV2 vertical lanes
    - 색상: floor_center (회색), office (파랑), corridor (연회색),
            EV1 (주황), EV2 (녹색), lobby zones (빨강 계열)
    """


def draw_floor_plan(
    g: nx.MultiDiGraph,
    floor: int,
    out_path: Path,
    figsize: tuple[float, float] = (10, 6),
) -> None:
    """단일 층 평면도 (top-down view):
    - 복도 + 7 offices 위치
    - EV1, EV2 위치
    - 거리 라벨"""


def draw_lobby_layout(
    g: nx.MultiDiGraph,
    out_path: Path,
    figsize: tuple[float, float] = (12, 6),
) -> None:
    """1F 로비 핸드오프 zone 상세 평면도:
    - lobby_entry (출입구)
    - handoff_counter, queue_zone, locker_bank, robot_pickup_zone
    - direct_corridor → EV1·EV2
    - locker bank 의 M compartments 표시"""
```

산출물:
- `paper/figures/fig_building_section.png` — 빌딩 측면도 (paper §5 main)
- `paper/figures/fig_floor_plan_typical.png` — 사무 층 (2F~5F) 평면도
- `paper/figures/fig_lobby_layout.png` — 1F 로비 zone 상세

---

## 7. ElevatorKinematics 검증 수치 (3.6m 층고 기준)

| 층 이동 | 거리 dH | 가속 단계 거리 (3.125 m) 도달? | 순수 시간 | + 도어 4s | 총 EV 시간 |
|---|---|---|---|---|---|
| 1F → 2F (1층) | 3.6 m | No (dH < 6.25m) | √(2·3.6/1.0) = 2.68s | | **6.68 s** |
| 1F → 3F (2층) | 7.2 m | Yes | 2·2.5 + (7.2−6.25)/2.5 = 5.38s | | **9.38 s** |
| 1F → 4F (3층) | 10.8 m | Yes | 2·2.5 + 4.55/2.5 = 6.82s | | **10.82 s** |
| 1F → 5F (4층) | 14.4 m | Yes | 2·2.5 + 8.15/2.5 = 8.26s | | **12.26 s** |
| B1F → 5F (6층) | 21.6 m | Yes | 2·2.5 + 15.35/2.5 = 11.14s | | **15.14 s** |

→ 빌딩 내부 last-100m 의 총 처리시간 중 *EV 이동 비중 10~15초*. 핸드오프 service 60s 와 비교해서 secondary.

→ 그러나 **EV 큐잉 대기 (자원 경합)** 는 ElevatorAgent (STAGE 3) 가 모델링; 이는 100s 단위까지 증가 가능 → vertical mobility bottleneck 의 진짜 원인.

---

## 8. 단계별 구현 순서

| Sub-stage | 작업 | 예상 시간 | 테스트 추가 |
|---|---|---|---|
| **2.1** | `build_building_graph(5F)` — 노드/엣지 생성 + 카운트 sanity | 1.5h | +6 |
| **2.2** | Query API (`shortest_walk_path`, `floor_of`, `offices_on_floor`, `elevator_nodes`) + B1F → 5F-office-3 거리 검증 | 1h | +5 |
| **2.3** | `add_lobby_handoff_zones` 6종 노드 + locker_bank M sweep ∈ {2, 4, 8} | 1h | +4 |
| **2.4** | `elevator_physics.ElevatorKinematics.travel_time_sec` 물리 검증 (5개 floor pair 의 정확한 수치) | 1h | +5 |
| **2.5** | EV1 (people-only) vs EV2 (shared) 라우팅 분기 + `robot_accessible` flag 동작 (`shortest_walk_path(..., robot=True)` 가 EV1 회피) | 1h | +4 |
| **2.6** | `visualize_space.py` 3개 함수 + 3개 figure 생성 (paper §5 figure) | 1.5h | +3 |
| **합계** | | **~7 h** | **+27 tests** |

---

## 9. 테스트 전략 (27 tests)

### 9.1 `test_space.py` (~18 tests)

| 카테고리 | 테스트 예시 |
|---|---|
| **구조 (5F)** | 노드 수 = 154 ± 5, office 28개, EV 노드 12개 |
| **연결성** | 모든 사무실 → b1f_charging 까지 walk-path 존재 |
| **거리 합** | b1f_charging → ev_EV2_B1 → ev_EV2_5 → floor_5_center → corridor[10] → office_3 |
| **거리 합 (구체)** | 위 경로의 walk 총거리 = 4 + 3 + 3 = 10 m (EV travel 제외) |
| **사무실 위치 (D2)** | 각 office_N 이 corridor[pos[N]] 와 walk edge 로 연결 |
| **EV1 제약** | `shortest_walk_path(robot=True)` 는 EV1 노드 미경유 |
| **EV2 공용** | `shortest_walk_path(robot=True)` 가 EV2 노드 경유 가능 |
| **층수 가변** | n_floors=10 시 그래프 비례 확장 (Future E3 토대) |
| **로비 zone** | 6종 모두 추가됨, locker M=2 → 2 노드, M=8 → 8 노드 |
| **corridor 해상도 (D1)** | 1m 간격으로 20개 corridor 노드 / 층 |

### 9.2 `test_elevator_physics.py` (~5 tests, 기존 skip stub 교체)

| 테스트 |
|---|
| 0층 차이 = 0s + 4s 도어 = 4s |
| 1F→2F = 6.68s (단순거리 공식) |
| 1F→5F = 12.26s (가감속 + 정속) |
| 대칭성: 1F→5F = 5F→1F |
| 음수 floor 입력 (B1F→3F) 정상 처리 |

### 9.3 `test_visualize_space.py` (~3 tests, smoke)

| 테스트 |
|---|
| `draw_building_section` 호출 시 PNG 파일 생성, 크기 > 20 KB |
| `draw_floor_plan` 호출 시 PNG 파일 생성 |
| `draw_lobby_layout` 호출 시 PNG 파일 생성 |

---

## 10. STAGE 3 와의 인터페이스 계약

STAGE 2 산출물 사용 패턴 (STAGE 3 의 `simulation/model.py` 에서):

```python
from simulation.space import (
    build_building_graph,
    add_lobby_handoff_zones,
    shortest_walk_path,
    elevator_nodes,
)
from simulation.elevator_physics import ElevatorKinematics


class BuildingHandoffModel(Model):
    def __init__(self, mode: HandoffMode, n_floors: int = 5, ...) -> None:
        # STAGE 2 산출물
        self.space_graph = build_building_graph(
            n_floors=n_floors,
            n_offices_per_floor=7,
            corridor_length_m=20.0,
            n_people_only_evs=1,
            n_shared_evs=1,
        )
        self.space_graph = add_lobby_handoff_zones(
            self.space_graph, n_locker_compartments=4
        )
        self.ev_kin = ElevatorKinematics()
        
        # STAGE 3 에서 추가: 8-agent system
        # self.agents = [...]
```

각 Agent (STAGE 3) 가 STAGE 2 그래프를 사용하는 방식:

| Agent | 사용 방식 |
|---|---|
| RobotAgent | `shortest_walk_path(g, src, tgt, robot=True)` — EV1 회피 |
| ExternalRiderAgent (H0) | `shortest_walk_path(g, src, tgt, robot=False)` — EV1·EV2 자유 |
| LockerAgent | `lobby_locker_bank` 노드 위치만 |
| ControlSystemAgent | 노드 간 거리 query 로 dispatch |
| ElevatorAgent | `elevator_nodes(g, ev_id)` + `ElevatorKinematics.travel_time_sec()` |
| PedestrianAgent | `elevator_nodes(g, 'EV1')` 호출 |
| CustomerAgent | `offices_on_floor(g, floor)` 에 균등 배정 |
| BuildingManagerAgent | 전체 그래프 read-only (NPV 산정용) |

---

## 11. 시각화 사양 (D4 상세)

### Figure 1: `fig_building_section.png` (paper §5 main)

```
 5F  ─┤ EV1 │     7 offices (3m spacing)     │ EV2 ├─
 4F  ─┤     │                                 │     ├─
 3F  ─┤     │                                 │     ├─
 2F  ─┤     │                                 │     ├─
 1F  ─┤  Lobby + Handoff Zone (entry,         │     ├─
       │   counter, queue, locker, pickup)    │      │
B1F  ─┤     │ Charging │ Robot Waiting        │     ├─
      ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
       0m              20m corridor                 22m
```
- 색상: EV1 주황 / EV2 녹색 / office 파랑 / corridor 연회색 / lobby 빨강 계열
- 척도: m 단위 격자 (1m grid lines)
- 라벨: 각 EV 의 capacity 명시 ("EV1: 10p", "EV2: 10p/6p+robot")

### Figure 2: `fig_floor_plan_typical.png` (사무 층)

```
                  +-------+-------+-------+-------+-------+-------+-------+
                  | O_0   | O_1   | O_2   | O_3   | O_4   | O_5   | O_6   |
                  +-------+-------+-------+-------+-------+-------+-------+
       EV1 ━━━━━━━━━━ corridor (20m, 1m grid) ━━━━━━━━━━ EV2
                  +-------+-------+-------+-------+-------+-------+-------+
                  |  EV halls / wall                                     |
                  +-------+-------+-------+-------+-------+-------+-------+
```
- 거리 라벨: 1, 4, 7, 10, 13, 16, 19 m
- corridor 1m grid 점선 표시
- EV1 (주황), EV2 (녹색) 색 코딩

### Figure 3: `fig_lobby_layout.png` (1F)

```
   +----------------------------------------------------+
   | lobby_entry (외부 진입)                            |
   |                                                    |
   |  handoff_counter ──── queue_zone (8명 대기)         |
   |       (H1)                  (H2)                   |
   |                                                    |
   |  locker_bank ─── robot_pickup_zone                 |
   |   (H3: 4 compartments)    (로봇 인계)              |
   |                                                    |
   |       direct_corridor ─── EV1 / EV2                |
   |               (H0)                                 |
   +----------------------------------------------------+
```
- 각 zone 의 capacity 명시
- 색상: H0 회색, H1 빨강, H2 노랑, H3 녹색

---

## 12. 일정 및 진입 조건

### 예상 일정
- **착수 ~ 완료**: ~7 시간 (test 작성 포함)
- 검증: 48 → 75 tests 증가 (skipped 5개 중 elevator_physics 1개는 실제 테스트로 전환)

### STAGE 2 완료 조건
1. ✅ `build_building_graph(5F)` 가 ~154 노드 그래프 생성
2. ✅ B1F → 5F-office query 가 정확한 거리·EV ID 반환
3. ✅ `ElevatorKinematics` 가 5개 floor pair 의 검증 수치 모두 일치
4. ✅ EV1 / EV2 라우팅 분기 (robot 인자) 동작
5. ✅ 3개 paper figure 생성 (paper §5 즉시 사용 가능)
6. ✅ 27 new tests 모두 통과

### STAGE 3 진입 조건 (모두 충족 시)
- 위 6가지 + 빌딩 시뮬레이션의 *공간 입력 query* 가 모든 Agent 사용 패턴을 커버

---

## 13. 잠재 후속 보강 (STAGE 2 후, 선택)

- **혼잡 모델 정밀화**: 현재 `corridor_density()` 는 ±2m 윈도우 단순 평균. LWR 모델 격상은 framework §2.7 에서 명시적으로 배제 (referee 사전 대응).
- **10F E3 확장**: `build_building_graph(n_floors=10, ...)` 호환성은 STAGE 2 에서 보장. E3 실험은 1차 결과 후 결정.
- **다중 빌딩**: 현재 단일 빌딩만. 다중 빌딩 네트워크 (라이더가 여러 빌딩 순회) 는 framework §2.7 에서 배제.

---

## 14. 즉시 다음 단계

STAGE 2.1 부터 순차 진행:
1. `simulation/space.py` 의 `build_building_graph` 구현 (1.5h)
2. 기본 노드/엣지 카운트 sanity test 6개 작성
3. 거리 query API 추가 (1h)
4. ElevatorKinematics 별도 파일 (1h)
5. 로비 zone 추가 (1h)
6. EV1/EV2 라우팅 분기 (1h)
7. 정적 평면도 3장 (1.5h)
8. 통합 테스트 + commit
