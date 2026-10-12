"""Animated SVG charts for the HTML decks (no JS libraries, works offline).

Animation hooks (CSS in html_renderer): .bar grows, .line draws, .pie sweeps,
.lbl fades in. Each element gets a --d delay (ms) for staggering.
"""
from __future__ import annotations

import math
from html import escape

from ..schema import ChartSpec
from .common import fmt_number


def _nice(v: float) -> float:
    if v <= 0:
        return 1.0
    exp = math.floor(math.log10(v))
    f = v / 10 ** exp
    for n in (1, 2, 2.5, 5, 10):
        if f <= n:
            return n * 10 ** exp
    return 10 ** (exp + 1)


def _values(spec: ChartSpec) -> list[list[float]]:
    n = len(spec.categories)
    return [(list(s.values) + [0.0] * n)[:n] for s in spec.series]


def chart_svg(spec: ChartSpec, colors: list[str], text: str, muted: str, grid: str,
              w: int = 1600, h: int = 700, font: str = "inherit") -> str:
    if spec.type in ("pie", "doughnut"):
        return _pie(spec, colors, text, muted, w, h, font)
    return _axes_chart(spec, colors, text, muted, grid, w, h, font)


def _legend(spec: ChartSpec, colors, text, x, y, font) -> str:
    if len(spec.series) < 2:
        return ""
    out, cx = [], x
    for i, s in enumerate(spec.series):
        c = colors[i % len(colors)]
        out.append(f'<rect x="{cx}" y="{y - 16}" width="22" height="22" rx="5" fill="{c}"/>'
                   f'<text x="{cx + 32}" y="{y}" fill="{text}" font-size="26">{escape(s.name)}</text>')
        cx += 70 + 15 * len(s.name)
    return f'<g class="lbl" style="--d:200">{"".join(out)}</g>'


def _axes_chart(spec, colors, text, muted, grid, w, h, font) -> str:
    vals = _values(spec)
    flat = [v for row in vals for v in row] or [0]
    hi = _nice(max(0.0, max(flat)))
    lo = -_nice(-min(flat)) if min(flat) < 0 else 0.0
    horizontal = spec.type == "bar"
    top = 70 if len(spec.series) > 1 else 30
    left = 260 if horizontal else 110
    right, bottom = 40, 80
    pw, ph = w - left - right, h - top - bottom
    ncat, nser = len(spec.categories), max(1, len(spec.series))
    parts = [f'<svg viewBox="0 0 {w} {h}" class="chart" font-family="{font}" role="img">']
    parts.append(_legend(spec, colors, text, left, 36, font))

    def vpos(v):  # value -> pixel along the value axis
        frac = (v - lo) / (hi - lo) if hi != lo else 0
        return left + frac * pw if horizontal else top + ph - frac * ph

    # grid + value labels
    for i in range(5):
        v = lo + (hi - lo) * i / 4
        p = vpos(v)
        if horizontal:
            parts.append(f'<line x1="{p:.1f}" y1="{top}" x2="{p:.1f}" y2="{top + ph}" stroke="{grid}" stroke-width="2"/>'
                         f'<text x="{p:.1f}" y="{top + ph + 40}" fill="{muted}" font-size="24" text-anchor="middle">{fmt_number(v, spec.number_format)}</text>')
        else:
            parts.append(f'<line x1="{left}" y1="{p:.1f}" x2="{left + pw}" y2="{p:.1f}" stroke="{grid}" stroke-width="2"/>'
                         f'<text x="{left - 16}" y="{p + 8:.1f}" fill="{muted}" font-size="24" text-anchor="end">{fmt_number(v, spec.number_format)}</text>')

    band = (ph if horizontal else pw) / max(1, ncat)
    zero = vpos(0)
    if spec.type == "line":
        step = pw / max(1, ncat - 1) if ncat > 1 else 0
        for ci, cat in enumerate(spec.categories):
            x = left + ci * step if ncat > 1 else left + pw / 2
            parts.append(f'<text x="{x:.1f}" y="{top + ph + 44}" fill="{muted}" font-size="24" text-anchor="middle">{escape(cat)}</text>')
        for si, row in enumerate(vals):
            c = colors[si % len(colors)]
            pts = [((left + i * step) if ncat > 1 else left + pw / 2, vpos(v)) for i, v in enumerate(row)]
            d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
            parts.append(f'<path class="line" style="--d:{300 + si * 250}" d="{d}" pathLength="1" fill="none" '
                         f'stroke="{c}" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/>')
            for pi, (x, y) in enumerate(pts):
                parts.append(f'<circle class="lbl" style="--d:{900 + si * 250 + pi * 60}" cx="{x:.1f}" cy="{y:.1f}" r="10" fill="{c}"/>')
                if nser == 1:
                    parts.append(f'<text class="lbl" style="--d:{1000 + pi * 60}" x="{x:.1f}" y="{y - 22:.1f}" fill="{text}" '
                                 f'font-size="26" font-weight="700" text-anchor="middle">{fmt_number(row[pi], spec.number_format)}</text>')
    else:
        inner = band * 0.72
        bw = inner / nser
        for ci, cat in enumerate(spec.categories):
            b0 = (top if horizontal else left) + ci * band + (band - inner) / 2
            if horizontal:
                parts.append(f'<text x="{left - 16}" y="{top + ci * band + band / 2 + 9:.1f}" fill="{muted}" font-size="24" text-anchor="end">{escape(cat)}</text>')
            else:
                parts.append(f'<text x="{left + ci * band + band / 2:.1f}" y="{top + ph + 44}" fill="{muted}" font-size="24" text-anchor="middle">{escape(cat)}</text>')
            for si, row in enumerate(vals):
                v = row[ci]
                c = colors[si % len(colors)]
                p = vpos(v)
                delay = 250 + ci * 90 + si * 40
                label = fmt_number(v, spec.number_format)
                if horizontal:
                    x, width = min(zero, p), abs(p - zero)
                    y = b0 + si * bw
                    parts.append(f'<rect class="bar hbar" style="--d:{delay}" x="{x:.1f}" y="{y:.1f}" width="{width:.1f}" height="{bw * 0.9:.1f}" rx="6" fill="{c}"/>')
                    parts.append(f'<text class="lbl" style="--d:{delay + 600}" x="{max(zero, p) + 12:.1f}" y="{y + bw * 0.45 + 9:.1f}" fill="{text}" font-size="24" font-weight="700">{label}</text>')
                else:
                    y, height = min(zero, p), abs(p - zero)
                    x = b0 + si * bw
                    parts.append(f'<rect class="bar vbar" style="--d:{delay}" x="{x:.1f}" y="{y:.1f}" width="{bw * 0.9:.1f}" height="{height:.1f}" rx="6" fill="{c}"/>')
                    parts.append(f'<text class="lbl" style="--d:{delay + 600}" x="{x + bw * 0.45:.1f}" y="{y - 12:.1f}" fill="{text}" font-size="24" font-weight="700" text-anchor="middle">{label}</text>')
    parts.append("</svg>")
    return "".join(parts)


