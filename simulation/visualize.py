"""Live SolaraViz building cross-section for the H0 baseline (plan Part F).

Mesa 3.5's built-in space drawers assume a grid/continuous space, but the H0
world is a networkx building graph, so the cross-section is a **custom
matplotlib Solara component**: a side elevation of the building (x = corridor
position in metres, y = floor *rank*, so the people-only basements B1/B2 sit
below the 1F line at rank 0/-1 — plan §1.6) with one shaft per
declared EV, an off-graph stair column, office ticks, riders/pedestrians
colored by state, and each elevator car drawn as a rectangle at its
interpolated `position_floor` with its passenger count. Geometry is read from
the config/graph, so a different corridor length or EV count needs no edit here.

`draw_cross_section(model, ax)` is the pure-matplotlib renderer (no Solara
dependency, so it is unit-testable headless). `CrossSection` wraps it in a
Solara component that re-renders on every model tick via `update_counter`.
"""

from __future__ import annotations

from typing import Any

import matplotlib.pyplot as plt
import solara
from matplotlib.figure import Figure
from mesa.visualization.utils import update_counter

from simulation.agents.pedestrian import PedestrianAgent
from simulation.kpi import summarize, summary_to_csv, summary_to_markdown
from simulation.space import floor_label, floor_rank

# rider/pedestrian state → color (states grouped by activity)
_STATE_COLORS: dict[str, str] = {
    # walking legs
    "walk_to_vert": "#1f77b4",
    "walk_to_office": "#1f77b4",
    "walk_back": "#1f77b4",
    "walk_to_exit": "#1f77b4",
    "walk_to_ev": "#1f77b4",
    "walk_off": "#1f77b4",
    # waiting for an elevator
    "wait_ev_up": "#ff7f0e",
    "wait_ev_down": "#ff7f0e",
    "wait_ev": "#ff7f0e",
    # riding an elevator
    "riding_up": "#2ca02c",
    "riding_down": "#2ca02c",
    "riding": "#2ca02c",
    # stairs (off-graph timer)
    "climb_stairs": "#9467bd",
    "descend_stairs": "#9467bd",
    # delivering
    "service": "#d62728",
}
_STATE_LEGEND = [
    ("walking", "#1f77b4"),
    ("waiting EV", "#ff7f0e"),
    ("riding EV", "#2ca02c"),
    ("on stairs", "#9467bd"),
    ("service", "#d62728"),
]
_DEADLINE_SOON_SEC = 300.0  # pending order turns red this close to deadline
# A3 / checklist_visual_h1 §0 R1~R3: robots must be distinguishable from people
# at a glance, so they get a SHAPE of their own (diamond) as well as a color —
# color alone fails the print/greyscale reading of the figure and fails a
# color-blind reviewer. A DIAMOND, not a square: the office markers are already
# small grey squares, so a square robot would be a new meaning for an old shape.
# The per-bucket colors deliberately reuse the human
# palette's semantics (orange = waiting for a car, green = riding) so one legend
# reads for both populations.
_ROBOT_BUCKET_COLORS: dict[str, str] = {
    "wait": "#7f7f7f",         # idle in the robot zone
    "meet_rider": "#17becf",   # walking to / waiting at the counter
    "handoff": "#e377c2",      # loading at the counter
    "deliver_up": "#2ca02c",   # to EV / waiting / riding / to office
    "drop": "#d62728",         # handing over at the office door
    "return": "#8c564b",       # back down to the robot zone
    "charge": "#bcbd22",       # CHARGING_BLOCKED — not dispatchable
}
_EV_STATE_COLORS = {"idle": "0.55", "moving": "#4c72b0", "doors": "#2ca02c"}
# v2 EV separation (plan_h0_revision.md §1.5-2). The cross-section's y axis is
# the floor number and a shaft spans every floor, so north/south cannot be
# separated vertically the way offices are (±0.3 floors) — a shaft has no single
# y. The banks are therefore split along x instead: each shaft is nudged toward
# its side of the corridor centre line, which keeps all four columns disjoint
# (north EV1/EV3 at 15.55/17.55, south EV2/EV4 at 16.45/18.45 for the default
# 16/18 placement) while preserving "which side is which" as a left/right read.
# The side is also spelled out in the shaft label and in the hall-queue badge
# placement below.
_EV_SIDE_DX = {"north": -0.45, "south": +0.45}
_EV_SIDE_MARK = {"north": "N", "south": "S"}
# 1F robot zone doubles as the charging dock (plan §1.3) — flagged on the graph
# node as charging=True and drawn with this marker for layout parity with the
# robot phases (H0 has no robots, so nothing occupies it yet).
_CHARGING_MARK = "⚡"
# per-EV series colors for the live queue/util plots (cycled if >4 EVs)
_EV_SERIES_COLORS = ["tab:orange", "tab:red", "tab:blue", "tab:green"]


def _stair_x(corridor_len: float) -> float:
    """Off-graph stair column x: just inside the corridor's right edge."""
    return corridor_len - 1.0


