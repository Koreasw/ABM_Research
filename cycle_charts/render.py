"""spec -> 자립 HTML. 사이클의 의미는 모르고 배치만 안다.

출력은 Artifact로 그대로 발행할 수 있는 형태다: `<!doctype>`/`<html>`/`<head>`/
`<body>`를 쓰지 않고 `<title>` + `<style>` + 본문만 낸다. 외부 자산은 하나도
참조하지 않는다(폰트 CDN 포함 — CSP가 막고, 조용한 폴백이 CJK에서 특히 나쁘다).
한글은 시스템 폰트 스택으로 받는다: CJK 웹폰트를 data URI로 인라인하면 수 MB다.

테마는 토큰 단위로 처리한다. `prefers-color-scheme`가 OS 설정을 나르고,
뷰어의 토글이 루트에 `data-theme`를 찍으며 그것이 양방향으로 미디어 쿼리를
이겨야 한다 — 그래서 팔레트를 세 번 선언한다.
"""

from __future__ import annotations

import html
from pathlib import Path

from cycle_charts.spec import CycleSpec, Diagram, Fixed, Stochastic, Variable

OUT_DIR = Path(__file__).resolve().parent / "out"

# 리본에서 이보다 좁은 세그먼트는 번호가 잘리므로 최소폭을 준다. 폭이 시간에
# 정확히 비례하지 않게 되지만, 읽을 수 없는 눈금보다는 낫다.
_SEG_MIN_PX = 21
_VAR_SEG_PX = 40


def _e(text: str) -> str:
    return html.escape(text, quote=True)


# ------------------------------------------------------------------ 토큰/CSS

def _palette_vars(spec: CycleSpec, mode: str) -> str:
    table = spec.palette.light if mode == "light" else spec.palette.dark
    return "\n".join(f"    --b-{k}: {v};" for k, v in table.items())


_NEUTRALS_LIGHT = """
    --paper: #EBEEF1; --panel: #F6F8F9; --ink: #16202A; --ink-2: #4A5A69;
    --ink-3: #7C8B98; --rule: #CBD4DB; --rule-soft: #DFE5EA; --shaft: #DDE4E9;
    --seg-ink: #fff;"""

_NEUTRALS_DARK = """
    --paper: #0F151B; --panel: #172029; --ink: #DDE5EB; --ink-2: #A2B0BC;
    --ink-3: #71828F; --rule: #2C3A46; --rule-soft: #222E38; --shaft: #1D2831;
    --seg-ink: #0F151B;"""


