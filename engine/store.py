"""Persistent state: decks with versions, the job list, brand signatures."""
from __future__ import annotations

import json
import shutil
import threading
import time
from pathlib import Path

from .schema import Deck
from .util import atomic_write_text, slugify


class State:
    """state.json: jobs (for the UI queue) + brand folder signatures. Thread-safe."""

    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.RLock()
        self.data = {"jobs": {}, "brands": {}}
        if path.exists():
            try:
                self.data.update(json.loads(path.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                pass
        for job in self.data["jobs"].values():  # a crash mid-job leaves it "running"
            if job.get("status") == "running":
                job["status"] = "failed"
                job["error"] = "interrupted (agent restarted)"

    def save(self) -> None:
        with self.lock:
            atomic_write_text(self.path, json.dumps(self.data, indent=2))

    def job(self, jid: str, **fields) -> dict:
        with self.lock:
            j = self.data["jobs"].setdefault(jid, {"id": jid, "created": time.time(), "log": []})
            j.update(fields)
            j["updated"] = time.time()
            self.save()
            return dict(j)

    def job_log(self, jid: str, line: str) -> None:
        with self.lock:
            j = self.data["jobs"].setdefault(jid, {"id": jid, "created": time.time(), "log": []})
            j.setdefault("log", []).append(time.strftime("%H:%M:%S ") + line)
            j["log"] = j["log"][-200:]
            j["updated"] = time.time()
            self.save()

    def jobs(self, limit: int = 100) -> list[dict]:
        with self.lock:
            return sorted((dict(j) for j in self.data["jobs"].values()),
                          key=lambda j: j.get("created", 0), reverse=True)[:limit]

    def brand_sig(self, name: str) -> str | None:
        return self.data["brands"].get(name)

    def set_brand_sig(self, name: str, sig: str) -> None:
        with self.lock:
            self.data["brands"][name] = sig
            self.save()


class DeckStore:
    """decks/<name>/ : deck.json (latest), versions/vNNN.json, vNNN.html (+.pptx), assets/, history.jsonl"""

    def __init__(self, root: Path, name: str):
        self.name = slugify(name)
        self.dir = root / self.name
        self.assets = self.dir / "assets"

    def exists(self) -> bool:
        return (self.dir / "deck.json").exists()

    def load(self) -> Deck:
        return Deck.model_validate_json((self.dir / "deck.json").read_text(encoding="utf-8"))

    def versions(self) -> list[int]:
        vdir = self.dir / "versions"
        if not vdir.exists():
            return []
        return sorted(int(p.stem[1:]) for p in vdir.glob("v*.json") if p.stem[1:].isdigit())

    def next_version(self) -> int:
        v = self.versions()
        return (v[-1] + 1) if v else 1

    def load_version(self, v: int) -> Deck:
        return Deck.model_validate_json((self.dir / "versions" / f"v{v:03d}.json").read_text(encoding="utf-8"))

    def save(self, deck: Deck, version: int) -> None:
        text = deck.model_dump_json(indent=2, exclude_none=True)
        atomic_write_text(self.dir / "versions" / f"v{version:03d}.json", text)
        atomic_write_text(self.dir / "deck.json", text)

    def add_assets(self, paths) -> None:
        self.assets.mkdir(parents=True, exist_ok=True)
        for p in paths:
            p = Path(p)
            if p.exists() and not (self.assets / p.name).exists():
                shutil.copy2(p, self.assets / p.name)

    def assets_block(self, captions: dict | None = None) -> str:
        captions = captions or {}
        cap_file = self.dir / "captions.json"
        if cap_file.exists():
            try:
                captions = {**json.loads(cap_file.read_text(encoding="utf-8")), **captions}
            except json.JSONDecodeError:
                pass
        if captions:
            atomic_write_text(cap_file, json.dumps(captions, indent=2))
        files = sorted(self.assets.glob("*")) if self.assets.exists() else []
        if not files:
            return "(none)"
        return "\n".join(f"- {f.name}: {captions.get(f.name) or 'image'}" for f in files)

    def history(self, entry: dict) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        with open(self.dir / "history.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"time": time.time(), **entry}) + "\n")

    def read_history(self) -> list[dict]:
        p = self.dir / "history.jsonl"
        if not p.exists():
            return []
        return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def list_decks(root: Path) -> list[dict]:
    out = []
    for d in sorted(root.iterdir() if root.exists() else [], key=lambda p: p.stat().st_mtime, reverse=True):
        if (d / "deck.json").exists():
            store = DeckStore(root, d.name)
            try:
                deck = store.load()
            except Exception:
                continue
            versions = store.versions()
            out.append({"name": d.name, "title": deck.title, "template": deck.template,
                        "slides": len(deck.slides), "versions": versions,
                        "latest": versions[-1] if versions else None,
                        "updated": d.stat().st_mtime})
    return out