def _building_geom(model) -> dict[str, Any]:  # noqa: ANN001
    b = model.config["building"]
    ev_x = {
        ev.ev_id: pos + _EV_SIDE_DX[side]
        for ev, pos, side in zip(
            model.elevators, b["ev_corridor_positions_m"], b["ev_sides"],
            strict=True,
        )
    }
    return {
        "n_floors": b["n_floors"],
        "n_basements": b.get("n_basements", 0),
        "corridor_len": b["corridor_length_m"],
        "ev_x": ev_x,
        "ev_positions": b["ev_corridor_positions_m"],
        "ev_sides": b["ev_sides"],
        "office_positions": b["office_positions_m"],
        "office_sides": b["office_sides"],
    }


def node_xy(model, node: str) -> tuple[float, float] | None:  # noqa: ANN001
    """Map a graph node to (x_m, floor_y) for the cross-section, or None.

    floor_y is the floor RANK, not the label, so basements plot continuously
    below 1F (labels skip 0 — plan §1.6). Above ground the two coincide.
    Offices are offset ±0.3 floors off the corridor line (north above, south
    below); locker compartments and unknown nodes return None (not drawn).
    """
    g = model.graph
    if node not in g:
        return None
    attrs = g.nodes[node]
    kind = attrs.get("type")
    floor = attrs.get("floor")
    if kind == "corridor":
        return (float(attrs["position_m"]), float(floor_rank(floor)))
    if kind == "office":
        dy = 0.30 if attrs.get("side") == "north" else -0.30
        return (float(attrs["corridor_position_m"]), float(floor_rank(floor)) + dy)
    if kind == "elevator":
        return (float(attrs["corridor_position_m"]), float(floor_rank(floor)))
    if kind == "floor_center":
        return (float(model.config["building"]["corridor_length_m"]) / 2.0,
                float(floor_rank(floor)))
    if kind == "lobby_zone":
        # floor-1 lobby: entrance far left, then the robot zone, then the direct
        # corridor closest to the EV bank at the corridor centre
        corridor_len = float(model.config["building"]["corridor_length_m"])
        lobby_x = {
            "lobby_entry": 1.0,
            "lobby_robot_pickup_zone": corridor_len / 2.0 - 5.0,
            # A3 / R4: the H1 handoff counter. Placed between the robot zone and
            # the corridor because that is the order the walk actually happens
            # in (courier: entry → counter; robot: zone → counter → EV bank), so
            # the two approaches read as converging on one point — which is the
            # thing §2ⓐ has to be able to judge. H0 never occupies this node, so
            # adding it leaves the H0 screen identical (§0 R7 constraint).
            "lobby_handoff_counter": corridor_len / 2.0 - 3.5,
            "lobby_direct_corridor": corridor_len / 2.0 - 2.0,
        }
        return (lobby_x.get(node, corridor_len / 2.0), 1.0)
    return None


def _rider_xy(model, rider) -> tuple[float, float] | None:  # noqa: ANN001
    """Rider position, interpolating stair climbs along the stair column."""
    state = rider.state
    if state in ("climb_stairs", "descend_stairs"):
        f = rider.order.floor
        total = max((f - 1) * model.stair_sec_per_floor, 1e-9)
        done = 1.0 - max(getattr(rider, "_timer", 0.0), 0.0) / total
        done = min(max(done, 0.0), 1.0)
        y = 1.0 + (f - 1) * (done if state == "climb_stairs" else 1.0 - done)
        return (_stair_x(model.config["building"]["corridor_length_m"]), y)
    return node_xy(model, rider.node)


