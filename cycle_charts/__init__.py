"""에이전트 1-사이클 차트 생성기.

각 에이전트 클래스의 FSM을 "한 번의 사이클"로 펼쳐 상태·소요시간·공간경로·
결정근거를 하나의 자립 HTML로 렌더한다.

    .venv/bin/python -m cycle_charts.build --agent robot_h1

왜 별도 패키지인가
------------------
`analysis/`는 **run 산출물**(results/)을 소비하는 사후 분석이다. 이쪽은 반대로
**코드와 config 자체**를 소비한다 — run을 한 번도 돌리지 않아도 렌더된다.
섞으면 `analysis/`의 "results를 읽는다"는 불변식이 깨진다.

세 개의 층
----------
    spec.py      순수 데이터 구조. 렌더러도 시뮬레이터도 모른다.
    geometry.py  config + 건물 그래프에서 **살아 있는 상수**를 뽑는다.
    render.py    spec -> HTML. 사이클의 의미는 모르고 배치만 안다.

`specs/<agent>.py`가 이 셋을 엮어 하나의 차트를 정의한다. 새 에이전트를 추가할 때
건드리는 것은 `specs/` 하나뿐이어야 한다 — 그렇지 않다면 spec 어휘가 부족한 것이니
`spec.py`를 넓히고 렌더러를 고쳐야지, 스펙에 raw HTML을 넣지 않는다.
"""
