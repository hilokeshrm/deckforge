"""Turns any mix of input files/URLs into one Markdown source + an image asset folder."""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from ..util import log
from . import readers as R


@dataclass
class Asset:
    path: Path
    caption: str = ""

    @property
    def name(self) -> str:
        return self.path.name


@dataclass
class Ingested:
    markdown: str
    assets: list[Asset] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def assets_block(self) -> str:
        if not self.assets:
            return "(none)"
        return "\n".join(f"- {a.name}: {a.caption or 'image'}" for a in self.assets)


class Ingestor:
    def __init__(self, cfg: dict, llm=None):
        self.cfg = cfg.get("ingest", {})
        self.llm = llm

    # OCR + captions go through the vision task (GPU model by default)
    def _ocr(self, image: Path) -> str:
        return self.llm.text("vision", "You transcribe documents exactly.",
                             "Transcribe all text on this page as clean Markdown (keep headings, lists and tables). "
                             "Output only the transcription.", images=[image], max_tokens=4000)

    def _caption(self, image: Path) -> str:
        return self.llm.text("caption", "You describe images for a presentation designer.",
                             "In one sentence: what does this image show, and is it a photo, chart, diagram, "
                             "screenshot, icon or logo? Mention key text or numbers if any.",
                             images=[image], max_tokens=200)

    def run(self, files: list[Path], urls: list[str], brief: str, out_dir: Path) -> Ingested:
        out_dir.mkdir(parents=True, exist_ok=True)
        assets_dir = out_dir / "assets"
        saver = R.ImageSaver(assets_dir, int(self.cfg.get("min_image_px", 120)),
                             int(self.cfg.get("max_extracted_images", 30)))
        vision_ok = self.llm is not None and self.llm.can("vision")
        ocr = self._ocr if (vision_ok and self.cfg.get("ocr_scanned_pdfs", True)) else None
        parts: list[str] = []
        warnings: list[str] = []

        for f in files:
            try:
                md = self._read(f, saver, ocr, out_dir)
            except Exception as e:
                log.warning("could not read %s: %s", f.name, e)
                warnings.append(f"could not read {f.name}: {e}")
                continue
            if md and md.strip():
                parts.append(f"# Source: {f.name}\n\n{md.strip()}")
        for u in urls:
            try:
                parts.append(f"# Source: {u}\n\n{R.read_url(u).strip()}")
            except Exception as e:
                warnings.append(f"could not fetch {u}: {e}")

        assets = [Asset(p) for p in saver.saved]
        captions_file = out_dir / "captions.json"
        if self.cfg.get("caption_images", True) and assets and self.llm is not None and self.llm.can("caption"):
            for a in assets[: int(self.cfg.get("max_captions", 15))]:
                try:
                    a.caption = self._caption(a.path).replace("\n", " ")[:300]
                except Exception as e:
                    log.warning("caption failed for %s: %s", a.name, e)
            captions_file.write_text(json.dumps({a.name: a.caption for a in assets}, indent=2), encoding="utf-8")

        md = "\n\n".join(parts)
        if brief.strip():
            md = "# Brief from the requester\n\n" + brief.strip() + ("\n\n" + md if md else "")
        (out_dir / "source.md").write_text(md, encoding="utf-8")
        return Ingested(md, assets, warnings)

    def _read(self, f: Path, saver: R.ImageSaver, ocr, out_dir: Path) -> str:
        s = f.suffix.lower()
        if s in R.IMAGE_EXT:
            saved = saver.save(f, f.stem)
            if saved is None:  # tiny image: copy as-is so the user's file is still usable
                saved = saver.dir / f.name
                saver.dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, saved)
                saver.saved.append(saved)
            if ocr and any(k in f.stem.lower() for k in ("scan", "page", "screenshot", "doc")):
                return ocr(saved)
            return ""
        if s in R.TEXT_EXT:
            text = R.read_text_file(f)
            return text if s in (".txt", ".md", ".markdown", ".rst") else f"```\n{text[:20000]}\n```"
        if s == ".docx":
            return R.read_docx(f, saver)
        if s == ".pdf":
            return R.read_pdf(f, saver, ocr, int(self.cfg.get("ocr_max_pages", 30)), out_dir)
        if s == ".pptx":
            return R.read_pptx(f, saver)
        if s in R.SHEET_EXT:
            return R.read_sheet(f)
        if s in R.HTML_EXT:
            return R.read_html(R.read_text_file(f))
        if s == ".url":
            for line in R.read_text_file(f).splitlines():
                if line.lower().startswith("url="):
                    return R.read_url(line[4:].strip())
            return ""
        if s in R.AUDIO_EXT:
            return "Transcript:\n\n" + R.transcribe(f, self.cfg.get("whisper_model", "large-v3"))
        text = R.read_text_file(f)
        if text and sum(ch.isprintable() or ch in "\n\t" for ch in text[:2000]) > 0.95 * min(len(text), 2000):
            return text
        raise ValueError(f"unsupported file type {s}")
