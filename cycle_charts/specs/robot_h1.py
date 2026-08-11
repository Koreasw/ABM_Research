"""H1 로봇 1 사이클 — 도크 대기에서 도크 대기까지.

대상: `simulation/agents/robot.py`의 `RobotAgent` (Step A1 구현 기준).
대표 케이스: 5F 주문 · 공용 카 · 사무실 평균 거리 · 큐잉 0.

숫자를 이 파일에 적지 않는다
----------------------------
전부 `cycle_charts.geometry.robot_geometry()`가 config와 건물 그래프에서
계산한다. 상태·leg·버킷 이름도 `simulation.agents.robot`에서 import한다 —
`RobotState`에 새 상태가 생기거나 `REPORT_BUCKETS`의 키가 바뀌면 이 스펙이
렌더 시점에 예외로 터지는 것이 의도다.
"""

from __future__ import annotations

from cycle_charts import geometry
from cycle_charts.spec import (
    CycleSpec,
    Diagram,
    DimLabel,
    Fixed,
    Fixture,
    Level,
    Marker,
    Metric,
    Note,
    NoTime,
    Palette,
    Path,
    Provenance,
    Shaft,
    Step,
    Stochastic,
    Variable,
)
from simulation.agents.robot import REPORT_BUCKETS, RobotLeg, RobotState

# 색 = 국면. hue가 사이클의 국면(1F 획득 / 상행·배달 / 복귀 / 도크)을 나르고,
# 같은 국면 안의 단계는 명도로 갈린다. 임의 배색이 아니라 내용의 구조다.
PALETTE = Palette(
    light={
        "wait": "#8C99A5", "meet_rider": "#C98A2E", "handoff": "#C24A15",
        "deliver_up": "#1B6B85", "drop": "#10495A", "return": "#63798F",
        "charge": "#4C8547",
    },
    dark={
        "wait": "#93A1AD", "meet_rider": "#E0A94A", "handoff": "#E4703B",
        "deliver_up": "#4FA3BE", "drop": "#3D8DA5", "return": "#8497AB",
        "charge": "#74AC6C",
    },
    legend_order=tuple(REPORT_BUCKETS),
    legend_note="&larr; <code>REPORT_BUCKETS</code> 7버킷",
)


def _check_buckets() -> None:
    """팔레트 키가 코드의 보고 버킷과 정확히 같은지 확인한다.

    A5의 B-게이트가 "새 상태에는 반드시 버킷이 있어야 한다"를 강제하듯,
    여기서는 "모든 버킷에는 반드시 색이 있어야 한다"를 강제한다.
    """
    diff = set(PALETTE.light) ^ set(REPORT_BUCKETS)
    if diff:
        raise ValueError(
            f"팔레트와 REPORT_BUCKETS가 어긋난다: {sorted(diff)}. "
            "robot.py에 버킷이 추가/개명되었다면 이 스펙의 색도 같이 정해야 한다."
        )


# 아래 표에서 상태·leg를 문자열로 적지 않기 위한 짧은 별칭. 개명이 곧 ImportError다.
_S = RobotState
_L = RobotLeg


