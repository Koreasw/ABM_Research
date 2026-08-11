"""T3 — uncongested travel-time precompute orchestrator.

etc/plan_travel_time_functions.md §5 (output schema) / §7 (T3 stage).

Combines:
  - {scenario}_movement_distances_v4.json (v4 mapping Step 6: horizontal_m,
    floor, office_id, in_floor_m per order)
  - scenario RIDERS (speed_mps per type, via analysis.load_data.load_scenario)
  - configs/baseline_10f.yaml `vertical:` block (via simulation.vertical_transport)

into, per order, the fully pre-computed uncongested reference time (T1
horizontal / T2 vertical / T3 in-floor). This is the source of:
  (a) the S6 validation lower-bound reference, and
  (b) the sampled vertical_mode ('elevator'/'stairs') — the same
      VerticalTransportModel.sample_mode(ord_id, floor) call the ABM makes,
      so the two are bit-identical by construction (no re-sync needed).

CLI:
    python -m analysis.travel_time_v4 data/data1/K50_1.json
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from analysis.load_data import load_scenario
from simulation.space import load_config
from simulation.vertical_transport import VerticalTransportModel

ROOT = Path(__file__).resolve().parent.parent
METHODOLOGY = "etc/plan_travel_time_functions.md"
RIDER_TYPES = ("BIKE", "WALK", "CAR")


def _rel(p: Path) -> str:
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


def compute_travel_times(
    scenario_path: str | Path,
    distances_path: str | Path,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Compute the per-order uncongested travel-time record set.

    Raises ValueError if the movement-distances file's K doesn't match the
    scenario's K, or if any RIDER_TYPES entry is missing from the scenario.
    """
    scenario_path = Path(scenario_path)
    distances_path = Path(distances_path)
    scenario = load_scenario(scenario_path)
    movement = json.loads(distances_path.read_text())

    if movement["K"] != scenario.K:
        raise ValueError(
            f"K mismatch: scenario K={scenario.K} vs "
            f"movement_distances K={movement['K']}"
        )

    speed_by_type = {r.type: r.speed_mps for r in scenario.riders}
    missing_types = [t for t in RIDER_TYPES if t not in speed_by_type]
    if missing_types:
        raise ValueError(f"scenario RIDERS missing type(s): {missing_types}")

    vt = VerticalTransportModel.from_config(config)
    now = datetime.now(timezone.utc).isoformat()

    orders_out = []
    for rec in movement["orders"]:
        ord_id = rec["ord_id"]
        floor = rec["floor"]
        horizontal_m = rec["horizontal_m"]
        in_floor_m = rec["in_floor_m"]

        horizontal_time_s = {
            t: round(horizontal_m / speed_by_type[t], 2) for t in RIDER_TYPES
        }

        t_elevator = vt.t_elevator_s(floor)
        t_stairs = vt.t_stairs_s(floor)
        mode = vt.sample_mode(ord_id, floor)
        mode_time = t_elevator if mode == "elevator" else t_stairs
        entrance_walk = vt.entrance_walk_s()
        vertical_total = entrance_walk + mode_time

        in_floor_time_s = round(in_floor_m / vt.walk_speed_mps, 2)

        total_time_s = {
            t: round(horizontal_time_s[t] + vertical_total + in_floor_time_s, 2)
            for t in RIDER_TYPES
        }

        orders_out.append(
            {
                "ord_id": ord_id,
                "row_index": rec["row_index"],
                "floor": floor,
                "office_id": rec["office_id"],
                "horizontal_m": horizontal_m,
                "horizontal_time_s": horizontal_time_s,
                "vertical": {
                    "entrance_walk_s": round(entrance_walk, 2),
                    "t_elevator_s": round(t_elevator, 2),
                    "t_stairs_s": round(t_stairs, 2),
                    "p_elevator": round(vt.p_elevator(floor), 3),
                    "mode": mode,
                    "mode_time_s": round(mode_time, 2),
                    "expected_time_s": round(vt.expected_vertical_time(floor), 2),
                    "total_time_s": round(vertical_total, 2),
                },
                "in_floor_m": in_floor_m,
                "in_floor_time_s": in_floor_time_s,
                "total_time_s": total_time_s,
            }
        )

    return {
        "source_file": movement.get("source_file"),
        "floor_mapping_file": movement.get("mapping_file"),
        "movement_distances_file": _rel(distances_path),
        "scenario_name": scenario.name,
        "K": scenario.K,
        "methodology": METHODOLOGY,
        "generated_at_utc": now,
        "rng_convention": (
            "default_rng(uint64(mode_seed) XOR uint64(ord_id)); one uniform draw"
        ),
        "parameters": {
            "accel_mps2": vt.kin.accel_mps2,
            "max_speed_mps": vt.kin.max_speed_mps,
            "floor_height_m": vt.kin.floor_height_m,
            "door_open_close_sec": vt.kin.door_open_close_sec,
            "ev_wait_sec": vt.ev_wait_sec,
            "stair_sec_per_floor": vt.stair_sec_per_floor,
            "mode_choice_beta_per_sec": vt.beta_per_sec,
            "mode_seed": vt.mode_seed,
            "walk_speed_mps": vt.walk_speed_mps,
            "entrance_m": vt.entrance_m,
        },
        "orders": orders_out,
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="T3 — travel-time precompute (uncongested baseline)"
    )
    parser.add_argument("scenario", help="path to scenario JSON, e.g. data/data1/K50_1.json")
    parser.add_argument(
        "--distances",
        default=None,
        help="movement_distances_v4.json path (default: derived from scenario stem)",
    )
    parser.add_argument("--config", default="configs/baseline_10f.yaml")
    parser.add_argument(
        "--out", default=None, help="output path (default: derived from scenario stem)"
    )
    args = parser.parse_args(argv)

    scenario_path = Path(args.scenario)
    if not scenario_path.is_absolute():
        scenario_path = ROOT / scenario_path
    stem = scenario_path.stem

    distances_path = (
        Path(args.distances)
        if args.distances
        else ROOT / "data" / "floor_mapping" / f"{stem}_movement_distances_v4.json"
    )
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = ROOT / config_path
    out_path = (
        Path(args.out)
        if args.out
        else ROOT / "data" / "floor_mapping" / f"{stem}_travel_times_v4.json"
    )

    config = load_config(config_path)
    result = compute_travel_times(scenario_path, distances_path, config)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2))

    n = len(result["orders"])
    n_stairs = sum(1 for o in result["orders"] if o["vertical"]["mode"] == "stairs")
    bike_times = sorted(o["total_time_s"]["BIKE"] for o in result["orders"])
    print(f"[travel_time_v4] {result['scenario_name']}  K={result['K']}")
    print(f"  stairs sampled: {n_stairs}/{n}")
    print(
        f"  BIKE total_time_s: min={bike_times[0]:.1f} "
        f"median={bike_times[n // 2]:.1f} max={bike_times[-1]:.1f}"
    )
    print(f"  wrote {_rel(out_path)}")


if __name__ == "__main__":
    main()
