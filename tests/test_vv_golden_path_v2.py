"""V2-GP absolute golden-path verification (etc/plan_h0v2_verification.md §3 L1).

WHY THIS EXISTS ALONGSIDE `test_vv_golden_path.py`. That module derives its
expected walk distances from the graph (`shortest_walk_only_path` on the built
building) and then checks the simulation against them. That catches *timing*
bugs, but it cannot catch a wrong building: if `build_building_graph` placed
office 2 at 13 m instead of 14 m, the derived expectation would move with it
and the test would still pass. This module closes that hole by hard-coding
absolute numbers computed **by hand from the design spec alone** — corridor
34 m, office branch positions [2, 7, 12, 22, 27, 32], office branch 3 m, EV
branch 1 m, lobby zone distances, floor height 4.0 m, walk 1.2 m/s, lift
a = 1.0 m/s², v = 2.5 m/s, door 4.0 s, stairs 16.5 s/floor (plan_h0_revision.md
§1.1–§1.3, §1.6 and configs/baseline_10f.yaml). Nothing below is read off the
graph. Keep both modules: they fail on different defects.

HAND DERIVATIONS (every constant in this file traces to one of these).

  Geometry, case A — elevator to 7F, office_2 (north @ 12 m), EV1 (north @ 16 m):
    d1 = lobby_entry → floor_1_center (4 m) → ev_EV1_1 (4 m)            = 8.0 m
         (the alternative route entry → center → direct_corridor (2 m) →
          ev_EV1_1 (2 m) is also 8.0 m, so the value is route-independent)
         d1 is a ground-floor leg and never touches the corridor, so it is
         unaffected by where the office branches sit.
    d2 = ev_EV1_7 → floor_7_corr_16 (1 m) → corr_12 (|16−12| = 4 m)
         → office_2 branch (3 m)                                        = 8.0 m

  Geometry, case B — stairs to 7F, office_2:
    s1 = lobby_entry → floor_1_center (4 m) → lobby_direct_corridor (2 m) = 6.0 m
    s2 = floor_7_corr_17 → corr_12 (|17−12| = 5 m) → branch (3 m)        = 8.0 m
    The stair access point is the corridor MIDPOINT, floor(34/1)/2 = 17.
    v1 used corr_14; that constant is pinned literally below, because a wrong
    midpoint keeps every graph-derived test green while making every stair
    distance wrong.

  2026-08-04 re-derivation (office branches moved, 사용자 확정): office_2 went
  14 m → 12 m, so d2 6.0 → 8.0 m and s2 6.0 → 8.0 m. d1, s1, the corridor
  midpoint and every vertical constant are unchanged — the layout change only
  moves branch points along the corridor. These were recomputed by hand from
  the spec; reading them off the graph would defeat the module.

  Vertical, from kinematics (d_ramp = v²/a = 6.25 m):
    1F→7F : 6 storeys × 4.0 =  24.0 m ≥ d_ramp → 2v/a + (d−d_ramp)/v
                                              = 5.0 + 17.75/2.5 = 12.1  s
    1F→B1 : 1 storey        =   4.0 m <  d_ramp → 2·√(d/a) = 2·2.0 =  4.0  s
    1F→B2 : 2 storeys       =   8.0 m ≥ d_ramp → 5.0 + 1.75/2.5  =  5.7  s
    B2→10F: 11 storeys      =  44.0 m ≥ d_ramp → 5.0 + 37.75/2.5 = 20.1  s
    The basement rows are the §1.6 additions: they are the only place the
    floor-label-vs-rank distinction shows up in a physical quantity. A naive
    |label difference| would read 1F→B1 as 2 storeys (8 m, 5.7 s) and 1F→B2 as
    3 storeys (12 m, 7.3 s) — both are asserted NOT to happen.

  Timing (walk at 1.2 m/s, service 120 s, stairs 16.5 s/floor):
    walk 8.0 m = 6.667 s | walk 6.0 m = 5.000 s | 6 flights = 99.0 s
    (case A uses 8.0 m on both legs; case B uses 6.0 m down in the lobby and
     8.0 m along the corridor)
    case A round trip = w(d1) + door + move + w(d2) + service
                          + w(d2) + door + move + w(d1)   → 9 segments
    case B round trip = w(s1) + climb + w(s2) + service
                          + w(s2) + climb + w(s1)         → 7 segments

TOLERANCE (plan L1 합격 기준): each segment is tick-quantized by the model, so a
hand-computed continuous value may sit up to one tick below the recorded one;
the accumulated t_lobby may therefore lag by up to (number of segments) ticks.
Exact equality is deliberately NOT required here — that is what the sibling
graph-derived module asserts. What this module pins is that the *absolute*
value is right, i.e. that the building matches its own specification.
"""

