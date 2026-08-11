"""v5 floor mapping: v4 method + per-scenario demand-centroid building anchor.

v4 (analysis/map_floor_v4.py, frozen) fixed the building at one Seoul
coordinate — only 6 of the data1 scenarios are actually Seoul-located, so the
Step-6 horizontal (street) decomposition is meaningless for the rest. v5
keeps every v4 rule (2D→3D mapping 기존대로) and changes exactly one thing:

  building anchor = the scenario's demand mid-point
                  = arithmetic mean of the K delivery coordinates
                    (DLV_LAT, DLV_LON) — per scenario, not global.

Unchanged from v4 (identical floors/offices for every scenario):
  Step 2  d_i = DIST[i][K+i]           (data road distance, anchor-free)
  Step 3  floor_i = clip(2 + floor(d_i / 500 m), 2, 10)
  Step 4  office_i = random.Random(42).randrange(12), row order
  Step 6  horizontal = c * haversine(shop → anchor)   ← anchor is v5's change
          vertical / in-floor terms identical

Writes under data/floor_mapping/:
  {scenario}_floor_mapping_v5.json
  {scenario}_movement_distances_v5.json

CLI:
  python -m analysis.map_floor_v5 data/data1/K50_1.json   # one scenario
  python -m analysis.map_floor_v5 --all                   # every data1 K*.json
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from analysis.load_data import Order, load_scenario
from analysis.map_floor_v4 import (
    CIRCUITY_C,
    BANDWIDTH_W,
    CONFIG_PATH,
    ENTRANCE_M,
    FLOOR_HEIGHT_M,
    N_OFFICES,
    OFFICE_FLOORS,
    OFFICE_SEED,
    assign_floor,
    haversine_m,
)
from simulation.space import build_from_config, load_config, shortest_walk_path

ROOT = Path(__file__).resolve().parent.parent
METHODOLOGY = (
    "etc/methodology_demand_to_floor_mapping_v4.md"
    " + per-scenario demand-centroid anchor (v5)"
)
ANCHOR_RULE = "mean(DLV_LAT), mean(DLV_LON) over the scenario's K orders"


def demand_centroid(orders: list[Order]) -> tuple[float, float]:
    """Building anchor: arithmetic mean of the delivery coordinates."""
    if not orders:
        raise ValueError("demand_centroid needs at least one order")
    lat = sum(o.dlv_lat for o in orders) / len(orders)
    lon = sum(o.dlv_lon for o in orders) / len(orders)
    return lat, lon


def generate(source_rel: str, quiet: bool = False) -> dict:
    """Generate the v5 mapping pair for one scenario; return the summary."""
    import random

    src = ROOT / source_rel
    scenario = load_scenario(src)
    K = scenario.K
    anchor = demand_centroid(scenario.orders)
    d = [float(scenario.dist[i][K + i]) for i in range(K)]  # Step 2 (= v4)

    floors = [assign_floor(di) for di in d]                 # Step 3 (= v4)
    rng = random.Random(OFFICE_SEED)                        # Step 4 (= v4)
    offices = [rng.randrange(N_OFFICES) for _ in range(K)]

    g = build_from_config(load_config(ROOT / CONFIG_PATH))
    in_floor_cache: dict[tuple[int, int], float] = {}

    def in_floor_m(floor: int, office_id: int) -> float:
        key = (floor, office_id)
        if key not in in_floor_cache:
            _, dist = shortest_walk_path(
                g, f"floor_{floor}_center", f"floor_{floor}_office_{office_id}"
            )
            in_floor_cache[key] = round(dist, 2)
        return in_floor_cache[key]

    now = datetime.now(timezone.utc).isoformat()

    fm_orders = []
    mv_orders = []
    floor_counts = {f: 0 for f in OFFICE_FLOORS}
    for i, order in enumerate(scenario.orders):
        f = floors[i]
        off = offices[i]
        floor_counts[f] += 1

        fm_orders.append({
            "ord_id": order.ord_id,
            "row_index": i,
            "delivery_distance_m": round(d[i], 1),
            "floor": f,
            "office_id": off,
        })

        horizontal = CIRCUITY_C * haversine_m(
            order.shop_lat, order.shop_lon, *anchor
        )
        interfloor = (f - 1) * FLOOR_HEIGHT_M
        vertical_total = ENTRANCE_M + interfloor
        infloor = in_floor_m(f, off)
        mv_orders.append({
            "ord_id": order.ord_id,
            "row_index": i,
            "shop_coord": {"lat": order.shop_lat, "lon": order.shop_lon},
            "delivery_distance_m": round(d[i], 1),
            "floor": f,
            "office_id": off,
            "horizontal_m": round(horizontal, 2),
            "vertical": {
                "entrance_m": ENTRANCE_M,
                "interfloor_m": round(interfloor, 2),
                "total_m": round(vertical_total, 2),
            },
            "in_floor_m": infloor,
            "total_travel_m": round(horizontal + vertical_total + infloor, 2),
        })

    dist_dist = [floor_counts[f] for f in OFFICE_FLOORS]
    vacant = [f for f in OFFICE_FLOORS if floor_counts[f] == 0]
    ds = sorted(d)
    n_clip = sum(1 for di in d if di >= 4000.0)

    stem = Path(source_rel).stem
    floor_mapping = {
        "source_file": source_rel,
        "scenario_name": scenario.name,
        "K": K,
        "methodology": f"{METHODOLOGY} (fixed-bandwidth affine discretization)",
        "generated_at_utc": now,
        "id_key": "ord_id = original ORDERS[i][0]; row_index = DIST node index i",
        "parameters": {
            "building_coord": {"lat": anchor[0], "lon": anchor[1]},
            "anchor_rule": ANCHOR_RULE,
            "office_floors": OFFICE_FLOORS,
            "n_offices_per_floor": N_OFFICES,
            "office_seed": OFFICE_SEED,
            "circuity_c": CIRCUITY_C,
            "bandwidth_w_m": BANDWIDTH_W,
            "floor_rule": "floor = clip(2 + floor(d_i / w), 2, 10)",
        },
        "floor_distribution_2_to_10": dist_dist,
        "vacant_floors": vacant,
        "distance_summary_m": {
            "min": round(ds[0], 1),
            "median": round(ds[K // 2], 1),
            "max": round(ds[-1], 1),
            "n_ge_4000m": n_clip,
        },
        "orders": fm_orders,
    }

    movement = {
        "source_file": source_rel,
        "mapping_file": f"data/floor_mapping/{stem}_floor_mapping_v5.json",
        "scenario_name": scenario.name,
        "K": K,
        "generated_at_utc": now,
        "building_coord": {"lat": anchor[0], "lon": anchor[1]},
        "anchor_rule": ANCHOR_RULE,
        "distance_model": {
            "horizontal": "circuity_c * great-circle(shop -> building_coord), meters",
            "vertical": "entrance_m + (floor-1)*floor_height_m",
            "in_floor": "building-graph shortest walk floor_center -> office",
            "circuity_c": CIRCUITY_C,
            "floor_height_m": FLOOR_HEIGHT_M,
            "entrance_m": ENTRANCE_M,
            "config": CONFIG_PATH,
        },
        "orders": mv_orders,
    }

    out_dir = ROOT / "data" / "floor_mapping"
    fm_path = out_dir / f"{stem}_floor_mapping_v5.json"
    mv_path = out_dir / f"{stem}_movement_distances_v5.json"
    fm_path.write_text(json.dumps(floor_mapping, ensure_ascii=False, indent=2))
    mv_path.write_text(json.dumps(movement, ensure_ascii=False, indent=2))

    horiz = [o["horizontal_m"] for o in mv_orders]
    summary = {
        "scenario": stem,
        "K": K,
        "anchor": anchor,
        "floor_distribution": dist_dist,
        "vacant_floors": vacant,
        "n_clip_10f": n_clip,
        "horizontal_m_median": round(sorted(horiz)[K // 2], 1),
        "fm_path": str(fm_path.relative_to(ROOT)),
    }
    if not quiet:
        print(f"[v5] {stem:9s} K={K:5d} anchor=({anchor[0]:.5f},{anchor[1]:.5f}) "
              f"floors 2..10F: {dist_dist}  clip@10F: {n_clip}  "
              f"horiz median: {summary['horizontal_m_median']:.0f} m")
    return summary


def main(argv: list[str] | None = None) -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sources", nargs="*",
                        help="scenario JSON path(s) relative to repo root")
    parser.add_argument("--all", action="store_true",
                        help="every data/data1/K*.json scenario")
    args = parser.parse_args(argv)

    if args.all:
        sources = sorted(
            str(p.relative_to(ROOT)) for p in (ROOT / "data" / "data1").glob("K*.json")
        )
    else:
        sources = args.sources or ["data/data1/K50_1.json"]

    summaries = [generate(s) for s in sources]
    vacant_any = [s["scenario"] for s in summaries if s["vacant_floors"]]
    print(f"[v5] generated {len(summaries)} scenario mapping(s)")
    if vacant_any:
        print(f"[v5] WARNING vacant office floors in: {', '.join(vacant_any)}")


if __name__ == "__main__":
    main()
