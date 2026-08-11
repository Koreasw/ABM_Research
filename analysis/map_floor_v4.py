"""v4 floor mapping: fixed-bandwidth affine discretization (methodology v4).

Implements etc/methodology_demand_to_floor_mapping_v4.md exactly:
  Step 3  floor_i = clip(2 + floor(d_i / w), 2, 10),  w = 500 m
  Step 4  office_i = random.Random(42).randrange(12), row order i=0..K-1
  Step 6  total = horizontal (c * haversine(shop, anchor))
                + vertical  (entrance_m + (floor-1)*floor_height_m)
                + in_floor  (building-graph shortest walk floor_center -> office)

Writes two artifacts under data/floor_mapping/:
  {scenario}_floor_mapping_v4.json      (Step 5 demand records)
  {scenario}_movement_distances_v4.json (Step 6 travel decomposition)
"""

from __future__ import annotations

import json
import math
import random
from datetime import datetime, timezone
from pathlib import Path

from analysis.load_data import load_scenario
from simulation.space import build_from_config, load_config, shortest_walk_path

ROOT = Path(__file__).resolve().parent.parent
METHODOLOGY = "etc/methodology_demand_to_floor_mapping_v4.md"

# --- v4 fixed parameters (methodology §5) ---
BUILDING_COORD = (37.497054, 127.037138)  # §5.1 anchor (lat, lon)
CIRCUITY_C = 1.402                         # §5.2 detour factor
BANDWIDTH_W = 500.0                        # §5.3 fixed band width (m)
OFFICE_FLOORS = list(range(2, 11))         # §5.4 office floors 2..10F
FLOOR_MIN, FLOOR_MAX = 2, 10
N_OFFICES = 12                             # §5.4
OFFICE_SEED = 42                           # Step 4 RNG spec
FLOOR_HEIGHT_M = 4.0                       # §5.4
ENTRANCE_M = 4.0                           # §5.4 lobby_entry -> floor_1_center
CONFIG_PATH = "configs/baseline_10f.yaml"


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in meters."""
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2)
    return r * 2 * math.asin(math.sqrt(a))


def assign_floor(d: float) -> int:
    """Step 3: fixed-bandwidth affine discretization."""
    return max(FLOOR_MIN, min(FLOOR_MAX, 2 + int(d // BANDWIDTH_W)))


def main(source_rel: str) -> None:
    src = ROOT / source_rel
    scenario = load_scenario(src)
    K = scenario.K
    d = [float(scenario.dist[i][K + i]) for i in range(K)]  # Step 2

    # Step 3: floors (deterministic, data-only)
    floors = [assign_floor(di) for di in d]

    # Step 4: offices (RNG spec: fresh Random(42), row order, randrange(12))
    rng = random.Random(OFFICE_SEED)
    offices = [rng.randrange(N_OFFICES) for _ in range(K)]

    # Step 6 ③: in-floor walk distances from the building graph
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

    # ---- Step 5: floor-mapping records ----
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
            order.shop_lat, order.shop_lon, *BUILDING_COORD
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

    floor_mapping = {
        "source_file": source_rel,
        "scenario_name": scenario.name,
        "K": K,
        "methodology": f"{METHODOLOGY} (fixed-bandwidth affine discretization)",
        "generated_at_utc": now,
        "id_key": "ord_id = original ORDERS[i][0]; row_index = DIST node index i",
        "parameters": {
            "building_coord": {"lat": BUILDING_COORD[0], "lon": BUILDING_COORD[1]},
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
        "mapping_file": f"data/floor_mapping/{Path(source_rel).stem}_floor_mapping_v4.json",
        "scenario_name": scenario.name,
        "K": K,
        "generated_at_utc": now,
        "building_coord": {"lat": BUILDING_COORD[0], "lon": BUILDING_COORD[1]},
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
    stem = Path(source_rel).stem
    fm_path = out_dir / f"{stem}_floor_mapping_v4.json"
    mv_path = out_dir / f"{stem}_movement_distances_v4.json"
    fm_path.write_text(json.dumps(floor_mapping, ensure_ascii=False, indent=2))
    mv_path.write_text(json.dumps(movement, ensure_ascii=False, indent=2))

    # ---- Step 7 quick verification to stdout ----
    total_travel = sum(o["total_travel_m"] for o in mv_orders)
    total_horiz = sum(o["horizontal_m"] for o in mv_orders)
    print(f"[v4] {scenario.name}  K={K}")
    print(f"  floor dist 2..10F: {dist_dist}  (vacant: {vacant or 'none'})")
    print(f"  distance m: min={ds[0]:.0f} median={ds[K//2]:.0f} "
          f"max={ds[-1]:.0f}  >=4000m(clip): {n_clip}")
    print(f"  horizontal share of total travel: "
          f"{100*total_horiz/total_travel:.1f}%")
    print(f"  wrote {fm_path.relative_to(ROOT)}")
    print(f"  wrote {mv_path.relative_to(ROOT)}")


if __name__ == "__main__":
    import sys
    main(sys.argv[1] if len(sys.argv) > 1 else "data/data1/K50_1.json")