def draw_cross_section(model, ax) -> None:  # noqa: ANN001
    """Render the building side elevation with all live agents onto `ax`."""
    geom = _building_geom(model)
    n_floors = geom["n_floors"]
    n_basements = geom["n_basements"]
    corridor_len = geom["corridor_len"]
    # Vertical axis runs in floor rank: B{n}..B1 occupy ranks 1-n..0, 1F..NF
    # keep their label value (plan §1.6). Everything drawn below uses rank.
    bottom_rank = 1 - n_basements

    # --- static scaffold ---------------------------------------------------
    for r in range(bottom_rank, n_floors + 1):
        ax.axhline(r, color="0.85", lw=0.8, zorder=0)
    # basement rows carry no offices/corridor (plan §1.6) -- mark the band so
    # an empty region below 1F reads as "parking levels", not as a drawing bug
    if n_basements:
        ax.axhspan(bottom_rank - 0.4, 0.4, color="#f5f5f5", zorder=0)
        ax.text(0.0, 0.5 * (bottom_rank + 0.0), "people-only\nbasement",
                ha="left", va="center", fontsize=6, color="0.55", zorder=0)
    # office ticks on floors 2..N (both corridor sides)
    for f in range(2, n_floors + 1):
        for pos, side in zip(geom["office_positions"], geom["office_sides"],
                             strict=True):
            dy = 0.15 if side == "north" else -0.15
            ax.plot([pos], [f + dy], marker="s", ms=2.5, color="0.75", zorder=0)
    # EV shafts — four columns, labelled with the side they serve. The shafts
    # sit ~1 m apart, so the labels are staggered onto two rows; at the app's
    # 9x5 figure size four labels on one row would run together.
    for i, (ev, side) in enumerate(
        zip(model.elevators, geom["ev_sides"], strict=True)
    ):
        x = geom["ev_x"][ev.ev_id]
        ax.axvspan(x - 0.35, x + 0.35, ymin=0, ymax=1, color="0.92", zorder=0)
        ax.text(x, n_floors + (0.75 if i % 2 else 0.35),
                f"{ev.ev_id}·{_EV_SIDE_MARK[side]}",
                ha="center", va="bottom", fontsize=6.5, color="0.4")
    # stair column
    stair_x = _stair_x(corridor_len)
    ax.axvspan(stair_x - 0.4, stair_x + 0.4, color="#f0e8f7", zorder=0)
    ax.text(stair_x, n_floors + 0.55, "stairs", ha="center", va="bottom",
            fontsize=7, color="#9467bd")
    # 1F robot zone = waiting + charging dock (v2, plan §1.3). Read off the
    # graph's charging flag rather than hardcoding the node, so the marker
    # tracks the layout if the dock is ever moved.
    robot_zone = "lobby_robot_pickup_zone"
    if model.graph.nodes.get(robot_zone, {}).get("charging"):
        xy = node_xy(model, robot_zone)
        if xy is not None:
            ax.text(xy[0], xy[1] - 0.40, f"{_CHARGING_MARK} robot", ha="center",
                    va="center", fontsize=7, color="#2ca02c", zorder=1)
    # A3 / R4: the handoff counter itself, drawn only when the graph has one, so
    # a layout without lobby zones renders exactly as before.
    counter_xy = node_xy(model, "lobby_handoff_counter")
    if counter_xy is not None:
        ax.plot([counter_xy[0]], [counter_xy[1] + 0.22], marker="v", ms=6,
                color="#e377c2", zorder=1)
        ax.text(counter_xy[0], counter_xy[1] - 0.40, "counter", ha="center",
                va="center", fontsize=7, color="#e377c2", zorder=1)

    # --- pending (placed, undelivered) orders at their offices --------------
    clock = model.clock_sec
    for c in model.customer_by_ord_id.values():
        if c.delivered_at_sec is not None or c.ord_time_sec > clock:
            continue
        xy = node_xy(model, f"floor_{c.floor}_office_{c.office_id}")
        if xy is None:
            continue
        urgent = (c.dlv_deadline_sec - clock) < _DEADLINE_SOON_SEC
        ax.plot([xy[0]], [xy[1]], marker="o", ms=8, mfc="none",
                mec="#d62728" if urgent else "#ff7f0e",
                mew=1.4 if urgent else 1.0, zorder=1.5)

    # --- elevator cars (color = state, arrow = committed direction) ---------
    for ev in model.elevators:
        x = geom["ev_x"][ev.ev_id]
        y = ev.position_floor
        ax.add_patch(plt.Rectangle((x - 0.32, y - 0.32), 0.64, 0.64,
                                   facecolor=_EV_STATE_COLORS.get(ev.state, "#4c72b0"),
                                   edgecolor="black", lw=0.8, alpha=0.85, zorder=3))
        ax.text(x, y, str(ev.passenger_count), ha="center", va="center",
                fontsize=6, color="white", fontweight="bold", zorder=4)
        if ev.direction != 0:
            arrow = "▲" if ev.direction > 0 else "▼"
            ax.text(x, y + (0.55 if ev.direction > 0 else -0.55), arrow,
                    ha="center", va="center", fontsize=6, color="black", zorder=4)

    # --- per-floor hall-queue badges (waiting count next to each shaft) -----
    # Badges sit on the *outward* side of their shaft (north banks to the left,
    # south to the right) so adjacent shafts' badges never collide; with four
    # shafts the old "innermost only" rule would stack two badges in one gap.
    for ev, side in zip(model.elevators, geom["ev_sides"], strict=True):
        x = geom["ev_x"][ev.ev_id]
        left = side == "north"
        for f, q in ev.hall_calls.items():
            if not q:
                continue
            bx = x - 0.55 if left else x + 0.55
            ax.text(bx, floor_rank(f), str(len(q)), ha="right" if left else "left",
                    va="center", fontsize=6, color="#ff7f0e",
                    fontweight="bold", zorder=4)

    # --- pedestrians (background, small gray dots) -------------------------
    for p in model.agents_of(PedestrianAgent):
        xy = node_xy(model, p.node)
        if xy is not None:
            ax.plot([xy[0]], [xy[1]], marker="o", ms=3, color="0.6",
                    alpha=0.5, zorder=2)

    # --- riders (colored by state) -----------------------------------------
    for r in model.agents_of(model.rider_cls):
        xy = _rider_xy(model, r)
        if xy is None:
            continue
        color = _STATE_COLORS.get(r.state, "black")
        ax.plot([xy[0]], [xy[1]], marker="o", ms=6, color=color,
                markeredgecolor="black", markeredgewidth=0.5, zorder=5)

    # --- robots (A3 / R1~R3: square marker, bucket color, state+SOC label) ---
    # `model.robots` is empty in H0, so this whole block is skipped there and the
    # H0 figure is byte-identical to the one signed in checklist_visual_h0v2.
    for rb in model.robots:
        xy = node_xy(model, rb.node)
        if xy is None:
            continue
        bucket = rb.report_bucket
        ax.plot([xy[0]], [xy[1]], marker="D", ms=6,
                color=_ROBOT_BUCKET_COLORS.get(bucket, "black"),
                markeredgecolor="black", markeredgewidth=0.6, zorder=6)
        # The label carries the reporting bucket and the SOC together because
        # the two questions the checklist asks of a robot (§3 FSM, §4 battery)
        # are asked of the same marker at the same moment. Robots stack on one
        # node when idle, so the text is nudged by index to stay readable.
        dy = 0.16 + 0.13 * (rb.unique_id % 3)
        ax.text(xy[0] + 0.15, xy[1] + dy, f"{bucket} {rb.soc_pct:.0f}%",
                ha="left", va="center", fontsize=5.5, color="#333333", zorder=6)

    # --- frame -------------------------------------------------------------
    ax.set_xlim(-1, corridor_len + 1)
    ax.set_ylim(bottom_rank - 0.7, n_floors + 1.2)
    ax.set_xlabel("corridor position (m)")
    ax.set_ylabel("floor")
    ranks = list(range(bottom_rank, n_floors + 1))
    ax.set_yticks(ranks)
    # tick labels go back to floor labels: rank 0 reads "B1", -1 reads "B2"
    ax.set_yticklabels([floor_label(r if r >= 1 else r - 1) for r in ranks])
    hh, rem = divmod(int(clock), 3600)
    mm, ss = divmod(rem, 60)
    n_riders = len(model.agents_of(model.rider_cls))
    delivered = sum(1 for c in model.customer_by_ord_id.values()
                    if c.delivered_at_sec is not None)
    n_sla = sum(1 for c in model.customer_by_ord_id.values() if c.sla_violation)
    ax.set_title(
        f"t={hh:02d}:{mm:02d}:{ss:02d}  |  riders: {n_riders}  |  "
        f"delivered: {delivered}/{model.K}  |  backlog: {model.backlog()}  |  "
        f"SLA viol: {n_sla}",
        fontsize=9,
    )
    # state legend
    handles = [plt.Line2D([], [], marker="o", ls="", color=c, label=lbl,
                          markeredgecolor="black", markeredgewidth=0.5)
               for lbl, c in _STATE_LEGEND]
    # A3: one legend entry per OCCUPIED robot bucket rather than all seven —
    # a fixed seven-entry block would take a third of the plot width to say
    # "no robot is doing this right now".
    for bucket in dict.fromkeys(rb.report_bucket for rb in model.robots):
        handles.append(plt.Line2D(
            [], [], marker="D", ls="", color=_ROBOT_BUCKET_COLORS.get(bucket, "black"),
            label=f"◆ {bucket}", markeredgecolor="black", markeredgewidth=0.6))
    ax.legend(handles=handles, loc="upper left", fontsize=6, ncol=5,
              framealpha=0.9, handletextpad=0.2, columnspacing=0.8)


