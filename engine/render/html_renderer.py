"""Deck JSON -> one self-contained, animated HTML presentation."""
from __future__ import annotations

import base64
import io
import json
from html import escape
from pathlib import Path

from ..brand.colors import is_dark, mix, text_on
from ..schema import Deck, Slide
from .common import AssetResolver, split_number
from .html_assets import CSS, JS
from .svg_charts import chart_svg

FONT_FALLBACK = '"Segoe UI", system-ui, -apple-system, Roboto, "Helvetica Neue", Arial, sans-serif'


def e(text) -> str:
    return escape(str(text or ""))


def rich(text: str) -> str:
    """'Label: detail' -> bold label. Also honours **bold** from the LLM."""
    t = str(text or "").strip()
    if "**" in t:
        parts = t.split("**")
        return "".join(f"<b>{escape(p)}</b>" if i % 2 else escape(p) for i, p in enumerate(parts))
    if ": " in t:
        head, rest = t.split(": ", 1)
        if 0 < len(head) <= 40:
            return f"<b>{escape(head)}:</b> {escape(rest)}"
    return escape(t)


class HtmlRenderer:
    def __init__(self, brand: dict, brand_dir: Path, asset_dirs: list[Path], embed: bool = True):
        self.b = brand
        self.dir = Path(brand_dir)
        self.assets = AssetResolver(list(asset_dirs) + [self.dir / "assets" / "images", self.dir / "assets"])
        self.embed = embed
        self.warnings: list[str] = []
        self._uri_cache: dict[str, str] = {}

    # ---------- helpers ----------
    def warn(self, idx: int, msg: str) -> None:
        self.warnings.append(f"slide {idx}: {msg}")

    def uri(self, path: Path | None, max_side: int = 1920) -> str | None:
        if not path or not Path(path).exists():
            return None
        key = str(path)
        if key in self._uri_cache:
            return self._uri_cache[key]
        from PIL import Image

        with Image.open(path) as im:
            im.load()
            alpha = im.mode in ("RGBA", "LA", "P")
            im = im.convert("RGBA" if alpha else "RGB")
            im.thumbnail((max_side, max_side))
            buf = io.BytesIO()
            if alpha:
                im.save(buf, "PNG", optimize=True)
                mt = "image/png"
            else:
                im.save(buf, "JPEG", quality=84, optimize=True)
                mt = "image/jpeg"
        out = f"data:{mt};base64," + base64.b64encode(buf.getvalue()).decode("ascii")
        self._uri_cache[key] = out
        return out

    def brand_file(self, rel: str | None) -> Path | None:
        if not rel:
            return None
        p = self.dir / rel
        return p if p.exists() else None

    def logo(self, dark: bool, cls: str = "") -> str:
        b = self.b
        pos = b.get("logo_position", "top-right")
        if dark:
            path = self.brand_file(b.get("logo_on_dark")) or self.brand_file(b.get("logo"))
            pill = not b.get("logo_on_dark") and not b.get("logo_has_alpha", True)
        else:
            path, pill = self.brand_file(b.get("logo")), False
        src = self.uri(path, 800)
        if not src:
            return ""
        return f'<img class="logo {pos} {cls} {"pill" if pill else ""}" src="{src}" alt="logo">'

    def chrome(self, idx: int, total: int, dark: bool) -> str:
        pos = self.b.get("logo_position", "top-right")
        pn_cls = "left" if pos == "bottom-right" else ""
        foot_cls = "center" if pos == "bottom-left" or pn_cls else ""
        out = self.logo(dark) + f'<div class="pn {pn_cls}">{idx:02d} / {total:02d}</div>'
        if self.b.get("footer"):
            out += f'<div class="foot {foot_cls}">{e(self.b["footer"])}</div>'
        return out

    def head(self, s: Slide, d0: int = 0) -> str:
        sub = f'<p class="sub a" style="--d:{d0 + 380}">{e(s.subtitle)}</p>' if s.subtitle else ""
        return (f'<div class="head"><h2 class="a fit" data-min="40" style="--d:{d0}">{e(s.title)}</h2>'
                f'<div class="accent-bar" style="--d:{d0 + 260}"></div>{sub}</div>')

    def bullets(self, items: list[str], d0: int = 450, step: int = 110, cls: str = "") -> str:
        items = [i for i in items if str(i).strip()]
        if not items:
            return ""
        lis = "".join(f'<li class="a" style="--d:{d0 + k * step}">{rich(t)}</li>' for k, t in enumerate(items))
        return f'<ul class="bul fit {cls}" data-min="24">{lis}</ul>'

    # ---------- layouts ----------
    def l_title(self, s: Slide, idx, total, deck: Deck):
        mode = self.b.get("title_background", "primary")
        img = self.uri(self.brand_file(self.b.get("background_image"))) if mode == "image" else None
        if img:
            cls, bg = "on-image bg-dark", f'<div class="bgimg kb" style="background-image:url({img})"></div><div class="shade full"></div>'
        elif mode == "background":
            cls, bg = "", '<div class="deco d1"></div><div class="deco d2"></div>'
        else:
            cls, bg = "bg-primary on-primary", '<div class="deco d1"></div><div class="deco d2"></div>'
        dark = bool(img) or (mode == "primary" and is_dark(self.b["colors"]["primary"])) or \
            (mode == "background" and is_dark(self.b["colors"]["background"]))
        subtitle = s.subtitle or deck.subtitle
        sub = f'<p class="sub a" style="--d:700">{e(subtitle)}</p>' if subtitle else ""
        logo = self.logo(dark, "big").replace("top-right", "top-left").replace("bottom-right", "top-left").replace("bottom-left", "top-left")
        return cls, (bg + logo + f'<div class="wrap"><h1 class="a fit" data-min="56" style="--d:150">{e(s.title or deck.title)}</h1>'
                     f'<div class="accent-bar" style="--d:500"></div>{sub}</div>')

    def l_section(self, s: Slide, idx, total, deck, section_no: int = 1):
        sub = f'<p class="sub a" style="--d:600">{e(s.subtitle)}</p>' if s.subtitle else ""
        return "bg-surface", (f'<div class="deco d2"></div><div class="wrap"><div class="num a" style="--d:0">{section_no:02d}</div>'
                              f'<h2 class="a fit" data-min="44" style="--d:250">{e(s.title)}</h2>'
                              f'<div class="accent-bar" style="--d:450"></div>{sub}</div>'
                              + self.chrome(idx, total, is_dark(self.b["colors"]["surface"])))

    def l_bullets(self, s: Slide, idx, total, deck):
        items = s.bullets or s.left + s.right
        if not items:
            self.warn(idx, "bullets slide has no bullets")
        return "", self.head(s) + f'<div class="body">{self.bullets(items)}</div>' + self.chrome(idx, total, self._dark_bg())

    def l_two_column(self, s: Slide, idx, total, deck):
        left, right = s.left, s.right
        if not left and not right and s.bullets:
            half = (len(s.bullets) + 1) // 2
            left, right = s.bullets[:half], s.bullets[half:]
        def col(title, items, d0):
            t = f"<h3>{e(title)}</h3>" if title else ""
            return f'<div class="card a" style="--d:{d0}">{t}{self.bullets(items, d0 + 250, 90)}</div>'
        body = f'<div class="body"><div class="cols">{col(s.left_title, left, 350)}{col(s.right_title, right, 600)}</div></div>'
        return "", self.head(s) + body + self.chrome(idx, total, self._dark_bg())

    def l_chart(self, s: Slide, idx, total, deck):
        if not s.chart or not s.chart.categories or not s.chart.series:
            self.warn(idx, "chart slide without chart data; rendered as bullets")
            return self.l_bullets(s, idx, total, deck)
        c = self.b["colors"]
        grid = mix(c["background"], c["text"], 0.12)
        font = self.b["fonts"]["body"].replace('"', "")
        if s.bullets:
            svg = chart_svg(s.chart, self.b["chart_colors"], c["text"], c["muted"], grid, 1100, 680, font)
            body = (f'<div class="body"><div class="split"><div class="a" style="--d:200;height:100%">{svg}</div>'
                    f'{self.bullets(s.bullets, 900, 140)}</div></div>')
        else:
            svg = chart_svg(s.chart, self.b["chart_colors"], c["text"], c["muted"], grid, 1700, 660, font)
            body = f'<div class="body"><div class="a" style="--d:200;height:100%">{svg}</div></div>'
        return "", self.head(s) + body + self.chrome(idx, total, self._dark_bg())

    def l_table(self, s: Slide, idx, total, deck):
        t = s.table
        if not t or not t.header:
            self.warn(idx, "table slide without table data; rendered as bullets")
            return self.l_bullets(s, idx, total, deck)
        header, rows = t.header[:7], [r[:7] for r in t.rows[:10]]
        if len(t.rows) > 10 or len(t.header) > 7:
            self.warn(idx, "table truncated to 10 rows x 7 columns")
        size = 32 if len(rows) <= 6 else 26
        th = "".join(f"<th>{e(h)}</th>" for h in header)
        trs = "".join(
            f'<tr class="a" style="--d:{400 + k * 90}">' + "".join(f"<td>{rich(c)}</td>" for c in (r + [""] * len(header))[: len(header)]) + "</tr>"
            for k, r in enumerate(rows))
        body = f'<div class="body"><table class="tb" style="font-size:{size}px"><thead><tr class="a" style="--d:250">{th}</tr></thead><tbody>{trs}</tbody></table></div>'
        return "", self.head(s) + body + self.chrome(idx, total, self._dark_bg())

    def l_stats(self, s: Slide, idx, total, deck):
        stats = s.stats[:4]
        if not stats:
            self.warn(idx, "stats slide without stats; rendered as bullets")
            return self.l_bullets(s, idx, total, deck)
        cards = []
        for k, st in enumerate(stats):
            pre, num, suf, dec = split_number(st.value)
            v = (f'<div class="v" data-count="{num}" data-dec="{dec}" data-pre="{e(pre)}" data-suf="{e(suf)}">{e(st.value)}</div>'
                 if num is not None else f'<div class="v">{e(st.value)}</div>')
            cards.append(f'<div class="stat a" style="--d:{300 + k * 160}">{v}<div class="l">{e(st.label)}</div></div>')
        body = (f'<div class="body"><div class="stats" style="grid-template-columns:repeat({len(stats)},1fr)">'
                f'{"".join(cards)}</div></div>')
        return "", self.head(s) + body + self.chrome(idx, total, self._dark_bg())

    def l_image(self, s: Slide, idx, total, deck):
        src = self.uri(self.assets.find(s.image))
        if not src:
            self.warn(idx, f"image '{s.image}' not found; rendered as bullets")
            return self.l_bullets(s, idx, total, deck)
        caption = s.subtitle or (s.bullets[0] if s.bullets else "")
        sub = f'<p class="sub a" style="--d:650">{e(caption)}</p>' if caption else ""
        return "on-image bg-dark", (f'<div class="bgimg kb" style="background-image:url({src})"></div><div class="shade"></div>'
                                    f'<div class="wrap"><h2 class="a fit" data-min="44" style="--d:300">{e(s.title)}</h2>'
                                    f'<div class="accent-bar" style="--d:550"></div>{sub}</div>' + self.chrome(idx, total, True))

    def l_image_text(self, s: Slide, idx, total, deck):
        src = self.uri(self.assets.find(s.image))
        if not src:
            self.warn(idx, f"image '{s.image}' not found; rendered as bullets")
            return self.l_bullets(s, idx, total, deck)
        sub = f'<p class="sub a" style="--d:650">{e(s.subtitle)}</p>' if s.subtitle else ""
        pos = self.b.get("logo_position", "top-right")
        logo = self.logo(self._dark_bg()) if "right" in pos else ""
        return "", (f'<div class="pic reveal"><div class="bgimg kb" style="background-image:url({src})"></div></div>'
                    f'<div class="side"><h2 class="a fit" data-min="40" style="--d:400">{e(s.title)}</h2>'
                    f'<div class="accent-bar" style="--d:600"></div>{sub}{self.bullets(s.bullets, 750, 110)}</div>'
                    + logo + f'<div class="pn">{idx:02d} / {total:02d}</div>')

    def l_quote(self, s: Slide, idx, total, deck):
        q = s.quote or s.title
        by = f'<div class="by a" style="--d:800">&mdash; {e(s.attribution)}</div>' if s.attribution else ""
        return "bg-surface", (f'<div class="mark a" style="--d:0">&ldquo;</div><div class="wrap">'
                              f'<div class="qt a fit" data-min="34" style="--d:250">{e(q)}</div>{by}</div>'
                              + self.chrome(idx, total, is_dark(self.b["colors"]["surface"])))

    def l_closing(self, s: Slide, idx, total, deck):
        dark = is_dark(self.b["colors"]["primary"])
        sub = f'<p class="sub a" style="--d:700">{e(s.subtitle)}</p>' if s.subtitle else ""
        logo = self.logo(dark, "big a")
        return "bg-primary on-primary", ('<div class="deco d1"></div><div class="deco d2"></div>'
                                         f'<div class="wrap">{logo}<h1 class="a fit" data-min="56" style="--d:250">{e(s.title or "Thank you")}</h1>'
                                         f'<div class="accent-bar" style="--d:500"></div>{sub}'
                                         + self.bullets(s.bullets, 850, 110) + "</div>")

    def _dark_bg(self) -> bool:
        return is_dark(self.b["colors"]["background"])

    # ---------- document ----------
    def css_vars(self) -> str:
        c = self.b["colors"]
        on_primary = text_on(c["primary"])
        fh = self.b["fonts"].get("heading") or "Segoe UI"
        fb = self.b["fonts"].get("body") or "Segoe UI"
        letterbox = mix(c["background"], "#000000", 0.85)
        return (":root{"
                f"--bg:{c['background']};--surface:{c['surface']};--text:{c['text']};--muted:{c['muted']};"
                f"--primary:{c['primary']};--accent:{c['accent']};--accent2:{c['accent2']};"
                f"--on-primary:{on_primary};--on-primary-muted:{mix(on_primary, c['primary'], 0.25)};"
                f"--on-primary-grid:{mix(c['primary'], on_primary, 0.2)};--grid:{mix(c['background'], c['text'], 0.12)};"
                f"--hl:{c['primary'] if not is_dark(c['background']) else c['accent']};"
                f"--letterbox:{letterbox};"
                f'--fh:"{fh}",{FONT_FALLBACK};--fb:"{fb}",{FONT_FALLBACK};'
                f"--anim:{self.b.get('animation', 'rise')}"
                "}")

    def render(self, deck: Deck, out: Path) -> list[str]:
        total = len(deck.slides)
        sections, notes = 0, []
        for i, s in enumerate(deck.slides, 1):
            notes.append(s.notes or "")
        slides_html = []
        for i, s in enumerate(deck.slides, 1):
            layout = s.layout
            if layout == "bullets" and s.image and self.assets.find(s.image):
                layout = "image_text"
            if layout == "bullets" and s.chart:
                layout = "chart"
            try:
                if layout == "section":
                    sections += 1
                    cls, inner = self.l_section(s, i, total, deck, sections)
                else:
                    fn = getattr(self, f"l_{layout}", self.l_bullets)
                    cls, inner = fn(s, i, total, deck)
            except Exception as ex:  # never lose the whole deck to one slide
                self.warn(i, f"layout {layout} failed ({ex}); rendered as bullets")
                cls, inner = self.l_bullets(s, i, total, deck)
            slides_html.append(f'<section class="slide s-{layout} {cls}" data-index="{i}" aria-label="Slide {i}">{inner}</section>')

        fonts = "".join(f'<link rel="stylesheet" href="{e(u)}">' for u in self.b.get("font_css", []) or [])
        doc = f"""<!doctype html>
<html lang="en" data-transition="{e(self.b.get('transition', 'slide'))}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(deck.title)}</title>
<meta name="generator" content="deck-agent">
{fonts}
<style>{self.css_vars()}{CSS}</style>
</head>
<body>
<div class="stage" id="stage">
{chr(10).join(slides_html)}
</div>
<div class="progress"><i></i></div>
<div class="notes-panel"></div>
<div class="hint">&larr; &rarr; navigate &middot; F fullscreen &middot; N notes &middot; Ctrl+P PDF</div>
<script type="application/json" id="deck-notes">{json.dumps(notes).replace("</", "<\\/")}</script>
<script>{JS}</script>
</body>
</html>"""
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(doc, encoding="utf-8")
        return self.warnings
