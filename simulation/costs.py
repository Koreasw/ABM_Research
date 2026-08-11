"""3-stakeholder NPV / TCO models (framework §7.4-7.5).

RiderEarnings_H(lambda, w_R) = sum [ (fixed + var * N_t) - w_R * T_lobby_t ]
CustomerSurplus_H(lambda)    = sum S_customer(T_e2e_t)
BuildingNPV_H(lambda, T)     = -C_acq_H + sum [Rev - C_OPEX_H] / (1+r)^t
                              + C_salvage / (1+r)^T

C_acq differs per mode (H0=0, H1=robots, H2=+queue zone, H3=+locker bank).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class NPVConfig:
    horizon_years: int = 5
    discount_rate: float = 0.05
    robot_capex_krw: float = 35_000_000.0
    locker_install_capex_krw: float = 8_000_000.0
    locker_compartment_capex_krw: float = 300_000.0
    elec_krw_per_kwh: float = 110.0


def building_npv(
    mode: str,
    n_robots: int,
    n_locker_compartments: int,
    annual_revenue_krw: float,
    annual_opex_krw: float,
    cfg: NPVConfig | None = None,
) -> float:
    raise NotImplementedError


def break_even_w_rider(
    mode_a: str,
    mode_b: str,
    lambda_baseline: float,
    cfg: NPVConfig | None = None,
) -> float:
    """Solve w_R s.t. NPV_a(w_R) = NPV_b(w_R). Returns KRW/h."""
    raise NotImplementedError