from __future__ import annotations

import json
import math

import pytest

from simulation.agents.walker import shortest_walk_only_path
from simulation.elevator_physics import ElevatorKinematics
from simulation.model import ROOT, BuildingHandoffModel, HandoffMode
from simulation.space import add_lobby_handoff_zones, build_from_config, load_config
from simulation.vertical_transport import VerticalTransportModel

# ---------------------------------------------------------------- hand constants
# Design-spec values. Do NOT replace any of these with a graph lookup — the
# whole point is that they are an independent statement of what the building
# should be.

WALK_SPEED = 1.2            # m/s   (rider_process.walk_speed_mps)
FLOOR_HEIGHT = 4.0          # m     (building.floor_height_m)
ACCEL = 1.0                 # m/s²  (elevator.accel_mps2)
MAX_SPEED = 2.5             # m/s   (elevator.max_speed_mps)
DOOR = 4.0                  # s     (elevator.door_open_close_sec)
STAIR_PER_FLOOR = 16.5      # s     (vertical.stair_sec_per_floor)
SERVICE = 120.0             # s     (synthetic scenario below)
D_RAMP = 6.25               # m     v²/a — the accel+decel distance

FLOOR = 7                   # target office floor for cases A and B
OFFICE_ID = 2               # office_2 = 3rd north branch = 12 m
OFFICE_POS_M = 12           # design spec office_positions_m[2]
EV1_POS_M = 16              # design spec ev_corridor_positions_m[0], north
CORRIDOR_MID_POS = 17       # floor(34 m / 1 m grid / 2) — the stair access point

D1_LOBBY_TO_EV = 8.0        # lobby_entry → ev_EV1_1
D2_EV_TO_OFFICE = 8.0       # ev_EV1_7 → floor_7_office_2  (1 + |16−12| + 3)
S1_LOBBY_TO_STAIR = 6.0     # lobby_entry → lobby_direct_corridor
S2_STAIR_TO_OFFICE = 8.0    # floor_7_corr_17 → floor_7_office_2  (|17−12| + 3)
D_BASEMENT_CENTER_TO_EV = 4.0   # floor_B{n}_center → ev_EV1_B{n} (non-office floor)

MOVE_1F_TO_7F = 12.1        # s
MOVE_1F_TO_B1 = 4.0         # s
MOVE_1F_TO_B2 = 5.7         # s
MOVE_B2_TO_10F = 20.1       # s

CLIMB_1F_TO_7F = 99.0       # s   = 6 flights × 16.5

# synthetic single-order scenario (mirrors test_vv_golden_path.py's setup)
BIKE_SPEED = 5.291
D0 = 1000.0
COOK = 900.0
ORD_ABS = 41400.0
MARGIN = 60.0
TICK = 1.0


def _hand_move_time(storeys: int) -> float:
    """Kinematic travel time for `storeys` storeys, from the spec constants."""
    d = storeys * FLOOR_HEIGHT
    if d < D_RAMP:
        return 2.0 * math.sqrt(d / ACCEL)
    return 2.0 * MAX_SPEED / ACCEL + (d - D_RAMP) / MAX_SPEED