def _steps(g: geometry.RobotCycleGeometry) -> tuple[Step, ...]:
    return (
        Step(
            n="1", state=_S.IDLE.name, bucket="wait", tag="결정 #19",
            what="로봇존(도크)에 서서 배차를 기다린다. <strong>대기 중에도 충전한다</strong> — "
                 "도크와 대기 장소가 같은 노드라 “쉬러 가기”와 “충전하러 가기”가 같은 행위다.",
            duration=Variable("배차까지"),
            why="<code>is_available == (state is IDLE)</code>. "
                "배차 가능성이 이 상태의 유일한 정의다.",
        ),
        Step(
            n="2", state=_S.MOVING.name, leg=_L.TO_COUNTER.value, bucket="meet_rider",
            what="디스패처가 <code>assign(order)</code>를 호출 → 인계 카운터로 걷는다. "
                 "이 시점에 적재량은 아직 0이다(음식은 인계 때 받는다).",
            duration=Fixed(g.to_counter_sec,
                           f"{g.home_to_counter_m:g} m ÷ {g.speed_mps:g} m/s"),
            why="배차 불가 상태거나 지하층 주문이면 <code>ValueError</code>. "
                "방어를 로그가 아니라 예외로 둔 것은 조용한 위반을 막기 위해서다.",
        ),
        Step(
            n="3", state=_S.WAIT_RIDER.name, bucket="meet_rider", tag="함정",
            what="카운터 도착. 라이더가 아직 안 왔으면 여기서 선다. "
                 "<strong>독립 상태로 둔 것이 핵심</strong> — “고객에게 이동” 안에 "
                 "숨겨두면 이 체류시간을 잴 수 없다.",
            duration=Variable("≥ 1 틱"),
            why="<code>notify_rider_ready()</code>는 플래그만 세우고 전이는 "
                "<strong>다음 틱</strong>에 일어난다. 틱 순서(라이더 → 로봇)의 실제 "
                "결과라 감추지 않고 노출했다.",
        ),
        Step(
            n="4", state=_S.HANDOFF.name, bucket="handoff", tag="R0-3",
            what="라이더 → 로봇 음식 전달. H1을 정의하는 행위이자 사이클 최대 단일 구간. "
                 "여기서 <code>carrying_vol</code>이 채워진다.",
            duration=Stochastic(
                g.handoff_mean_sec,
                f"N({g.handoff_mean_sec:g}, {g.handoff_sd_sec:g}²) 0-절단",
            ),
            why="난수는 로봇이 아니라 <strong>라이더가 뽑는다</strong> — "
                "<code>'hoff'</code> 스트림 <code>[tag, seed, ord_id]</code>. "
                "한 스트림에 주인은 하나.",
        ),
        Step(
            n="5", state=_S.MOVING.name, leg=_L.TO_EV_UP.value, bucket="deliver_up",
            what="탈 카를 <strong>먼저 고르고</strong> 그 카의 승강장으로 걷는다. "
                 "도착해서 다시 고르지 않는다.",
            duration=Fixed(g.to_ev_up_sec, f"{g.counter_to_ev_m:g} m"),
            why="라이더와 <strong>동일한 규칙</strong>. 도착 시 재선택하면 로봇만 "
                "라이더보다 똑똑해져 W5d의 designated-dispatch 대가(stale 52.95%) "
                "비교가 깨진다. 다른 점은 후보를 공용 카로 제한하는 것뿐.",
        ),
        Step(
            n="6", state=_S.WAIT_EV.name, leg="direction = +1", bucket="deliver_up",
            tag="함정",
            what="hall call 등록 후 대기. 여기가 <strong>사람과 자원을 다투는 지점</strong>이다.",
            duration=Variable("0 가능"),
            why="유휴 카가 같은 층에 있으면 <strong>0틱</strong>이다. A4 수기 체인에서 "
                "상행 대기를 양수로 가정하면 틀린다. 상태 관측은 틱이 아니라 "
                "서브스텝 단위로 샘플링해야 한다.",
        ),
        Step(
            n="7", state=_S.RIDING.name, leg="direction = +1", bucket="deliver_up",
            what="공용 카 탑승. 로봇이 타면 그 카의 사람 정원이 줄고, 같은 카에 "
                 "로봇은 <strong>1대만</strong> 탄다.",
            duration=Fixed(g.riding_sec,
                           f"{g.ride_sec:g} s 주행 + {g.door_sec:g} s 도어"),
            why="엘리베이터의 승객 프로토콜(<code>on_board</code>/<code>on_alight</code>)을 "
                "그대로 쓴다 — 수직 이동 코드는 <strong>한 줄도 새로 쓰지 않았다</strong>. "
                "만차로 못 타면 <code>robot_board_denied</code>에 계상.",
        ),
        Step(
            n="8", state=_S.MOVING.name, leg=_L.TO_OFFICE.value, bucket="deliver_up",
            what=f"{g.floor}F 승강장 → 사무실 문. EV는 복도 {g.ev_corridor_pos_m:g} m 지점, "
                 f"사무실은 {[int(x) for x in g.office_positions_m]} m.",
            duration=Fixed(g.to_office_sec, f"평균 {g.ev_to_office_mean_m:g} m"),
            why=f"사무실별로 {g.ev_to_office_min_m:g}~{g.ev_to_office_max_m:g} m라 "
                "<strong>층 안에서도 편차가 크다</strong>. 층수만이 아니라 사무실 "
                "위치가 배달시간에 들어간다.",
        ),
        Step(
            n="9", state=_S.DROP.name, bucket="drop", tag="결정 5",
            what="문 앞 인도. <strong><code>delivered_at_sec</code>이 찍히는 곳</strong> — "
                 "주문이 완료되는 시점은 사무실 도착이 아니라 인도 종료다.",
            duration=Fixed(g.drop_sec, "service_time_drop_sec"),
            why="<strong>저SOC 판단을 여기서만 한다.</strong> 그래서 로봇이 음식을 든 채 "
                "충전하러 이탈하는 일이 원천적으로 없다.",
        ),
        Step(
            n="10", state=_S.MOVING.name, leg=_L.TO_EV_DOWN.value, bucket="return",
            what="사무실 → 승강장. 하행 카도 <strong>걷기 전에</strong> 고른다(⑤와 동일).",
            duration=Fixed(g.to_ev_down_sec, "상행과 대칭"),
            why="빈 채로 돌아온다. 이 구간이 <code>return</code> 버킷의 시작이고, "
                "단건 배송(R0-4)이라 묶음 배달로 상쇄되지 않는 순수 오버헤드다.",
        ),
        Step(
            n="11", state=_S.WAIT_EV.name, leg="direction = −1", bucket="return",
            what="하행 대기. 상행과 같은 상태이고 <code>direction</code>만 뒤집힌다.",
            duration=Variable("0 가능"),
            why="상태를 늘리는 대신 <strong>직교 속성</strong>으로 나눈 지점. 덕분에 "
                "상태는 배타적으로 남고 보고 단계에서 상·하행을 분리할 수 있다.",
        ),
        Step(
            n="12", state=_S.RIDING.name, leg="direction = −1", bucket="return",
            what="1F로 하강. 빈 로봇이지만 정원 잠식은 상행과 동일하다.",
            duration=Fixed(g.riding_sec, "주행 + 도어"),
            why="복귀 편도 자체가 EV 부하다 — “로봇이 사람의 EV를 얼마나 먹는가”의 "
                "절반이 여기서 나온다.",
        ),
        Step(
            n="13", state=_S.MOVING.name, leg=_L.TO_HOME.value, bucket="return",
            what="1F 승강장 → 로봇존. 도착과 동시에 주문을 비우고 "
                 "<code>trips_completed</code>를 올린다.",
            duration=Fixed(g.to_home_sec, f"{g.ev_to_home_m:g} m"),
            why=f"복귀 경로가 상행보다 {g.counter_to_ev_m - g.ev_to_home_m:g} m 짧다 — "
                "카운터를 경유하지 않기 때문. <code>return_reason</code>이 여기서 "
                "분기를 결정한다.",
        ),
        Step(
            n="→1", state=_S.IDLE.name, bucket="wait", in_ribbon=False,
            what="<code>return_reason == \"idle\"</code>이면 곧바로 재배차 가능 상태로 "
                 "복귀. 사이클이 닫힌다.",
            duration=NoTime(),
            why="코퍼스에서 <strong>사실상 항상 이쪽</strong>이다(종료 SOC 43~90%).",
        ),
        Step(
            n="→X", state=_S.CHARGING_BLOCKED.name, bucket="charge", tag="결정 #26",
            in_ribbon=False,
            what=f"<code>return_reason == \"low_soc\"</code>(⑨에서 SOC &lt; "
                 f"{g.soc_low_pct:g}%)이면 <strong>배차를 거부하며</strong> 충전. "
                 f"{g.soc_resume_pct:g}%에 닿으면 <code>IDLE</code>로.",
            duration=Fixed(g.resume_charge_min * 60.0,
                           f"{g.soc_low_pct:g}% → {g.soc_resume_pct:g}%"),
            why="<code>IDLE</code>과의 차이는 <strong>충전 여부가 아니라 배차 "
                "가능성</strong>이다. 둘 다 충전한다. 이 구분이 없으면 "
                "“40%까지 채우고 재투입”을 표현할 수 없다.",
        ),
    )


