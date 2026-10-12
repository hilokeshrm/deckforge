"""Turn a folder of brand assets into a reusable template (design/templates/<name>/)."""
from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import yaml

from ..util import atomic_write_text, log, slugify
from .colors import (contrast, distance, hue_shift, is_dark, is_hex, mix, norm_hex,
                     palette_from_image, roles_from_palette, text_on)
from .extract import brand_from_theme, theme_from_pptx

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp"}
DOC_EXT = {".pdf", ".docx", ".txt", ".md"}

DEFAULT_BRAND: dict = {
    "name": "default",
    "colors": {
        "background": "#FFFFFF",
        "surface": None,
        "text": "#111827",
        "muted": None,
        "primary": "#1D4ED8",
        "accent": "#F59E0B",
        "accent2": "#10B981",
    },
    "chart_colors": [],
    "fonts": {"heading": "Segoe UI Semibold", "body": "Segoe UI"},
    "sizes": {"title": 44, "heading": 32, "body": 22, "small": 12},
    "logo": None,            # path relative to the template folder
    "logo_on_dark": None,    # white version for dark backgrounds (auto-made when possible)
    "logo_has_alpha": True,
    "logo_position": "top-right",   # top-right | top-left | bottom-right | bottom-left
    "title_background": "primary",  # primary | image | background
    "background_image": None,
    "images": [],
    "footer": "",
    "tone": "clear, confident, concise",
    "base_pptx": None,       # copied sample deck: its masters/backgrounds are reused (pptx export)
    "use_master_background": True,
    # HTML deck motion
    "transition": "slide",   # fade | slide | zoom   (between slides)
    "animation": "rise",     # rise | fade | zoom | slide  (elements entering a slide)
    "font_css": [],          # optional stylesheet URLs, e.g. Google Fonts links for the brand fonts
}


def _merge(base: dict, patch: dict) -> dict:
    for k, v in (patch or {}).items():
        if v in (None, "", {}, []):
            continue
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v
    return base


def finalize_brand(brand: dict) -> dict:
    """Fill derived colours and fix unreadable combinations."""
    b = copy.deepcopy(DEFAULT_BRAND)
    _merge(b, brand)
    c = b["colors"]
    for k, v in list(c.items()):
        if v is not None:
            try:
                c[k] = norm_hex(v)
            except ValueError:
                log.warning("brand colour %s=%r is not a hex value, ignoring", k, v)
                c[k] = DEFAULT_BRAND["colors"].get(k)
    for k in ("background", "text", "primary", "accent", "accent2"):
        c[k] = c.get(k) or DEFAULT_BRAND["colors"][k]
    if contrast(c["text"], c["background"]) < 4.5:
        c["text"] = text_on(c["background"])
    c["muted"] = c.get("muted") or mix(c["text"], c["background"], 0.42)
    c["surface"] = c.get("surface") or (
        mix(c["background"], c["primary"], 0.07) if not is_dark(c["background"]) else mix(c["background"], "#FFFFFF", 0.08))
    if distance(c["accent"], c["primary"]) < 60:  # accent indistinguishable from primary
        c["accent"] = hue_shift(c["primary"], 0.5)
    if not b.get("chart_colors"):
        b["chart_colors"] = [c["primary"], c["accent"], c["accent2"],
                             mix(c["primary"], c["background"], 0.45),
                             mix(c["accent"], c["background"], 0.45), c["muted"]]
    b["chart_colors"] = [norm_hex(x) for x in b["chart_colors"] if is_hex(x)]
    return b


def load_brand(templates_root: Path, name: str | None) -> tuple[dict, Path]:
    """Return (brand dict, template folder). Unknown names fall back to the built-in default."""
    name = slugify(name or "default")
    folder = templates_root / name
    f = folder / "brand.json"
    if f.exists():
        return finalize_brand(json.loads(f.read_text(encoding="utf-8"))), folder
    if name != "default":
        log.warning("template '%s' not found, using default", name)
    folder = templates_root / "default"
    f = folder / "brand.json"
    if f.exists():
        return finalize_brand(json.loads(f.read_text(encoding="utf-8"))), folder
    return finalize_brand({"name": "default"}), folder