# ============================================================ layer 1: geometry
# The building must match its own specification. These compare hand constants
# against the built graph; a builder that drifts fails here first, before any
# timing question is asked.


@pytest.fixture(scope="module")
def graph():
    cfg = load_config(ROOT / "configs" / "baseline_10f.yaml")
    return add_lobby_handoff_zones(
        build_from_config(cfg), n_locker_compartments=cfg["locker"]["n_compartments"]
    )


def test_office_and_ev_branch_positions_match_spec(graph) -> None:
    """office_2 sits at 14 m north and EV1 at 16 m north — the two constants
    every case-A distance is built from."""
    office = graph.nodes[f"floor_{FLOOR}_office_{OFFICE_ID}"]
    assert office["corridor_position_m"] == OFFICE_POS_M
    assert office["side"] == "north"
    ev1 = graph.nodes[f"ev_EV1_{FLOOR}"]
    assert ev1["corridor_position_m"] == EV1_POS_M
    assert ev1["side"] == "north"


def test_stair_access_is_the_corridor_midpoint(graph) -> None:
    """Case B's pinned constant: the stair column meets the corridor at 17 m.

    v1 used corr_14. Deriving this from the graph (as the sibling module does)
    would keep passing if the midpoint moved, because both sides would move
    together — so the literal is asserted here.
    """
    assert graph.graph["corridor_mid_pos"] == CORRIDOR_MID_POS
    assert f"floor_{FLOOR}_corr_{CORRIDOR_MID_POS}" in graph


def test_hand_computed_walk_distances_match_the_graph(graph) -> None:
    """All four case A/B legs, as absolute metres."""
    d1 = shortest_walk_only_path(graph, "lobby_entry", "ev_EV1_1")[1]
    d2 = shortest_walk_only_path(
        graph, f"ev_EV1_{FLOOR}", f"floor_{FLOOR}_office_{OFFICE_ID}"
    )[1]
    s1 = shortest_walk_only_path(graph, "lobby_entry", "lobby_direct_corridor")[1]
    s2 = shortest_walk_only_path(
        graph, f"floor_{FLOOR}_corr_{CORRIDOR_MID_POS}",
        f"floor_{FLOOR}_office_{OFFICE_ID}",
    )[1]
    assert d1 == pytest.approx(D1_LOBBY_TO_EV)
    assert d2 == pytest.approx(D2_EV_TO_OFFICE)
    assert s1 == pytest.approx(S1_LOBBY_TO_STAIR)
    assert s2 == pytest.approx(S2_STAIR_TO_OFFICE)


def test_basement_boarding_distance_matches_spec(graph) -> None:
    """§1.6: a basement is a floor_center plus EV stops, 4 m apart — the same
    rule the ground floor already used for a non-office level."""
    for label in ("B1", "B2"):
        d = shortest_walk_only_path(
            graph, f"floor_{label}_center", f"ev_EV1_{label}"
        )[1]
        assert d == pytest.approx(D_BASEMENT_CENTER_TO_EV), label


# =========================================================== layer 2: kinematics
# Absolute seconds from the velocity profile. Pure functions, no simulation.


def test_hand_computed_ride_times_match_kinematics() -> None:
    cfg = load_config(ROOT / "configs" / "baseline_10f.yaml")
    kin = ElevatorKinematics.from_config(cfg)
    assert kin.travel_time_sec(1, FLOOR) == pytest.approx(MOVE_1F_TO_7F)
    assert kin.travel_time_sec(1, -1) == pytest.approx(MOVE_1F_TO_B1)
    assert kin.travel_time_sec(1, -2) == pytest.approx(MOVE_1F_TO_B2)
    assert kin.travel_time_sec(-2, 10) == pytest.approx(MOVE_B2_TO_10F)
    # the hand formula and the implementation agree for every storey count used
    for storeys, pair in ((6, (1, 7)), (1, (1, -1)), (2, (1, -2)), (11, (-2, 10))):
        assert kin.travel_time_sec(*pair) == pytest.approx(_hand_move_time(storeys))