@solara.component
def CrossSection(model):  # noqa: ANN001
    """Solara component: live building cross-section, re-rendered each tick."""
    update_counter.get()
    fig = Figure(figsize=(9, 5))
    ax = fig.subplots()
    draw_cross_section(model, ax)
    fig.tight_layout()
    solara.FigureMatplotlib(fig, format="png", bbox_inches="tight")


# ------------------------------------------------------------ live KPI panel


def _kpi_panel_markdown(model) -> str:  # noqa: ANN001
    """Compact live KPI table (system + per-agent), rebuilt every tick from
    kpi.summarize — which only reads cumulative logs, so mid-run calls are
    exact running statistics, not approximations."""
    s = summarize(model)
    cu, ri, pe, bu = s["customer"], s["rider"], s["pedestrian"], s["building"]

    def f(v, fmt="{:.1f}"):  # noqa: ANN001
        return fmt.format(v) if v is not None else "—"

    rows = [
        ("delivered / K", f"{cu['n_delivered']} / {cu['n_orders']}"),
        ("backlog (발주·미인도)", str(model.backlog())),
        ("SLA 위반", f"{cu['n_sla_violations']}건"
                    f" ({f(cu['sla_violation_rate'], '{:.1%}')})"),
        ("T_e2e mean / p95 [s]", f"{f(cu['t_e2e_mean_sec'])} / {f(cu['t_e2e_p95_sec'])}"),
        ("T_lobby mean / p95 [s] (n=%d)" % ri["n_exited"],
         f"{f(ri['t_lobby_mean_sec'])} / {f(ri['t_lobby_p95_sec'])}"),
        ("라이더 EV대기 상/하행 [s]",
         f"{f(ri['ev_wait_up_mean_sec'])} / {f(ri['ev_wait_down_mean_sec'])}"),
        ("수단 EV / 계단", f"{ri['n_by_mode']['elevator']} / {ri['n_by_mode']['stairs']}"),
    ]
    # A3 / R5: robot queue + fleet state. `robot_requests` is the FCFS line of
    # couriers waiting for a robot to be assigned — the saturation signal the
    # checklist §4ⓕ asks the observer to watch grow at K200. Present only in the
    # robot modes, so the H0 panel keeps exactly the rows it had.
    ro = s.get("robot")
    if ro:
        queued = len(model.control.robot_requests)
        busy = sum(1 for rb in model.robots if not rb.is_available)
        rows += [
            ("로봇 배차대기 주문 수", f"{queued}건"),
            ("로봇 가동/전체", f"{busy} / {ro['n_robots']}"),
            ("로봇 완료 트립", str(ro["trips_completed"])),
            ("로봇 대기(라이더) mean/p95 [s]",
             f"{f(ri['robot_wait_mean_sec'])} / {f(ri['robot_wait_p95_sec'])}"),
            ("SOC 최저/현재평균 [%]",
             f"{f(ro['soc_min_pct'])} / {f(ro['soc_end_pct_mean'])}"),
            ("충전 이벤트 / 충전대기 [s]",
             f"{ro['n_charge_events']} / {f(ro['charge_blocked_sec'])}"),
            ("로봇 탑승거부(정원)", f"{ro['n_board_denied']}건"),
            ("T_building_order mean/p95 [s]",
             f"{f(cu['t_building_order_mean_sec'])} / "
             f"{f(cu['t_building_order_p95_sec'])}"),
        ]
    # R8 §4-1: 주 지표는 배달창 가동률. 배달창은 첫 주문~마지막 라이더 퇴장이라
    # 라이더가 아직 아무도 안 나간 초반에는 None이므로 full-window로 되돌린다.
    # 가동률은 "차가 안 서 있던 시간 비율"이지 적재율이 아니라서(R8 §4-2)
    # 평균 재차 인원을 같은 줄에 붙여 오독을 막는다.
    for ev_id, ev in s["elevator"].items():
        util_d = ev.get("utilization_delivery")
        util_txt = (f"{util_d:.1%} (배달창)" if util_d is not None
                    else f"{ev['utilization']:.1%} (전 구간)")
        pax = ev.get("mean_passengers_delivery")
        # A3 / R6: 공용(로봇 동승)인지 전용(사람 전용)인지를 지표 이름에 붙인다 —
        # 양면 외부성은 "어느 카가 어느 그룹인가"를 모르면 읽을 수 없다.
        grp = "공용" if ev["shared_with_robot"] else "전용"
        rows.append((
            f"{ev_id}[{grp}] 가동률·재차·탑승·W_EV",
            f"{util_txt} · {f(pax, '{:.2f}')}명 · {ev['n_boardings']} "
            f"· {f(ev['w_ev_mean_sec'])}s",
        ))
    rows += [
        ("보행자 생성/완료/건물내", f"{pe['n_spawned']} / {pe['n_completed']}"
                                  f" / {pe.get('n_in_building_at_end', '—')}"),
        ("보행자 EV대기", f"{f(pe['ev_wait_mean_sec'])}s"),
        ("opex 누적 [KRW]", f"{bu['opex_running_krw']:,.0f}"),
        ("cost/order 누적 [KRW]", f(bu["cost_per_order_krw"], "{:,.1f}")),
    ]
    hh, rem = divmod(int(model.clock_sec), 3600)
    mm, ss = divmod(rem, 60)
    lines = [
        f"#### 라이브 KPI — t={hh:02d}:{mm:02d}:{ss:02d} (tick {model.tick_count})",
        "", "| 지표 | 값 |", "|---|---|",
    ]
    lines += [f"| {k} | {v} |" for k, v in rows]
    return "\n".join(lines)


