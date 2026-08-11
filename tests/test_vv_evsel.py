"""V-EVSEL tests (etc/plan_h0_verification.md §2 L5-3).

Covers the opt-in EV-selection staleness instrumentation:
  * evsel OFF is bit-for-bit identical to the pre-instrumentation path
    (the standard "instrumentation must not perturb results" regression);
  * evsel ON is a well-formed smoke run (events logged, waits backfilled);
  * the stale-determination logic fires correctly on hand-built EV states
    (one positive, one negative case);
  * the conservative additional-wait bound clips no-harm stale flags at 0.
"""

from __future__ import annotations

from types import SimpleNamespace

from analysis.vv_evsel import _harm
from simulation.model import BuildingHandoffModel
from simulation.run import run_baseline

SCENARIO = "data/data1/K50_1.json"


def _fresh_model() -> BuildingHandoffModel:
    """Construct (do not run) a paper-track model with evsel on."""
    return BuildingHandoffModel(
        scenario_path=SCENARIO,
        rng_seed=42,
        dynamic_pool=True,
        scenario_window=True,
        floor_profile="uniform",
        evsel=True,
    )


class _StubPassenger:
    """Hashable (identity) passenger stub — Mesa agents are identity-hashable
    too, so the _evsel_pending dict keys the same way in production."""

    def __init__(self, model: BuildingHandoffModel) -> None:
        self.order = SimpleNamespace(ord_id=999)
        self.kind = "rider"
        self.ev_wait_started_sec = model.clock_sec


def _stub_passenger(model: BuildingHandoffModel):
    return _StubPassenger(model)


def test_evsel_off_is_bit_for_bit_identical():
    """evsel=True must not perturb results vs the default evsel=False path.

    The instrumentation is pure observation (reads EV state, no mutation, no
    RNG draw), so even ON it may not shift a single timestamp.
    """
    common = dict(scenario_path=SCENARIO, rng_seed=42, floor_profile="uniform")
    plain = run_baseline(**common)
    logged = run_baseline(**common, evsel=True)
    assert "evsel_events" not in plain  # additive: absent unless requested
    assert plain["per_order"] == logged["per_order"]
    assert plain["kpi_summary"] == logged["kpi_summary"]


def test_evsel_on_smoke():
    """ON run logs a well-formed event per hall call; boarded calls get waits."""
    res = run_baseline(
        scenario_path=SCENARIO, rng_seed=42, floor_profile="uniform", evsel=True
    )
    events = res["evsel_events"]
    assert events, "expected hall-call events on a K50 run"
    required = {
        "kind", "reg_clock_sec", "from_floor", "chosen_ev", "reeval_best_ev",
        "stale", "est_chosen_sec", "est_reeval_best_sec", "reeval_best_lb_sec",
        "observed_wait_sec",
    }
    for e in events:
        assert required <= e.keys()
        assert isinstance(e["stale"], bool)
        assert e["chosen_ev"] in ("EV1", "EV2", "EV3", "EV4")
    # R8: a wait is backfilled when the passenger BOARDS, so under the
    # `delivery` policy the handful still queued when the run stops stay None
    # (censored). `analysis/vv_evsel.py` drops them before computing harm — if
    # it counted them as zero the harm estimate would be biased low. What must
    # hold is that censoring is a rounding error, not a structural hole.
    censored = [e for e in events if e["observed_wait_sec"] is None]
    policy = res["kpi_summary"]["simulation"].get("termination_policy", "drain_all")
    if policy == "drain_all":
        assert not censored, "drain-all must leave nobody waiting"
    else:
        assert len(censored) / len(events) < 0.02, (
            f"{len(censored)}/{len(events)} hall calls censored — too many to "
            "treat as an end-of-run artefact"
        )
        assert all(e["kind"] == "pedestrian" for e in censored), (
            "a courier was left waiting at an EV when the run ended"
        )
    assert all(
        e["observed_wait_sec"] >= 0
        for e in events if e["observed_wait_sec"] is not None
    )
    # the chosen EV was argmin at selection; a re-eval argmin can only differ
    assert 0 < sum(1 for e in events if e["stale"]) < len(events)


def test_stale_positive_when_argmin_moved():
    """chosen != current argmin -> stale True."""
    model = _fresh_model()
    ev1, ev2 = model.elevators[0], model.elevators[1]
    ev1.position_floor = 10.0   # committed EV is now far away
    ev2.position_floor = 2.0    # the other EV sits on the call floor
    # (EV3/EV4 idle at 1F: one floor from the call -> strictly worse than EV2)
    model._evsel_on_register(ev1, from_floor=2, passenger=_stub_passenger(model))
    event = model.evsel_events[-1]
    assert event["chosen_ev"] == "EV1"
    assert event["reeval_best_ev"] == "EV2"
    assert event["stale"] is True
    assert event["est_reeval_best_sec"] < event["est_chosen_sec"]


def test_stale_negative_when_choice_still_optimal():
    """chosen == current argmin -> stale False."""
    model = _fresh_model()
    ev1, ev2 = model.elevators[0], model.elevators[1]
    ev1.position_floor = 2.0    # committed EV is on the call floor
    ev2.position_floor = 10.0   # the other EV is far away
    # (EV3/EV4 idle at 1F: one floor from the call -> worse than EV1's 0)
    model._evsel_on_register(ev1, from_floor=2, passenger=_stub_passenger(model))
    event = model.evsel_events[-1]
    assert event["chosen_ev"] == "EV1"
    assert event["reeval_best_ev"] == "EV1"
    assert event["stale"] is False


def test_harm_clips_no_harm_stale_calls_to_zero():
    """observed wait below the re-eval-optimal EV's physical floor => 0 harm."""
    no_harm = {"observed_wait_sec": 10.0, "reeval_best_lb_sec": 28.0}
    harmful = {"observed_wait_sec": 40.0, "reeval_best_lb_sec": 12.0}
    assert _harm(no_harm) == 0.0
    assert _harm(harmful) == 28.0