def _css(spec: CycleSpec) -> str:
    light = _NEUTRALS_LIGHT + "\n" + _palette_vars(spec, "light")
    dark = _NEUTRALS_DARK + "\n" + _palette_vars(spec, "dark")
    return f""":root {{{light}

    --f-sans: -apple-system, BlinkMacSystemFont, "Pretendard", "Apple SD Gothic Neo",
              "Malgun Gothic", "Noto Sans KR", "Segoe UI", sans-serif;
    --f-mono: ui-monospace, "SF Mono", "JetBrains Mono", "Cascadia Mono", Menlo,
              Consolas, monospace;
  }}

  /* 다크는 토큰만 다시 선언한다 — 컴포넌트는 언제나 토큰을 통해서만 칠한다 */
  @media (prefers-color-scheme: dark) {{ :root {{{dark} }} }}
  :root[data-theme="dark"] {{{dark} }}
  :root[data-theme="light"] {{{light} }}

  body {{
    background: var(--paper); color: var(--ink);
    font-family: var(--f-sans); font-size: 15px; line-height: 1.65;
    -webkit-font-smoothing: antialiased;
  }}
  .wrap {{
    max-width: 1080px; margin: 0 auto; padding: 44px 24px 96px;
    display: flex; flex-direction: column; gap: 52px;
  }}

  .masthead {{ display: flex; flex-direction: column; gap: 14px; }}
  .eyebrow {{
    font-family: var(--f-mono); font-size: 11.5px; letter-spacing: 0.14em;
    text-transform: uppercase; color: var(--ink-3);
  }}
  h1 {{
    font-size: clamp(28px, 4.4vw, 40px); font-weight: 700;
    letter-spacing: -0.022em; line-height: 1.18; text-wrap: balance; margin: 0;
  }}
  .standfirst {{ max-width: 64ch; color: var(--ink-2); font-size: 16px; }}

  /* 출처 배지. `pending`(구현보다 스펙이 먼저 온 차트)은 파선으로 갈라 놓는다 —
     "이미 도는 것"과 "아직 없는 것"이 같은 무게로 읽히면 안 된다. */
  .prov {{
    display: inline-flex; align-items: baseline; gap: 9px; align-self: flex-start;
    font-family: var(--f-mono); font-size: 11.5px;
    padding: 4px 10px; border: 1px solid var(--rule); color: var(--ink-3);
  }}
  .prov b {{ font-weight: 650; color: var(--ink-2); }}
  .prov.pending {{ border-style: dashed; border-color: var(--ink-2); }}
  .prov.pending b {{ color: var(--ink); }}
  code {{
    font-family: var(--f-mono); font-size: 0.9em;
    background: var(--rule-soft); padding: 0.1em 0.36em; border-radius: 2px;
  }}

  .ledger {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(148px, 1fr));
    gap: 1px; background: var(--rule); border: 1px solid var(--rule); margin-top: 8px;
  }}
  .ledger > div {{
    background: var(--panel); padding: 13px 16px;
    display: flex; flex-direction: column; gap: 3px;
  }}
  .ledger dt {{
    font-family: var(--f-mono); font-size: 10.5px; letter-spacing: 0.1em;
    text-transform: uppercase; color: var(--ink-3);
  }}
  .ledger dd {{
    margin: 0; font-size: 21px; font-weight: 650; letter-spacing: -0.02em;
    font-variant-numeric: tabular-nums;
  }}
  .ledger dd span {{ font-size: 13px; font-weight: 450; color: var(--ink-2); }}

  section {{ display: flex; flex-direction: column; gap: 18px; }}
  h2 {{
    font-size: 13px; font-family: var(--f-mono); font-weight: 600;
    letter-spacing: 0.11em; text-transform: uppercase; color: var(--ink);
    margin: 0; padding-bottom: 9px; border-bottom: 1.5px solid var(--ink);
  }}
  h2 .sub {{
    text-transform: none; letter-spacing: 0; font-family: var(--f-sans);
    font-weight: 400; color: var(--ink-3); margin-left: 10px;
  }}
  .lede {{ max-width: 66ch; color: var(--ink-2); margin: 0; }}

  .ribbon-frame {{ display: flex; flex-direction: column; gap: 9px; }}
  .ribbon {{
    display: flex; height: 54px; border: 1px solid var(--rule);
    background: var(--panel); overflow: hidden;
  }}
  .seg {{
    position: relative; display: flex; align-items: center; justify-content: center;
    min-width: {_SEG_MIN_PX}px; border-right: 1px solid var(--paper);
    color: var(--seg-ink); font-family: var(--f-mono); font-size: 11px; font-weight: 600;
  }}
  .seg:last-child {{ border-right: 0; }}
  .seg.var {{
    flex: 0 0 {_VAR_SEG_PX}px; background-color: var(--panel); color: var(--ink-2);
    background-image: repeating-linear-gradient(45deg, var(--rule) 0 4px, transparent 4px 8px);
  }}
  .axis {{
    display: flex; justify-content: space-between; gap: 12px;
    font-family: var(--f-mono); font-size: 11px; color: var(--ink-3);
    font-variant-numeric: tabular-nums;
  }}

  .legend {{ display: flex; flex-wrap: wrap; gap: 7px 20px; }}
  .legend > div {{
    display: flex; align-items: center; gap: 7px;
    font-family: var(--f-mono); font-size: 11.5px; color: var(--ink-2);
  }}
  .swatch {{ width: 13px; height: 13px; flex: none; }}

  .figure {{ border: 1px solid var(--rule); background: var(--panel); margin: 0; }}
  .scroller {{ overflow-x: auto; }}
  .scroller svg {{ display: block; width: 100%; height: auto; }}
  figcaption {{
    border-top: 1px solid var(--rule-soft); padding: 11px 16px;
    font-size: 12.5px; color: var(--ink-3);
  }}

  .tbl-scroll {{ overflow-x: auto; border: 1px solid var(--rule); }}
  table {{ border-collapse: collapse; width: 100%; min-width: 900px; background: var(--panel); }}
  thead th {{
    position: sticky; top: 0; background: var(--panel); text-align: left;
    font-family: var(--f-mono); font-size: 10.5px; letter-spacing: 0.1em;
    text-transform: uppercase; color: var(--ink-3); font-weight: 600;
    padding: 11px 14px; border-bottom: 1.5px solid var(--ink); white-space: nowrap;
  }}
  tbody td {{
    padding: 13px 14px; border-bottom: 1px solid var(--rule-soft);
    vertical-align: top; font-size: 13.5px; line-height: 1.6;
  }}
  tbody tr:last-child td {{ border-bottom: 0; }}
  td.n {{
    font-family: var(--f-mono); font-variant-numeric: tabular-nums;
    color: var(--ink-3); width: 38px; padding-right: 0; position: relative;
  }}
  td.n::before {{
    content: ""; position: absolute; left: 0; top: 0; bottom: 0;
    width: 4px; background: var(--bar, transparent);
  }}
  td.st {{ white-space: nowrap; }}
  .state {{
    font-family: var(--f-mono); font-size: 12.5px; font-weight: 650;
    letter-spacing: -0.01em;
  }}
  .leg {{
    display: block; font-family: var(--f-mono); font-size: 11px;
    color: var(--ink-3); margin-top: 2px;
  }}
  td.dur {{
    font-family: var(--f-mono); font-variant-numeric: tabular-nums;
    white-space: nowrap; font-size: 12.5px;
  }}
  td.dur em {{ font-style: normal; color: var(--ink-3); font-size: 11px; display: block; }}
  .why {{ color: var(--ink-2); font-size: 12.5px; }}
  .tag {{
    display: inline-block; font-family: var(--f-mono); font-size: 10.5px;
    padding: 1px 5px; border: 1px solid var(--rule); color: var(--ink-3);
    margin-right: 4px; white-space: nowrap;
  }}

  .notes {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(288px, 1fr));
    gap: 1px; background: var(--rule); border: 1px solid var(--rule);
  }}
  .note {{
    background: var(--panel); padding: 17px 18px;
    display: flex; flex-direction: column; gap: 7px;
  }}
  .note h3 {{ margin: 0; font-size: 13.5px; font-weight: 650; letter-spacing: -0.01em; }}
  .note p {{ margin: 0; font-size: 13px; color: var(--ink-2); line-height: 1.62; }}
  .note .stamp {{
    font-family: var(--f-mono); font-size: 10.5px; letter-spacing: 0.09em;
    text-transform: uppercase; color: var(--ink-3);
  }}
  .note.flag {{ border-left: 3px solid var(--flag-color, var(--ink)); }}

  a {{ color: inherit; }}
  :focus-visible {{ outline: 2px solid var(--ink); outline-offset: 2px; }}
  @media (prefers-reduced-motion: reduce) {{
    * {{ animation: none !important; transition: none !important; }}
  }}"""


