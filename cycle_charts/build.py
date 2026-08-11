"""차트 생성 CLI.

    .venv/bin/python -m cycle_charts.build                 # 전부
    .venv/bin/python -m cycle_charts.build --agent robot_h1
    .venv/bin/python -m cycle_charts.build --list
    .venv/bin/python -m cycle_charts.build --check         # 쓰지 않고 검증만

`--check`는 CI용이다. config가 바뀌어 차트가 낡았는지가 아니라, **스펙 자체가
코드와 어긋났는지**를 잡는다 — 상태 개명, 버킷 추가, 팔레트 누락, 표에 없는
도면 마커. 전부 렌더 시점 예외다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from cycle_charts import render
from cycle_charts.specs import REGISTRY


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="cycle_charts.build", description=__doc__)
    ap.add_argument("--agent", action="append", metavar="SLUG",
                    help="생성할 에이전트 slug (반복 가능). 생략하면 전부")
    ap.add_argument("--out", type=Path, default=None,
                    help=f"출력 디렉터리 (기본 {render.OUT_DIR})")
    ap.add_argument("--list", action="store_true", help="등록된 slug를 출력하고 종료")
    ap.add_argument("--check", action="store_true",
                    help="렌더만 하고 파일은 쓰지 않는다 (스펙 검증)")
    args = ap.parse_args(argv)

    if args.list:
        for slug in sorted(REGISTRY):
            print(slug)
        return 0

    slugs = args.agent or sorted(REGISTRY)
    unknown = [s for s in slugs if s not in REGISTRY]
    if unknown:
        print(f"알 수 없는 slug: {unknown}. --list로 확인.", file=sys.stderr)
        return 2

    for slug in slugs:
        spec = REGISTRY[slug]()
        if args.check:
            render.render(spec)          # validate + 렌더까지 실제로 태운다
            print(f"OK   {slug}  ({spec.deterministic_sec():.1f} s / "
                  f"{len(spec.steps)}단계)")
        else:
            path = render.write(spec, args.out)
            print(f"작성 {path}  ({spec.deterministic_sec():.1f} s / "
                  f"{len(spec.steps)}단계)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
