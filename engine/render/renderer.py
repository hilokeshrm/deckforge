from __future__ import annotations

from pathlib import Path

from ..schema import Deck
from ..util import log


def render_deck(deck: Deck, brand: dict, brand_dir: Path, out_base: Path,
                asset_dirs: list[Path] | None = None, formats=("html",)) -> tuple[dict, list[str]]:
    """Render `deck` to out_base.html (+ out_base.pptx if requested).

    Returns ({format: path}, warnings).
    """
    asset_dirs = [Path(d) for d in (asset_dirs or [])]
    outputs: dict[str, Path] = {}
    warnings: list[str] = []
    if "html" in formats:
        from .html_renderer import HtmlRenderer

        out = out_base.with_suffix(".html")
        warnings += HtmlRenderer(brand, brand_dir, asset_dirs).render(deck, out)
        outputs["html"] = out
    if "pptx" in formats:
        from .pptx_renderer import PptxRenderer

        out = out_base.with_suffix(".pptx")
        try:
            warnings += PptxRenderer(brand, brand_dir, asset_dirs).render(deck, out)
            outputs["pptx"] = out
        except Exception as e:  # pptx is an extra; never fail the HTML deck because of it
            log.exception("pptx export failed")
            warnings.append(f"pptx export failed: {e}")
    return outputs, warnings