def list_templates(templates_root: Path) -> list[dict]:
    out = []
    for d in sorted(templates_root.iterdir()) if templates_root.exists() else []:
        f = d / "brand.json"
        if f.exists():
            b = json.loads(f.read_text(encoding="utf-8"))
            out.append({"name": d.name, "colors": b.get("colors", {}), "fonts": b.get("fonts", {}),
                        "logo": b.get("logo"), "preview": (d / "preview.html").exists(),
                        "notes": b.get("build_notes", [])})
    if not any(t["name"] == "default" for t in out):
        out.insert(0, {"name": "default", "colors": finalize_brand({})["colors"],
                       "fonts": DEFAULT_BRAND["fonts"], "logo": None, "preview": False})
    return out


def _to_png(src: Path, dst: Path) -> Path | None:
    from PIL import Image

    try:
        with Image.open(src) as im:
            im.load()
            mode = "RGBA" if im.mode in ("RGBA", "LA", "P") else "RGB"
            dst.parent.mkdir(parents=True, exist_ok=True)
            im.convert(mode).save(dst, "PNG")
        return dst
    except Exception as e:
        log.warning("could not read image %s: %s", src.name, e)
        return None


def _logo_variants(logo: Path, out_dir: Path) -> dict:
    """Detect transparency and make a white version of a dark logo for dark slides."""
    from PIL import Image

    with Image.open(logo) as im:
        im = im.convert("RGBA")
        alpha = im.split()[-1]
        has_alpha = alpha.getextrema()[0] < 250
        info = {"logo_has_alpha": has_alpha}
        if not has_alpha:
            return info
        px = [p for p in im.getdata() if p[3] > 128]
        if not px:
            return info
        lum = sum(0.2126 * r + 0.7152 * g + 0.0722 * b for r, g, b, _ in px) / len(px) / 255
        if lum < 0.6:  # dark logo -> needs a light version on dark backgrounds
            white = Image.new("RGBA", im.size, (255, 255, 255, 0))
            white.putalpha(alpha)
            p = out_dir / "logo_on_dark.png"
            white.save(p)
            info["logo_on_dark"] = "assets/logo_on_dark.png"
        else:
            info["logo_on_dark"] = "assets/logo.png"
    return info


def build_brand(src_dir: Path, templates_root: Path, llm=None, name: str | None = None,
                cfg: dict | None = None, preview: bool = True) -> Path:
    """Build design/templates/<name>/ from a brand folder.

    Precedence (last wins): defaults < logo colours < style guide (LLM) < sample .pptx theme < brand.yaml
    """
    src_dir = Path(src_dir)
    name = slugify(name or src_dir.name)
    out = templates_root / name
    assets = out / "assets"
    if out.exists():
        shutil.rmtree(out)
    (assets / "images").mkdir(parents=True, exist_ok=True)

    files = [p for p in sorted(src_dir.rglob("*")) if p.is_file() and not p.name.startswith((".", "~$"))]
    brand: dict = {"name": name}
    notes: list[str] = []

    # 1. logo -> colours
    logos = [p for p in files if "logo" in p.stem.lower() and p.suffix.lower() in IMAGE_EXT]
    svgs = [p for p in files if "logo" in p.stem.lower() and p.suffix.lower() == ".svg"]
    if svgs and not logos:
        notes.append("SVG logos aren't supported directly; export the logo as PNG.")
    if logos:
        logo = _to_png(logos[0], assets / "logo.png")
        if logo:
            brand["logo"] = "assets/logo.png"
            brand.update(_logo_variants(logo, assets))
            roles = roles_from_palette(palette_from_image(logo))
            if roles:
                _merge(brand, {"colors": roles})
                notes.append(f"colours from logo: {roles}")

    # 2. style guide documents -> LLM
    guides = [p for p in files if p.suffix.lower() in DOC_EXT and p.name.lower() not in ("brand.yaml", "brand.yml")]
    if guides and llm is not None and llm.can("brand"):
        from ..ingest.readers import read_text_only
        from ..schema import BrandPatch

        text = "\n\n".join(read_text_only(p) for p in guides)[:20000]
        if text.strip():
            try:
                patch = llm.structured(
                    "brand",
                    "You extract brand identity settings from brand guidelines.",
                    "Extract the brand colours (as #RRGGBB hex, roles: primary, accent, accent2, background, text), "
                    "heading and body font families, a short tone-of-voice description and a footer line if one is "
                    "specified. Only include values that are stated in the text.\n\nGUIDELINES:\n" + text,
                    BrandPatch,
                    max_tokens=2000,
                )
                _merge(brand, patch.model_dump())
                notes.append("settings from style guide")
            except Exception as e:
                notes.append(f"style guide skipped: {e}")

    # 3. sample deck -> theme colours/fonts + reuse its masters
    decks = [p for p in files if p.suffix.lower() in (".pptx", ".potx")]
    if decks:
        try:
            _merge(brand, brand_from_theme(theme_from_pptx(decks[0])))
            if decks[0].suffix.lower() == ".pptx":
                shutil.copy2(decks[0], out / "base.pptx")
                brand["base_pptx"] = "base.pptx"
            notes.append(f"theme from {decks[0].name}")
        except Exception as e:
            notes.append(f"sample deck skipped: {e}")

    # 4. images
    imgs = []
    for p in files:
        if p.suffix.lower() in IMAGE_EXT and "logo" not in p.stem.lower():
            dst = _to_png(p, assets / "images" / (slugify(p.stem) + ".png"))
            if dst:
                rel = f"assets/images/{dst.name}"
                if any(k in p.stem.lower() for k in ("background", "bg", "cover", "hero")) and not brand.get("background_image"):
                    brand["background_image"] = rel
                    brand["title_background"] = "image"
                imgs.append(rel)
    brand["images"] = imgs

    # 5. explicit settings win
    for yml in (src_dir / "brand.yaml", src_dir / "brand.yml"):
        if yml.exists():
            data = yaml.safe_load(yml.read_text(encoding="utf-8")) or {}
            _merge(brand, data)
            notes.append("brand.yaml applied")

    final = finalize_brand(brand)
    final["name"] = name
    final["build_notes"] = notes
    atomic_write_text(out / "brand.json", json.dumps(final, indent=2))
    log.info("template '%s' built: %s", name, "; ".join(notes) or "defaults")

    if preview:
        try:
            make_template_preview(final, out, cfg or {})
        except Exception as e:
            log.warning("template preview failed: %s", e)
    return out


