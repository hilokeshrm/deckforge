"""Small colour toolkit: parsing, WCAG contrast, mixing, palettes."""
from __future__ import annotations

import colorsys
import re

_HEX = re.compile(r"^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def norm_hex(value: str) -> str:
    m = _HEX.match(str(value).strip())
    if not m:
        raise ValueError(f"not a hex colour: {value!r}")
    h = m.group(1)
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return "#" + h.upper()


def is_hex(value) -> bool:
    return bool(value) and bool(_HEX.match(str(value).strip()))


def hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = norm_hex(h)[1:]
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def rgb_to_hex(rgb) -> str:
    r, g, b = (max(0, min(255, int(round(c)))) for c in rgb)
    return f"#{r:02X}{g:02X}{b:02X}"


def rel_lum(h: str) -> float:
    def ch(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = hex_to_rgb(h)
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a: str, b: str) -> float:
    la, lb = sorted((rel_lum(a), rel_lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def is_dark(h: str) -> bool:
    return rel_lum(h) < 0.25


def mix(a: str, b: str, t: float) -> str:
    """t=0 -> a, t=1 -> b."""
    ra, rb = hex_to_rgb(a), hex_to_rgb(b)
    return rgb_to_hex(tuple(x + (y - x) * t for x, y in zip(ra, rb)))


def hls(h: str) -> tuple[float, float, float]:
    r, g, b = (c / 255 for c in hex_to_rgb(h))
    return colorsys.rgb_to_hls(r, g, b)


def saturation(h: str) -> float:
    return hls(h)[2]


def lightness(h: str) -> float:
    return hls(h)[1]


def hue_shift(h: str, delta: float) -> str:
    hue, light, sat = hls(h)
    r, g, b = colorsys.hls_to_rgb((hue + delta) % 1.0, light, sat)
    return rgb_to_hex((r * 255, g * 255, b * 255))


def distance(a: str, b: str) -> float:
    return sum((x - y) ** 2 for x, y in zip(hex_to_rgb(a), hex_to_rgb(b))) ** 0.5


def text_on(bg: str, light: str = "#FFFFFF", dark: str = "#111827") -> str:
    return light if contrast(light, bg) >= contrast(dark, bg) else dark


def palette_from_image(path, n: int = 6) -> list[tuple[str, float]]:
    """Dominant colours of a logo/image, ignoring transparent and near-white pixels."""
    from PIL import Image

    with Image.open(path) as im:
        im = im.convert("RGBA")
        im.thumbnail((256, 256))
        pixels = [p[:3] for p in im.getdata() if p[3] > 200 and not all(c > 235 for c in p[:3])]
    if not pixels:
        return []
    tmp = Image.new("RGB", (len(pixels), 1))
    tmp.putdata(pixels)
    q = tmp.quantize(colors=n, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette() or []
    counts = sorted(q.getcolors() or [], reverse=True)
    total = sum(c for c, _ in counts) or 1
    return [(rgb_to_hex(pal[i * 3 : i * 3 + 3]), c / total) for c, i in counts]


def roles_from_palette(pal: list[tuple[str, float]]) -> dict:
    """Pick primary/accent colours from a logo palette."""
    if not pal:
        return {}
    chroma = [h for h, _ in pal if saturation(h) > 0.25 and 0.12 < lightness(h) < 0.85]
    primary = chroma[0] if chroma else pal[0][0]
    if lightness(primary) > 0.85:  # basically white/grey logo
        return {}
    accent = next((h for h in chroma[1:] if distance(h, primary) > 90), None) or hue_shift(primary, 0.5)
    out = {"primary": primary, "accent": accent, "accent2": hue_shift(primary, 0.33)}
    darks = [h for h, _ in pal if rel_lum(h) < 0.04]
    if darks:
        out["text"] = darks[0]
    return out
