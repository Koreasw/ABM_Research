"""차트 스펙 — 순수 데이터. 렌더러도 시뮬레이터도 import하지 않는다.

여기의 어휘가 곧 "1-사이클 차트란 무엇인가"의 정의다. 새 에이전트가 표현되지
않으면 spec을 넓혀라. `specs/`에 raw HTML을 끼워 넣는 순간 이 패키지의 존재
이유가 사라진다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# --------------------------------------------------------------------- 출처
# 차트가 "이미 도는 것"을 그린 것인지 "아직 없는 것"을 그린 것인지는 내용이지
# 장식이 아니다. 구분하지 않으면 둘이 같은 무게로 읽힌다.

@dataclass(frozen=True)
class Provenance:
    """스펙이 무엇을 근거로 그려졌는가.

    `pending=False`가 정상이다 — 상태 이름을 살아 있는 코드에서 import했고,
    개명은 렌더 시점 예외가 된다. `pending=True`는 **구현보다 스펙이 먼저 온**
    경우로, 그때 차트는 설계 제안이자 그 Step의 수용 기준 노릇을 한다. 코드가
    생기는 순간 스펙이 그것을 import해서 자기 자신과 대조해야 하며, 그 대조가
    통과하면 `pending`을 내린다.
    """
    label: str                      # 배지 텍스트 ("구현 기준" / "설계 선행")
    detail: str                     # 근거 ("simulation/agents/robot.py · Step A1")
    pending: bool = False


def state_names(cls: type) -> tuple[str, ...]:
    """클래스가 선언한 FSM 상태 상수의 **이름** 전부.

    `RobotState`처럼 Enum으로 상태를 적은 에이전트가 아니라,
    `ExternalRiderAgent`처럼 대문자 클래스 상수로 적은 에이전트를 위한 것이다.
    새 상태가 생기면 자동으로 목록에 들어오므로 `CycleSpec.covers_states`와
    엮으면 "차트가 상태 하나를 빠뜨렸다"가 렌더 시점 예외가 된다.

    대문자 이름의 `str` 클래스 속성만 센다 — `kind = "rider"` 같은 소문자
    메타데이터가 상태로 오해되지 않게 하는 것이 이 조건의 목적이다.
    """
    return tuple(k for k, v in vars(cls).items() if k.isupper() and isinstance(v, str))


# --------------------------------------------------------------------- 시간
# 사이클 구간의 소요시간은 세 종류뿐이다. 세 번째(Variable)가 중요하다 —
# 큐잉 구간을 "0"이나 "평균"으로 뭉개면 포화(rho>1)에서 발산하는 것이 정확히
# 어느 칸인지가 차트에서 사라진다.

@dataclass(frozen=True)
class Fixed:
    """결정적 소요. `sec`가 리본의 폭이 된다."""
    sec: float
    note: str = ""                  # 계산 근거 ("5.0 m / 1.0 m/s")

    @property
    def ribbon_sec(self) -> float:
        return self.sec

    @property
    def label(self) -> str:
        return f"{self.sec:.1f} s"


@dataclass(frozen=True)
class Stochastic:
    """분포에서 뽑는 소요. 리본에는 평균 폭으로 그리되 라벨은 분포를 밝힌다."""
    mean_sec: float
    dist: str                       # "N(60, 15**2) 0-절단"
    note: str = ""

    @property
    def ribbon_sec(self) -> float:
        return self.mean_sec

    @property
    def label(self) -> str:
        return f"{self.mean_sec:.1f} s"


@dataclass(frozen=True)
class Variable:
    """부하에 따라 변하는 큐잉 구간. 폭이 없으므로 리본에 빗금으로 그린다."""
    note: str = ""                  # "0 가능" / ">= 1 tick"

    @property
    def ribbon_sec(self) -> float:
        return 0.0

    @property
    def label(self) -> str:
        return "가변"


@dataclass(frozen=True)
class NoTime:
    """시간 축에 올리지 않는 칸 (분기 결과 등)."""
    @property
    def ribbon_sec(self) -> float:
        return 0.0

    @property
    def label(self) -> str:
        return "—"


Duration = Fixed | Stochastic | Variable | NoTime


# --------------------------------------------------------------------- 단계

@dataclass(frozen=True)
class Step:
    """사이클의 한 칸. 표의 한 행이자 리본의 한 세그먼트이자 도면의 한 마커.

    셋이 같은 객체에서 나오므로 번호가 어긋날 수 없다 — 손으로 세 번 적던
    시절의 주된 오류원을 구조로 제거한 것이다.
    """
    n: str                          # "1", "13", "->X" (분기는 번호가 아니다)
    state: str                      # FSM 상태명 (코드의 enum 값 그대로)
    bucket: str                     # Palette의 키
    what: str                       # 무슨 일이 일어나나
    duration: Duration
    why: str                        # 결정·논리
    leg: str = ""                   # 직교 속성 ("to_counter", "direction = +1")
    tag: str = ""                   # "결정 #26", "R0-3", "함정"
    in_ribbon: bool = True          # 시간 리본에 올릴 것인가


# --------------------------------------------------------------------- 도면
# 건물 단면. 이 모델의 모든 에이전트는 "층 + 샤프트 + 레인" 위를 움직이므로
# 로봇 전용이 아니라 클래스 공통의 어휘다.

@dataclass(frozen=True)
class Level:
    """한 층. `spans`는 슬래브를 그릴 x 구간들 — 샤프트 자리는 비운다."""
    label: str
    baseline_y: float               # 에이전트가 걷는 높이
    slab_y: float
    spans: tuple[tuple[float, float], ...]
    label_x: float = 64.0
    label_dy: float = 26.0          # 슬래브 아래쪽으로의 오프셋


@dataclass(frozen=True)
class Shaft:
    x: float
    width: float
    y_top: float
    y_bottom: float
    label: str = ""                 # 샤프트 위 캡션
    inner_label: str = ""           # 샤프트 안 세로 캡션 (주행시간 등)


@dataclass(frozen=True)
class Fixture:
    """도크·카운터·승강장·문 같은 고정 설비. 바닥에 놓인 패드로 그린다."""
    x: float
    y: float
    width: float
    bucket: str
    label: str
    label_y: float
    anchor: str = "middle"


@dataclass(frozen=True)
class DimLabel:
    """거리·시간 치수선 텍스트."""
    x: float
    y: float
    text: str
    anchor: str = "middle"


@dataclass(frozen=True)
class Path:
    points: tuple[tuple[float, float], ...]
    bucket: str
    dashed: bool = False
    arrow: bool = False


@dataclass(frozen=True)
class Marker:
    """도면 위의 단계 번호. `n`은 Step.n과 일치해야 한다 (렌더러가 검증)."""
    n: str
    x: float
    y: float


@dataclass(frozen=True)
class Diagram:
    width: float
    height: float
    alt: str                        # 스크린리더용 설명 — 비우지 말 것
    caption: str
    levels: tuple[Level, ...] = ()
    # 복수형인 이유: H0 라이더에게 수직 채널은 둘이다(EV 샤프트 + 계단). 하나만
    # 그리면 분기가 그림에서 사라지고, 그 분기는 상태 2개를 차지한다.
    shafts: tuple[Shaft, ...] = ()
    fixtures: tuple[Fixture, ...] = ()
    dims: tuple[DimLabel, ...] = ()
    paths: tuple[Path, ...] = ()
    markers: tuple[Marker, ...] = ()
    min_px: int = 780               # 이보다 좁아지면 가로 스크롤


# --------------------------------------------------------------------- 주변

@dataclass(frozen=True)
class Metric:
    label: str
    value: str
    unit: str = ""


@dataclass(frozen=True)
class Note:
    stamp: str                      # 눈썹 라벨 ("전력 수지", "확인 필요")
    title: str
    body: str                       # 인라인 HTML 허용 (<code>, <strong>, <em>)
    flag: bool = False              # 좌측에 경고 레일


@dataclass(frozen=True)
class Palette:
    """버킷 이름 -> (light hex, dark hex).

    로봇의 경우 키가 `REPORT_BUCKETS`와 정확히 일치해야 하며, spec이 그것을
    import해서 대조한다. 색은 장식이 아니라 버킷의 시각적 이름이다.
    """
    light: dict[str, str]
    dark: dict[str, str]
    legend_order: tuple[str, ...] = ()
    legend_note: str = ""

    def __post_init__(self) -> None:
        missing = set(self.light) ^ set(self.dark)
        if missing:
            raise ValueError(f"팔레트의 light/dark 키 불일치: {sorted(missing)}")

    def buckets(self) -> tuple[str, ...]:
        return self.legend_order or tuple(self.light)


# --------------------------------------------------------------------- 전체

@dataclass
class CycleSpec:
    slug: str                       # 출력 파일명 (`robot_h1` -> robot_h1.html)
    title: str
    eyebrow: str
    standfirst: str                 # 인라인 HTML 허용
    metrics: tuple[Metric, ...]
    ribbon_lede: str
    ribbon_axis_note: str
    steps: tuple[Step, ...]
    palette: Palette
    diagram: Diagram | None = None
    notes: tuple[Note, ...] = ()
    closing: str = ""
    section_titles: dict[str, str] = field(default_factory=dict)
    provenance: Provenance | None = None
    # 이 에이전트의 FSM 상태 **전부**. 코드에서 뽑아 넣는다(`state_names()` 또는
    # Enum 순회). 로봇의 `REPORT_BUCKETS` 대조와 같은 역할을 상태 층위에서 한다 —
    # 버킷이 없는 에이전트에게는 이쪽이 유일한 드리프트 방어다.
    covers_states: tuple[str, ...] = ()

    def validate(self) -> None:
        """렌더 전에 스펙 자체의 모순을 잡는다.

        차트가 틀리는 방식은 대개 "표에는 있는데 도면에 없는 단계"이거나
        "팔레트에 없는 버킷"이거나 "코드에는 있는데 차트에 없는 상태"다. 전부
        조용히 넘어가면 눈으로만 발견된다.
        """
        if self.covers_states:
            declared = set(self.covers_states)
            drawn = {s.state for s in self.steps}
            if missing := declared - drawn:
                raise ValueError(
                    f"차트가 빠뜨린 상태: {sorted(missing)}. "
                    "에이전트에 상태가 추가되었다면 단계도 같이 늘려야 한다."
                )
            if unknown := drawn - declared:
                raise ValueError(
                    f"코드에 없는 상태를 그렸다: {sorted(unknown)}. "
                    "개명되었거나 스펙이 상태를 지어낸 것이다."
                )
        known = set(self.palette.light)
        for s in self.steps:
            if s.bucket not in known:
                raise ValueError(
                    f"단계 {s.n}({s.state})의 버킷 {s.bucket!r}이 팔레트에 없다"
                )
        if not self.diagram:
            return
        step_ns = {s.n for s in self.steps}
        for m in self.diagram.markers:
            if m.n not in step_ns:
                raise ValueError(f"도면 마커 {m.n!r}에 대응하는 단계가 없다")
        drawn = [f.bucket for f in self.diagram.fixtures]
        drawn += [p.bucket for p in self.diagram.paths]
        for bucket in drawn:
            if bucket not in known:
                raise ValueError(f"도면 요소의 버킷 {bucket!r}이 팔레트에 없다")

    def deterministic_sec(self) -> float:
        """리본에 올라간 결정적 구간의 합. 큐잉 0을 가정한 하한이다."""
        return sum(s.duration.ribbon_sec for s in self.steps if s.in_ribbon)