@solara.component
def KPIPanel(model):  # noqa: ANN001
    """Live system/per-agent KPI numbers, updated every tick."""
    update_counter.get()
    solara.Markdown(_kpi_panel_markdown(model))


# --------------------------------------------------- floor-demand panel (R8-g)


def _floor_demand_markdown(model) -> str:  # noqa: ANN001
    """Which floors this run's demand actually landed on, next to the profile
    that was asked for.

    Written because the profile selector had no observable effect: the sidebar
    applies a changed value only on **Reset** (mesa re-instantiates the model
    there and nowhere else), and the only demand-dependent thing on screen was
    the handful of pending-order markers in the cross-section — far too sparse
    to tell `uniform` from `bottom_heavy` by eye. This panel names the live
    profile and shows design probability against the realised histogram, so
    "did my choice take effect" is answerable at a glance
    (etc/plan_h0v21_window.md §5.2).
    """
    floors = list(range(2, model.n_floors + 1))
    observed = dict.fromkeys(floors, 0)
    for o in model.orders:
        if o.floor in observed:
            observed[o.floor] += 1
    delivered = dict.fromkeys(floors, 0)
    for c in model.customer_by_ord_id.values():
        if c.delivered_at_sec is not None and c.floor in delivered:
            delivered[c.floor] += 1

    probs = list(model.floor_demand.probs) if model.floor_demand else None
    profile = model.floor_profile or "mapping 파일(프로파일 미사용)"
    k = max(1, len(model.orders))
    lines = [
        f"#### 층 수요 — 프로파일 **{profile}** · 창 정책 **{model.window_policy}**",
        "",
        f"- 층 시드 `floor_seed={model.floor_seed}` · 주문 K={len(model.orders)}",
        "- ⚠️ 사이드바에서 프로파일·시나리오를 바꾸면 **Reset을 눌러야** 반영된다"
        " (모델이 그때 재생성된다).",
        "",
        "| 층 | 설계 확률 | 기대 | 실제 주문 | 배달 완료 |",
        "|---|---|---|---|---|",
    ]
    for i, f in enumerate(floors):
        p = probs[i] if probs else None
        lines.append(
            f"| {f}F | {f'{p:.3f}' if p is not None else '—'} "
            f"| {f'{k * p:.1f}' if p is not None else '—'} "
            f"| {observed[f]} | {delivered[f]} |"
        )
    return "\n".join(lines)


@solara.component
def FloorDemandPanel(model):  # noqa: ANN001
    """Design floor probabilities vs the realised order histogram (R8-g)."""
    update_counter.get()
    solara.Markdown(_floor_demand_markdown(model))


