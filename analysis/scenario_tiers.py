"""Demand-scenario tiers (etc/plan_h0_revision.md §1.4, §3 R5).

Single source of truth: configs/scenario_tiers.yaml. This module only reads
that file and offers small lookup helpers -- the tier -> K-level mapping is
data, not code, so changing the tier boundaries never requires touching this
file (or plan_h0_revision.md's §1.4 assertions about it).

    primary (1차)  = K50, K100, K200  -> 20 scenarios. Default for analysis
                      and reporting outputs.
    extreme (극단) = K300             -> 8 scenarios. Extreme-case analysis,
                      run after the primary tier.
    all            = the modelling corpus, 20 + 8 = 28 scenarios.

    excluded       = K500, K750, K1000 -> 11 scenarios. **Held out of this
                      study** (사용자 확정 2026-08-04). Not a tier: excluded
                      scenarios are not in `all`, are not analysed, and are
                      not exercised by the verification battery either.

IMPORTANT -- this changed on 2026-08-03. The battery previously used a raw
`data/data1/K*.json` glob (39 files) and deliberately did not import this
module. Now that K500/K750/K1000 are held out, **the battery uses
the same 28-scenario corpus** and must resolve it through here. Any code that
globs data/data1 directly and expects 39 is now wrong (plan §1.4).

Statistical-reporting caveat (plan §1.4, §7 risk 2): K50 has only 2 scenario
files, so it is not statistically representative on its own. Reporting over
the primary tier should center on K100/K200, with K50 noted as a low-demand
reference point.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
TIERS_YAML = ROOT / "configs" / "scenario_tiers.yaml"
DATA_DIR = ROOT / "data" / "data1"

# Tier names in analysis-pipeline order (primary first). "all" is not a real
# tier bucket -- it means "no tier filter, use the whole modelling corpus"
# (28 scenarios, excluded ones still omitted) and is accepted everywhere a
# tier name is accepted (CLI flags, scenario_paths()).
TIER_NAMES: tuple[str, ...] = ("primary", "extreme")
TIER_CHOICES: tuple[str, ...] = (*TIER_NAMES, "all")
# Returned by tier_of_k/tier_of_scenario for K levels held out of this study.
# Deliberately NOT in TIER_NAMES or TIER_CHOICES: it is not selectable, so no
# runner can be pointed at the excluded scenarios by passing a flag.
EXCLUDED: str = "excluded"


@lru_cache(maxsize=1)
def _load_tiers() -> dict[str, list[int]]:
    """Parse configs/scenario_tiers.yaml -> {tier_name: [K levels]}."""
    raw = yaml.safe_load(TIERS_YAML.read_text())
    tiers = {name: sorted(spec["k_levels"]) for name, spec in raw["tiers"].items()}
    missing = set(TIER_NAMES) - set(tiers)
    if missing:
        raise ValueError(f"{TIERS_YAML} is missing tier(s): {sorted(missing)}")
    extra = set(tiers) - set(TIER_NAMES)
    if extra:
        raise ValueError(
            f"{TIERS_YAML} declares unknown tier(s) {sorted(extra)}; excluded K "
            f"levels belong under the top-level 'excluded:' key, not 'tiers:'"
        )
    overlap = set(tiers_flat(tiers)) & set(excluded_k_levels())
    if overlap:
        raise ValueError(
            f"K level(s) {sorted(overlap)} are both in a tier and excluded"
        )
    return tiers


def tiers_flat(tiers: dict[str, list[int]]) -> list[int]:
    """All K levels across the given tier mapping."""
    return [k for levels in tiers.values() for k in levels]


@lru_cache(maxsize=1)
def excluded_k_levels() -> list[int]:
    """K levels held out of the modelling corpus for this study.

    사용자 확정 2026-08-03: K500/K750/K1000. These are not a tier -- they are
    outside the study's demand range entirely, so they appear in no tier, are
    absent from `all`, and are not run by the verification battery.
    """
    raw = yaml.safe_load(TIERS_YAML.read_text())
    return sorted(raw.get("excluded", {}).get("k_levels", []))


def is_excluded_k(k: int) -> bool:
    """True if K level `k` is out of scope for this study."""
    return k in excluded_k_levels()


def is_excluded(stem_or_path: str | Path) -> bool:
    """True if a scenario stem/path is out of scope for this study."""
    return is_excluded_k(k_of(stem_or_path))


def excluded_paths(data_dir: Path | None = None) -> list[Path]:
    """Sorted K*.json paths that are held out (for audits/tests)."""
    d = data_dir if data_dir is not None else DATA_DIR
    out = []
    for p in sorted(d.glob("K*.json")):
        try:
            k = k_of(p)
        except ValueError:
            continue
        if is_excluded_k(k):
            out.append(p)
    return out


def k_levels(tier: str) -> list[int]:
    """K levels belonging to `tier` (TIER_CHOICES: 'primary' | 'extreme' | 'all').

    The former 'hold' tier (K750/K1000) no longer exists -- those levels are
    held out (사용자 확정 2026-08-03 2차), so asking for it raises.
    """
    if tier == "all":
        return sorted(k for levels in _load_tiers().values() for k in levels)
    tiers = _load_tiers()
    if tier not in tiers:
        raise ValueError(f"unknown tier {tier!r}; expected one of {TIER_CHOICES}")
    return list(tiers[tier])


def k_of(stem_or_path: str | Path) -> int:
    """Parse the nominal K level from a scenario stem or path.

    'K300_4' -> 300, 'K300_4.json' -> 300, Path('.../K50_1.json') -> 50.
    Raises ValueError for non-K-prefixed stems (e.g. STAGE3_1 -- not part of
    the tier system).
    """
    stem = Path(stem_or_path).stem
    head = stem.split("_")[0]
    if not head.startswith("K") or not head[1:].isdigit():
        raise ValueError(f"cannot parse a K level from scenario stem {stem!r}")
    return int(head[1:])


def tier_of_k(k: int) -> str:
    """Tier name owning K level `k`, or EXCLUDED if out of scope for this study.

    Raises ValueError only for a K level that is neither -- i.e. data that the
    tier file has never been told about, which is a config gap, not a policy.
    """
    for name, levels in _load_tiers().items():
        if k in levels:
            return name
    if is_excluded_k(k):
        return EXCLUDED
    raise ValueError(
        f"K{k} is in no tier and not listed as excluded ({TIERS_YAML})"
    )


def tier_of_scenario(stem_or_path: str | Path) -> str:
    """Tier name owning a scenario stem/path, via its parsed K level."""
    return tier_of_k(k_of(stem_or_path))


def scenario_paths(tier: str = "primary", data_dir: Path | None = None) -> list[Path]:
    """Sorted K*.json paths under `data_dir` belonging to `tier`.

    `tier='all'` returns the whole modelling corpus (28 scenarios) -- this is
    also the verification battery's scenario set. Held-out K
    levels (K500/K750/K1000) are never returned by any tier including 'all';
    use excluded_paths() if you specifically need them. STAGE3_*.json and
    other non-K-prefixed files are never included, tier or no tier.
    """
    levels = set(k_levels(tier))
    d = data_dir if data_dir is not None else DATA_DIR
    paths = []
    for p in sorted(d.glob("K*.json")):
        try:
            k = k_of(p)
        except ValueError:
            continue
        if k in levels:
            paths.append(p)
    return paths


def scenario_stems(tier: str = "primary", data_dir: Path | None = None) -> list[str]:
    """Sorted scenario stems (e.g. 'K100_3') belonging to `tier`."""
    return [p.stem for p in scenario_paths(tier, data_dir)]
