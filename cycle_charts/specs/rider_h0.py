"""H0 라이더 1 사이클 — 입구에서 입구까지.

대상: `simulation/agents/external_rider.py`의 `ExternalRiderAgent`.
대표 케이스: 5F 주문 · EV 경로 · 사무실 평균 거리 · 큐잉 0.

왜 이 차트가 로봇 차트보다 먼저인가
------------------------------------
`robot_h1`의 대조군이다. 두 FSM을 로봇 규약(direction을 직교 속성으로 분리)으로
정규화하면 정확히 이렇게 떨어진다:

    로봇 = 라이더 + {WAIT_RIDER, HANDOFF, CHARGING_BLOCKED}
    leg  = 로봇에만 TO_COUNTER / 라이더에만 계단 2종

즉 **H1이 H0에 더한 전부가 그 3개 상태**다. 이 차집합이 논문의 기여를 그림 하나로
설명하므로, 여기서 상태 이름을 손으로 적으면 그 주장이 조용히 늙는다.

버킷 대조가 로봇과 다르다
--------------------------
`external_rider.py`에는 `REPORT_BUCKETS` 상당물이 없다 — 12상태 raw다. 그래서
드리프트 방어를 버킷이 아니라 **상태 전수 커버**(`CycleSpec.covers_states`)로 건다.
`state_names(ExternalRiderAgent)`가 12개를 자동으로 긁어오므로, 상태가 하나
추가되면 이 차트가 렌더 시점에 터진다.
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
    Variable,
    state_names,
)
from simulation.agents.external_rider import ExternalRiderAgent

# 색 = 국면. 로봇 팔레트와 **의도적으로 대응**시킨다: approach↔meet_rider(황),
# ascend↔deliver_up(청), service↔drop(농청), descend↔return(회청). 두 차트를
# 나란히 놓았을 때 같은 국면이 같은 색이어야 차집합이 눈에 보인다.
PALETTE = Palette(
    light={
        "approach": "#C98A2E", "ascend": "#1B6B85", "service": "#10495A",
        "descend": "#63798F", "stairs": "#7A5AA6", "exit": "#8C99A5",
    },
    dark={
        "approach": "#E0A94A", "ascend": "#4FA3BE", "service": "#3D8DA5",
        "descend": "#8497AB", "stairs": "#A387CE", "exit": "#93A1AD",
    },
    legend_order=("approach", "ascend", "service", "descend", "stairs", "exit"),
    legend_note="&larr; 로봇 팔레트와 국면이 대응한다",
)

# 상태 이름은 코드에서. 개명이 곧 AttributeError다.
_R = ExternalRiderAgent
STATES = state_names(_R)


def _steps(g: geometry.RiderCycleGeometry) -> tuple[Step, ...]:
    svc = g.service_range
    svc_note = (
        "config 폴백 — 실제는 타입별 "
        + " · ".join(f"{t} {v:g}" for t, v in g.service_by_type)
        if g.service_by_type else "rider_process.service_time_sec"
    )
    return (
        Step(
            n="1", state="WALK_TO_VERT", bucket="approach", tag="함정",
            what=f"입구 도착 즉시 <strong>탈 카를 고르고</strong>({g.ev_id}) 그 "
                 f"승강장으로 걷는다. 선택은 <code>__init__</code>에서 일어난다 — "
                 "걷기 <em>전</em>이다.",
            duration=Fixed(g.to_vert_sec,
                           f"{g.entry_to_ev_m:g} m ÷ {g.speed_mps:g} m/s"),
            why="<strong>로봇이 그대로 베낀 규칙이다.</strong> 도착해서 다시 고르면 "
                "W5d가 재는 designated-dispatch 대가(stale 52.95% · harm ≤28.81 s)의 "
                "비교 기준이 사라진다. 여기가 그 52.95%가 발생하는 지점이다.",
        ),
        Step(
            n="2", state="WAIT_EV_UP", bucket="ascend",
            what="hall call 등록 후 승강장에서 대기. 보행자와 <strong>같은 큐</strong>에 "
                 "선다 — 라이더에게 우선권은 없다.",
            duration=Variable("0 가능"),
            why="로봇의 <code>WAIT_EV(direction=+1)</code>에 대응. 라이더는 "
                "<strong>방향을 상태 이름에 녹였고</strong> 로봇은 직교 속성으로 뺐다. "
                "정규화하면 같은 칸이다.",
        ),
        Step(
            n="3", state="RIDING_UP", bucket="ascend",
            what=f"{g.ev_id} 탑승, 1F → {g.floor}F. 사람 한 명분의 정원을 차지한다 — "
                 "로봇이 네 명분을 먹는 것과 대비된다.",
            duration=Fixed(g.riding_sec,
                           f"{g.ride_sec:g} s 주행 + {g.door_sec:g} s 도어"),
            why="로봇과 <strong>같은 규약</strong>으로 잰다 — 승차 도어 1회 + 주행, "
                "하차 도어는 세지 않는다(<code>_open_doors()</code>가 문을 여는 그 "
                "순간 하차가 처리된다). 규약이 갈리면 두 차트의 초가 비교 불가능해진다.",
        ),
        Step(
            n="4", state="WALK_TO_OFFICE", bucket="ascend",
            what=f"{g.floor}F 승강장 → 사무실 문. EV는 복도 {g.ev_corridor_pos_m:g} m, "
                 f"사무실은 {[int(x) for x in g.office_positions_m]} m 지점.",
            duration=Fixed(g.to_office_sec, f"평균 {g.ev_to_office_mean_m:g} m"),
            why=f"사무실별 {g.ev_to_office_min_m:g}~{g.ev_to_office_max_m:g} m. "
                "로봇의 같은 구간과 <strong>거리는 같고 속도만 다르다</strong>"
                "(1.2 vs 1.0 m/s) — 로봇 열세의 순수한 원천이 여기다.",
        ),
        Step(
            n="5", state="SERVICE", bucket="service", tag="결정 5",
            what="문 앞 인도. <strong><code>delivered_at_sec</code>이 찍히는 곳</strong>. "
                 "H1에서 이 행위를 대신하는 것이 로봇의 <code>DROP</code>이다.",
            duration=Fixed(g.service_sec, svc_note),
            why="사이클 최대 단일 구간이고 "
                f"<strong>전체의 {100 * g.service_sec / g.cycle_sec:.0f}%</strong>다. "
                + (f"타입별로 {svc[0]:g}~{svc[1]:g} s라 CAR 라이더는 더 오래 머문다. "
                   if svc else "")
                + "H1은 이 구간을 라이더에게서 떼어 로봇에게 옮긴다 — "
                "인계(60 s) + 로봇 DROP(30 s)로 갈린다.",
        ),
        Step(
            n="6", state="WALK_BACK", bucket="descend", tag="함정",
            what="사무실 → 승강장. <strong>여기서 카를 다시 고른다</strong> — "
                 "<code>choose_elevator(f, 1)</code>. 사이클에서 EV 선택은 딱 두 번, "
                 "①과 여기다.",
            duration=Fixed(g.back_sec, f"평균 {g.office_to_ev_mean_m:g} m"),
            why="상행 카와 <strong>다른 카가 나올 수 있다</strong>. 로봇의 "
                "<code>TO_EV_DOWN</code>이 이 규칙을 그대로 물려받되 후보만 "
                f"<code>{list(g.shared_ev_ids)}</code>로 좁힌다.",
        ),
        Step(
            n="7", state="WAIT_EV_DOWN", bucket="descend",
            what="하행 대기. 상행과 같은 구조이고 방향만 뒤집힌다.",
            duration=Variable("0 가능"),
            why="이 구간이 <code>ev_wait_down_sec</code>으로 기록되어 "
                "<strong>보행자 EV 대기와 같은 자원 경합 지표</strong>에 들어간다. "
                "측정 창 3층의 ①층(모드 불변 창)이 재는 대상이다.",
        ),
        Step(
            n="8", state="RIDING_DOWN", bucket="descend",
            what=f"{g.floor}F → 1F 하강. 빈손이지만 정원 잠식은 상행과 같다.",
            duration=Fixed(g.riding_sec, "주행 + 도어"),
            why="<strong>복귀 편도 자체가 EV 부하다.</strong> H1에서 이 부하는 "
                "사라지지 않고 <em>로봇에게 이전</em>된다 — 그것도 사람 정원을 "
                "15 → 11로 줄이면서.",
        ),
        Step(
            n="9", state="WALK_TO_EXIT", bucket="descend",
            what="1F 승강장 → 입구. 도착과 동시에 기록이 확정된다.",
            duration=Fixed(g.to_exit_sec, f"{g.ev_to_entry_m:g} m"),
            why="<code>_finalize()</code>가 <code>rider_records</code>에 "
                "행을 쓰고 <code>remove()</code>한다. 이 시점이 "
                "<code>T_lobby</code>의 끝이다.",
        ),
        Step(
            n="10", state="EXITED", bucket="exit", in_ribbon=False,
            what="퇴장. 에이전트가 스케줄러에서 제거되고 "
                 "<code>on_rider_exit()</code>가 동적 풀에 라이더를 돌려준다.",
            duration=NoTime(),
            why="<strong>H1에서 이 시점이 크게 앞당겨진다</strong> — 배달은 아직 "
                "끝나지 않았는데 라이더가 먼저 나간다. 그래서 A2가 "
                "<code>ord_id</code> 조인을 필요로 한다(함정 2).",
        ),
        Step(
            n="S1", state="CLIMB_STAIRS", bucket="stairs", in_ribbon=False,
            what=f"①에서 수단이 계단이면 이쪽. {g.floor}F까지 "
                 f"{g.stair_sec_per_floor:g} s/층. 계단은 <strong>그래프 밖 "
                 f"타이머</strong>라 복도 중점 {g.stair_corr_pos} m로 순간이동한다.",
            duration=Fixed(g.stair_sec, f"({g.floor}−1) × {g.stair_sec_per_floor:g} s"),
            why=f"이항 로짓이 {g.floor}F에서 "
                f"<strong>P(EV) = {100 * g.p_elevator:.1f}%</strong>를 준다 — "
                "사실상 발화하지 않는 분기다. 저층에서만 의미가 있다. "
                "<strong>로봇에게는 이 분기가 아예 없다</strong>(계단 불가).",
        ),
        Step(
            n="S2", state="DESCEND_STAIRS", bucket="stairs", in_ribbon=False,
            what="하강도 같은 수단으로. <code>descend_same_mode: true</code>라 "
                 "상행이 계단이면 하행도 계단이다.",
            duration=Fixed(g.stair_sec, "상행과 대칭"),
            why=f"계단 전 경로 총합 {g.stair_cycle_sec:.0f} s vs EV 경로 "
                f"{g.cycle_sec:.0f} s. 차이가 로짓의 입력이고, "
                "<strong>EV 대기가 0인 이 하한에서는 계단이 더 느리다</strong> — "
                "혼잡할수록 그 열세가 줄어든다.",
        ),
    )


def _diagram(g: geometry.RiderCycleGeometry) -> Diagram:
    # 로봇 도면과 같은 좌표계를 쓴다 — 두 그림을 위아래로 놓고 볼 것이기 때문.
    up_y, ret_y = 418.0, 402.0
    top_up_y, top_ret_y = 142.0, 126.0
    sh_x, sh_w = 430.0, 80.0
    st_x, st_w = 250.0, 46.0            # 계단 샤프트
    entry_x, land_x = 110.0, 409.0
    office_x = 804.0

    return Diagram(
        width=940, height=545,
        alt=f"건물 단면도. 1층 입구에서 엘리베이터를 타고 {g.floor}층 사무실로 "
            f"올라가 배달한 뒤 같은 경로로 되돌아 나오는 라이더의 왕복 경로. "
            f"왼쪽에 거의 쓰이지 않는 계단 분기가 함께 표시돼 있다",
        caption="실선 = 상행·배달, 파선 = 하행·퇴장. 라이더는 "
                "<strong>4대 전부</strong>를 탈 수 있다 — 로봇이 "
                "<code>shared_ev_ids</code> 2대로 묶이는 것과 대비된다. "
                "계단 샤프트가 흐린 것은 그래프 밖 타이머라 실제 경로가 없기 "
                "때문이고, 동시에 이 층에서 선택될 확률이 "
                f"{100 * (1 - g.p_elevator):.1f}%뿐이기 때문이다.",
        levels=(
            Level(f"{g.floor}F · 사무실 층", top_up_y, 150.0,
                  ((60, st_x - st_w / 2), (st_x + st_w / 2, sh_x),
                   (sh_x + sh_w, 880))),
            Level("1F · 로비", up_y, 430.0,
                  ((60, st_x - st_w / 2), (st_x + st_w / 2, sh_x),
                   (sh_x + sh_w, 880))),
        ),
        shafts=(
            Shaft(x=sh_x, width=sh_w, y_top=96, y_bottom=448,
                  label=f"{' · '.join(g.all_ev_ids)} (라이더는 전부 가능)",
                  inner_label=f"{g.rise_m:g} m · {g.ride_sec:g} s · "
                              f"도어 {g.door_sec:g} s"),
            # 계단은 두 층의 **보행선**(142 / 418)을 모두 덮어야 한다. 슬래브
            # (150 / 430)까지만 그리면 라이더가 슬래브 위에서 사라진다.
            Shaft(x=st_x - st_w / 2, width=st_w, y_top=110, y_bottom=430,
                  label="계단", inner_label=f"{g.stair_sec:g} s"),
        ),
        fixtures=(
            Fixture(entry_x, 424, 44, "approach", "건물 입구", 480),
            Fixture(land_x, 424, 26, "ascend", "승강장", 480),
            Fixture(office_x, 144, 44, "service", "사무실 문", 132),
        ),
        dims=(
            DimLabel(340, 500, f"{g.entry_to_ev_m:g} m"),
            DimLabel(250, 500, f"계단 {g.entry_to_stair_m:g} m"),
            DimLabel(250, 382, f"{g.ev_to_entry_m:g} m · 퇴장"),
            DimLabel(655, 176,
                     f"평균 {g.ev_to_office_mean_m:g} m "
                     f"(범위 {g.ev_to_office_min_m:g}–{g.ev_to_office_max_m:g} m)"),
        ),
        paths=(
            Path(((entry_x, up_y), (land_x, up_y), (452, up_y),
                  (452, top_up_y), (830, top_up_y)), "ascend", arrow=True),
            Path(((office_x, top_ret_y), (488, top_ret_y),
                  (488, ret_y), (entry_x, ret_y)), "descend",
                 dashed=True, arrow=True),
            Path(((st_x, up_y), (st_x, top_up_y)), "stairs", dashed=True),
        ),
        markers=(
            Marker("1", 180, up_y), Marker("2", land_x, up_y),
            Marker("3", 452, 300),
            Marker("4", 620, top_up_y), Marker("5", office_x, top_up_y),
            Marker("6", 660, top_ret_y), Marker("7", 528, top_ret_y),
            Marker("8", 488, 300), Marker("9", 300, ret_y),
            Marker("S1", st_x, 240),
        ),
    )


def _notes(g: geometry.RiderCycleGeometry) -> tuple[Note, ...]:
    svc = g.service_range
    return (
        Note(
            "구조", f"정규화하면 로봇 8상태에서 3개가 빠진 것이 이 {len(STATES)}상태다",
            "라이더는 방향을 <strong>상태 이름에 녹였고</strong>"
            "(<code>WAIT_EV_UP</code> / <code>WAIT_EV_DOWN</code>), 로봇은 "
            "<strong>직교 속성으로 뺐다</strong>(<code>WAIT_EV(±1)</code>). 로봇 "
            "규약으로 정규화하면 라이더는 <code>MOVING · WAIT_EV · RIDING · DROP · "
            "IDLE</code> 5상태가 되고, 로봇은 거기에 <code>WAIT_RIDER · HANDOFF · "
            "CHARGING_BLOCKED</code> 셋을 더한 것과 정확히 같아진다. "
            "<strong>그 셋이 H1이 H0에 더한 전부다.</strong>",
        ),
        Note(
            "비교 가능성", "라이더와 로봇의 차이는 속도 1.2 : 1.0뿐이다",
            f"수평 구간의 <em>거리</em>는 같다 — {g.floor}F 승강장→사무실은 양쪽 다 "
            f"평균 {g.ev_to_office_mean_m:g} m다. 로봇이 느린 이유는 경로가 아니라 "
            "<strong>속도(사람의 0.833배)</strong>와 "
            "<strong>카운터 왕복이라는 추가 leg</strong> 둘뿐이다. "
            "차트의 초를 나란히 놓을 수 있는 것은 riding 규약(승차 도어 1회 + 주행)을 "
            "양쪽이 공유하기 때문이다.",
        ),
        Note(
            "창", "이 사이클이 곧 T_lobby의 하한이다",
            f"큐잉 0에서 <strong>{g.cycle_sec:.1f} s</strong>. 실측 "
            "<code>T_lobby</code>가 이보다 큰 만큼이 EV 대기(②⑦)이고, 그것이 "
            "보행자와의 경합에서 온다. H1의 <code>T_lobby_rider</code>는 이 값과 "
            "<strong>직접 비교하면 안 된다</strong> — ρ&gt;1에서 발산하기 때문이고, "
            "그래서 A3가 <code>T_building_order</code>를 따로 만든다.",
        ),
        Note(
            "데이터 출처",
            "서비스 시간만 config가 아니라 시나리오에서 온다"
            if g.service_by_type else "서비스 시간은 config 폴백을 썼다",
            (f"리본은 config 폴백 <strong>{g.service_fallback_sec:g} s</strong>를 "
             f"쓰지만 실행 시에는 <code>RIDERS</code> 표의 타입별 값이 이긴다: "
             + " · ".join(f"<code>{t}</code> {v:g} s" for t, v in g.service_by_type)
             + f". 최대 {svc[1]:g} s면 사이클이 "
               f"{g.cycle_sec + svc[1] - g.service_sec:.0f} s로 늘어난다 — "
               "타입 구성이 <code>T_lobby</code>에 직접 들어간다는 뜻이다."
             if g.service_by_type else
             f"시나리오 파일을 찾지 못해 <code>rider_process.service_time_sec</code> "
             f"= {g.service_fallback_sec:g} s만 표시한다. 실행 시에는 "
             "<code>RIDERS</code> 표의 타입별 값이 이긴다."),
        ),
        Note(
            "분기", f"계단은 {g.floor}F에서 {100 * (1 - g.p_elevator):.1f}%다",
            f"이항 로짓(β = 0.15/s)이 EV {g.cycle_sec:.0f} s 대 계단 "
            f"{g.stair_cycle_sec:.0f} s를 비교한다. 고층일수록 계단이 급격히 불리해져 "
            "<strong>사실상 저층 전용 분기</strong>가 된다. 상태 2개"
            "(<code>CLIMB_STAIRS</code>·<code>DESCEND_STAIRS</code>)를 차지하지만 "
            "코퍼스에서는 거의 관측되지 않는다 — 로봇의 충전 분기와 같은 성격이다.",
        ),
        Note(
            "A2 예고", "이 차트의 ④~⑨가 통째로 사라진다", flag=True,
            body="H1에서 라이더는 <strong>1F를 벗어나지 않는다.</strong> "
                 "<code>WALK_TO_VERT</code>부터 <code>WALK_TO_EXIT</code>까지 "
                 "8개 상태가 <code>WALK_TO_COUNTER · WAIT_ROBOT · HANDOFF</code> "
                 "3개로 접히고, 떨어져 나간 일은 로봇이 받는다. "
                 "<code>handoff_rider_h1</code> 차트가 그 접힌 결과다.",
        ),
    )


def build() -> CycleSpec:
    g = geometry.rider_geometry()
    steps = _steps(g)
    det = sum(s.duration.ribbon_sec for s in steps if s.in_ribbon)

    return CycleSpec(
        slug="rider_h0",
        title="H0 라이더 1 사이클 — 입구에서 입구까지",
        eyebrow="abm_new · H0 정본 · robot_h1의 대조군",
        provenance=Provenance(
            "구현 기준", "simulation/agents/external_rider.py · H0 v2.1 동결"
        ),
        standfirst=(
            f"<code>external_rider.py</code>가 정의하는 {len(STATES)}상태 FSM을 한 "
            "번의 배달로 펼친 것. 로봇 차트와 <strong>같은 대표 케이스</strong>"
            f"({g.floor}F 주문 · 사무실 평균 거리 · 큐잉 0)를 쓰고 시간·거리는 "
            "<code>configs/baseline_10f.yaml</code>과 건물 그래프에서 실측했다. "
            "두 차트의 차집합이 곧 H1의 기여다."
        ),
        metrics=(
            Metric("체류 하한", f"{det:.1f}", " s"),
            Metric("보행 거리", f"{g.walk_total_m:g}", " m"),
            Metric("EV 편도",
                   f'{sum(1 for s in steps if s.state.startswith("RIDING"))}', " 회"),
            Metric("서비스 비중", f"{100 * g.service_sec / det:.0f}", " %"),
            Metric("상태", f"{len(STATES)}", " 개"),
        ),
        ribbon_lede=(
            "큐잉 2구간(<code>WAIT_EV_UP</code> · <code>WAIT_EV_DOWN</code>)을 0으로 "
            "둔 <strong>하한</strong>이다. 로봇이 큐잉 3구간인 것과 대비된다 — "
            f"늘어난 하나가 <code>WAIT_RIDER</code>다. 리본의 절반 이상"
            f"({100 * g.service_sec / g.cycle_sec:.0f}%)을 ⑤ 서비스가 차지하는 것이 "
            "이 사이클의 형태를 결정한다."
        ),
        ribbon_axis_note="진입 → 상행 → 인도 → 하행 → 퇴장",
        steps=steps,
        palette=PALETTE,
        diagram=_diagram(g),
        notes=_notes(g),
        covers_states=STATES,
        closing=(
            "요약하면 <strong>이 사이클은 배달 자체가 아니라 배달을 위한 수직 "
            "왕복이 지배한다</strong> — 인도(⑤)를 빼면 "
            f"{g.cycle_sec - g.service_sec:.0f} s가 오르내리는 데 쓰인다. "
            "H1의 논지는 바로 그 부분을 사람에게서 떼어낼 수 있다는 것이고, "
            "떼어낸 뒤에 남는 것이 <code>handoff_rider_h1</code>이다."
        ),
        section_titles={
            "diagram": "공간 경로",
            "notes": "사이클을 읽을 때 걸리는 것들",
        },
    )