def _diagram(g: geometry.RobotCycleGeometry) -> Diagram:
    # 도면 좌표는 기하학적 축척이 아니라 다이어그램 좌표다(거리는 치수선으로
    # 밝힌다). 층·샤프트·레인 구조만 실제와 일치시킨다.
    up_y, ret_y = 418.0, 402.0          # 1F: 상행 레인 / 복귀 레인
    top_up_y, top_ret_y = 142.0, 126.0  # 대표 층
    sh_x, sh_w = 430.0, 80.0
    home_x, counter_x, land_x = 110.0, 250.0, 409.0
    office_x = 804.0

    return Diagram(
        width=940, height=545,
        alt=f"건물 단면도. 1층 로비의 로봇 도크에서 인계 카운터, 공용 엘리베이터를 "
            f"거쳐 {g.floor}층 사무실로 올라갔다가 되돌아오는 경로",
        caption="실선 = 상행·배달, 파선 = 복귀. 로봇은 "
                "<code>shared_ev_ids</code>의 카만 탈 수 있고 지하(B1·B2)에는 절대 "
                "들어가지 않는다 — 두 금지 모두 FSM·<code>can_board</code>·"
                "<code>_audit_invariants</code>·게이트 B3의 4중 방어다.",
        levels=(
            Level(f"{g.floor}F · 사무실 층", top_up_y, 150.0,
                  ((60, sh_x), (sh_x + sh_w, 880))),
            Level("1F · 로비", up_y, 430.0, ((60, sh_x), (sh_x + sh_w, 880))),
        ),
        shafts=(
            Shaft(
                x=sh_x, width=sh_w, y_top=96, y_bottom=448,
                label=f"{' · '.join(g.shared_ev_ids)} (공용 카)",
                inner_label=f"{g.rise_m:g} m · {g.ride_sec:g} s · 도어 {g.door_sec:g} s",
            ),
        ),
        fixtures=(
            Fixture(home_x, 424, 44, "charge", "로봇존 = 도크", 480),
            Fixture(counter_x, 424, 44, "handoff", "인계 카운터", 480),
            Fixture(land_x, 424, 26, "deliver_up", "승강장", 480),
            Fixture(office_x, 144, 44, "drop", "사무실 문", 132),
        ),
        dims=(
            DimLabel(180, 500, f"{g.home_to_counter_m:g} m"),
            DimLabel(330, 500, f"{g.counter_to_ev_m:g} m"),
            DimLabel(250, 382, f"{g.ev_to_home_m:g} m · 복귀"),
            DimLabel(655, 176,
                     f"평균 {g.ev_to_office_mean_m:g} m "
                     f"(범위 {g.ev_to_office_min_m:g}–{g.ev_to_office_max_m:g} m)"),
        ),
        paths=(
            Path(((home_x, up_y), (285, up_y)), "meet_rider"),
            Path(((285, up_y), (land_x, up_y), (452, up_y),
                  (452, top_up_y), (830, top_up_y)), "deliver_up", arrow=True),
            Path(((office_x, top_ret_y), (528, top_ret_y), (488, top_ret_y),
                  (488, ret_y), (home_x, ret_y)), "return", dashed=True, arrow=True),
        ),
        markers=(
            Marker("1", home_x, up_y), Marker("2", 175, up_y),
            Marker("3", 238, up_y), Marker("4", 272, up_y),
            Marker("5", 350, up_y), Marker("6", land_x, up_y),
            Marker("7", 452, 300),
            Marker("8", 620, top_up_y), Marker("9", office_x, top_up_y),
            Marker("10", 660, top_ret_y), Marker("11", 528, top_ret_y),
            Marker("12", 488, 300), Marker("13", 240, ret_y),
        ),
    )


