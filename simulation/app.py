"""SolaraViz entry point for the H0 baseline (plan Part F + S7.1 extensions).

Run the live building cross-section + KPI dashboards with:

    .venv/bin/solara run simulation/app.py

Solara imports this module and renders the module-level `page`. Each browser
session builds its **own** model with `make_model()` from configs/baseline_10f.yaml
(H0 v2 geometry: 10F, 34 m corridor, 4 cross-placed EVs, people-only basements
B1/B2) with the K50_1 scenario on the `uniform` demand profile; use the
play/step controls in the browser to advance the simulation. The scenario picker
lists every file under data/data1 — the analysis tiering (plan_h0_revision.md
§1.4) governs reported results, not this exploration UI.

⚠️ The model MUST NOT be a module-level object. Solara executes this script
**once per server** (`AppScript._first_execute_app` is cached) and every virtual
kernel reuses the resulting module, so a module-level model is shared by every
browser session. That combination is what made the app die mid-run: a dropped
websocket leaves the old kernel's mesa play thread running (kernel cull_timeout
defaults to 24h and `ModelController`'s loop only watches `playing`/`running`),
so after the user refreshes, the *new* kernel drives the *same* model while the
orphan keeps stepping it. The two render trees then collide inside
`force_update()` with

    reacton/core.py: assert widget.model_id in _get_widgets_dict()  -> AssertionError

which `ModelController.step()` swallows into `error_message` and returns from —
the play loop dies and the simulation freezes. Measured: 7.2 ticks/s on a single
kernel, 1.6 ticks/s plus two AssertionErrors after one refresh. `use_memo` inside
`Page` gives every kernel its own model and removes the sharing entirely.

Pair this with a short kernel cull timeout so orphaned kernels (and their play
threads) actually get collected instead of lingering for 24 h:

    SOLARA_KERNEL_CULL_TIMEOUT=60s .venv/bin/solara run simulation/app.py

Parameter sidebar (S7.1): `rng_seed` (rider type/ε sampling + pedestrian
stream — vertical-mode choice stays on vertical.mode_seed XOR ord_id, so it
does NOT change with this seed) and `scenario_path` (all data/data1/K*.json
scenarios — floor/office now come from the runtime population-density
profile, so no per-scenario mapping file is required). Floor demand is
picked with `floor_profile` (uniform / bottom_heavy / top_heavy;
etc/demand_mapping.md); `floor_seed` stays unexposed here and defaults to
`rng_seed` (framework §7.1). Changed values apply on **Reset**, which
reconstructs the model via `type(model)(**model_params)` — `floor_profile`
MUST stay a model_params key, or Reset would silently fall back to the
(now-unmapped) v4 mapping path and crash on scenarios lacking a v4 mapping
file. Combining `dynamic_pool=False` (static) with a floor_profile is an
invalid combination that the model rejects with ValueError; there's no
extra UI guard against it.
"""

from __future__ import annotations

import solara
from mesa.visualization import Slider

from simulation.model import ROOT, BuildingHandoffModel, HandoffMode
from simulation.space import load_config
from simulation.visualize import build_solara_app


def available_scenarios() -> list[str]:
    """All scenario files under data/data1 (floor/office source is the
    runtime demand profile, not a per-scenario mapping file)."""
    return [
        f"data/data1/{p.name}"
        for p in sorted((ROOT / "data" / "data1").glob("K*.json"))
    ]


_DEFAULT_SCENARIO = "data/data1/K50_1.json"
_DEFAULT_FLOOR_PROFILE = "uniform"

model_params = {
    "rng_seed": Slider("RNG seed (rider type·ε·pedestrians)", 42, 0, 999, 1),
    "scenario_path": {
        "type": "Select",
        "label": "Scenario",
        "value": _DEFAULT_SCENARIO,
        "values": available_scenarios() or [_DEFAULT_SCENARIO],
    },
    # ⚠️ 이 Select(및 아래 위젯 전부)는 값을 바꿔도 **Reset을 눌러야** 반영된다.
    # mesa 3.5의 SolaraViz는 do_reset()에서만 모델을 재생성하고, 그 전까지는
    # reactive 값만 갱신한다. 프로파일이 실제로 적용됐는지는 FloorDemandPanel
    # (visualize.py, R8-g)이 설계 확률 대 실제 층 히스토그램으로 보여 준다.
    "floor_profile": {
        "type": "Select",
        "label": "층 수요 프로파일 (Reset 후 적용)",
        "value": _DEFAULT_FLOOR_PROFILE,
        "values": ["uniform", "bottom_heavy", "top_heavy"],
    },
    # 동적 라이더 풀 (etc/plan_rider_pool_dynamic.md): type별 유한 재고에서
    # 비용순위 cascade로 배차, 건물 퇴장 시 복귀. 끄면 기존 정적 v4 replay.
    "dynamic_pool": {
        "type": "Checkbox",
        "label": "동적 라이더 풀 (재고 차감/복귀)",
        "value": True,
    },
    "return_leg": {
        "type": "Checkbox",
        "label": "복귀 이동시간 포함 (return leg)",
        "value": False,
    },
}

def make_model() -> BuildingHandoffModel:
    """A fresh H0 model for one browser session.

    The config is loaded per call too — a shared config object would be another
    piece of module-level state travelling between kernels.
    """
    return BuildingHandoffModel(
        mode=HandoffMode.H0_DIRECT,
        config=load_config(ROOT / "configs" / "baseline_10f.yaml"),
        scenario_path=_DEFAULT_SCENARIO,
        rng_seed=42,
        dynamic_pool=True,
        floor_profile=_DEFAULT_FLOOR_PROFILE,
    )


@solara.component
def Page():
    """Per-kernel root: `use_memo` keeps one model per browser session, built on
    first render and reused across re-renders (see the module docstring for why
    a module-level model breaks after a refresh)."""
    model = solara.use_memo(make_model, dependencies=[])
    build_solara_app(model, model_params=model_params)


page = Page()
