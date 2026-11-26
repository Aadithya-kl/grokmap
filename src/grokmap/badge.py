"""A shields-style SVG badge: `comprehension debt | 23%`."""

from __future__ import annotations

from xml.sax.saxutils import escape


def badge_color(debt_pct: float, ai_lines: int) -> str:
    if ai_lines == 0:
        return "#6b7280"
    if debt_pct < 10:
        return "#0a8f1e"
    if debt_pct < 25:
        return "#7a9a01"
    if debt_pct < 50:
        return "#c77c02"
    return "#c62828"


def _width(text: str) -> int:
    # approximate Verdana 11px advance widths, good enough for a badge
    wide = sum(1 for c in text if c in "mwMW%@")
    narrow = sum(1 for c in text if c in "il.,:;|!' ")
    return int(6.6 * (len(text) - wide - narrow) + 9.5 * wide + 3.6 * narrow) + 12


def render_badge(debt_pct: float, ai_lines: int, label: str = "comprehension debt") -> str:
    value = "no AI code" if ai_lines == 0 else f"{debt_pct:.0f}%"
    color = badge_color(debt_pct, ai_lines)
    lw, vw = _width(label), _width(value)
    total = lw + vw
    lab, val = escape(label), escape(value)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{total}" height="20" role="img" aria-label="{lab}: {val}">
<title>{lab}: {val}</title>
<linearGradient id="s" x2="0" y2="100%"><stop offset="0" stop-color="#bbb" stop-opacity=".1"/><stop offset="1" stop-opacity=".1"/></linearGradient>
<clipPath id="r"><rect width="{total}" height="20" rx="3" fill="#fff"/></clipPath>
<g clip-path="url(#r)"><rect width="{lw}" height="20" fill="#555"/><rect x="{lw}" width="{vw}" height="20" fill="{color}"/><rect width="{total}" height="20" fill="url(#s)"/></g>
<g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" font-size="11">
<text x="{lw / 2:.1f}" y="15" fill="#010101" fill-opacity=".3">{lab}</text><text x="{lw / 2:.1f}" y="14">{lab}</text>
<text x="{lw + vw / 2:.1f}" y="15" fill="#010101" fill-opacity=".3">{val}</text><text x="{lw + vw / 2:.1f}" y="14">{val}</text>
</g></svg>
"""