def test_basement_rides_are_not_label_arithmetic() -> None:
    """§1.6 rank convention, stated as a physical claim.

    Labels skip 0, so |label difference| would make 1F→B1 two storeys and
    1F→B2 three. Those wrong values are named explicitly so the test says what
    the bug would look like, not just what the right answer is.
    """
    kin = ElevatorKinematics.from_config(load_config(ROOT / "configs" / "baseline_10f.yaml"))
    wrong_b1 = _hand_move_time(2)   # 8 m  -> 5.7 s
    wrong_b2 = _hand_move_time(3)   # 12 m -> 7.3 s
    assert kin.travel_time_sec(1, -1) != pytest.approx(wrong_b1)
    assert kin.travel_time_sec(1, -2) != pytest.approx(wrong_b2)
    assert kin.floor_height_between(1, -1) == pytest.approx(FLOOR_HEIGHT)
    assert kin.floor_height_between(1, -2) == pytest.approx(2 * FLOOR_HEIGHT)


# ========================================================= layer 3: full journey
# One synthetic order through the real model, compared against the hand chain in
# absolute seconds with the plan's per-segment tick tolerance.


def _scenario() -> dict:
    return {
        "name": "GPV2",
        "K": 1,
        # [type, speed, capa, var_cost, fixed_cost, service_time, available]
        "RIDERS": [["BIKE", BIKE_SPEED, 100, 60, 5000, SERVICE, 1]],
        # [ORD_ID, ORD_TIME, SHOP_LAT, SHOP_LON, DLV_LAT, DLV_LON, COOK, VOL, DEADLINE]
        "ORDERS": [[0, 0.0, 0, 0, 0, 0, COOK, 10, 5400.0]],
        "DIST": [[0.0, D0], [D0, 0.0]],
    }


def _cfg_for(mode: str) -> dict:
    """baseline config, zero pedestrians, all demand pinned to 7F, and a
    mode_seed searched so the single order takes `mode` (the mode RNG stream is
    isolated, so searching it perturbs nothing else)."""
    cfg = load_config(ROOT / "configs" / "baseline_10f.yaml")
    cfg["pedestrian"]["arrival_rate_per_min"] = 0.0
    cfg["pedestrian"]["window_margin_sec"] = MARGIN
    cfg["demand"]["floor_profiles"]["single7"] = [0, 0, 0, 0, 0, 1, 0, 0, 0]
    for seed in range(10_000):
        cfg["vertical"]["mode_seed"] = seed
        if VerticalTransportModel.from_config(cfg).sample_mode(0, FLOOR) == mode:
            return cfg
    raise AssertionError(f"no mode_seed yields {mode} at floor {FLOOR}")


def _run_one(cfg: dict, scenario_path, floor_seed: int) -> dict:
    model = BuildingHandoffModel(
        mode=HandoffMode.H0_DIRECT,
        config=cfg,
        scenario_path=scenario_path,
        dynamic_pool=True,
        scenario_window=True,
        rng_seed=42,
        floor_profile="single7",
        floor_seed=floor_seed,
        audit=True,
    )
    while not model.rider_records and model.tick_count < 20_000:
        model.step()
    assert model.rider_records, "order never completed"
    return model.rider_records[0]


@pytest.fixture(scope="module")
def scenario_path(tmp_path_factory):
    p = tmp_path_factory.mktemp("gpv2") / "GPV2.json"
    p.write_text(json.dumps(_scenario()))
    return p


def _office_seed(cfg: dict) -> int:
    """A floor_seed that lands the single order on OFFICE_ID (needed because the
    hand distances are specific to office_2's 14 m branch)."""
    from simulation.floor_demand import FloorDemandModel

    for seed in range(10_000):
        fd = FloorDemandModel.from_config(cfg, "single7", floor_seed=seed)
        floor, office = fd.sample(0)
        if floor == FLOOR and office == OFFICE_ID:
            return seed
    raise AssertionError(f"no floor_seed puts order 0 on office {OFFICE_ID}")