# ------------------------------------------------------------- agent tables


def _rider_table_rows(model) -> list[dict]:  # noqa: ANN001
    """Riders currently in the building, longest-dwelling first."""
    rows = []
    for r in model.agents_of(model.rider_cls):
        rows.append({
            "ord_id": r.order.ord_id,
            "type": r.order.rider_type,
            "floor": r.order.floor,
            "state": r.state,
            "mode": r.mode_used,
            "체류 [s]": round(model.clock_sec - r.entered_at_sec, 1),
            "EV대기↑ [s]": r.ev_wait_up_sec,
            "EV대기↓ [s]": r.ev_wait_down_sec,
            "walked [m]": round(r.walked_m, 1),
        })
    return sorted(rows, key=lambda x: -x["체류 [s]"])


def _elevator_table_rows(model) -> list[dict]:  # noqa: ANN001
    rows = []
    for i, ev in enumerate(model.elevators):
        hall = ", ".join(
            f"{f}F:{len(q)}" for f, q in sorted(ev.hall_calls.items()) if q
        )
        util_cum = ev.busy_ticks / model.tick_count if model.tick_count else 0.0
        rows.append({
            "EV": ev.ev_id,
            # A3 / R6: the group is a property of the car, not of the run, so it
            # belongs in the car's own row — the observer reading §2ⓑ ("robots
            # only ever board EV3/EV4") should not have to consult the config.
            "구분": "공용" if ev.shared_with_robot else "전용",
            "state": ev.state,
            "dir": {1: "▲", -1: "▼", 0: "—"}[ev.direction],
            "floor": round(ev.position_floor, 2),
            "탑승/정원": f"{ev.passenger_count}/{ev.capacity_people}",
            "hall calls": hall or "—",
            "car calls": ", ".join(f"{f}F" for f in sorted(ev.car_calls)) or "—",
            "가동률(누적)": f"{util_cum:.1%}",
            "가동률(60s)": f"{model.ev_util_window_pct(i):.0f}%",
        })
    return rows


@solara.component
def RiderTable(model):  # noqa: ANN001
    """Live table of riders in the building (why is ord X slow? → here)."""
    update_counter.get()
    import pandas as pd

    rows = _rider_table_rows(model)
    solara.Markdown(f"#### 건물 내 라이더 ({len(rows)}명)")
    if rows:
        solara.DataFrame(pd.DataFrame(rows), items_per_page=10)
    else:
        solara.Markdown("*현재 건물 내 라이더 없음*")


@solara.component
def ElevatorTable(model):  # noqa: ANN001
    """Live SCAN state of both elevators (calls, direction, utilization)."""
    update_counter.get()
    import pandas as pd

    solara.Markdown("#### 엘리베이터 상태")
    solara.DataFrame(pd.DataFrame(_elevator_table_rows(model)), items_per_page=5)


# ------------------------------------------------- dynamic rider-pool panels


def _pool_summary_rows(model) -> list[dict]:  # noqa: ANN001
    """Per-type pool inventory (free / out / initial + cumulative stats)."""
    pool = model.rider_pool
    rows = []
    for t, n0 in pool.initial.items():
        rows.append({
            "type": t,
            "가용": pool.free[t],
            "배달중": pool.busy(t),
            "초기": n0,
            "누적 배차": pool.dispatch_count[t],
        })
    return rows


def _fleet_table_rows(model) -> list[dict]:  # noqa: ANN001
    """라이더별 상세 현황: 주문 대기 → 배차·이동중 → 건물내(FSM) → 복귀중.

    One row per in-flight rider (or stock-starved waiting order), so the
    whole fleet lifecycle is visible at a glance during the run.
    """
    now = model.clock_sec
    rows: list[dict] = []
    if model.dynamic_pool:
        for o in model.rider_pool.waiting:  # orders waiting for stock
            rows.append({
                "ord_id": o.ord_id, "type": "—", "단계": "① 라이더 대기(소진)",
                "floor": o.floor, "dist [m]": round(o.dist_m),
                "경과/ETA [s]": round(now - o.ready_time_sec, 1), "비고": "queue",
            })
        for arr, _, o in sorted(model.pending_arrivals):  # en route to lobby
            rows.append({
                "ord_id": o.ord_id, "type": o.rider_type, "단계": "② 배차·이동중",
                "floor": o.floor, "dist [m]": round(o.dist_m),
                "경과/ETA [s]": round(arr - now, 1),
                "비고": "fallback" if o.was_fallback else "",
            })
    for r in model.agents_of(model.rider_cls):  # inside the building
        o = r.order
        note = []
        if getattr(o, "was_fallback", False):
            note.append("fallback")
        if (getattr(o, "rider_wait_sec", None) or 0) > 0:
            note.append(f"wait {o.rider_wait_sec:.0f}s")
        rows.append({
            "ord_id": o.ord_id, "type": o.rider_type,
            "단계": f"③ 건물내:{r.state}", "floor": o.floor,
            "dist [m]": round(getattr(o, "dist_m", float("nan"))) if getattr(
                o, "dist_m", None) is not None else "—",
            "경과/ETA [s]": round(now - r.entered_at_sec, 1),
            "비고": " ".join(note),
        })
    if model.dynamic_pool:
        for rel, t in sorted(model.pending_releases):  # return leg
            rows.append({
                "ord_id": "—", "type": t, "단계": "④ 복귀중",
                "floor": "—", "dist [m]": "—",
                "경과/ETA [s]": round(rel - now, 1), "비고": "return leg",
            })
    return rows