def _pie(spec, colors, text, muted, w, h, font) -> str:
    vals = [max(0.0, v) for v in _values(spec)[0]] if spec.series else []
    total = sum(vals) or 1
    r = min(h, w * 0.5) * 0.36
    cx, cy = w * 0.3, h / 2
    sw = r * (0.55 if spec.type == "doughnut" else 1)
    rr = r if spec.type == "doughnut" else r / 2
    parts = [f'<svg viewBox="0 0 {w} {h}" class="chart" font-family="{font}" role="img">',
             f'<g transform="rotate(-90 {cx} {cy})">']
    acc = 0.0
    for i, v in enumerate(vals):
        pct = 100 * v / total
        c = colors[i % len(colors)]
        parts.append(f'<circle class="pie" style="--d:{250 + i * 180}" cx="{cx}" cy="{cy}" r="{rr:.1f}" fill="none" '
                     f'stroke="{c}" stroke-width="{sw:.1f}" pathLength="100" stroke-dasharray="{pct:.3f} 100" '
                     f'stroke-dashoffset="{-acc:.3f}"/>')
        acc += pct
    parts.append("</g>")
    lx, ly = w * 0.62, cy - (len(vals) * 64) / 2 + 30
    for i, (cat, v) in enumerate(zip(spec.categories, vals)):
        c = colors[i % len(colors)]
        y = ly + i * 64
        parts.append(f'<g class="lbl" style="--d:{500 + i * 120}"><rect x="{lx}" y="{y - 26}" width="30" height="30" rx="7" fill="{c}"/>'
                     f'<text x="{lx + 48}" y="{y}" fill="{text}" font-size="30">{escape(cat)}</text>'
                     f'<text x="{w - 40}" y="{y}" fill="{muted}" font-size="30" font-weight="700" text-anchor="end">{100 * v / total:.0f}%</text></g>')
    parts.append("</svg>")
    return "".join(parts)
