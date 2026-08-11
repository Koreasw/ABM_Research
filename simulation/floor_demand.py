"""Profile-based floor demand — etc/demand_mapping.md 단계 2·3 (2026-07-10 확정).

Destination floors are an independent categorical draw from a building
population-density profile, fully decoupled from the 2D city data (which,
per demand_mapping.md 단계 1, only drives arrival timing and external travel
time). This supersedes the distance-band mapping files (v4/v5) on the paper
track; those remain frozen regression paths.

RNG convention (per-order, call-order independent, independently re-derivable):

    rng = np.random.default_rng([FLOOR_STREAM_TAG, floor_seed, ord_id])
    u = rng.random()                    # draw 1: floor inverse-CDF
    floor = 2 + searchsorted(cum, u, side="right")
    office = rng.integers(0, offices_per_floor)   # draw 2: office uniform

Exactly two draws, floor first — changing the draw order or count breaks
bit-reproducibility of every recorded assignment. `Generator.choice(p=...)`
is deliberately NOT used: its internal draw count is a numpy implementation
detail, so verifiers could not re-derive assignments independently.

Stream-family separation: existing per-order streams are 1-word seeds
(`mode_seed XOR ord_id`, vertical_transport) and 2-word seeds
(`[rng_seed, ord_id]`, arrival noise). This module uses a 3-word seed
`[FLOOR_STREAM_TAG, floor_seed, ord_id]`, so the seeded states cannot
coincide with either family. Trap the tag prevents: a naive
`default_rng(uint64(floor_seed) ^ uint64(ord_id))` with floor_seed=42 would
be bit-identical to the mode stream (mode_seed=42) — floor and vertical-mode
draws would be perfectly correlated.

CRN property (documented feature, framework §7.1): at a fixed floor_seed the
same per-order u is inverted through each profile's CDF, so floors are
monotonically coupled across profiles (a top-heavier profile never yields a
lower floor for the same order). Useful for low-variance profile contrasts.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from simulation.vertical_transport import VerticalTransportModel

FLOOR_STREAM_TAG = 0x666C6F72  # ascii 'flor' — SeedSequence domain tag (see module docstring)


@dataclass(frozen=True)
class FloorDemandModel:
    profile: str
    probs: tuple[float, ...]        # normalized in __post_init__; probs[0] <-> floor 2
    n_floors: int
    offices_per_floor: int
    floor_seed: int
    _cum: tuple[float, ...] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.n_floors < 2:
            raise ValueError(f"n_floors must be >= 2, got {self.n_floors}")
        if self.offices_per_floor < 1:
            raise ValueError(f"offices_per_floor must be >= 1, got {self.offices_per_floor}")
        if int(self.floor_seed) < 0:
            raise ValueError(f"floor_seed must be a non-negative int, got {self.floor_seed}")
        n_office_floors = self.n_floors - 1
        weights = tuple(float(w) for w in self.probs)
        if len(weights) != n_office_floors:
            raise ValueError(
                f"profile {self.profile!r} has {len(weights)} weights, "
                f"expected {n_office_floors} (floors 2..{self.n_floors})"
            )
        if any(not math.isfinite(w) for w in weights):
            raise ValueError(f"profile {self.profile!r} has non-finite weight(s): {weights}")
        if any(w < 0.0 for w in weights):
            raise ValueError(f"profile {self.profile!r} has negative weight(s): {weights}")
        total = sum(weights)
        if total <= 0.0:
            raise ValueError(f"profile {self.profile!r} weights sum to {total}; must be > 0")
        normalized = tuple(w / total for w in weights)
        cum = np.cumsum(normalized)
        cum[-1] = 1.0  # pin against fp drift so u < 1 can never fall past the last floor
        object.__setattr__(self, "probs", normalized)
        object.__setattr__(self, "_cum", tuple(float(c) for c in cum))

    @property
    def floors(self) -> tuple[int, ...]:
        """Office floors covered by the profile: (2, ..., n_floors)."""
        return tuple(range(2, self.n_floors + 1))

    def expected_share(self, floor: int) -> float:
        """Normalized demand share of `floor` (charts / conformance tests)."""
        if not 2 <= floor <= self.n_floors:
            raise ValueError(f"floor must be in 2..{self.n_floors}, got {floor}")
        return self.probs[floor - 2]

    def sample(self, ord_id: int) -> tuple[int, int]:
        """(floor, office_id) for one order — the two-draw convention above.

        Fresh Generator per ord_id: reproducible bit-for-bit from
        (floor_seed, ord_id, probs) regardless of call order.
        """
        rng = np.random.default_rng([FLOOR_STREAM_TAG, self.floor_seed, int(ord_id)])
        u = rng.random()
        idx = int(np.searchsorted(np.asarray(self._cum), u, side="right"))
        floor = min(2 + idx, self.n_floors)
        office = int(rng.integers(0, self.offices_per_floor))
        return floor, office

    @classmethod
    def from_config(
        cls, config: dict[str, Any], profile: str | None = None, *, floor_seed: int
    ) -> FloorDemandModel:
        """Build from a parsed config; profile=None uses demand.default_profile."""
        demand = config.get("demand")
        if not demand:
            raise ValueError(
                "config has no 'demand' block — define demand.floor_profiles "
                "(see configs/baseline_10f.yaml and etc/demand_mapping.md 단계 3)"
            )
        profiles = demand.get("floor_profiles") or {}
        name = profile if profile is not None else demand.get("default_profile")
        if name not in profiles:
            raise ValueError(
                f"unknown floor profile {name!r}; available: {sorted(profiles)}"
            )
        b = config["building"]
        return cls(
            profile=name,
            probs=tuple(float(w) for w in profiles[name]),
            n_floors=int(b["n_floors"]),
            offices_per_floor=int(b["n_offices_per_floor"]),
            floor_seed=int(floor_seed),
        )


def rederive_profile_assignment(
    config: dict[str, Any],
    profile: str,
    floor_seed: int,
    ord_ids: Iterable[int],
) -> dict[int, tuple[int, int, str]]:
    """(floor, office_id, vertical_mode) per ord_id from provenance alone.

    Reconstructs profile-mode assignments using only what a results JSON
    records (floor_profile, floor_seed) plus the config — no simulation
    state. Consumed by tests now and by analysis/verify_h0.py's A9
    floor-profile conformance check later (etc/plan_h0_verification.md).
    vertical_mode reuses VerticalTransportModel.sample_mode(ord_id, floor),
    whose mode_seed XOR ord_id stream is untouched by this module.
    """
    fd = FloorDemandModel.from_config(config, profile, floor_seed=floor_seed)
    vt = VerticalTransportModel.from_config(config)
    out: dict[int, tuple[int, int, str]] = {}
    for oid in ord_ids:
        floor, office = fd.sample(int(oid))
        out[int(oid)] = (floor, office, vt.sample_mode(int(oid), floor))
    return out
