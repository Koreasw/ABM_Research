"""에이전트별 차트 스펙.

새 에이전트를 추가할 때 손대는 곳은 여기뿐이어야 한다. 모듈은 인자 없는
`build() -> CycleSpec`을 노출하고, `REGISTRY`에 slug로 등록한다.

작성 순서 (로봇 스펙이 그 예시다):
  1. `geometry.py`에 그 에이전트가 쓰는 상수를 **계산**으로 추가한다.
     숫자를 스펙에 직접 적는 순간 문서가 늙기 시작한다.
  2. 상태·leg 이름은 에이전트 모듈에서 **import**해서 쓴다. 오타나 이름 변경이
     렌더 시점에 예외로 터져야지, 그림을 눈으로 보고 발견해서는 안 된다.
  3. 버킷 키는 그 에이전트의 보고 버킷과 정확히 일치시킨다.
"""

from __future__ import annotations

from collections.abc import Callable

from cycle_charts.spec import CycleSpec
from cycle_charts.specs import rider_h0, robot_h1

REGISTRY: dict[str, Callable[[], CycleSpec]] = {
    "rider_h0": rider_h0.build,
    "robot_h1": robot_h1.build,
}
