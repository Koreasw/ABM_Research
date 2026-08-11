"""Tests for analysis.scenario_tiers (etc/plan_h0_revision.md §1.4, §3 R5).

Pins the user-confirmed tier boundaries and their file counts, a round-trip
over data/data1, and -- the single most important invariant of this step --
that the verification battery scripts resolve their scenario set through the
tier module and run the 28-file modelling corpus.

REGIME CHANGE (사용자 확정 2026-08-03, 2차 — this file was rewritten for it):
K500/K750/K1000 (11 files) are held out from the modelling
corpus. Consequences pinned below:
  * the 'hold' tier is gone; asking for it raises ValueError,
  * 'extreme' is K300 alone (8 files) and 'all' is 20 + 8 = 28,
  * `excluded` is NOT a tier -- it is outside TIER_CHOICES and unreachable
    from any CLI flag; only excluded_paths()/is_excluded_k() see it,
  * the battery scripts, which under the old regime were forbidden from
    importing this module (they globbed all 39 files for regression reach),
  * are now *required* to import it. That guard is inverted here, not deleted.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from analysis.scenario_tiers import (
    DATA_DIR,
    EXCLUDED,
    TIER_CHOICES,
    TIER_NAMES,
    excluded_k_levels,
    excluded_paths,
    is_excluded,
    is_excluded_k,
    k_levels,
    k_of,
    scenario_paths,
    scenario_stems,
    tier_of_k,
    tier_of_scenario,
)

ROOT = Path(__file__).resolve().parent.parent

# Scripts that must enumerate the whole 28-file modelling corpus (plan §1.4:
# "배터리도 28개 코퍼스를 쓴다"), resolved via analysis.scenario_tiers.
CORPUS_SCRIPTS = [
    ROOT / "experiments" / "vv_all39.py",
    ROOT / "analysis" / "vv_data_integrity.py",
    ROOT / "analysis" / "vv_decomp.py",
    ROOT / "analysis" / "vv_face.py",
    ROOT / "analysis" / "vv_map5_audit.py",
    ROOT / "analysis" / "vv_balance.py",      # W5c, added 2026-08-04
]

# Verification-battery scripts that run a representative subset instead of the
# whole corpus. They must not name an excluded scenario as a representative.
SUBSET_SCRIPTS = [
    ROOT / "experiments" / "vv_monotonicity.py",
    ROOT / "experiments" / "vv_variance.py",
    ROOT / "experiments" / "vv_window_bias.py",
    ROOT / "analysis" / "vv_evsel.py",
    # R8 / V21-NEW, added 2026-08-06. HANDOFF_r8_step78 §3.3 asked for these two
    # in CORPUS_SCRIPTS, but that guard demands a literal "== 28" corpus-count
    # assertion plus a scenario_tiers import — neither script sweeps the corpus
    # (the head sweep is 7 levels x 8 seeds, the window comparison needs the
    # long legacy arm), so they are representative-subset scripts and belong to
    # the guard that actually protects stem-naming.
    ROOT / "experiments" / "vv_warmup_bias.py",
    ROOT / "experiments" / "vv_window_compare.py",
]

# The representative low/mid/high triplet after K1000_1 left the corpus
# (plan_h0v2_verification.md §0.4-3: keep three ascending K levels).
REPRESENTATIVE_TRIPLET = ["K50_1", "K200_1", "K300_4"]


# --------------------------------------------------------------------- yaml

def test_tier_names_and_choices() -> None:
    """'hold' is gone and 'excluded' was never a tier -- neither is selectable."""
    assert TIER_NAMES == ("primary", "extreme")
    assert TIER_CHOICES == ("primary", "extreme", "all")
    assert EXCLUDED not in TIER_CHOICES


def test_tier_k_levels_pinned() -> None:
    """User-confirmed (2026-08-03, 2차) tier -> K-level mapping. Do not relitigate."""
    assert k_levels("primary") == [50, 100, 200]
    assert k_levels("extreme") == [300]
    assert k_levels("all") == [50, 100, 200, 300]


def test_excluded_k_levels_pinned() -> None:
    """K500/K750/K1000 are held out of the corpus for this study."""
    assert excluded_k_levels() == [500, 750, 1000]
    for k in (500, 750, 1000):
        assert is_excluded_k(k)
    for k in (50, 100, 200, 300):
        assert not is_excluded_k(k)
    assert is_excluded("K750_1")
    assert not is_excluded("K300_4")


def test_hold_tier_no_longer_exists() -> None:
    """The former 'hold' tier (K750/K1000) is not requestable by any name."""
    with pytest.raises(ValueError):
        k_levels("hold")
    with pytest.raises(ValueError):
        scenario_paths("hold")


def test_excluded_is_not_reachable_as_a_tier() -> None:
    """Excluded scenarios must not be obtainable through the tier API."""
    with pytest.raises(ValueError):
        k_levels(EXCLUDED)
    for tier in TIER_CHOICES:
        for k in k_levels(tier):
            assert not is_excluded_k(k)


def test_unknown_tier_raises() -> None:
    with pytest.raises(ValueError):
        k_levels("nope")
    with pytest.raises(ValueError):
        tier_of_k(999)


# ------------------------------------------------------------------- k_of

def test_k_of_parses_stem_and_path() -> None:
    assert k_of("K300_4") == 300
    assert k_of("K300_4.json") == 300
    assert k_of(DATA_DIR / "K50_1.json") == 50
    assert k_of("K1000_5") == 1000


def test_k_of_rejects_non_k_stems() -> None:
    with pytest.raises(ValueError):
        k_of("STAGE3_1")


def test_tier_of_scenario() -> None:
    assert tier_of_scenario("K50_1") == "primary"
    assert tier_of_scenario("K200_9") == "primary"
    assert tier_of_scenario("K300_1") == "extreme"
    # Excluded files still parse and still classify -- as EXCLUDED, so callers
    # that meet a stray K500/K750/K1000 path get a meaningful answer instead of
    # a crash or a silent tier membership.
    assert tier_of_scenario("K500_5") == EXCLUDED
    assert tier_of_scenario("K750_1") == EXCLUDED
    assert tier_of_scenario("K1000_5") == EXCLUDED


# --------------------------------------------------------------- file counts

@pytest.mark.skipif(not DATA_DIR.exists(), reason="data/data1 not present")
def test_tier_file_counts() -> None:
    """Pinned counts (plan §1.4): primary 20, extreme 8, corpus 28."""
    assert len(scenario_paths("primary")) == 20
    assert len(scenario_paths("extreme")) == 8
    assert len(scenario_paths("all")) == 28


@pytest.mark.skipif(not DATA_DIR.exists(), reason="data/data1 not present")
def test_excluded_file_count() -> None:
    """11 excluded files: K500 5 + K750 1 + K1000 5 (plan §1.4)."""
    assert len(excluded_paths()) == 11


@pytest.mark.skipif(not DATA_DIR.exists(), reason="data/data1 not present")
def test_corpus_file_counts_by_k_level() -> None:
    """K50=2, K100=9, K200=9, K300=8 -> 28 in corpus (plan §1.4)."""
    expected = {50: 2, 100: 9, 200: 9, 300: 8}
    assert sum(expected.values()) == 28
    for k, n in expected.items():
        paths = [p for p in scenario_paths("all") if k_of(p) == k]
        assert len(paths) == n, f"K{k}: expected {n} corpus files, found {len(paths)}"


@pytest.mark.skipif(not DATA_DIR.exists(), reason="data/data1 not present")
def test_excluded_file_counts_by_k_level() -> None:
    """K500=5, K750=1, K1000=5 -> 11 excluded. On disk but out of scope."""
    expected = {500: 5, 750: 1, 1000: 5}
    assert sum(expected.values()) == 11
    for k, n in expected.items():
        paths = [p for p in excluded_paths() if k_of(p) == k]
        assert len(paths) == n, f"K{k}: expected {n} excluded files, found {len(paths)}"


# ---------------------------------------------------------------- round trip

@pytest.mark.skipif(not DATA_DIR.exists(), reason="data/data1 not present")
def test_every_scenario_is_in_exactly_one_tier_or_excluded() -> None:
    """All 39 files on disk resolve to exactly one tier OR to excluded.

    The v1 invariant was "exactly one tier" over 39 files; with 11 files now
    outside the corpus the partition has a second half, and the point of the
    test is that nothing falls between the two (an unlisted K level raises in
    tier_of_k, which would surface here as an error).
    """
    all_k_files = sorted(DATA_DIR.glob("K*.json"))
    assert len(all_k_files) == 39
    for p in all_k_files:
        memberships = [name for name in TIER_NAMES if k_of(p) in k_levels(name)]
        if is_excluded(p):
            assert memberships == [], f"{p.name} is excluded but also in {memberships}"
            assert tier_of_scenario(p) == EXCLUDED
        else:
            assert len(memberships) == 1, (
                f"{p.name} belongs to {memberships}, expected exactly 1"
            )


@pytest.mark.skipif(not DATA_DIR.exists(), reason="data/data1 not present")
def test_tiers_and_excluded_partition_the_data_dir_disjointly() -> None:
    primary = set(scenario_stems("primary"))
    extreme = set(scenario_stems("extreme"))
    excluded = {p.stem for p in excluded_paths()}
    corpus = set(scenario_stems("all"))

    assert primary & extreme == set()
    assert primary & excluded == set()
    assert extreme & excluded == set()
    assert primary | extreme == corpus
    assert corpus & excluded == set()
    assert corpus | excluded == {p.stem for p in DATA_DIR.glob("K*.json")}


@pytest.mark.skipif(not DATA_DIR.exists(), reason="data/data1 not present")
def test_scenario_paths_excludes_non_k_files() -> None:
    """STAGE3_*.json and friends are never part of the tier system."""
    for tier in TIER_CHOICES:
        for p in scenario_paths(tier):
            assert p.stem.startswith("K")


# ---------------------------------------------------- verification battery

def test_verification_battery_uses_28_scenario_corpus() -> None:
    """The corpus-wide battery scripts run 28 scenarios, not a raw 39-file glob.

    Inverted guard: under the pre-2026-08-03 regime these scripts were pinned
    to `glob("K*.json")` + `== 39` so that regression reach stayed maximal.
    The exclusion is permanent now, so the battery must not run out-of-scope
    demand at all. Checked at the source level (running the batteries costs
    real simulation time) -- each script must carry a 28-count expectation and
    must not carry a stale 39-count assertion.
    """
    for path in CORPUS_SCRIPTS:
        assert path.exists(), path
        src = path.read_text(encoding="utf-8")
        assert "== 28" in src, f"{path}: lost its 28-scenario corpus expectation"
        assert "== 39" not in src, f"{path}: still asserts the stale 39-file count"


def test_verification_battery_imports_scenario_tiers() -> None:
    """Inverted R5 constraint: the battery's corpus IS the tier module's corpus.

    plan §1.4 (2차 확정): "배터리는 이제 이 파일을 정본으로 참조해야 하며,
    data/data1를 직접 glob 해 39개를 세는 코드는 전부 오류다." The old test
    asserted the exact opposite ("scenario_tiers" must not appear); it is
    inverted rather than dropped so the reversal stays visible in the suite.
    """
    for path in CORPUS_SCRIPTS:
        assert path.exists(), path
        src = path.read_text(encoding="utf-8")
        assert "scenario_tiers" in src, (
            f"{path}: must resolve its scenario set through analysis.scenario_tiers "
            "-- a raw data/data1 glob would silently re-admit K500/K750/K1000"
        )


@pytest.mark.skipif(not DATA_DIR.exists(), reason="data/data1 not present")
def test_battery_subset_scripts_use_in_corpus_representatives() -> None:
    """Representative-subset scripts must not name an excluded scenario.

    These scripts pick 3 scenarios by stem rather than sweeping the corpus, so
    the tier module cannot protect them -- the stems are checked directly.
    """
    for stem in REPRESENTATIVE_TRIPLET:
        assert not is_excluded(stem), stem
        assert (DATA_DIR / f"{stem}.json").exists(), stem
    # ascending K: a monotonicity ladder, not just three arbitrary files
    ks = [k_of(s) for s in REPRESENTATIVE_TRIPLET]
    assert ks == sorted(ks) and len(set(ks)) == 3

    excluded_stems = {p.stem for p in excluded_paths()}
    for path in SUBSET_SCRIPTS:
        assert path.exists(), path
        src = path.read_text(encoding="utf-8")
        for stem in excluded_stems:
            assert f'"{stem}"' not in src, (
                f"{path}: names excluded scenario {stem} as a representative"
            )


# ------------------------------------------------------- analysis runners

def test_h0_descriptive_defaults_to_primary_tier() -> None:
    from experiments.h0_descriptive import DEFAULT_TIER as h0d_default

    assert h0d_default == "primary"


def test_h0_baseline_stats_defaults_to_primary_tier() -> None:
    from analysis.h0_baseline_stats import DEFAULT_TIER as stats_default

    assert stats_default == "primary"


@pytest.mark.skipif(not DATA_DIR.exists(), reason="data/data1 not present")
def test_h0_descriptive_scenario_stems_honor_tier() -> None:
    """experiments.h0_descriptive.scenario_stems(tier) == scenario_tiers, exactly.

    The old K1000_5 duplicate exclusion that used to sit between the two is
    gone: K1000 is out of corpus, so the byte-clone pair is unreachable and
    the two stem sets are now equal for every tier.
    """
    from experiments.h0_descriptive import scenario_stems as h0d_stems

    for tier in TIER_CHOICES:
        assert set(h0d_stems(tier)) == set(scenario_stems(tier)), tier
    assert len(h0d_stems("all")) == 28


def test_h0_descriptive_has_no_stale_duplicate_exclusion() -> None:
    """The module-level EXCLUDED={'K1000_5'} set must be gone (plan §1.4)."""
    import experiments.h0_descriptive as h0d

    assert not hasattr(h0d, "EXCLUDED")
