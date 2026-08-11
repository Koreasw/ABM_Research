"""살아 있는 상수 — config와 건물 그래프에서 직접 뽑는다.

차트에 숫자를 손으로 적지 않기 위한 모듈이다. `etc/HANDOFF_phase_a.md` §A4의
로봇 기하 상수가 실제 그래프와 1 m 어긋나 있었던 것이 이 모듈이 존재하는 이유다:
문서에 적힌 상수는 조용히 늙지만, 그래프에서 계산한 상수는 config가 바뀌면 같이
바뀐다.

그래프는 `model.py`와 **동일한 경로**로 만든다 (`build_from_config` +
`add_lobby_handoff_zones`). 여기서 지름길을 쓰면 차트가 재는 건물이 시뮬레이터가
도는 건물과 달라진다.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import networkx as nx
import yaml

from simulation.config_params import HandoffParams, RobotParams
from simulation.elevator_physics import ElevatorKinematics
from simulation.space import add_lobby_handoff_zones, build_from_config
from simulation.vertical_transport import VerticalTransportModel

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "configs" / "baseline_10f.yaml"

HOME_NODE = "lobby_robot_pickup_zone"
COUNTER_NODE = "lobby_handoff_counter"
ENTRY_NODE = "lobby_entry"
STAIR_NODE_1F = "lobby_direct_corridor"

# 라이더 서비스 시간만은 config가 아니라 시나리오의 RIDERS 표에서 온다
# (`model.service_time_for`). run 산출물이 아니라 **입력 데이터**이므로 이 패키지의
# "results를 읽지 않는다" 불변식은 유지된다. 없으면 config 폴백으로 조용히 물러선다.
DEFAULT_SCENARIO = ROOT / "data" / "data1" / "K50_1.json"


def load_config(path: str | Path = DEFAULT_CONFIG) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def build_graph(cfg: dict[str, Any]) -> nx.MultiDiGraph:
    return add_lobby_handoff_zones(
        build_from_config(cfg),
        n_locker_compartments=cfg["locker"]["n_compartments"],
    )


def walk_m(g: nx.MultiDiGraph, a: str, b: str) -> float:
    """두 노드 사이 최단 **보행** 거리(m).

    MultiDiGraph라 병렬 간선이 있고, EV 간선은 `distance_m`이 없다(수직 이동은
    거리가 아니라 시간으로 정의된다). 그래서 가중치 함수가 EV 간선을 사실상
    무한대로 취급해 보행 경로만 남긴다 — 이걸 놓치면 "1F에서 5F까지 0 m"가 된다.
    """
    def weight(_u: str, _v: str, edges: dict) -> float:
        return min(e.get("distance_m", float("inf")) for e in edges.values())

    return nx.shortest_path_length(g, a, b, weight=weight)


# --------------------------------------------------------------------- 로봇

@dataclass(frozen=True)
class RobotCycleGeometry:
    """로봇 1 사이클이 필요로 하는 전부. 전 필드가 config/그래프 유래다."""

    floor: int                      # 대표 배달 층
    ev_id: str                      # 대표 공용 카

    # 수평 (m)
    home_to_counter_m: float
    counter_to_ev_m: float
    ev_to_home_m: float
    ev_to_office_mean_m: float
    ev_to_office_min_m: float
    ev_to_office_max_m: float

    # 수직 (s)
    ride_sec: float
    door_sec: float

    # 서비스 (s)
    speed_mps: float
    drop_sec: float
    handoff_mean_sec: float
    handoff_sd_sec: float

    # 배터리
    capacity_wh: float
    wh_per_m: float
    wh_per_min_idle: float
    charge_wh_per_min: float
    soc_low_pct: float
    soc_resume_pct: float

    # 건물 (도면 라벨용)
    office_positions_m: tuple[float, ...]
    ev_corridor_pos_m: float
    shared_ev_ids: tuple[str, ...]
    floor_height_m: float

    @property
    def rise_m(self) -> float:
        """1F에서 대표 층까지의 실제 상승 높이."""
        return (self.floor - 1) * self.floor_height_m

    # ---------------------------------------------------------- 파생 (보행)
    @property
    def to_counter_sec(self) -> float:
        return self.home_to_counter_m / self.speed_mps

    @property
    def to_ev_up_sec(self) -> float:
        return self.counter_to_ev_m / self.speed_mps

    @property
    def to_office_sec(self) -> float:
        return self.ev_to_office_mean_m / self.speed_mps

    @property
    def to_ev_down_sec(self) -> float:
        return self.to_office_sec

    @property
    def to_home_sec(self) -> float:
        return self.ev_to_home_m / self.speed_mps

    @property
    def walk_total_m(self) -> float:
        return (
            self.home_to_counter_m
            + self.counter_to_ev_m
            + 2.0 * self.ev_to_office_mean_m
            + self.ev_to_home_m
        )

    # ---------------------------------------------------------- 파생 (탑승)
    @property
    def riding_sec(self) -> float:
        """탑승 1회 = 도어 사이클 + 주행.

        하차 쪽 도어는 세지 않는다: `_open_doors()`가 문을 여는 그 순간
        하차를 처리하므로 하차 승객에게는 도어 시간이 붙지 않는다. 승차는 반대로
        타고 나서 타이머가 다 흘러야 출발하므로 도어 1회가 온전히 붙는다.
        """
        return self.door_sec + self.ride_sec

    # ---------------------------------------------------------- 파생 (전력)
    @property
    def stationary_sec(self) -> float:
        """큐잉 0 가정의 비주행 시간. 대기가 붙으면 늘기만 한다."""
        return self.handoff_mean_sec + self.drop_sec + 2.0 * self.riding_sec

    @property
    def cycle_sec(self) -> float:
        """큐잉 0 가정의 사이클 총 소요. 라이더 기하와 나란히 놓기 위한 값이라
        여기에 둔다 — 스펙의 리본 합계와 일치해야 하고, `robot_h1`이 그것을
        렌더 시점에 대조한다."""
        return (
            self.to_counter_sec
            + self.handoff_mean_sec
            + self.to_ev_up_sec
            + self.riding_sec
            + self.to_office_sec
            + self.drop_sec
            + self.to_ev_down_sec
            + self.riding_sec
            + self.to_home_sec
        )

    @property
    def walk_wh(self) -> float:
        return self.walk_total_m * self.wh_per_m

    @property
    def idle_wh(self) -> float:
        return self.stationary_sec / 60.0 * self.wh_per_min_idle

    @property
    def cycle_wh(self) -> float:
        """코드가 거리와 시간을 **더하지 않고 택일**하는 것을 그대로 반영한다:
        걸은 틱은 거리로만, 나머지 틱은 시간으로만 과금된다."""
        return self.walk_wh + self.idle_wh

    @property
    def cycle_soc_pct(self) -> float:
        return 100.0 * self.cycle_wh / self.capacity_wh

    @property
    def net_charge_wh_per_min(self) -> float:
        """도킹 중에도 대기 소모가 흐르므로 실효 충전은 명판보다 느리다."""
        return self.charge_wh_per_min - self.wh_per_min_idle

    @property
    def resume_charge_min(self) -> float:
        """soc_low -> soc_resume 실소요(분). 명판 계산과 어긋나는 값이다."""
        span_wh = self.capacity_wh * (self.soc_resume_pct - self.soc_low_pct) / 100.0
        return span_wh / self.net_charge_wh_per_min

    @property
    def nameplate_charge_min(self) -> float:
        span_wh = self.capacity_wh * (self.soc_resume_pct - self.soc_low_pct) / 100.0
        return span_wh / self.charge_wh_per_min


def robot_geometry(
    cfg: dict[str, Any] | None = None,
    *,
    floor: int = 5,
) -> RobotCycleGeometry:
    """대표 배달 층 하나에 대한 로봇 사이클 기하를 실측한다.

    공용 카는 `building.shared_ev_ids`의 첫 번째를 쓴다. 기하는 EV3/EV4가
    대칭이라 어느 쪽을 골라도 같지만, `ev_id` 타이브레이크는 비대칭이므로
    "아무거나"가 아니라 "첫 번째"로 못박아 재현 가능하게 둔다.
    """
    cfg = cfg or load_config()
    g = build_graph(cfg)

    shared = list(cfg["building"]["shared_ev_ids"])
    if not shared:
        raise ValueError("building.shared_ev_ids가 비어 있다 — 로봇 모드가 성립하지 않는다")
    ev_id = shared[0]

    n_floors = int(cfg["building"]["n_floors"])
    if not 2 <= floor <= n_floors:
        raise ValueError(f"대표 층 {floor}는 2..{n_floors} 범위를 벗어난다")

    n_off = int(cfg["building"]["n_offices_per_floor"])
    offices = [f"floor_{floor}_office_{i}" for i in range(n_off)]
    ev_node = f"ev_{ev_id}_{floor}"
    to_office = [walk_m(g, ev_node, o) for o in offices]

    robot = RobotParams.from_config(cfg)
    handoff = HandoffParams.from_config(cfg)
    kin = ElevatorKinematics.from_config(cfg)
    bat = robot.battery

    # ev_id -> 복도 위치: 리스트 순서가 EV1..EVn을 정의한다 (space.py 관례)
    ev_positions = cfg["building"]["ev_corridor_positions_m"]
    ev_order = [f"EV{i + 1}" for i in range(len(ev_positions))]
    ev_corridor_pos = float(ev_positions[ev_order.index(ev_id)])

    return RobotCycleGeometry(
        floor=floor,
        ev_id=ev_id,
        home_to_counter_m=walk_m(g, HOME_NODE, COUNTER_NODE),
        counter_to_ev_m=walk_m(g, COUNTER_NODE, f"ev_{ev_id}_1"),
        ev_to_home_m=walk_m(g, f"ev_{ev_id}_1", HOME_NODE),
        ev_to_office_mean_m=statistics.mean(to_office),
        ev_to_office_min_m=min(to_office),
        ev_to_office_max_m=max(to_office),
        ride_sec=kin.travel_time_sec(1, floor),
        door_sec=float(cfg["elevator"]["door_open_close_sec"]),
        speed_mps=robot.speed_mps,
        drop_sec=robot.service_time_drop_sec,
        handoff_mean_sec=handoff.service_mean_sec,
        handoff_sd_sec=handoff.service_sd_sec,
        capacity_wh=bat.capacity_wh,
        wh_per_m=bat.wh_per_m,
        wh_per_min_idle=bat.wh_per_min_idle,
        charge_wh_per_min=bat.charge_wh_per_min,
        soc_low_pct=bat.soc_low_pct,
        soc_resume_pct=bat.soc_resume_pct,
        office_positions_m=tuple(
            float(x) for x in cfg["building"]["office_positions_m"][
                : cfg["building"]["n_offices_per_floor"] // 2
            ]
        ),
        ev_corridor_pos_m=ev_corridor_pos,
        shared_ev_ids=tuple(shared),
        floor_height_m=float(cfg["building"]["floor_height_m"]),
    )


# ------------------------------------------------------------------- 라이더 H0

def _service_by_type(
    scenario: str | Path | None,
) -> tuple[tuple[str, float], ...]:
    """시나리오 RIDERS 표의 타입별 서비스 시간. 없으면 빈 튜플."""
    if scenario is None:
        return ()
    path = Path(scenario)
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        return ()
    from analysis.load_data import load_riders

    return tuple((r.type, float(r.service_time_sec)) for r in load_riders(path))


@dataclass(frozen=True)
class RiderCycleGeometry:
    """H0 라이더 1 사이클 — 입구에서 입구까지.

    로봇 기하와 **같은 대표 층·같은 파생 규약**(riding = 도어 + 주행)을 쓴다.
    두 차트의 초 단위가 비교 가능해야 하기 때문이다: 규약이 갈리면 "라이더가
    로봇보다 빠르다"가 기하가 아니라 계산 방식의 산물이 된다.
    """

    floor: int
    ev_id: str

    # 수평 — EV 경로 (m)
    entry_to_ev_m: float
    ev_to_office_mean_m: float
    ev_to_office_min_m: float
    ev_to_office_max_m: float
    office_to_ev_mean_m: float
    ev_to_entry_m: float

    # 수평·수직 — 계단 분기
    entry_to_stair_m: float
    stair_to_office_mean_m: float
    stair_sec_per_floor: float
    stair_corr_pos: int
    p_elevator: float

    # 수직 (s)
    ride_sec: float
    door_sec: float

    # 서비스 (s)
    speed_mps: float
    service_fallback_sec: float
    service_by_type: tuple[tuple[str, float], ...]

    # 건물 (도면 라벨용)
    ev_corridor_pos_m: float
    all_ev_ids: tuple[str, ...]
    shared_ev_ids: tuple[str, ...]
    office_positions_m: tuple[float, ...]
    floor_height_m: float

    @property
    def rise_m(self) -> float:
        return (self.floor - 1) * self.floor_height_m

    # ---------------------------------------------------------- 파생 (보행)
    @property
    def to_vert_sec(self) -> float:
        return self.entry_to_ev_m / self.speed_mps

    @property
    def to_office_sec(self) -> float:
        return self.ev_to_office_mean_m / self.speed_mps

    @property
    def back_sec(self) -> float:
        return self.office_to_ev_mean_m / self.speed_mps

    @property
    def to_exit_sec(self) -> float:
        return self.ev_to_entry_m / self.speed_mps

    @property
    def walk_total_m(self) -> float:
        return (
            self.entry_to_ev_m
            + self.ev_to_office_mean_m
            + self.office_to_ev_mean_m
            + self.ev_to_entry_m
        )

    # ---------------------------------------------------------- 파생 (탑승)
    @property
    def riding_sec(self) -> float:
        """로봇과 동일한 규약 — 승차 도어 1회 + 주행. 하차 도어는 세지 않는다."""
        return self.door_sec + self.ride_sec

    # ---------------------------------------------------------- 파생 (서비스)
    @property
    def service_sec(self) -> float:
        """리본에 올리는 값. config 폴백을 쓴다 — 실제는 타입별로 갈린다."""
        return self.service_fallback_sec

    @property
    def service_range(self) -> tuple[float, float] | None:
        if not self.service_by_type:
            return None
        vals = [v for _, v in self.service_by_type]
        return min(vals), max(vals)

    # ---------------------------------------------------------- 파생 (합계)
    @property
    def cycle_sec(self) -> float:
        """큐잉 0 가정의 건물 체류시간 하한 = T_lobby의 하한."""
        return (
            self.to_vert_sec
            + self.riding_sec
            + self.to_office_sec
            + self.service_sec
            + self.back_sec
            + self.riding_sec
            + self.to_exit_sec
        )

    # ---------------------------------------------------------- 파생 (계단)
    @property
    def stair_sec(self) -> float:
        return (self.floor - 1) * self.stair_sec_per_floor

    @property
    def to_stair_sec(self) -> float:
        return self.entry_to_stair_m / self.speed_mps

    @property
    def stair_to_office_sec(self) -> float:
        return self.stair_to_office_mean_m / self.speed_mps

    @property
    def stair_cycle_sec(self) -> float:
        """계단 분기의 사이블 총합. EV 경로와의 차가 곧 로짓의 입력이다."""
        return 2.0 * (
            self.to_stair_sec + self.stair_sec + self.stair_to_office_sec
        ) + self.service_sec


def rider_geometry(
    cfg: dict[str, Any] | None = None,
    *,
    floor: int = 5,
    scenario: str | Path | None = DEFAULT_SCENARIO,
) -> RiderCycleGeometry:
    """H0 라이더의 대표 사이클 기하.

    대표 카는 **무부하 타이브레이크**의 결과다: 모든 카가 1F에 서 있고 pending
    stop이 없으면 `_estimate_wait`이 전부 0으로 같아지고, `choose_elevator`가
    `ev_id` 오름차순 정렬 후 `min`을 취하므로 가장 낮은 `ev_id`가 나온다.
    부하가 걸리면 달라지는 값이라 "대표"이지 "고정"이 아니다 — 로봇이
    `shared_ev_ids`로 **강제**되는 것과 대비되는 지점이고, 그 대비가 W5d의
    designated-dispatch 대가를 만든다.
    """
    cfg = cfg or load_config()
    g = build_graph(cfg)

    n_floors = int(cfg["building"]["n_floors"])
    if not 2 <= floor <= n_floors:
        raise ValueError(f"대표 층 {floor}는 2..{n_floors} 범위를 벗어난다")

    ev_positions = cfg["building"]["ev_corridor_positions_m"]
    all_ev_ids = tuple(f"EV{i + 1}" for i in range(len(ev_positions)))
    ev_id = sorted(all_ev_ids)[0]

    n_off = int(cfg["building"]["n_offices_per_floor"])
    offices = [f"floor_{floor}_office_{i}" for i in range(n_off)]
    ev_node = f"ev_{ev_id}_{floor}"
    to_office = [walk_m(g, ev_node, o) for o in offices]
    back = [walk_m(g, o, ev_node) for o in offices]

    stair_pos = g.graph["corridor_mid_pos"]
    stair_node = f"floor_{floor}_corr_{stair_pos}"
    from_stair = [walk_m(g, stair_node, o) for o in offices]

    kin = ElevatorKinematics.from_config(cfg)
    vt = VerticalTransportModel.from_config(cfg)

    return RiderCycleGeometry(
        floor=floor,
        ev_id=ev_id,
        entry_to_ev_m=walk_m(g, ENTRY_NODE, f"ev_{ev_id}_1"),
        ev_to_office_mean_m=statistics.mean(to_office),
        ev_to_office_min_m=min(to_office),
        ev_to_office_max_m=max(to_office),
        office_to_ev_mean_m=statistics.mean(back),
        ev_to_entry_m=walk_m(g, f"ev_{ev_id}_1", ENTRY_NODE),
        entry_to_stair_m=walk_m(g, ENTRY_NODE, STAIR_NODE_1F),
        stair_to_office_mean_m=statistics.mean(from_stair),
        stair_sec_per_floor=float(cfg["vertical"]["stair_sec_per_floor"]),
        stair_corr_pos=int(stair_pos),
        p_elevator=vt.p_elevator(floor),
        ride_sec=kin.travel_time_sec(1, floor),
        door_sec=float(cfg["elevator"]["door_open_close_sec"]),
        speed_mps=float(cfg["rider_process"]["walk_speed_mps"]),
        service_fallback_sec=float(cfg["rider_process"]["service_time_sec"]),
        service_by_type=_service_by_type(scenario),
        ev_corridor_pos_m=float(ev_positions[all_ev_ids.index(ev_id)]),
        all_ev_ids=all_ev_ids,
        shared_ev_ids=tuple(cfg["building"]["shared_ev_ids"]),
        office_positions_m=tuple(
            float(x) for x in cfg["building"]["office_positions_m"][: n_off // 2]
        ),
        floor_height_m=float(cfg["building"]["floor_height_m"]),
    )


# ------------------------------------------------------------- 인계 라이더 H1

@dataclass(frozen=True)
class HandoffRiderCycleGeometry:
    """H1 인계 라이더 1 사이클 — 입구에서 인계 카운터를 찍고 다시 입구로.

    대조군 둘을 통째로 들고 있다. 이 사이클의 의미는 자기 길이가 아니라
    **H0 라이더에게서 무엇이 떨어져 나가 로봇에게 갔는가**이고, 그 차이는 두
    기하를 나란히 놓아야만 계산된다.
    """

    entry_to_counter_m: float
    counter_to_entry_m: float
    speed_mps: float
    handoff_mean_sec: float
    handoff_sd_sec: float
    h0: RiderCycleGeometry
    robot: RobotCycleGeometry

    @property
    def to_counter_sec(self) -> float:
        return self.entry_to_counter_m / self.speed_mps

    @property
    def to_exit_sec(self) -> float:
        return self.counter_to_entry_m / self.speed_mps

    @property
    def cycle_sec(self) -> float:
        return self.to_counter_sec + self.handoff_mean_sec + self.to_exit_sec

    @property
    def walk_total_m(self) -> float:
        return self.entry_to_counter_m + self.counter_to_entry_m

    # ---------------------------------------------------------- 파생 (대조)
    @property
    def saved_sec(self) -> float:
        """라이더가 건물에서 덜 보내는 시간. w_R이 곱해지는 바로 그 양이다."""
        return self.h0.cycle_sec - self.cycle_sec

    @property
    def saved_pct(self) -> float:
        return 100.0 * self.saved_sec / self.h0.cycle_sec

    @property
    def system_sec(self) -> float:
        """라이더 + 로봇. 시스템이 **더 많은** 총 시간을 쓴다는 사실의 근거."""
        return self.cycle_sec + self.robot.cycle_sec

    @property
    def system_delta_sec(self) -> float:
        return self.system_sec - self.h0.cycle_sec


def handoff_rider_geometry(
    cfg: dict[str, Any] | None = None,
    *,
    floor: int = 5,
    scenario: str | Path | None = DEFAULT_SCENARIO,
) -> HandoffRiderCycleGeometry:
    cfg = cfg or load_config()
    g = build_graph(cfg)
    handoff = HandoffParams.from_config(cfg)

    return HandoffRiderCycleGeometry(
        entry_to_counter_m=walk_m(g, ENTRY_NODE, COUNTER_NODE),
        counter_to_entry_m=walk_m(g, COUNTER_NODE, ENTRY_NODE),
        speed_mps=float(cfg["rider_process"]["walk_speed_mps"]),
        handoff_mean_sec=handoff.service_mean_sec,
        handoff_sd_sec=handoff.service_sd_sec,
        h0=rider_geometry(cfg, floor=floor, scenario=scenario),
        robot=robot_geometry(cfg, floor=floor),
    )
