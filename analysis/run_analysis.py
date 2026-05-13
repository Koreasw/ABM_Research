"""STAGE 1 pipeline entry point (framework §4).

Runs the full analysis:
  1. NHPP lambda(t) — pooled + K-stratum + bootstrap CI
  2. Cook time fit (Gamma vs Lognormal vs Weibull, AIC)
  3. VOL distribution
  4. Lead time distribution (DLV_DEADLINE - ORD_TIME)
  5. Pickup-drop road distance (context)
  6. K-scaling structural indicators
  7. Rider arrival time synthesis (§2.5)
  8. w_R per rider type

Outputs: analysis/fitted_params.json, analysis/figures/*.png, analysis/fit_report.md
"""

from __future__ import annotations


def main() -> None:
    raise NotImplementedError


if __name__ == "__main__":
    main()
