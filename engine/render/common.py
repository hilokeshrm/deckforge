"""Helpers shared by the HTML and PPTX renderers."""
from __future__ import annotations

import math
import re
from pathlib import Path

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff"}


class AssetResolver:
    def __init__(self, dirs: list[Path]):
        self.dirs = [Path(d) for d in dirs if d and Path(d).exists()]

    def find(self, name: str | None) -> Path | None:
        if not name:
            return None
        p = Path(name)
        if p.is_absolute() and p.exists():
            return p
        for d in self.dirs:
            if (d / name).exists():
                return d / name
        stem = Path(name).stem.lower()
        for d in self.dirs:  # tolerate a wrong extension / case from the LLM
            for f in d.iterdir():
                if f.suffix.lower() in IMAGE_EXT and f.stem.lower() == stem:
                    return f
        return None


def est_lines(texts: list[str], width: float, size: float, char_w: float = 0.52) -> int:
    per_line = max(1, int(width / (size * char_w)))
    return sum(max(1, math.ceil(len(t) / per_line)) for t in texts)


def fit_size(texts: list[str], width: float, height: float, size: float, min_size: float,
             line_h: float = 1.25, gap: float = 0.0) -> tuple[float, bool]:
    """Largest font size (same units as width/height) at which the text should fit."""
    s = size
    while s >= min_size:
        h = est_lines(texts, width, s) * s * line_h + gap * s * max(0, len(texts) - 1)
        if h <= height:
            return s, True
        s -= 1
    return min_size, False


_NUM = re.compile(r"-?\d[\d,]*\.?\d*")


def split_number(value: str) -> tuple[str, float | None, str, int]:
    """'$1,250.5M' -> ('$', 1250.5, 'M', 1 decimal)."""
    m = _NUM.search(value or "")
    if not m:
        return value, None, "", 0
    raw = m.group(0)
    try:
        num = float(raw.replace(",", ""))
    except ValueError:
        return value, None, "", 0
    decimals = len(raw.split(".")[1]) if "." in raw else 0
    return value[: m.start()], num, value[m.end():], decimals


def fmt_number(v: float, number_format: str | None = None) -> str:
    if abs(v) >= 100 or float(v).is_integer():
        s = f"{v:,.0f}"
    else:
        s = f"{v:,.1f}"
    if number_format and "#" in number_format:
        return number_format.replace("#", s, 1)
    return s
