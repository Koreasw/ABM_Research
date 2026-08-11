"""H0 baseline runner CLI (plan_abm_baseline_h0.md Part D + paper-track wiring).

    python -m simulation.run --scenario data/data1/K100_3.json --seed 7

Runs the BuildingHandoffModel to completion (all orders delivered, everyone
out of the building — capped at ped-window end + max_overrun) and writes a
results JSON consumed by analysis/verify_baseline.py (S6, static runs) and
analysis/plot_baseline.py (S7): per-order records + KPI summary + model
variable time series.

Paper-track defaults (2026-07-10 사용자 확정): dynamic rider pool ON,
scenario ±1 h pedestrian window ON, floor/office from an independent
population-density profile (etc/demand_mapping.md, default `uniform`).
`--static`, `--legacy-window`, `--mapping`, `--mapping-version {v4,v5}`
select the frozen distance-band floor-mapping regression paths.
`--floor-profile`/`--floor-seed` are mutually exclusive with those.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from simulation.kpi import summarize
from simulation.model import ROOT, BuildingHandoffModel, HandoffMode
from simulation.space import load_config


def resolve_mapping(
    scenario_path: str | Path, mapping: str | Path | None, version: str = "v5"
) -> Path:
    """Mapping path: explicit wins; else {stem}_floor_mapping_{version}.json."""
    if mapping is not None:
        p = Path(mapping)
        return p if p.is_absolute() else ROOT / p
    stem = Path(scenario_path).stem
    return ROOT / "data" / "floor_mapping" / f"{stem}_floor_mapping_{version}.json"


def run_baseline(
    config_path: str | Path = "configs/baseline_10f.yaml",
    scenario_path: str | Path = "data/data1/K50_1.json",
    mapping_path: str | Path | None = None,
    rng_seed: int = 42,
    dynamic_pool: bool = True,
    return_leg: bool = False,
    scenario_window: bool = True,
    mapping_version: str | None = None,
    floor_profile: str | None = None,
    floor_seed: int | None = None,
    audit: bool = False,
    evsel: bool = False,
    # A2: 'h0' | 'hr'. `hr` selects H1_SYNC (handoff rider + robot fleet). The
    # CLI spelling stays `hr` because that is what every plan document and the
    # A2/A5 gates call it; the enum name is the internal one.
    mode: str = "h0",
    # A3 (이월 §A0-②-3): an already-built config dict, used INSTEAD of reading
    # `config_path`. Without it a caller that wants to vary one parameter has to
    # drive BuildingHandoffModel directly and reimplement everything this
    # function does after `run_to_completion` — which is what A0's parameter
    # tests had to do, and what Phase D's sizing sweep (robots {5,7,9} × shared
    # EVs {2,3,4}) would have had to do 84 more times. `config_path` is still
    # recorded in the result as the base the dict came from, with
    # `config_injected` marking that it was not read from disk.
    config: dict | None = None,
    # Fleet-size override for that same sweep; None keeps the config's value.
    n_robots: int | None = None,
) -> dict:
    config_path = Path(config_path)
    if not config_path.is_absolute():
        config_path = ROOT / config_path
    config_injected = config is not None
    if config is None:
        config = load_config(config_path)

    # profile mode iff floor_profile given: floors come from the independent
    # population-density draw, no mapping file. Otherwise resolve the frozen
    # distance-band mapping file (v5 default naming).
    profile_mode = floor_profile is not None
    resolved_mapping = (
        None if profile_mode
        else resolve_mapping(scenario_path, mapping_path, mapping_version or "v5")
    )

    handoff_mode = {"h0": HandoffMode.H0_DIRECT, "hr": HandoffMode.H1_SYNC}[mode]

    t0 = time.perf_counter()
    model = BuildingHandoffModel(
        mode=handoff_mode,
        config=config,
        scenario_path=scenario_path,
        mapping_path=resolved_mapping,
        rng_seed=rng_seed,
        dynamic_pool=dynamic_pool,
        return_leg=return_leg,
        scenario_window=scenario_window,
        floor_profile=floor_profile,
        floor_seed=floor_seed,
        audit=audit,
        evsel=evsel,
        n_robots=n_robots,
    )
    model.run_to_completion()
    elapsed = time.perf_counter() - t0

    model_vars = model.datacollector.get_model_vars_dataframe()
    if profile_mode:
        floor_source = "profile"
        floor_probs: list[float] | None = list(model.floor_demand.probs)
        resolved_floor_seed: int | None = model.floor_seed
        mapping_path_out: str | None = None
    else:
        floor_source = "mapping"
        floor_probs = None
        resolved_floor_seed = None
        mapping_path_out = str(model.mapping_path)

    result = {
        "config_path": str(config_path),
        "config_injected": config_injected,
        "scenario_path": str(model.scenario_path),
        "mapping_path": mapping_path_out,
        "floor_source": floor_source,
        "floor_profile": floor_profile,
        "floor_seed": resolved_floor_seed,
        "floor_probs": floor_probs,
        "mode": model.mode.value,
        "rng_seed": rng_seed,
        "dynamic_pool": dynamic_pool,
        "return_leg": return_leg,
        "scenario_window": scenario_window,
        "window": {
            "clock_start_sec": model.clock_start_sec,
            "ped_start_sec": model.ped_start_sec,
            "ped_end_sec": model.ped_end_sec,
            "cap_time_sec": model.cap_time_sec,
        },
        "config": config,
        "per_order": sorted(model.rider_records, key=lambda r: r["ord_id"]),
        "kpi_summary": summarize(model),
        "model_vars": {k: list(v) for k, v in model_vars.items()},
        "runtime_wall_sec": round(elapsed, 2),
    }
    # V-EVSEL: additive, only present when instrumentation was requested
    if evsel:
        result["evsel_events"] = model.evsel_events
    # A5: the robot half of the order timeline plus the fleet's end state, so
    # `analysis/verify_hr.py` can judge a run from its artefact alone — the same
    # contract `verify_h0.py` has with `per_order`. Emitted only when a fleet
    # exists, matching the `robot` KPI block: an H0 artefact carrying an empty
    # `robot_legs` would claim it measured a fleet it never had.
    if model.robots:
        result["robot_legs"] = [
            model.robot_leg_records[k] for k in sorted(model.robot_leg_records)
        ]
        result["robot_fleet"] = [
            {
                "robot_id": rb.unique_id,
                "state": rb.state.value,
                "node": rb.node,
                "soc_pct": rb.soc_pct,
                "soc_min_pct": rb.soc_min_pct,
                "trips_completed": rb.trips_completed,
                "charge_events": rb.charge_events,
                "charge_blocked_sec": rb.charge_blocked_sec,
                "distance_traveled_m": rb.distance_traveled_m,
                "return_reason": rb.return_reason,
            }
            for rb in model.robots
        ]
    return result


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="H0 baseline ABM runner")
    parser.add_argument("--config", default="configs/baseline_10f.yaml")
    parser.add_argument("--scenario", default="data/data1/K50_1.json")
    parser.add_argument("--mapping", default=None,
                        help="floor-mapping JSON (default: derived from "
                             "scenario stem + --mapping-version)")
    parser.add_argument("--mapping-version", default=None, choices=["v4", "v5"],
                        help="frozen distance-band mapping naming convention "
                             "(v5 = per-scenario demand-centroid anchor). "
                             "Passing this selects the mapping regression path; "
                             "omit it for the profile paper track.")
    parser.add_argument("--floor-profile", default=None,
                        choices=["uniform", "bottom_heavy", "top_heavy"],
                        help="population-density floor profile (paper track "
                             "default: uniform). Mutually exclusive with "
                             "--static/--mapping/--mapping-version.")
    parser.add_argument("--floor-seed", type=int, default=None,
                        help="floor-assignment RNG seed (default: --seed). "
                             "Profile mode only; pin for CRN floor contrasts.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--static", action="store_true",
                        help="static replay rider supply (frozen v4 path); "
                             "default is the dynamic rider pool (paper track)")
    parser.add_argument("--return-leg", action="store_true",
                        help="dynamic pool: defer pool return by the drop->shop leg")
    parser.add_argument("--legacy-window", action="store_true",
                        help="fixed lunch-peak horizon window instead of the "
                             "scenario ±margin pedestrian window")
    parser.add_argument("--audit", action="store_true",
                        help="enable tick-level conservation asserts (V-AUD "
                             "audit mode); default off, no effect on results")
    parser.add_argument("--mode", default="h0", choices=["h0", "hr"],
                        help="h0 = rider carries the order the whole way "
                             "(baseline); hr = H1 handoff at the 1F counter to "
                             "a robot fleet (Phase A)")
    parser.add_argument("--out", default=None,
                        help="results JSON path (default: results/"
                             "baseline_h0_{scenario}[_static][_s{seed}].json)")
    args = parser.parse_args(argv)

    # mode judgement: any frozen distance-band flag selects the mapping path;
    # the profile paper track is the default. The two are mutually exclusive.
    mapping_mode = (
        args.static or args.mapping is not None or args.mapping_version is not None
    )
    if mapping_mode and (
        args.floor_profile is not None or args.floor_seed is not None
    ):
        parser.error(
            "--floor-profile/--floor-seed (profile paper track) are mutually "
            "exclusive with --static/--mapping/--mapping-version (frozen "
            "distance-band regression path)"
        )

    if mapping_mode:
        effective_profile: str | None = None
        effective_version: str | None = args.mapping_version or "v5"
        effective_floor_seed: int | None = None
    else:
        effective_profile = args.floor_profile or "uniform"
        effective_version = None
        effective_floor_seed = args.floor_seed

    stem = Path(args.scenario).stem
    # the filename carries the mode so an hr run can never overwrite the H0
    # baseline artefact that the frozen gates and the paper tables read
    prefix = f"baseline_{args.mode}"
    if args.out is None:
        if mapping_mode:
            tag = "" if not args.static else "_static"
            args.out = f"results/{prefix}_{stem}{tag}_s{args.seed}.json"
        else:
            fs_tag = ""
            if args.floor_seed is not None and args.floor_seed != args.seed:
                fs_tag = f"_fs{args.floor_seed}"
            args.out = (f"results/{prefix}_{stem}_{effective_profile}"
                        f"_s{args.seed}{fs_tag}.json")

    result = run_baseline(
        config_path=args.config,
        scenario_path=args.scenario,
        mapping_path=args.mapping,
        rng_seed=args.seed,
        dynamic_pool=not args.static,
        return_leg=args.return_leg,
        scenario_window=not args.legacy_window,
        mapping_version=effective_version,
        floor_profile=effective_profile,
        floor_seed=effective_floor_seed,
        audit=args.audit,
        mode=args.mode,
    )

    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = ROOT / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=1))

    k = result["kpi_summary"]
    supply = "dynamic" if result["dynamic_pool"] else "static"
    # R8: `scenario_window` is a legacy_margin-only switch; the window is now
    # named by the policy that actually produced it, so the banner cannot claim
    # "±1h" for a run whose head is 600 s and whose tail has no cutoff at all.
    policy = k["simulation"].get("window_policy", "legacy_margin")
    if policy == "delivery":
        window = f"delivery(warmup {k['simulation']['warmup_sec']:.0f}s)"
    else:
        window = "legacy_margin/scenario±1h" if result["scenario_window"] else "legacy_margin/fixed"
    floor_desc = (f"floor=profile:{result['floor_profile']}"
                  if result["floor_source"] == "profile"
                  else f"mapping={effective_version}")
    print(f"[run] mode={result['mode']} supply={supply} window={window} "
          f"{floor_desc} "
          f"K={k['customer']['n_orders']} "
          f"delivered={k['customer']['n_delivered']} "
          f"ticks={k['simulation']['ticks']} wall={result['runtime_wall_sec']}s")
    print(f"  T_e2e mean/p95: {k['customer']['t_e2e_mean_sec']:.1f}"
          f"/{k['customer']['t_e2e_p95_sec']:.1f}s  "
          f"SLA violation: {k['customer']['sla_violation_rate']:.1%}")
    # A3 (이월 §A2-⑤-5): in H1 the courier never touches the vertical system, so
    # `n_by_mode` is structurally {0, 0} and printing it invites the reader to
    # conclude something went wrong. The robot modes print what actually varies
    # there — the wait for a free robot — and the H0 banner is unchanged.
    rd = k["rider"]
    if k.get("robot"):
        tail = (f"robot_wait mean/p95: {rd['robot_wait_mean_sec']:.1f}"
                f"/{rd['robot_wait_p95_sec']:.1f}s")
    else:
        tail = f"modes: {rd['n_by_mode']}"
    print(f"  T_lobby mean/p95: {rd['t_lobby_mean_sec']:.1f}"
          f"/{rd['t_lobby_p95_sec']:.1f}s  {tail}")
    # A3: the mode-comparable order KPI (§3.7 layer ②). H0's T_lobby happens to
    # equal it; H1's does not, so it is printed in both modes to stop anyone
    # comparing the two T_lobby lines above across modes.
    cu = k["customer"]
    if cu["t_building_order_mean_sec"] is not None:
        print(f"  T_building_order mean/p95: {cu['t_building_order_mean_sec']:.1f}"
              f"/{cu['t_building_order_p95_sec']:.1f}s")
    # R8 §4-1: the headline utilization is the delivery-window one. The
    # full-window figure is kept alongside as a diagnostic (it carries the
    # warm-up head in its denominator, which is what made it read low) and
    # falls back to it on the legacy path, where no delivery window exists.
    for ev_id, ev in k["elevator"].items():
        w = ev["w_ev_mean_sec"]
        util_d = ev.get("utilization_delivery")
        util_txt = (f"util(delivery)={util_d:.1%} full={ev['utilization']:.1%}"
                    if util_d is not None else f"util(full)={ev['utilization']:.1%}")
        pax = ev.get("mean_passengers_delivery")
        # time-in-use, not load factor — print mean occupancy next to it so the
        # two are never conflated (R8 §4-2).
        pax_txt = f" pax={pax:.2f}" if pax is not None else ""
        print(f"  {ev_id}: {util_txt}{pax_txt} boards={ev['n_boardings']} "
              f"W_EV={'%.1f' % w if w is not None else 'n/a'}s")
    # A3: fleet line + the drain, printed only when a fleet exists. `charge=0`
    # is the expected corpus result, not a missing measurement (§3.5), so the
    # SOC floor is printed next to it to make that readable at a glance.
    rb = k.get("robot")
    if rb:
        print(f"  robots={rb['n_robots']} trips={rb['trips_completed']} "
              f"util(ops)={rb['utilization_ops_mean']:.1%} "
              f"(fixed {rb['utilization_fixed_mean']:.1%}) "
              f"soc_min={rb['soc_min_pct']:.1f}% charge_events={rb['n_charge_events']} "
              f"board_denied={rb['n_board_denied']}")
    bd = k["building"]
    if bd["drain_span_sec"] is not None:
        print(f"  drain: span={bd['drain_span_sec']:.0f}s "
              f"deliveries={bd['drain_deliveries']}/{cu['n_delivered']} "
              f"ev_boardings={bd['drain_ev_boardings']}")
    print(f"  wrote {out_path}")


if __name__ == "__main__":
    main()