@solara.component
def RiderPoolPanel(model):  # noqa: ANN001
    """Pool inventory summary (dynamic_pool mode).

    Split from the fleet detail table (RiderFleetPanel) into its own grid
    slot: Mesa's SolaraViz grid gives every registered component the same
    fixed cell height (make_initial_grid_layout, h=10 regardless of content),
    so stacking two variable-height tables in one component overflowed the
    cell and visually bled into whatever sat below it in the 2-column grid.
    """
    update_counter.get()
    import pandas as pd

    if not model.dynamic_pool:
        solara.Markdown(
            "#### 라이더 풀\n\n*정적 모드(dynamic_pool=False) — 풀 없음. "
            "사이드바에서 dynamic pool을 켜고 Reset 하세요.*"
        )
        return
    pool = model.rider_pool
    solara.Markdown(
        f"#### 라이더 풀 현황 — 대기열 {len(pool.waiting)}건 · "
        f"fallback 누적 {pool.fallback_count} · 재고대기 누적 {pool.queued_count}"
    )
    solara.DataFrame(pd.DataFrame(_pool_summary_rows(model)), items_per_page=5)


@solara.component
def RiderFleetPanel(model):  # noqa: ANN001
    """Fleet lifecycle detail table (dynamic_pool mode) — own grid slot."""
    update_counter.get()
    import pandas as pd

    if not model.dynamic_pool:
        solara.Markdown(
            "#### 라이더별 상세 현황\n\n*정적 모드 — 배차 이력 없음.*"
        )
        return
    rows = _fleet_table_rows(model)
    solara.Markdown(f"#### 라이더별 상세 현황 ({len(rows)}건 in-flight)")
    if rows:
        # items_per_page kept small so the table's rendered height stays
        # inside the grid's fixed cell (see class docstring above)
        solara.DataFrame(pd.DataFrame(rows), items_per_page=5)
    else:
        solara.Markdown("*현재 배차·이동·건물내·복귀 중인 라이더 없음*")


# ------------------------------------------------------------- KPI download


def build_kpi_report(model) -> tuple[str, str, str]:  # noqa: ANN001
    """(markdown, csv, file_stem) for the end-of-run KPI report download."""
    meta = {
        "scenario": model.scenario_path.name,
        # profile mode has no mapping file (model.mapping_path is None) — label
        # the floor source by the active profile instead of crashing on .name
        "floor_mapping": (
            model.mapping_path.name if model.mapping_path
            else f"profile:{model.floor_profile}"
        ),
        "mode": model.mode.value,
        "rng_seed": model.rng_seed,
        "K": model.K,
        "ticks": model.tick_count,
        "clock_end_sec": model.clock_sec,
        "terminated_by_cap": model.terminated_by_cap,
    }
    if getattr(model, "floor_profile", None) is not None:
        meta["floor_profile"] = model.floor_profile
        meta["floor_seed"] = getattr(model, "floor_seed", None)
    summary = summarize(model)
    stem = f"kpi_h0_{model.scenario_path.stem}_seed{model.rng_seed}"
    return (
        summary_to_markdown(summary, meta),
        summary_to_csv(summary, meta),
        stem,
    )


@solara.component
def DownloadPanel(model):  # noqa: ANN001
    """KPI report download (Markdown + CSV), enabled once the run finishes."""
    update_counter.get()
    finished = (not model.running) and model.tick_count > 0
    if not finished:
        solara.Markdown(
            "#### KPI 리포트\n\n*시뮬레이션 완료 후(전 주문 인도·전원 퇴장) "
            "다운로드 버튼이 활성화됩니다.*"
        )
        return
    md, csv_text, stem = build_kpi_report(model)
    with solara.Column():
        solara.Markdown(f"#### KPI 리포트 — 완료 (tick {model.tick_count})")
        solara.FileDownload(md, filename=f"{stem}.md", label=f"{stem}.md 다운로드")
        solara.FileDownload(csv_text, filename=f"{stem}.csv",
                            label=f"{stem}.csv 다운로드")


# --------------------------------------------------------------- page build


def _titled(title: str):
    """post_process factory for make_plot_component: label a plot's axis.

    matplotlib's default font (DejaVu Sans) has no CJK glyphs, so a Korean
    title would render as tofu boxes — pin Noto Sans CJK KR (confirmed present
    in this env) for the title only; axis/legend labels stay ASCII.
    """
    def _post_process(ax):  # noqa: ANN001
        ax.set_title(title, fontsize=10, fontfamily="Noto Sans CJK KR")
    return _post_process


