"""V-EXT-HR — HR-mode extreme battery (Phase A Step A6,
etc/scie_phase/phase_A_robot_h1.md §2 "Step A6": "극한 — 로봇 1대 포화·보행자
x10"). Mirrors tests/test_vv_extreme.py's convention for H0: an extreme input
must not crash or deadlock and must produce interpretable output — completion,
`delivered == K`, and every B-gate (analysis.verify_hr) PASS. Neither case is
required to *avoid* saturation; the point is that saturation is measurable
and gate-clean, not that it disappears (HANDOFF_phase_a.md §3.6).

Both cases run under `audit=True` (tick-level conservation asserts), the same
choice test_vv_extreme.py makes for its own saturation cases: heavy
contention is exactly where a double-registered passenger or a dropped
conservation invariant is most likely to surface.
"""

from __future__ import annotations

from analysis.verify_hr import verify_result
from simulation.run import run_baseline
from simulation.space import load_config

CONFIG = "configs/baseline_10f.yaml"


def test_extreme_single_robot_fleet_saturates_gracefully():
    """n_robots=1 on K100_1 (baseline is 5): the courier's wait for a free
    robot balloons under FCFS serialization by a single carrier, but the run
    still completes under the PRODUCTION cap (`max_overrun_sec_robot` =
    32,400 s -- no local override; measured 20,943 ticks, well inside it),
    delivers every order, and passes every B-gate.

    Measured (seed 42): robot_wait mean 7,753.0 s / p95 14,119.0 s, vs the
    5-robot baseline's queue p95 of a few hundred seconds at this K tier
    (HANDOFF_phase_a.md §4 4-tier table). The floor below is set with a large
    margin under the measured mean so the assertion is about "this is
    clearly the single-carrier-bottleneck regime", not a fitted value.
    """
    res = run_baseline(scenario_path="data/data1/K100_1.json", floor_profile="uniform",
                        mode="hr", rng_seed=42, n_robots=1, audit=True)
    k = res["kpi_summary"]

    assert k["simulation"]["terminated_by_cap"] is False
    assert k["customer"]["n_delivered"] == 100
    assert k["rider"]["robot_wait_mean_sec"] > 3000.0, (
        "a single-robot fleet at K100 should be deep in the queueing regime "
        f"(measured 7,753.0 s); got {k['rider']['robot_wait_mean_sec']}"
    )
    assert k["robot"]["n_robots"] == 1

    report = verify_result(res)
    assert report["all_passed"], [c.name for c in report["checks"] if not c.passed]


def test_extreme_pedestrian_rush_x10_completes():
    """Background pedestrian rate x10 the lunch-peak baseline (7.5 -> 75/min)
    on K50_1: the heaviest background contention this battery drives the two
    shared cars (EV3/EV4) through. The run still completes under the
    PRODUCTION cap (measured 25,407 ticks, inside the 32,400 s
    `max_overrun_sec_robot` default -- no local override needed), delivers
    every order, and passes every B-gate.

    Directional check: extreme background contention drives the robot's own
    boarding-denial count up hard relative to the corpus baseline (K50
    baseline = 17, HANDOFF_phase_a.md §3.8; measured at x10 = 737). The floor
    below keeps a wide margin under that measurement.
    """
    cfg = load_config(CONFIG)
    cfg["pedestrian"]["arrival_rate_per_min"] = 75.0  # 10x the 7.5/min baseline
    res = run_baseline(config=cfg, scenario_path="data/data1/K50_1.json",
                        floor_profile="uniform", mode="hr", rng_seed=42, audit=True)
    k = res["kpi_summary"]

    assert k["simulation"]["terminated_by_cap"] is False
    assert k["customer"]["n_delivered"] == 50
    assert k["robot"]["n_board_denied"] > 200, (
        "x10 pedestrian rate should drive robot boarding denials well above "
        f"the K50 baseline of 17 (measured 737); got {k['robot']['n_board_denied']}"
    )

    report = verify_result(res)
    assert report["all_passed"], [c.name for c in report["checks"] if not c.passed]