# -------------------------------------------------------------------- 조각들

def _masthead(spec: CycleSpec) -> str:
    cells = "\n".join(
        f'      <div><dt>{_e(m.label)}</dt>'
        f'<dd>{_e(m.value)}<span>{_e(m.unit)}</span></dd></div>'
        for m in spec.metrics
    )
    badge = ""
    if (p := spec.provenance):
        cls = "prov pending" if p.pending else "prov"
        badge = (
            f'\n    <div class="{cls}"><b>{_e(p.label)}</b>'
            f'<span>{_e(p.detail)}</span></div>'
        )
    return f"""  <header class="masthead">
    <div class="eyebrow">{_e(spec.eyebrow)}</div>
    <h1>{_e(spec.title)}</h1>{badge}
    <p class="standfirst">{spec.standfirst}</p>
    <dl class="ledger">
{cells}
    </dl>
  </header>"""


def _sub_label(d: Fixed | Stochastic | Variable | object) -> str:
    """소요시간의 부가 설명 — 분포식이 있으면 그것, 없으면 계산 근거.

    `NoTime`에는 둘 다 없다. `getattr` 대신 타입으로 갈라야 새 Duration 종류가
    생겼을 때 여기가 조용히 빈 문자열을 내지 않는다.
    """
    if isinstance(d, Stochastic):
        return d.dist
    if isinstance(d, (Fixed, Variable)):
        return d.note
    return ""


