"""RiderPool — type별 유한 라이더 재고의 차감/복귀/대기열 관리자.

etc/plan_rider_pool_dynamic.md Part C. 배정 규칙은
etc/rider_type_assignment_inventory.md §5:

  capa 필터 → 거리 비용순위(type_priority) → 재고 cascade
  (전 후보 소진 시 FIFO 대기열, release마다 재스캔)

Mesa Agent가 아닌 순수 헬퍼 — BuildingHandoffModel이 tick에서 호출한다.
type 배정에 RNG가 없으므로(비용순위 + cascade는 결정적) sigma_eps=0이면
동적 경로 전체가 시드 무관 결정적이다.

Invariants (tests/test_rider_pool.py):
  0 <= free[t] <= initial[t]        (release 초과 시 ValueError)
  free[t] + busy(t) == initial[t]   (busy = 배차됐고 아직 미복귀)
"""

from __future__ import annotations

from collections import deque

from analysis.load_data import Rider
from analysis.rider_arrival_model import type_priority


class RiderPool:
    """Per-type finite rider inventory with FIFO overflow queue.

    Parameters
    ----------
    riders : RIDERS table rows (initial stock = available_number).
    throughput_per_rider_h : passed to the wage-calibrated cost priority.
    """

    def __init__(
        self, riders: list[Rider], throughput_per_rider_h: float = 50.0
    ) -> None:
        if not riders:
            raise ValueError("RiderPool needs at least one rider type")
        self.riders_by_type: dict[str, Rider] = {r.type: r for r in riders}
        self.initial: dict[str, int] = {
            r.type: int(r.available_number) for r in riders
        }
        self.free: dict[str, int] = dict(self.initial)
        self.throughput_per_rider_h = throughput_per_rider_h
        # FIFO queue of DispatchOrder whose eligible types were all exhausted
        self.waiting: deque = deque()
        # cumulative stats (KPI / status table)
        self.dispatch_count: dict[str, int] = {t: 0 for t in self.riders_by_type}
        self.fallback_count: int = 0
        self.queued_count: int = 0

    # ------------------------------------------------------------- queries

    def busy(self, rider_type: str) -> int:
        """Riders of this type currently out (dispatched, not yet released)."""
        return self.initial[rider_type] - self.free[rider_type]

    def eligible_riders(self, vol: int) -> list[Rider]:
        """capa filter — same feasibility rule as the static sampler."""
        eligible = [r for r in self.riders_by_type.values() if r.capa >= vol]
        if not eligible:
            raise ValueError(
                f"No rider type can carry VOL={vol} "
                f"(max capa = {max(r.capa for r in self.riders_by_type.values())})"
            )
        return eligible

    # ------------------------------------------------------------ dispatch

    def try_dispatch(self, order) -> tuple[str, bool] | None:  # noqa: ANN001
        """Pick the cheapest eligible type with free stock; deduct it.

        Returns (rider_type, was_fallback) — was_fallback True when the
        cost-optimal type had no free rider and a pricier type was used.
        Returns None when every eligible type is exhausted (caller should
        enqueue()).
        """
        priority = type_priority(
            self.eligible_riders(order.vol), order.dist_m,
            self.throughput_per_rider_h,
        )
        for rank, t in enumerate(priority):
            if self.free[t] > 0:
                self.free[t] -= 1
                self.dispatch_count[t] += 1
                was_fallback = rank > 0
                if was_fallback:
                    self.fallback_count += 1
                return t, was_fallback
        return None

    def enqueue(self, order) -> None:  # noqa: ANN001
        """FIFO-append an order whose eligible types were all exhausted."""
        self.waiting.append(order)
        self.queued_count += 1

    # ------------------------------------------------------------- release

    def release(self, rider_type: str) -> list[tuple]:
        """Return one rider to the pool, then rescan the FIFO queue.

        Rescan dispatches every waiting order that can now be served (an
        order skips ahead only if the earlier orders cannot use the freed
        type — capa mismatch — so FIFO fairness holds within a type).

        Returns [(order, rider_type, was_fallback), ...] for orders released
        from the queue (usually 0 or 1).
        """
        if self.free[rider_type] >= self.initial[rider_type]:
            raise ValueError(
                f"release() overflow: free[{rider_type}] already at initial "
                f"{self.initial[rider_type]}"
            )
        self.free[rider_type] += 1
        dispatched: list[tuple] = []
        kept: deque = deque()
        while self.waiting:
            o = self.waiting.popleft()
            res = self.try_dispatch(o)
            if res is None:
                kept.append(o)
            else:
                dispatched.append((o, res[0], res[1]))
        self.waiting = kept
        return dispatched