def _notes(g: geometry.RobotCycleGeometry) -> tuple[Note, ...]:
    return (
        Note(
            "전력 수지",
            f"1 사이클 = {g.cycle_wh:.2f} Wh, 배터리의 {g.cycle_soc_pct:.2f}%",
            f"주행 {g.walk_total_m:g} m × {g.wh_per_m:g} = "
            f"<strong>{g.walk_wh:.2f} Wh</strong>, 비주행 {g.stationary_sec:.1f} s × "
            f"{g.wh_per_min_idle:g} Wh/min = <strong>{g.idle_wh:.2f} Wh</strong>. "
            "코드는 둘을 더하지 않고 <em>택일</em>한다 — 걸은 틱은 거리로, 나머지 "
            "틱(탑승·인계·인도 포함)은 시간으로 과금한다. 대기가 길어질수록 시간 항이 "
            "커져서, 실제 코퍼스에서는 9~10 Wh로 관측된다.",
        ),
        Note(
            "임계값", "충전 분기는 발화하지 않는다 — 그게 결과다",
            f"{g.capacity_wh:g} Wh에 사이클당 ~{g.cycle_wh:.0f} Wh면 점심 피크 한 run이 "
            "SOC 43~90%로 끝난다. 결함이 아니라 <strong>“1.3 kWh급 로봇에게 충전은 "
            "점심 피크 운영의 제약이 아니다”</strong>라는 발견이다. 분기를 실제로 태우는 "
            "경로는 합성 단위 테스트와 Phase E <code>soc_init</code> 스윕뿐이다.",
        ),
        Note(
            "각주 필요",
            f"실효 충전은 명판보다 {100 * (g.resume_charge_min / g.nameplate_charge_min - 1):.0f}% 느리다",
            f"명판 {g.charge_wh_per_min:g} Wh/min이지만 도킹 중에도 대기 소모 "
            f"{g.wh_per_min_idle:g} Wh/min이 흘러 <strong>순 "
            f"{g.net_charge_wh_per_min:g} Wh/min</strong>. "
            f"{g.soc_low_pct:g}→{g.soc_resume_pct:g}%가 명판 "
            f"{g.nameplate_charge_min:.0f}분이 아니라 "
            f"<strong>{g.resume_charge_min:.1f}분</strong>이다. "
            "B10 정보행 + 논문 각주 대상.",
        ),
        Note(
            "구조", f"왜 9상태가 아니라 {len(RobotState)}상태인가",
            "원안의 “고객에게 이동”은 EV 대기와 탑승을 <strong>포함</strong>한다 — "
            "분할(partition)이 아니라서 체류시간이 중복 계상되고 B4·B5 기구학 항등식이 "
            "닫히지 않는다. 게다가 인계와 라이더 대기에 해당하는 상태가 아예 없었다. "
            "실행 FSM은 세분화된 채 두고, 합치는 일은 보고 계층"
            f"(<code>REPORT_BUCKETS</code> {len(REPORT_BUCKETS)}버킷)에만 맡긴다.",
        ),
        Note(
            "종료 조건", "“전원 IDLE”이 아니다",
            "H1 완료 = 전 주문 배달 ∧ 라이더 전원 퇴장 ∧ 로봇 전원 로봇존에 "
            "<strong>(IDLE ∨ CHARGING_BLOCKED)</strong>. 뒤쪽을 빼면 마지막 배달 직후 "
            "SOC가 낮은 로봇 하나 때문에 run이 영원히 끝나지 않는다. 구현 자리"
            "(<code>model._carriers_settled()</code>)는 아직 비어 있다 — Step A2 몫.",
        ),
        Note(
            "확인 필요", "A4 기하 상수에 1 m가 빠져 있다",
            "<code>etc/HANDOFF_phase_a.md</code> §A4는 EV→사무실을 “복도 "
            "[4,6,9,11,14,16] + 지선 3.0”으로 적어 평균 <strong>13.0 m</strong>가 "
            "되지만, 실제 그래프에는 EV 노드 → 복도 노드 <strong>스텁 1.0 m</strong>가 "
            f"더 있어 실측 평균은 <strong>{g.ev_to_office_mean_m:g} m</strong>다"
            f"(구간 {g.ev_to_office_min_m:g}~{g.ev_to_office_max_m:g} m). "
            "A4 수기 체인이 이 상수를 직접 쓰므로, 문서 쪽을 고쳐야 한다.",
            flag=True,
        ),
    )