def build_solara_app(model, model_params=None):  # noqa: ANN001
    """Assemble the SolaraViz page (cross-section + KPI panel + live plots +
    agent tables + end-of-run KPI download).

    Imported lazily by simulation/app.py so headless tests can exercise the
    pure renderer without constructing the full Solara viz. `model_params`
    (Slider/Select dicts keyed by model __init__ kwargs) adds the parameter
    sidebar; changed values are applied by SolaraViz on Reset (the model is
    reconstructed as type(model)(**params)).
    """
    from mesa.visualization import SolaraViz, make_plot_component

    # Single page (2026-07-23): all views live on one page — no tab navigation.
    # Tab switching while Play was running competed with the play loop's
    # force_update() render stream and froze the sim (Mesa SolaraViz single-
    # thread render limit); collapsing to one page removes that failure mode
    # entirely. Trade-off: every registered component now re-renders on each
    # render pass (Mesa only renders the active tab, which is now the only
    # tab), so render_interval is raised below to keep stepping responsive.
    #
    # Every plot carries a Korean title via post_process=_titled(...) so the
    # trend is self-describing; tables/panels already print their own
    # Markdown header. Order groups related views: overview → rider pool/fleet
    # → rider trends + table → elevator → delivery/cost + download. All
    # components default to page 0 (plain functions and make_plot_component's
    # own (fn, 0) return are both normalised to page 0 by ComponentsView).
    components = [
        # --- 개요: 건물 단면 + KPI 숫자 + 라이더 풀/플릿 현황 ---
        CrossSection,
        KPIPanel,
        FloorDemandPanel,
        RiderPoolPanel,
        RiderFleetPanel,
        # --- 라이더·인원 동향 ---
        make_plot_component(
            {"free_bike": "tab:blue", "free_walk": "tab:green",
             "free_car": "tab:red", "dispatch_queue_len": "tab:orange"},
            post_process=_titled("라이더 풀 가용 대수(유형별) · 배차 대기열"),
        ),
        make_plot_component(
            {"fallback_cum": "tab:purple", "riders_en_route": "tab:cyan"},
            post_process=_titled("누적 fallback · 로비로 이동 중 라이더 수"),
        ),
        make_plot_component(
            {"riders_in_building": "tab:blue", "peds_active": "tab:gray",
             "peds_waiting": "tab:orange"},
            post_process=_titled("건물 내 라이더 · 보행자(활동/대기) 수"),
        ),
        make_plot_component(
            {"riders_walking": "tab:blue", "riders_waiting_ev": "tab:orange",
             "riders_riding_ev": "tab:green", "riders_on_stairs": "tab:purple",
             "riders_in_service": "tab:red"},
            post_process=_titled(
                "라이더 상태 분해(도보·EV대기·EV탑승·계단·서비스)"),
        ),
        RiderTable,
        # --- 엘리베이터 상태 (시리즈는 선언된 EV 대수만큼 동적 생성) ---
        make_plot_component(
            {
                f"{ev.ev_id.lower()}_queue": _EV_SERIES_COLORS[i % len(_EV_SERIES_COLORS)]
                for i, ev in enumerate(model.elevators)
            },
            post_process=_titled("엘리베이터 홀콜 대기열(EV별)"),
        ),
        make_plot_component(
            {
                f"{ev.ev_id.lower()}_util_window": _EV_SERIES_COLORS[i % len(_EV_SERIES_COLORS)]
                for i, ev in enumerate(model.elevators)
            },
            post_process=_titled("엘리베이터 가동률 60초 윈도우(EV별)"),
        ),
        ElevatorTable,
        # --- 배송 성과·비용 ---
        make_plot_component(
            {"backlog": "tab:red", "delivered": "tab:green",
             "sla_violations": "tab:brown"},
            post_process=_titled("누적 배송 현황(백로그·완료·SLA 위반)"),
        ),
        make_plot_component(
            {"t_e2e_running_mean": "tab:blue",
             "t_lobby_running_mean": "tab:green"},
            post_process=_titled("평균 배송시간 추이(E2E·로비 체류) [초]"),
        ),
        make_plot_component(
            {"opex_running_krw": "tab:brown"},
            post_process=_titled("누적 운영비 OPEX [원]"),
        ),
        DownloadPanel,
    ]
    return SolaraViz(
        model,
        components=components,
        model_params=model_params,
        # use_threads=True looked like the fix for "Too many renders
        # triggered" (it coalesces backlogged force_update() calls via a
        # threading.Event instead of queuing one per tick) — but it makes a
        # SECOND thread call force_update()/get_model_vars_dataframe() while
        # the model.step() thread is concurrently still appending to
        # datacollector.model_vars, and Mesa's DataCollector isn't
        # thread-safe: a read can catch some columns already appended for
        # the new tick and others not yet, so pd.DataFrame(...) raises
        # "All arrays must be of the same length". That is a *worse*
        # failure mode (hit within seconds) than the render backlog it
        # fixed, so use_threads stays False — collect() and every render
        # then happen on the single step-thread, sequentially, and the race
        # is structurally impossible. Instead we avoid the render backlog by
        # giving each render pass (15 live components) generous headroom:
        # rarer force_update() calls (play_interval) each covering more
        # simulated time (render_interval), so a slow render has room to
        # finish before the next one is due. If a user's machine is slower
        # still, the Play/Render Interval sliders in the sidebar are the
        # user-facing release valve (Mesa's own hint: "Increase play
        # interval to avoid skipping plots").
        play_interval=300,
        # raised 5→12: single page renders all ~16 components each pass, so
        # render less often (more steps per render) to keep stepping smooth.
        # The Render Interval / Play Interval sliders in the sidebar remain the
        # user-facing knobs if a machine needs more or less headroom.
        render_interval=12,
        name="H0 Baseline — rider direct delivery (single page)",
    )
