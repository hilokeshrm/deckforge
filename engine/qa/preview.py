"""Slide screenshots for QA and thumbnails.

HTML decks are captured with Playwright (headless Chromium) in ?static mode,
so every slide shows its final, fully-animated state. PPTX previews use LibreOffice.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from ..util import log


def playwright_available() -> bool:
    try:
        import playwright.sync_api  # noqa: F401
        return True
    except ImportError:
        return False


def html_to_pngs(html: Path, out_dir: Path, count: int | None = None, width: int = 1600) -> list[Path]:
    if not playwright_available():
        log.info("playwright not installed: skipping slide screenshots")
        return []
    from playwright.sync_api import sync_playwright

    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("slide-*.png"):
        old.unlink()
    height = int(width * 9 / 16)
    paths: list[Path] = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": width, "height": height})
            page.goto(Path(html).resolve().as_uri() + "?static=1#1")
            page.wait_for_function("window.deckReady === true", timeout=30000)
            n = count or page.evaluate("window.deck.count")
            for i in range(n):
                page.evaluate(f"window.deck.go({i})")
                page.wait_for_timeout(120)
                path = out_dir / f"slide-{i + 1:02d}.png"
                page.screenshot(path=str(path))
                paths.append(path)
            browser.close()
    except Exception as e:
        log.warning("html screenshots failed: %s (run `playwright install chromium`)", e)
    return paths


def html_to_pdf(html: Path, out_pdf: Path) -> Path | None:
    if not playwright_available():
        return None
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(Path(html).resolve().as_uri() + "?static=1")
            page.wait_for_function("window.deckReady === true", timeout=30000)
            page.pdf(path=str(out_pdf), width="1920px", height="1080px", print_background=True)
            browser.close()
        return out_pdf
    except Exception as e:
        log.warning("pdf export failed: %s", e)
        return None


def find_soffice(value: str | None = "auto") -> str | None:
    if value and value != "auto" and Path(value).exists():
        return value
    for name in ("soffice", "libreoffice"):
        p = shutil.which(name)
        if p:
            return p
    for c in (r"C:\Program Files\LibreOffice\program\soffice.exe",
              r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
              "/Applications/LibreOffice.app/Contents/MacOS/soffice"):
        if Path(c).exists():
            return c
    return None


def pptx_to_pngs(pptx: Path, out_dir: Path, soffice: str, zoom: float = 1.25) -> list[Path]:
    import fitz

    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        profile = Path(tmp, "profile").as_uri()
        try:
            subprocess.run([soffice, "--headless", "--norestore", f"-env:UserInstallation={profile}",
                            "--convert-to", "pdf", "--outdir", tmp, str(pptx)],
                           check=True, timeout=300, capture_output=True)
        except (subprocess.SubprocessError, OSError) as e:
            log.warning("LibreOffice conversion failed: %s", e)
            return []
        pdf = Path(tmp) / (Path(pptx).stem + ".pdf")
        if not pdf.exists():
            return []
        paths = []
        with fitz.open(pdf) as doc:
            for i, page in enumerate(doc):
                p = out_dir / f"slide-{i + 1:02d}.png"
                page.get_pixmap(matrix=fitz.Matrix(zoom, zoom)).save(str(p))
                paths.append(p)
    return paths


def contact_sheet(pngs: list[Path], out: Path, cols: int = 3, thumb_w: int = 480, start: int = 1) -> Path:
    """Grid of numbered thumbnails (used for the vision review and template previews)."""
    from PIL import Image, ImageDraw

    thumbs = []
    for p in pngs:
        with Image.open(p) as im:
            im = im.convert("RGB")
            im.thumbnail((thumb_w, thumb_w))
            thumbs.append(im.copy())
    if not thumbs:
        raise ValueError("no images for contact sheet")
    tw, th = thumbs[0].size
    pad = 16
    rows = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (tw + pad) + pad, rows * (th + pad) + pad), (40, 40, 46))
    draw = ImageDraw.Draw(sheet)
    for k, im in enumerate(thumbs):
        x = pad + (k % cols) * (tw + pad)
        y = pad + (k // cols) * (th + pad)
        sheet.paste(im, (x, y))
        draw.rectangle([x, y, x + 44, y + 28], fill=(220, 38, 38))
        draw.text((x + 8, y + 7), str(start + k), fill=(255, 255, 255))
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return out