def build() -> CycleSpec:
    _check_buckets()
    g = geometry.robot_geometry()
    steps = _steps(g)
    det = sum(s.duration.ribbon_sec for s in steps if s.in_ribbon)
    # 기하의 `cycle_sec`은 라이더 차트와 나란히 놓기 위해 geometry에도 있다.
    # 두 정의가 갈리면 두 차트의 비교가 조용히 틀어지므로 여기서 묶어둔다.
    if abs(det - g.cycle_sec) > 1e-6:
        raise ValueError(
            f"리본 합계 {det:.3f} s와 geometry.cycle_sec {g.cycle_sec:.3f} s가 "
            "어긋난다 — 한쪽만 고쳤다는 뜻이다."
        )

    return CycleSpec(
        slug="robot_h1",
        title="로봇 1 사이클 — 도크 대기에서 도크 대기까지",
        eyebrow="abm_new · Phase A · Step A1 구현 기준",
        provenance=Provenance(
            "구현 기준", "simulation/agents/robot.py · Step A1"
        ),
        standfirst=(
            "<code>simulation/agents/robot.py</code>가 정의하는 "
            f"{len(RobotState)}상태 FSM을 한 번의 배달로 펼친 것. 시간·거리 상수는 "
            "<code>configs/baseline_10f.yaml</code>과 건물 그래프에서 실측했고, "
            f"대표 케이스는 <strong>{g.floor}F 주문 · 공용 카({g.ev_id}) · "
            "사무실 평균 거리</strong>다."
        ),
        metrics=(
            Metric("결정적 소요", f"{det:.1f}", " s"),
            Metric("주행 거리", f"{g.walk_total_m:g}", " m"),
            Metric("소모 전력", f"{g.cycle_wh:.2f}", " Wh"),
            Metric("SOC 변화", f"−{g.cycle_soc_pct:.2f}", " %"),
            Metric("상태 전이", f"{sum(1 for s in steps if s.in_ribbon)}", " 회"),
        ),
        ribbon_lede=(
            "큐잉 3구간(<code>WAIT_RIDER</code> · <code>WAIT_EV</code> ×2)을 0으로 "
            "두었을 때의 <strong>하한</strong>이다. 이 셋이 부하에 따라 늘어나는 유일한 "
            "구간이고, 포화(ρ&gt;1)에서 발산하는 것도 이들이다."
        ),
        ribbon_axis_note="배차 → 인계 → 상행 → 인도 → 복귀",
        steps=steps,
        palette=PALETTE,
        diagram=_diagram(g),
        notes=_notes(g),
        covers_states=tuple(s.name for s in RobotState),
        closing=(
            "한 가지 더 — 이 사이클은 <strong>정의는 완성됐지만 아직 돌지 "
            "않는다</strong>. <code>IDLE</code>에서 밀어내는 FCFS 디스패처"
            "(<code>control_system.step()</code>는 현재 <code>pass</code>)와 "
            "<code>WAIT_RIDER</code>를 풀어주는 핸드오프 라이더가 Step A2 몫이기 "
            "때문이다. ①③⑥⑪ 네 칸이 A2 이후에 채워진다."
        ),
        section_titles={
            "diagram": "공간 경로",
            "notes": "사이클을 읽을 때 걸리는 것들",
        },
    )