def _ribbon(spec: CycleSpec) -> str:
    segs = []
    for s in spec.steps:
        if not s.in_ribbon:
            continue
        d = s.duration
        tip = f"{s.n} {s.state}"
        if s.leg:
            tip += f" ({s.leg})"
        tip += f" · {d.label}"
        if isinstance(d, Stochastic):
            tip += f" · {d.dist}"
        if (note := _sub_label(d)):
            tip += f" · {note}"

        if isinstance(d, Variable):
            segs.append(f'        <div class="seg var" title="{_e(tip)}">{_e(s.n)}</div>')
        elif isinstance(d, (Fixed, Stochastic)):
            segs.append(
                f'        <div class="seg" style="flex:{d.ribbon_sec:g};'
                f'background:var(--b-{s.bucket})" title="{_e(tip)}">{_e(s.n)}</div>'
            )

    total = spec.deterministic_sec()
    return f"""    <div class="ribbon-frame">
      <div class="ribbon" role="img" aria-label="{_e(spec.ribbon_axis_note)}">
{chr(10).join(segs)}
      </div>
      <div class="axis">
        <span>0 s</span><span>{_e(spec.ribbon_axis_note)}</span>
        <span>{total:.1f} s</span>
      </div>
    </div>"""


def _legend(spec: CycleSpec) -> str:
    items = "\n".join(
        f'      <div><span class="swatch" style="background:var(--b-{b})"></span>{_e(b)}</div>'
        for b in spec.palette.buckets()
    )
    tail = (
        f'\n      <div style="color:var(--ink-3)">{spec.palette.legend_note}</div>'
        if spec.palette.legend_note else ""
    )
    return f'    <div class="legend">\n{items}{tail}\n    </div>'


def _svg(d: Diagram, marker_bucket: dict[str, str]) -> str:
    """`marker_bucket`은 단계에서 만들어 넘긴다 — 도면이 색을 따로 들고 있으면
    표와 어긋날 수 있고, 그 어긋남은 눈으로만 발견된다."""
    parts: list[str] = []

    for s in d.shafts:
        parts.append(
            f'          <rect x="{s.x}" y="{s.y_top}" width="{s.width}" '
            f'height="{s.y_bottom - s.y_top}" fill="var(--shaft)"/>'
        )
        cx = s.x + s.width / 2
        if s.label:
            parts.append(
                f'          <text x="{cx}" y="{s.y_top - 10}" text-anchor="middle" '
                f'font-family="var(--f-mono)" font-size="12" fill="var(--ink-2)">'
                f'{_e(s.label)}</text>'
            )
        if s.inner_label:
            cy = (s.y_top + s.y_bottom) / 2
            parts.append(
                f'          <text x="{cx}" y="{cy}" text-anchor="middle" '
                f'font-family="var(--f-mono)" font-size="11.5" fill="var(--ink-3)" '
                f'transform="rotate(-90 {cx} {cy})">{_e(s.inner_label)}</text>'
            )

    for lv in d.levels:
        for x0, x1 in lv.spans:
            parts.append(
                f'          <rect x="{x0}" y="{lv.slab_y}" width="{x1 - x0}" '
                f'height="10" fill="var(--rule)"/>'
            )
        parts.append(
            f'          <text x="{lv.label_x}" y="{lv.slab_y + lv.label_dy}" '
            f'font-family="var(--f-mono)" font-size="12" fill="var(--ink-3)">'
            f'{_e(lv.label)}</text>'
        )

    for f in d.fixtures:
        parts.append(
            f'          <rect x="{f.x - f.width / 2}" y="{f.y}" width="{f.width}" '
            f'height="6" fill="var(--b-{f.bucket})"/>'
        )
        parts.append(
            f'          <text x="{f.x}" y="{f.label_y}" text-anchor="{f.anchor}" '
            f'font-family="var(--f-mono)" font-size="11.5" fill="var(--ink-3)">'
            f'{_e(f.label)}</text>'
        )

    for dim in d.dims:
        parts.append(
            f'          <text x="{dim.x}" y="{dim.y}" text-anchor="{dim.anchor}" '
            f'font-family="var(--f-mono)" font-size="11" fill="var(--ink-3)">'
            f'{_e(dim.text)}</text>'
        )

    for p in d.paths:
        pts = " ".join(f"{x},{y}" for x, y in p.points)
        attrs = (
            f'fill="none" stroke="var(--b-{p.bucket})" stroke-width="2.5" '
            f'stroke-linejoin="round" stroke-linecap="round"'
        )
        if p.dashed:
            attrs += ' stroke-dasharray="7 4"'
        if p.arrow:
            attrs += ' marker-end="url(#ah)"'
        parts.append(f'          <polyline points="{pts}" {attrs}/>')

    for m in d.markers:
        r = 13 if len(m.n) <= 2 else 15
        parts.append(
            f'          <g><circle cx="{m.x}" cy="{m.y}" r="{r}" '
            f'fill="var(--b-{marker_bucket[m.n]})"/>'
            f'<text x="{m.x}" y="{m.y + 4}" text-anchor="middle" '
            f'font-family="var(--f-mono)" font-size="11.5" font-weight="700" '
            f'fill="var(--seg-ink)">{_e(m.n)}</text></g>'
        )

    body = "\n".join(parts)
    return f"""    <figure class="figure">
      <div class="scroller">
        <svg viewBox="0 0 {d.width} {d.height}" role="img"
             style="min-width:{d.min_px}px"
             aria-label="{_e(d.alt)}">
          <defs>
            <marker id="ah" viewBox="0 0 10 10" refX="8" refY="5"
                    markerWidth="5.5" markerHeight="5.5" orient="auto-start-reverse">
              <path d="M0,1 L9,5 L0,9 z" fill="context-stroke"/>
            </marker>
          </defs>
{body}
        </svg>
      </div>
      <figcaption>{d.caption}</figcaption>
    </figure>"""


