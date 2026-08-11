"""Typed, validated accessors for the Phase A config blocks (Step A0).

Why this module exists
----------------------
Before Step A0 the ``robot:`` block in ``configs/baseline_10f.yaml`` was read by
**nothing** (``grep -rn 'cfg\\["robot"\\]'`` -> 0 hits), ``configs/modes/*.yaml``
was read by **nothing**, and ``run.py`` hardcoded ``mode=H0_DIRECT``. The design
freeze's handoff sigma (R0-3, ``N(60, 15^2)``) lived only in an unloaded file.
So H1 had to invent its own parameter plumbing anyway; doing it here, once,
keeps `model.py` from growing three ad-hoc ``cfg.get(...)`` chains and gives
A1/A2 a single import.

Contract with the H0 verification battery
-----------------------------------------
**Every block here is optional and every default reproduces pre-A0 behaviour.**
That is not politeness, it is the frozen-regression contract:
``configs/regression_nobasement_10f.yaml`` carries the *old* robot block and no
``handoff``/``ped_decay`` at all, and
``test_h0_frozen_snapshot.py::test_nobasement_replay_matches_pre_basement_snapshot``
replays it against ``results/pre_basement/``. A required key here would make that
gate permanently red.

``PedDecay`` is the only one of the three that H0 can *touch*, so read its
docstring before changing it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# R0-3: 'hoff' as a 4-byte tag — the 4th 3-word stream family of the P3
# stream-family convention. Kept here so A2 does not re-derive the literal.
DEFAULT_HANDOFF_RNG_TAG = 0x686F6666


def _num(block: dict[str, Any], key: str, default: float) -> float:
    v = block.get(key, default)
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        raise ValueError(f"{key} must be a number; got {v!r}")
    return float(v)


@dataclass(frozen=True)
class BatteryParams:
    """Robot battery/charging (결정 #26, 사용자 확정 2026-08-06).

    This *reverses* design-freeze R0-5 ("충전 비활성") and decision #19
    ("충전 사이클 미모델링"). The reversal is deliberate and is recorded as
    decision #26; `plan_hr_extension.md` §2 R0-5 and `research_plan_scie.md`
    §1 #19 / §8 (limitations) are updated to match.

    Sizing note, so nobody reports the inert threshold as a bug: at 1,300 Wh
    with these rates a robot survives ~21.7 h of pure idling or ~9,286 m of
    travel, while one delivery costs ~9-10 Wh. Over a lunch-peak run the SOC
    lands at 43~90 % depending on drain length, so `soc_low_pct` is **not
    expected to fire in the corpus**. The two paths that do exercise it are
    (a) synthetic unit tests and (b) the Phase E `soc_init_pct` sweep.
    """

    capacity_wh: float
    wh_per_m: float
    wh_per_min_idle: float
    charge_wh_per_min: float
    soc_low_pct: float
    soc_resume_pct: float
    soc_init_pct: float

    @staticmethod
    def from_block(block: dict[str, Any] | None) -> BatteryParams:
        b = block or {}
        p = BatteryParams(
            capacity_wh=_num(b, "capacity_wh", 1300.0),
            wh_per_m=_num(b, "wh_per_m", 0.14),
            wh_per_min_idle=_num(b, "wh_per_min_idle", 1.0),
            charge_wh_per_min=_num(b, "charge_wh_per_min", 13.0),
            soc_low_pct=_num(b, "soc_low_pct", 20.0),
            soc_resume_pct=_num(b, "soc_resume_pct", 40.0),
            soc_init_pct=_num(b, "soc_init_pct", 100.0),
        )
        if p.capacity_wh <= 0:
            raise ValueError(f"battery.capacity_wh must be > 0; got {p.capacity_wh}")
        if p.wh_per_m < 0 or p.wh_per_min_idle < 0:
            raise ValueError("battery drain rates must be >= 0")
        if p.charge_wh_per_min <= 0:
            raise ValueError(
                f"battery.charge_wh_per_min must be > 0; got {p.charge_wh_per_min}"
            )
        # A robot that resumes at or below its cut-off would leave the dock and
        # immediately re-trigger -> a charge/dispatch loop that never delivers.
        if not 0.0 <= p.soc_low_pct < p.soc_resume_pct <= 100.0:
            raise ValueError(
                "battery SOC thresholds must satisfy "
                f"0 <= soc_low_pct ({p.soc_low_pct}) < soc_resume_pct "
                f"({p.soc_resume_pct}) <= 100"
            )
        if not 0.0 < p.soc_init_pct <= 100.0:
            raise ValueError(
                f"battery.soc_init_pct must be in (0, 100]; got {p.soc_init_pct}"
            )
        return p

    @property
    def wh_per_sec_idle(self) -> float:
        return self.wh_per_min_idle / 60.0

    @property
    def charge_wh_per_sec(self) -> float:
        return self.charge_wh_per_min / 60.0

    def wh_for_soc_pct(self, pct: float) -> float:
        return self.capacity_wh * pct / 100.0


@dataclass(frozen=True)
class RobotParams:
    """`robot:` block. H0 builds no robots, so this is inert on the paper track
    — `tests/test_a0_config_wiring.py` pins that by mutating the block and
    asserting the H0 result stays bit-identical."""

    n_robots: int
    capa: int
    speed_mps: float
    service_time_drop_sec: float
    service_time_pickup_sec_h3: float
    battery: BatteryParams

    @staticmethod
    def from_config(cfg: dict[str, Any]) -> RobotParams:
        b = cfg.get("robot") or {}
        n = b.get("n_robots", 5)
        if not isinstance(n, int) or isinstance(n, bool) or n < 1:
            raise ValueError(f"robot.n_robots must be an int >= 1; got {n!r}")
        capa = b.get("capa", 100)
        if not isinstance(capa, int) or isinstance(capa, bool) or capa < 1:
            raise ValueError(f"robot.capa must be an int >= 1; got {capa!r}")
        p = RobotParams(
            n_robots=n,
            capa=capa,
            speed_mps=_num(b, "speed_mps", 1.0),
            service_time_drop_sec=_num(b, "service_time_drop_sec", 30.0),
            service_time_pickup_sec_h3=_num(b, "service_time_pickup_sec_h3", 15.0),
            battery=BatteryParams.from_block(b.get("battery")),
        )
        if p.speed_mps <= 0:
            raise ValueError(f"robot.speed_mps must be > 0; got {p.speed_mps}")
        if p.service_time_drop_sec < 0 or p.service_time_pickup_sec_h3 < 0:
            raise ValueError("robot service times must be >= 0")
        return p


@dataclass(frozen=True)
class HandoffParams:
    """`handoff:` block — design freeze R0-3, ``N(60, 15^2)`` 0-truncated.

    Pre-A0 these lived in `configs/modes/h1_sync.yaml`, which no code read.
    """

    service_mean_sec: float
    service_sd_sec: float
    rng_stream_tag: int

    @staticmethod
    def from_config(cfg: dict[str, Any]) -> HandoffParams:
        b = cfg.get("handoff") or {}
        tag = b.get("rng_stream_tag", DEFAULT_HANDOFF_RNG_TAG)
        if not isinstance(tag, int) or isinstance(tag, bool) or tag < 0:
            raise ValueError(
                f"handoff.rng_stream_tag must be a non-negative int; got {tag!r}"
            )
        p = HandoffParams(
            service_mean_sec=_num(b, "service_mean_sec", 60.0),
            service_sd_sec=_num(b, "service_sd_sec", 15.0),
            rng_stream_tag=tag,
        )
        if p.service_mean_sec < 0 or p.service_sd_sec < 0:
            raise ValueError("handoff service mean/sd must be >= 0")
        return p


@dataclass(frozen=True)
class PedDecay:
    """Post-lunch-peak decay of the background pedestrian stream (결정 10).

    **Why**: R8's `delivery` policy spawns background pedestrians until the run
    ends, with no cutoff (clipping the tail biases the late orders, W_EV -28 %).
    That is fine for H0, whose runs are ~7,700 ticks. Robot modes drain far
    longer (K300 ~27,000 ticks), and holding the *lunch-peak* rate of 7.5/min
    for 7.5 h is both unphysical (900 residents x 30 trips/day) and destroys
    cross-mode comparability: H0 K300 sees ~960 pedestrians, H1 K300 would see
    ~3,375.

    **Why it cannot perturb H0** — two independent reasons, either sufficient:

    1. `start_sec` is `last order + start_after_last_order_sec`, and the default
       `start_after_last_order_sec` (7200) equals H0's `max_overrun_sec`. H0's
       cap is `last order + max_overrun_sec`, so H0 terminates *at* `start_sec`
       at the very latest. Combined with the **strict** ``t > start_sec`` test
       in :meth:`rate_per_sec_at`, an H0 run can never be in the decayed regime.
       `tests/test_a0_ped_decay.py` pins `cap_time_sec <= ped_decay.start_sec`.
    2. The decay changes only the *value* of the Poisson rate, never the RNG
       call pattern: `model._spawn_pedestrians` draws `ped_rng.poisson(rate*dt)`
       exactly once per tick regardless of the rate. Before `start_sec` the rate
       is unchanged, so the draw — and every draw it gates — is bit-identical.

    Absent block => ``None`` => the stream is a flat Poisson exactly as before,
    which is what keeps `configs/regression_nobasement_10f.yaml` frozen.
    """

    start_sec: float
    ramp_sec: float
    floor_rate_per_sec: float
    peak_rate_per_sec: float

    @staticmethod
    def from_config(
        cfg: dict[str, Any],
        *,
        last_order_abs_sec: float | None,
        peak_rate_per_sec: float,
    ) -> PedDecay | None:
        block = (cfg.get("simulation") or {}).get("ped_decay")
        if block is None:
            return None
        if last_order_abs_sec is None:
            # No orders => no anchor for the decay. The run is bounded by the
            # background window instead, so a decay would have nothing to mean.
            return None
        if peak_rate_per_sec <= 0.0:
            # No background stream to decay. This is not a corner case to
            # tolerate — `pedestrian.arrival_rate_per_min: 0` is the standard
            # golden-path / extreme-test setup in this repo (a deterministic
            # building with no traffic), and those configs must stay
            # bit-identical. Returning None also keeps the floor-vs-peak check
            # below from firing on a peak of zero, where every floor rate
            # would look like a ramp-up.
            return None
        start_after = _num(block, "start_after_last_order_sec", 7200.0)
        ramp = _num(block, "ramp_sec", 1800.0)
        floor_per_min = _num(block, "floor_rate_per_min", 2.0)
        if start_after < 0:
            raise ValueError(
                f"ped_decay.start_after_last_order_sec must be >= 0; got {start_after}"
            )
        if ramp < 0:
            raise ValueError(f"ped_decay.ramp_sec must be >= 0; got {ramp}")
        if floor_per_min < 0:
            raise ValueError(
                f"ped_decay.floor_rate_per_min must be >= 0; got {floor_per_min}"
            )
        floor_per_sec = floor_per_min / 60.0
        if floor_per_sec > peak_rate_per_sec:
            raise ValueError(
                "ped_decay.floor_rate_per_min must not exceed the peak "
                f"pedestrian.arrival_rate_per_min ({peak_rate_per_sec * 60.0:g}); "
                f"got {floor_per_min:g} — this block models decay, not a ramp-up"
            )
        return PedDecay(
            start_sec=last_order_abs_sec + start_after,
            ramp_sec=ramp,
            floor_rate_per_sec=floor_per_sec,
            peak_rate_per_sec=peak_rate_per_sec,
        )

    def rate_per_sec_at(self, t: float) -> float:
        """Poisson rate at absolute time ``t``.

        The ``t > start_sec`` test is **strict on purpose** (see class
        docstring, reason 1): at ``t == start_sec`` the peak rate still applies,
        so a run whose cap coincides with ``start_sec`` — every H0 run — is
        bit-identical to a run with no decay block at all.
        """
        if t <= self.start_sec:
            return self.peak_rate_per_sec
        if self.ramp_sec <= 0.0 or t >= self.start_sec + self.ramp_sec:
            return self.floor_rate_per_sec
        frac = (t - self.start_sec) / self.ramp_sec
        return self.peak_rate_per_sec + frac * (
            self.floor_rate_per_sec - self.peak_rate_per_sec
        )
