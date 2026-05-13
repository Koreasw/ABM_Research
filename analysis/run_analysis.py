"""STAGE 1 pipeline entry point (framework §4).

Runs the full analysis:
  1. NHPP lambda(t) — pooled + K-stratum
  2. Cook time fit (Gamma vs Lognormal vs Weibull, AIC)
  3. VOL distribution
  4. Lead time distribution
  5. Pickup-drop road distance (context)
  6. K-scaling structural indicators
  7. Rider arrival time synthesis (§2.5) — lambda by K with bootstrap CI
  8. Per-type w_R calibration

Outputs:
  analysis/fitted_params.json
  analysis/figures/*.png  (8 figures)
  analysis/fit_report.md
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from scipy import stats  # noqa: E402

from analysis.demand_model import DemandModel  # noqa: E402
from analysis.load_data import load_scenario, pickup_drop_distance  # noqa: E402
from analysis.rider_arrival_model import (  # noqa: E402
    compute_w_R_krw_per_h,
    estimate_lambda_rider_K,
    sample_rider_arrivals,
)

K_STRATA = [50, 100, 200, 300]   # 1차 분석: 일관된 ~1h horizon (framework §2.6 caveat)
# K_STRATA_TIER2 = [500, 1000]   # 2차: horizon 혼재 → 60min truncate 또는 sub-stratify 후 분석


# ---------- helpers ----------

def _serialize_lambda(d: dict) -> dict:
    return {
        "bin_edges": d["bin_edges"].tolist(),
        "bin_centers": d["bin_centers"].tolist(),
        "lambda_per_sec": d["lambda_per_sec"].tolist(),
        "lambda_per_h": d["lambda_per_h"].tolist(),
        "ci_lo_per_h": d["ci_lo_per_h"].tolist(),
        "ci_hi_per_h": d["ci_hi_per_h"].tolist(),
        "n_scenarios": int(d["n_scenarios"]),
        "K": d["K"],
    }


def _filter_paths_by_K(paths: list[Path], K: int) -> list[Path]:
    return [p for p in paths if load_scenario(p).K == K]


# ---------- figure functions ----------

def plot_lambda_pooled(dm: DemandModel, out_path: Path) -> None:
    centers = 0.5 * (dm.bin_edges[:-1] + dm.bin_edges[1:])
    lam_h = dm.lambda_per_sec * 3600.0
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(centers / 60, lam_h, width=4.5, color="steelblue", alpha=0.85)
    ax.set_xlabel("t (min from scenario start)")
    ax.set_ylabel("lambda(t) per scenario [orders/h]")
    ax.set_title(
        f"Pooled NHPP lambda(t) (tier-1: K in {{50,100,200,300}}, n={dm.n_scenarios_fit})"
    )
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def plot_lambda_by_K(dm_by_K: dict[int, DemandModel], out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(9, 5))
    cmap = plt.cm.viridis(np.linspace(0.1, 0.9, len(dm_by_K)))
    for color, (K, dm) in zip(cmap, sorted(dm_by_K.items()), strict=False):
        centers = 0.5 * (dm.bin_edges[:-1] + dm.bin_edges[1:])
        ax.plot(centers / 60, dm.lambda_per_sec * 3600.0,
                label=f"K={K} (n={dm.n_scenarios_fit})", color=color, lw=1.6)
    ax.set_xlabel("t (min from scenario start)")
    ax.set_ylabel("lambda_K(t) per scenario [orders/h]")
    ax.set_title("NHPP arrival rate by K-stratum")
    ax.legend(loc="upper right", fontsize=9)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def plot_k50_per_scenario_arrivals(scenarios: list[Path], out_path: Path) -> None:
    k50_paths = _filter_paths_by_K(scenarios, 50)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.5))
    for p in k50_paths:
        s = load_scenario(p)
        times = np.sort([o.ord_time_sec for o in s.orders]) / 60.0
        ax1.step(times, np.arange(1, len(times) + 1), where="post", label=s.name, alpha=0.85)
    ax1.set_xlabel("t (min)")
    ax1.set_ylabel("cumulative orders")
    ax1.set_title("K=50 per-scenario cumulative arrivals (face validity)")
    ax1.legend(fontsize=9)

    bin_edges = np.arange(0, 70, 5) * 60.0
    for p in k50_paths:
        s = load_scenario(p)
        times = np.array([o.ord_time_sec for o in s.orders])
        counts, _ = np.histogram(times, bins=bin_edges)
        centers = 0.5 * (bin_edges[:-1] + bin_edges[1:])
        ax2.plot(centers / 60, counts / 5 * 60.0, marker="o", label=s.name, alpha=0.85)
    ax2.set_xlabel("t (min)")
    ax2.set_ylabel("orders/h (5-min bins)")
    ax2.set_title("K=50 per-scenario lambda(t)")
    ax2.legend(fontsize=9)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def plot_cook_time_fit(cook_samples: np.ndarray, dm: DemandModel, out_path: Path) -> None:
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.5))
    x = np.linspace(1, cook_samples.max() * 1.05, 400)
    ax1.hist(cook_samples / 60, bins=30, density=True, color="lightgray",
             edgecolor="black", alpha=0.85, label="data")
    label_map = {"gamma": stats.gamma, "lognormal": stats.lognorm, "weibull": stats.weibull_min}
    for name, dist in label_map.items():
        if name == dm.cook_fit.distribution:
            params = dm.cook_fit.params
            color, lw = "red", 2.0
        else:
            params = dist.fit(cook_samples, floc=0)
            color, lw = "gray", 1.0
        pdf = dist.pdf(x, *params)
        ax1.plot(x / 60, pdf * 60, label=f"{name}", color=color, lw=lw)
    ax1.set_xlabel("cook time (min)")
    ax1.set_ylabel("density")
    ax1.set_title(f"Cook time fit — best AIC: {dm.cook_fit.distribution}")
    ax1.legend()

    aic_items = list(dm.cook_fit.aic_alternatives.items())
    aic_items.sort(key=lambda kv: kv[1])
    names = [n for n, _ in aic_items]
    aics = [a for _, a in aic_items]
    ax2.barh(names, aics, color=["red" if n == dm.cook_fit.distribution else "lightgray" for n in names])
    ax2.set_xlabel("AIC (lower is better)")
    ax2.set_title("AIC comparison")
    for i, a in enumerate(aics):
        ax2.text(a, i, f" {a:.0f}", va="center", fontsize=9)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def plot_vol_distribution(dm: DemandModel, out_path: Path) -> None:
    vol = dm.vol_samples
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.hist(vol, bins=30, color="seagreen", alpha=0.85, edgecolor="black")
    ax.axvline(vol.mean(), color="red", lw=2, label=f"mean = {vol.mean():.1f}")
    ax.axvline(np.median(vol), color="orange", lw=2, ls="--",
               label=f"median = {np.median(vol):.0f}")
    ax.set_xlabel("VOL")
    ax.set_ylabel("count")
    ax.set_title(f"Order volume distribution (n={len(vol)}, range [{vol.min()}, {vol.max()}])")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def plot_lead_time(lead: np.ndarray, dm: DemandModel, out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.hist(lead / 60, bins=40, color="cornflowerblue", alpha=0.85, edgecolor="black")
    for q, color in [(0.05, "red"), (0.5, "orange"), (0.95, "green")]:
        val = dm.lead_time_quantiles[q] / 60
        ax.axvline(val, color=color, lw=2, label=f"q{int(q * 100):02d} = {val:.1f} min")
    ax.set_xlabel("promised ETA duration (min)  =  DLV_DEADLINE - ORD_TIME")
    ax.set_ylabel("count")
    ax.set_title(
        "Platform SLA distribution — BaeMin's algorithmic ETA promise\n"
        f"(cook + restaurant accuracy + distance;  n={len(lead)}).  "
        "Used as L_sla_violation target; customer renege NOT modeled."
    )
    ax.legend(loc="upper right")
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def plot_pickup_drop_distance(pdd: np.ndarray, out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.hist(pdd / 1000, bins=40, color="plum", alpha=0.85, edgecolor="black")
    ax.axvline(pdd.mean() / 1000, color="red", lw=2, label=f"mean = {pdd.mean() / 1000:.2f} km")
    ax.axvline(np.median(pdd) / 1000, color="orange", lw=2, ls="--",
               label=f"median = {np.median(pdd) / 1000:.2f} km")
    ax.set_xlabel("pickup -> drop distance (km, road network)")
    ax.set_ylabel("count")
    ax.set_title(f"DIST[i][K+i]  (n={len(pdd)}, max {pdd.max() / 1000:.2f} km)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def plot_vol_by_rider_type(
    scenarios: list[Path],
    out_path: Path,
    n_seeds: int = 10,
) -> None:
    """VOL distribution conditional on rider type (capa-conditional sampling)."""
    type_capa = {"BIKE": 100, "WALK": 70, "CAR": 200}
    type_vols: dict[str, list[int]] = {t: [] for t in type_capa}
    for p in scenarios:
        for seed in range(n_seeds):
            events = sample_rider_arrivals(p, seed=seed)
            for e in events:
                type_vols[e.rider_type].append(e.vol)

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.2), sharey=True)
    colors = {"BIKE": "tab:orange", "WALK": "tab:green", "CAR": "tab:blue"}
    bin_edges = np.arange(0, 105, 5)
    for ax, t in zip(axes, ["BIKE", "WALK", "CAR"], strict=False):
        vols = np.array(type_vols[t])
        if len(vols) == 0:
            ax.set_title(f"{t}  (no events)")
            continue
        ax.hist(vols, bins=bin_edges, color=colors[t], edgecolor="black", alpha=0.85)
        ax.axvline(vols.mean(), color="red", lw=2,
                   label=f"mean = {vols.mean():.1f}")
        ax.axvline(np.median(vols), color="darkorange", lw=2, ls=":",
                   label=f"median = {np.median(vols):.0f}")
        capa = type_capa[t]
        if capa <= 105:
            ax.axvline(capa, color="black", lw=1.5, ls="--",
                       label=f"capa = {capa}")
        ax.set_xlabel("VOL")
        ax.set_title(f"{t}  (capa={capa}, n={len(vols):,}, "
                     f"range=[{vols.min()},{vols.max()}])")
        ax.legend(loc="upper right", fontsize=9)
    axes[0].set_ylabel("count")
    fig.suptitle(
        "VOL distribution by rider type — capa-conditional dispatch "
        f"({n_seeds} seeds x {len(scenarios)} scenarios)"
    )
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def plot_rider_arrival_lambda_by_K(
    rider_lambda_by_K: dict[int, dict], out_path: Path
) -> None:
    import math

    items = sorted(rider_lambda_by_K.items())
    n = len(items)
    ncols = max(1, math.ceil(math.sqrt(n)))
    nrows = max(1, math.ceil(n / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(5 * ncols, 4 * nrows), sharey=False)
    axes = np.atleast_1d(axes).flatten()
    for ax, (K, d) in zip(axes, items, strict=False):
        centers_min = np.array(d["bin_centers"]) / 60.0
        ax.fill_between(centers_min, d["ci_lo_per_h"], d["ci_hi_per_h"],
                        color="steelblue", alpha=0.25, label="95% bootstrap CI")
        ax.plot(centers_min, d["lambda_per_h"], color="steelblue", lw=1.6, label="mean")
        ax.set_xlabel("t since lunch peak start (min)")
        ax.set_ylabel("rider arrivals/h")
        ax.set_title(f"K={K}  (n={d['n_scenarios']})")
        ax.legend(fontsize=9)
    for ax in axes[len(items):]:
        ax.set_visible(False)
    fig.suptitle("Rider lobby-arrival rate lambda_rider,K(t)  (§2.5 synthesis)")
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


# ---------- pipeline ----------

def main(
    data_root: Path = Path("data/data1"),
    out_dir: Path = Path("analysis"),
) -> None:
    figures_dir = out_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    all_scenarios = sorted(data_root.glob("K*_*.json"))
    # 1차 분석 cohort: K ∈ {50,100,200,300}, consistent ~1h horizon (framework §2.6)
    scenarios = [p for p in all_scenarios if load_scenario(p).K in K_STRATA]
    print(f"discovered {len(all_scenarios)} scenarios; "
          f"using {len(scenarios)} for tier-1 analysis (K in {K_STRATA})")

    print("fitting pooled DemandModel (tier-1 cohort)...")
    dm_pooled = DemandModel.fit_from_corpus(scenarios)

    print("fitting K-stratum DemandModels...")
    dm_by_K: dict[int, DemandModel] = {}
    for K in K_STRATA:
        try:
            dm_by_K[K] = DemandModel.fit_from_corpus(scenarios, K=K)
            print(f"  K={K}: {dm_by_K[K].n_scenarios_fit} scenarios")
        except ValueError:
            print(f"  K={K}: skipped (no scenarios)")

    print("estimating rider arrival lambda by K...")
    rider_lambda_by_K: dict[int, dict] = {}
    for K in K_STRATA:
        try:
            rider_lambda_by_K[K] = estimate_lambda_rider_K(scenarios, K=K, bootstrap_iters=500)
            print(f"  K={K} rider lambda: ok")
        except ValueError:
            print(f"  K={K} rider lambda: skipped (no scenarios)")

    print("aggregating cook / vol / lead / pickup-drop pools...")
    cook_samples: list[float] = []
    pdd_samples: list[float] = []
    lead_samples: list[float] = []
    for p in scenarios:
        s = load_scenario(p)
        cook_samples.extend(o.cook_time_sec for o in s.orders)
        lead_samples.extend(o.dlv_deadline_sec - o.ord_time_sec for o in s.orders)
        pdd_samples.extend(pickup_drop_distance(p))
    cook_arr = np.array(cook_samples, dtype=float)
    pdd_arr = np.array(pdd_samples, dtype=float)
    lead_arr = np.array(lead_samples, dtype=float)

    print("computing w_R per type from K=50_1 (RIDERS structure)...")
    s_ref = load_scenario(scenarios[0])
    w_R_by_type = {r.type: compute_w_R_krw_per_h(r) for r in s_ref.riders}

    print("serializing fitted_params.json...")
    params = {
        "pooled": dm_pooled.to_dict(),
        "by_K": {str(K): dm.to_dict() for K, dm in dm_by_K.items()},
        "rider_arrivals_by_K": {
            str(K): _serialize_lambda(d) for K, d in rider_lambda_by_K.items()
        },
        "w_R_by_type_krw_per_h": w_R_by_type,
        "summary": {
            "n_scenarios": len(scenarios),
            "n_orders_total": int(sum(load_scenario(p).K for p in scenarios)),
            "cook_mean_sec": float(cook_arr.mean()),
            "cook_median_sec": float(np.median(cook_arr)),
            "vol_mean": float(dm_pooled.vol_samples.mean()),
            "vol_median": float(np.median(dm_pooled.vol_samples)),
            "lead_q05_min": float(np.quantile(lead_arr, 0.05) / 60),
            "lead_q50_min": float(np.quantile(lead_arr, 0.5) / 60),
            "lead_q95_min": float(np.quantile(lead_arr, 0.95) / 60),
            "pdd_mean_m": float(pdd_arr.mean()),
            "pdd_max_m": float(pdd_arr.max()),
        },
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "fitted_params.json").write_text(json.dumps(params, indent=2))

    print("generating figures...")
    plot_lambda_pooled(dm_pooled, figures_dir / "fig_lambda_pooled.png")
    plot_lambda_by_K(dm_by_K, figures_dir / "fig_lambda_by_K.png")
    plot_k50_per_scenario_arrivals(scenarios, figures_dir / "fig_k50_per_scenario_arrivals.png")
    plot_cook_time_fit(cook_arr, dm_pooled, figures_dir / "fig_cook_time_fit.png")
    plot_vol_distribution(dm_pooled, figures_dir / "fig_vol_distribution.png")
    plot_lead_time(lead_arr, dm_pooled, figures_dir / "fig_lead_time.png")
    plot_pickup_drop_distance(pdd_arr, figures_dir / "fig_pickup_drop_distance.png")
    if rider_lambda_by_K:
        plot_rider_arrival_lambda_by_K(
            rider_lambda_by_K, figures_dir / "fig_rider_arrival_lambda_K.png"
        )
    plot_vol_by_rider_type(scenarios, figures_dir / "fig_vol_by_rider_type.png")

    print("writing fit_report.md...")
    write_fit_report(dm_pooled, dm_by_K, params["summary"], w_R_by_type, out_dir / "fit_report.md")
    print(f"done. outputs under {out_dir}")


def write_fit_report(
    dm_pooled: DemandModel,
    dm_by_K: dict[int, DemandModel],
    summary: dict,
    w_R_by_type: dict[str, float],
    out_path: Path,
) -> None:
    cook = dm_pooled.cook_fit
    aic_alt = cook.aic_alternatives

    lines = [
        "# STAGE 1 적합 리포트",
        "",
        f"전체 시나리오: **{summary['n_scenarios']}개**, 총 주문: **{summary['n_orders_total']:,}건**",
        "",
        "## 1. NHPP λ(t)",
        f"- 풀링 적합: {dm_pooled.n_scenarios_fit}개 시나리오, "
        f"horizon ≈ {dm_pooled.bin_edges[-1] / 3600:.1f} h",
        "- K-stratum 적합 (시나리오 수):",
    ]
    for K in sorted(dm_by_K):
        lines.append(f"  - K={K}: {dm_by_K[K].n_scenarios_fit} 시나리오, "
                     f"horizon ≈ {dm_by_K[K].bin_edges[-1] / 3600:.2f} h")

    lines.extend([
        "",
        "## 2. 음식 준비시간 F_prep",
        f"- 최우수 분포 (AIC): **{cook.distribution}** "
        f"params = {tuple(round(p, 3) for p in cook.params)}, AIC = {cook.aic:.1f}",
        "- AIC 비교:",
    ])
    for name in sorted(aic_alt, key=lambda n: aic_alt[n]):
        marker = "  ←" if name == cook.distribution else ""
        lines.append(f"  - {name}: AIC = {aic_alt[name]:.1f}{marker}")
    lines.extend([
        f"- mean = {summary['cook_mean_sec'] / 60:.1f} min, "
        f"median = {summary['cook_median_sec'] / 60:.0f} min",
        "- 주의: 데이터는 5분 단위 이산값 → 연속분포 가정 하에서 KS 통계량 과대평가",
        "",
        "## 3. 주문 부피 VOL",
        f"- mean = {summary['vol_mean']:.1f}, median = {summary['vol_median']:.0f}",
        "- 활용: LockerAgent V_max baseline 100 결정 근거 (q95 ≈ 70)",
        "",
        "## 4. 플랫폼 SLA 분포 (DLV_DEADLINE − ORD_TIME = 약속된 ETA 대기시간)",
        f"- q05 = {summary['lead_q05_min']:.1f} min  (가장 빠른 ETA 약속)",
        f"- q50 = {summary['lead_q50_min']:.1f} min",
        f"- q95 = {summary['lead_q95_min']:.1f} min  (가장 늦은 ETA 약속)",
        "- DLV_DEADLINE 은 배민 알고리즘 산출 ETA (cook + 거리 + 식당 정확도). 본 paper 에서는 L_sla_violation KPI 의 비교 기준으로 사용 (CustomerAgent.dlv_deadline_sec 로 직접 주입). 고객 포기 (renege) 행동은 모델링하지 않음.",
        "",
        "## 5. 도로망 픽업-드롭 거리 (context)",
        f"- mean = {summary['pdd_mean_m'] / 1000:.2f} km, "
        f"max = {summary['pdd_max_m'] / 1000:.2f} km",
        "- 빌딩 내부 거리는 §5 networkx 그래프에서 별도 산출",
        "- 본 페이퍼는 라이더 빌딩 도착 시각 합성식의 travel_time 항에 이 거리를 사용",
        "",
        "## 6. 라이더 시간단가 w_R (KRW/h)  — throughput 50건/h 가정",
    ])
    for typ, w in w_R_by_type.items():
        lines.append(f"- {typ}: {w:,.0f}")
    lines.extend([
        "",
        "## 7. 산출 figure (analysis/figures/)",
        "- fig_lambda_pooled.png — 풀링 NHPP λ(t)",
        "- fig_lambda_by_K.png — K-stratum λ_K(t)",
        "- fig_k50_per_scenario_arrivals.png — K=50 face validity",
        "- fig_cook_time_fit.png — 분포 적합 + AIC 비교",
        "- fig_vol_distribution.png",
        "- fig_lead_time.png",
        "- fig_pickup_drop_distance.png",
        "- fig_rider_arrival_lambda_K.png — §2.5 합성 결과 + bootstrap CI",
        "- fig_vol_by_rider_type.png — capa-conditional VOL 분포 (BIKE/WALK/CAR)",
        "",
        "## 8. fitted_params.json 키 구조",
        "- `pooled`, `by_K[K]`: DemandModel.to_dict() 직렬화",
        "- `rider_arrivals_by_K[K]`: λ_rider,K(t) + 95% CI",
        "- `w_R_by_type_krw_per_h`: 라이더 시간단가",
        "- `summary`: 핵심 요약 통계",
    ])
    out_path.write_text("\n".join(lines))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="STAGE 1 pipeline (framework §4)")
    parser.add_argument("--data-root", default="data/data1", type=Path)
    parser.add_argument("--out-dir", default="analysis", type=Path)
    args = parser.parse_args()
    main(args.data_root, args.out_dir)