def test_case_a_elevator_journey_matches_hand_absolute_times(scenario_path) -> None:
    """Case A: every segment within 1 tick of the hand value, t_lobby within 9.

    Hand chain (seconds, continuous):
      walk 8.0 m = 6.667 | door 4.0 | ride 12.1 | walk 8.0 m = 6.667
      | service 120 | walk 8.0 | door 4.0 | ride 12.1 | walk 8.0
    """
    cfg = _cfg_for("elevator")
    rec = _run_one(cfg, scenario_path, _office_seed(cfg))
    assert rec["vertical_mode"] == "elevator"

    up = D1_LOBBY_TO_EV / WALK_SPEED + DOOR + MOVE_1F_TO_7F + D2_EV_TO_OFFICE / WALK_SPEED
    down = D2_EV_TO_OFFICE / WALK_SPEED + DOOR + MOVE_1F_TO_7F + D1_LOBBY_TO_EV / WALK_SPEED
    hand_t_lobby = up + SERVICE + down
    n_segments = 9

    assert rec["t_lobby_sec"] >= hand_t_lobby - 1e-9, (
        "recorded round trip is faster than the physical hand floor — "
        f"{rec['t_lobby_sec']} < {hand_t_lobby}"
    )
    assert rec["t_lobby_sec"] <= hand_t_lobby + n_segments * TICK, (
        f"t_lobby {rec['t_lobby_sec']} exceeds hand value {hand_t_lobby} by more "
        f"than {n_segments} ticks of quantization"
    )
    # walked distance is not tick-quantized: it must match exactly
    assert rec["walked_m"] == pytest.approx(
        2.0 * (D1_LOBBY_TO_EV + D2_EV_TO_OFFICE), abs=0.01
    )
    # an idle car at the caller's floor boards in the same tick (V-GP finding)
    assert rec["ev_wait_up_sec"] == 0.0
    assert rec["ev_wait_down_sec"] == 0.0


def test_case_b_stair_journey_matches_hand_absolute_times(scenario_path) -> None:
    """Case B: the stair route via corr_17, in absolute seconds.

    Hand chain: walk 6.0 m = 5.0 | climb 99.0 | walk 8.0 = 6.667 | service 120
    | walk 8.0 | climb 99.0 | walk 6.0   → 7 segments.
    """
    cfg = _cfg_for("stairs")
    rec = _run_one(cfg, scenario_path, _office_seed(cfg))
    assert rec["vertical_mode"] == "stairs"

    leg = S1_LOBBY_TO_STAIR / WALK_SPEED + CLIMB_1F_TO_7F + S2_STAIR_TO_OFFICE / WALK_SPEED
    hand_t_lobby = 2.0 * leg + SERVICE
    n_segments = 7

    assert rec["t_lobby_sec"] >= hand_t_lobby - 1e-9
    assert rec["t_lobby_sec"] <= hand_t_lobby + n_segments * TICK
    assert rec["walked_m"] == pytest.approx(
        2.0 * (S1_LOBBY_TO_STAIR + S2_STAIR_TO_OFFICE), abs=0.01
    )
    # stairs bypass the cars entirely
    assert rec["ev_wait_up_sec"] is None
    assert rec["ev_wait_down_sec"] is None


def test_stair_route_is_longer_than_the_elevator_route_at_7f() -> None:
    """Sanity on the two hand chains: 6 flights (99 s) dominates a 12.1 s ride.

    Not a redundant restatement — it is the qualitative claim the paper makes
    about high floors, derived here from the absolute constants rather than
    from a simulation run.
    """
    ev_vertical = 2.0 * (DOOR + MOVE_1F_TO_7F)
    stair_vertical = 2.0 * CLIMB_1F_TO_7F
    assert stair_vertical > 4.0 * ev_vertical
