# abm-handoff

Agent-Based Simulation of Robot-Mediated Lobby Handoff in Smart Buildings.

See [`research_framework_handoff.md`](research_framework_handoff.md) for the
full research plan (RQ, data calibration, agent design, experiments, V&V).

## Setup (uv + Python 3.13)

```bash
uv venv                          # creates .venv/ using .python-version
uv pip install -e ".[dev]"       # install package + dev tools
source .venv/bin/activate        # (optional) activate
```

## Project layout

```
analysis/      STAGE 1 — data loading, demand model, rider arrival synthesis
simulation/    STAGE 2-3 — Mesa ABM (8 agents, 4 handoff modes)
experiments/   STAGE 4 — E1-E6 + V&V + sensitivity (Morris/Sobol)
configs/       YAML configs (baseline, modes h0-h3, scenarios, sensitivity)
tests/         pytest regression suite
data/          BaeMin source data (git-ignored; expected externally)
paper/         STAGE 5 — figures, tables for SCIE submission
notebooks/     Exploratory analysis
```

## Data

The BaeMin source data (`data/data1/`, `data/data2/`, `data/data_ex.txt`)
is git-ignored due to size (~919 MB). Place locally before running STAGE 1.

## Target journal

Simulation Modelling Practice and Theory (IF ~4.0).