def _table(spec: CycleSpec) -> str:
    rows = []
    for s in spec.steps:
        leg = f'<span class="leg">{_e(s.leg)}</span>' if s.leg else ""
        d = s.duration
        sub = _sub_label(d)
        sub_html = f"<em>{_e(sub)}</em>" if sub else ""
        tag = f'<span class="tag">{_e(s.tag)}</span>' if s.tag else ""
        rows.append(
            f'          <tr style="--bar:var(--b-{s.bucket})">\n'
            f'            <td class="n">{_e(s.n)}</td>\n'
            f'            <td class="st"><span class="state">{_e(s.state)}</span>{leg}</td>\n'
            f"            <td>{s.what}</td>\n"
            f'            <td class="dur">{_e(d.label)}{sub_html}</td>\n'
            f'            <td class="why">{tag}{s.why}</td>\n'
            f"          </tr>"
        )
    return f"""    <div class="tbl-scroll">
      <table>
        <thead>
          <tr><th>#</th><th>상태 / 속성</th><th>무슨 일이 일어나나</th>
              <th>시간</th><th>결정·논리</th></tr>
        </thead>
        <tbody>
{chr(10).join(rows)}
        </tbody>
      </table>
    </div>"""


def _notes(spec: CycleSpec) -> str:
    cards = []
    for n in spec.notes:
        cls = "note flag" if n.flag else "note"
        cards.append(
            f'      <div class="{cls}">\n'
            f'        <span class="stamp">{_e(n.stamp)}</span>\n'
            f"        <h3>{_e(n.title)}</h3>\n"
            f"        <p>{n.body}</p>\n"
            f"      </div>"
        )
    return f'    <div class="notes">\n{chr(10).join(cards)}\n    </div>'


# --------------------------------------------------------------------- 진입

def render(spec: CycleSpec) -> str:
    spec.validate()
    t = spec.section_titles
    blocks = [
        _masthead(spec),
        "  <section>\n"
        f'    <h2>{_e(t.get("ribbon", "시간 소요"))}'
        f'<span class="sub">폭 = 초. 빗금 = 큐잉 대기(가변)</span></h2>\n'
        f'    <p class="lede">{spec.ribbon_lede}</p>\n'
        f"{_ribbon(spec)}\n{_legend(spec)}\n  </section>",
    ]
    if spec.diagram:
        buckets = {s.n: s.bucket for s in spec.steps}
        blocks.append(
            "  <section>\n"
            f'    <h2>{_e(t.get("diagram", "공간 경로"))}</h2>\n'
            f"{_svg(spec.diagram, buckets)}\n  </section>"
        )
    blocks.append(
        "  <section>\n"
        f'    <h2>{_e(t.get("table", "단계별 정의"))}'
        f'<span class="sub">상태 · 소요 · 근거</span></h2>\n'
        f"{_table(spec)}\n  </section>"
    )
    if spec.notes or spec.closing:
        tail = (
            f'\n    <p class="lede" style="margin-top:6px">{spec.closing}</p>'
            if spec.closing else ""
        )
        blocks.append(
            "  <section>\n"
            f'    <h2>{_e(t.get("notes", "읽을 때 걸리는 것들"))}</h2>\n'
            f"{_notes(spec)}{tail}\n  </section>"
        )

    body = "\n\n".join(blocks)
    return f"""<title>{_e(spec.title)}</title>

<style>
  {_css(spec)}
</style>

<div class="wrap">

{body}

</div>
"""


def write(spec: CycleSpec, out_dir: Path | None = None) -> Path:
    out_dir = out_dir or OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{spec.slug}.html"
    path.write_text(render(spec), encoding="utf-8")
    return path
