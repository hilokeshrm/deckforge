from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
import os
import re
import time
import unicodedata
from pathlib import Path

log = logging.getLogger("deckagent")


def setup_logging(log_dir: Path | None = None, level: str = "INFO") -> None:
    fmt = "%(asctime)s %(levelname)-7s %(message)s"
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_dir / "agent.log", encoding="utf-8"))
    logging.basicConfig(level=level, format=fmt, datefmt="%H:%M:%S", handlers=handlers, force=True)


def slugify(text: str, maxlen: int = 48) -> str:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return (text[:maxlen].rstrip("-")) or "untitled"


def now_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def strip_think(text: str) -> str:
    return _THINK_RE.sub("", text or "")


def extract_json(text: str) -> dict:
    """Pull the first JSON object out of an LLM reply (handles fences, <think>, prose)."""
    text = strip_think(text).strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    if start == -1:
        raise ValueError("no JSON object found in reply")
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start : i + 1])
    raise ValueError("unterminated JSON object in reply")


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def image_payload(path: Path, max_side: int = 1568) -> tuple[str, str]:
    """Downscale an image and return (base64, media_type) for LLM vision input."""
    from PIL import Image

    with Image.open(path) as im:
        im.load()
        if im.mode not in ("RGB", "L"):
            bg = Image.new("RGB", im.size, (255, 255, 255))
            rgba = im.convert("RGBA")
            bg.paste(rgba, mask=rgba.split()[-1])
            im = bg
        im.thumbnail((max_side, max_side))
        buf = io.BytesIO()
        im.convert("RGB").save(buf, format="JPEG", quality=88)
    return base64.b64encode(buf.getvalue()).decode("ascii"), "image/jpeg"


def dir_signature(path: Path) -> str:
    """Cheap change detector for a folder: names + sizes + mtimes."""
    h = hashlib.sha1()
    for p in sorted(path.rglob("*")):
        if p.is_file():
            st = p.stat()
            h.update(f"{p.relative_to(path)}|{st.st_size}|{int(st.st_mtime)}".encode())
    return h.hexdigest()


def md_table(rows: list[list[str]]) -> str:
    rows = [[str(c).replace("|", "/").replace("\n", " ").strip() for c in r] for r in rows if r]
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    out = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * width]
    out += ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n".join(out)