def make_template_preview(brand: dict, folder: Path, cfg: dict) -> Path:
    """Render a sample deck with every layout so the template can be checked at a glance."""
    from ..qa.preview import contact_sheet, html_to_pngs
    from ..render.renderer import render_deck
    from ..schema import Deck

    image = brand["images"][0].split("/")[-1] if brand.get("images") else None
    sample = {
        "title": f"{brand['name'].title()} template",
        "subtitle": "Layout preview",
        "template": brand["name"],
        "slides": [
            {"layout": "title", "title": f"{brand['name'].title()} template", "subtitle": "Layout preview"},
            {"layout": "section", "title": "Section divider", "subtitle": "Part one"},
            {"layout": "bullets", "title": "Bullets keep one idea per line",
             "bullets": ["Revenue: up 18% year on year", "Two new markets opened in Q3",
                         "Customer churn fell below 3%", "Hiring plan on track"]},
            {"layout": "two_column", "title": "Compare two options",
             "left_title": "Today", "left": ["Manual reports", "Weekly updates"],
             "right_title": "Next quarter", "right": ["Automated dashboards", "Daily updates"]},
            {"layout": "chart", "title": "Charts use brand colours",
             "chart": {"type": "column", "categories": ["Q1", "Q2", "Q3", "Q4"],
                       "series": [{"name": "2025", "values": [12, 15, 14, 19]},
                                  {"name": "2026", "values": [14, 18, 21, 24]}]}},
            {"layout": "stats", "title": "Headline numbers",
             "stats": [{"value": "18%", "label": "Revenue growth"}, {"value": "2.9%", "label": "Churn"},
                       {"value": "4", "label": "New markets"}]},
            {"layout": "table", "title": "Tables stay editable",
             "table": {"header": ["Region", "Q3", "Q4"], "rows": [["North", "1.2M", "1.4M"], ["South", "0.9M", "1.1M"]]}},
            {"layout": "quote", "quote": "Good design is as little design as possible.", "attribution": "Dieter Rams"},
        ] + ([{"layout": "image_text", "title": "Picture and text", "image": image,
               "bullets": ["Brand images are reusable", "Cropped to fit automatically"]}] if image else [])
          + [{"layout": "closing", "title": "Thank you", "subtitle": "questions@example.com"}],
    }
    deck = Deck.model_validate(sample)
    outputs, _ = render_deck(deck, brand, folder, folder / "preview",
                             asset_dirs=[folder / "assets" / "images"], formats=("html",))
    html = outputs["html"]
    pngs = html_to_pngs(html, folder / "preview-slides", len(deck.slides))
    if pngs:
        contact_sheet(pngs, folder / "preview.png", cols=3)
    return html
