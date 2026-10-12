"""Read colours and fonts out of an existing PowerPoint theme."""
from __future__ import annotations

import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from .colors import is_hex, norm_hex

A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"


def theme_from_pptx(path: Path) -> dict:
    """Return {'scheme': {dk1, lt1, accent1..}, 'fonts': {heading, body}} from the deck's theme."""
    with zipfile.ZipFile(path) as z:
        names = sorted(n for n in z.namelist() if n.startswith("ppt/theme/theme") and n.endswith(".xml"))
        if not names:
            return {}
        root = ET.fromstring(z.read(names[0]))
    scheme = {}
    clr = root.find(f".//{A}clrScheme")
    if clr is not None:
        for el in clr:
            role = el.tag.replace(A, "")
            srgb = el.find(f"{A}srgbClr")
            sys_ = el.find(f"{A}sysClr")
            val = srgb.get("val") if srgb is not None else (sys_.get("lastClr") if sys_ is not None else None)
            if val and is_hex(val):
                scheme[role] = norm_hex(val)
    fonts = {}
    major = root.find(f".//{A}majorFont/{A}latin")
    minor = root.find(f".//{A}minorFont/{A}latin")
    if major is not None and major.get("typeface"):
        fonts["heading"] = major.get("typeface")
    if minor is not None and minor.get("typeface"):
        fonts["body"] = minor.get("typeface")
    return {"scheme": scheme, "fonts": fonts}


def brand_from_theme(theme: dict) -> dict:
    s = theme.get("scheme", {})
    colors = {}
    for role, key in (("primary", "accent1"), ("accent", "accent2"), ("accent2", "accent3"),
                      ("text", "dk1"), ("background", "lt1")):
        if key in s:
            colors[role] = s[key]
    return {"colors": colors, "fonts": theme.get("fonts", {})}
