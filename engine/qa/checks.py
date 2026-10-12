"""Content and brand checks that don't need a model."""
from __future__ import annotations

from ..brand.colors import contrast, text_on
from ..schema import Deck


def static_checks(deck: Deck, qa: dict) -> list[str]:
    max_b = int(qa.get("max_bullets", 6))
    max_w = int(qa.get("max_bullet_words", 18))
    out = []
    if not deck.slides:
        return ["deck has no slides"]
    for i, s in enumerate(deck.slides, 1):
        if not s.title and s.layout not in ("quote", "image"):
            out.append(f"slide {i}: missing title")
        if len(s.title.split()) > 14:
            out.append(f"slide {i}: title is long ({len(s.title.split())} words)")
        items = s.bullets + s.left + s.right
        if len(s.bullets) > max_b:
            out.append(f"slide {i}: {len(s.bullets)} bullets (max {max_b})")
        for b in items:
            if len(b.split()) > max_w:
                out.append(f"slide {i}: bullet too long: '{b[:50]}...'")
        if s.chart:
            n = len(s.chart.categories)
            for ser in s.chart.series:
                if len(ser.values) != n:
                    out.append(f"slide {i}: series '{ser.name}' has {len(ser.values)} values for {n} categories")
        if len(s.stats) > 4:
            out.append(f"slide {i}: {len(s.stats)} stats (only 4 are shown)")
    return out


def brand_checks(brand: dict) -> list[str]:
    c = brand["colors"]
    out = []
    if contrast(c["text"], c["background"]) < 4.5:
        out.append("body text contrast is below WCAG AA (4.5:1)")
    if contrast(text_on(c["primary"]), c["primary"]) < 3:
        out.append("text on the primary colour is hard to read")
    return out
