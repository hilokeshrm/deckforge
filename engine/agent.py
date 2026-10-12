"""The loop: watch inbox/ and brand-inbox/, run each request through ingest -> plan -> render -> QA."""
from __future__ import annotations

import os
import shutil
import threading
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .brand import build_brand, load_brand
from .ingest import Ingestor
from .llm import LLM
from .planner import edit_deck, fix_instruction, plan_deck, review_slides
from .qa.checks import brand_checks, static_checks
from .qa.preview import contact_sheet, html_to_pdf, html_to_pngs
from .render import render_deck
from .schema import Deck
from .store import DeckStore, State
from .util import atomic_write_text, dir_signature, log, now_id, slugify

ACTIONS = ("create", "edit", "restyle", "revert", "brand", "export", "save")


@dataclass
class Request:
    action: str = "create"
    deck: str | None = None
    template: str | None = None
    slides: int | None = None
    audience: str | None = None
    version: int | None = None
    formats: list[str] = field(default_factory=list)
    instructions: str = ""
    files: list[Path] = field(default_factory=list)
    urls: list[str] = field(default_factory=list)


def _front_matter(text: str) -> tuple[dict, str]:
    if text.startswith("---"):
        parts = text.split("\n---", 1)
        if len(parts) == 2:
            meta = yaml.safe_load(parts[0][3:]) or {}
            body = parts[1].split("\n", 1)[1] if "\n" in parts[1] else ""
            if isinstance(meta, dict):
                return meta, body.strip()
    return {}, text.strip()


def parse_request(entry: Path) -> Request:
    """An inbox entry is a .md/.txt request, a single document, or a folder (request.md + files)."""
    meta, body, files = {}, "", []
    if entry.is_dir():
        req_file = next((entry / n for n in ("request.md", "request.txt", "request.yaml") if (entry / n).exists()), None)
        if req_file:
            meta, body = _front_matter(req_file.read_text(encoding="utf-8", errors="replace"))
        files = [p for p in sorted(entry.rglob("*"))
                 if p.is_file() and p != req_file and not p.name.startswith((".", "~$"))]
    elif entry.suffix.lower() in (".md", ".txt"):
        meta, body = _front_matter(entry.read_text(encoding="utf-8", errors="replace"))
    else:
        files = [entry]
    action = str(meta.get("action", "create")).lower().strip()
    if action not in ACTIONS:
        raise ValueError(f"unknown action '{action}' (use one of {', '.join(ACTIONS)})")
    urls = meta.get("urls") or meta.get("sources") or []
    if isinstance(urls, str):
        urls = [urls]
    formats = meta.get("formats") or []
    if isinstance(formats, str):
        formats = [f.strip() for f in formats.split(",")]
    return Request(
        action=action,
        deck=meta.get("deck"),
        template=meta.get("template"),
        slides=int(meta["slides"]) if meta.get("slides") else None,
        audience=meta.get("audience"),
        version=int(meta["version"]) if meta.get("version") else None,
        formats=[str(f).lower() for f in formats],
        instructions=body,
        files=files,
        urls=[str(u) for u in urls],
    )


class Agent:
    def __init__(self, cfg: dict, llm=None):
        self.cfg = cfg
        self.paths = cfg["paths"]
        self.llm = llm or LLM(cfg)
        self.state = State(self.paths["state"])
        self.ingestor = Ingestor(cfg, self.llm)
        self.busy = threading.Lock()
        self.current: str | None = None
        self.wake = threading.Event()  # set by the UI to skip the poll wait

    # ---------------- loop ----------------
    def run_forever(self, stop: threading.Event | None = None) -> None:
        stop = stop or threading.Event()
        poll = float(self.cfg.get("agent", {}).get("poll_seconds", 15))
        log.info("agent watching %s (every %ss)", self.paths["inbox"], poll)
        while not stop.is_set():
            try:
                self.tick()
            except Exception:
                log.exception("agent tick failed")
            self.wake.wait(poll)
            self.wake.clear()

    def tick(self) -> int:
        with self.busy:
            self.sync_brands()
            n = 0
            for entry in self.pending():
                self.process(entry)
                n += 1
            return n

    def pending(self) -> list[Path]:
        settle = float(self.cfg.get("agent", {}).get("settle_seconds", 3))
        now = time.time()
        items = []
        for p in self.paths["inbox"].iterdir():
            if p.name.startswith((".", "_", "~$")) or p.suffix in (".tmp", ".part", ".crdownload"):
                continue
            stamps = [p.stat().st_mtime]
            if p.is_dir():
                stamps += [c.stat().st_mtime for c in p.rglob("*")]
            mtime = max(stamps)
            if now - mtime >= settle:
                items.append((mtime, p))
        return [p for _, p in sorted(items)]

    def sync_brands(self) -> None:
        root = self.paths["brand_inbox"]
        for d in sorted(root.iterdir()):
            if not d.is_dir() or d.name.startswith((".", "_")):
                continue
            sig = dir_signature(d)
            name = slugify(d.name)
            if self.state.brand_sig(name) == sig:
                continue
            log.info("brand folder changed: %s", d.name)
            try:
                build_brand(d, self.paths["templates"], self.llm, name=name, cfg=self.cfg)
            except Exception:
                log.exception("brand build failed for %s", d.name)
            self.state.set_brand_sig(name, sig)

    # ---------------- one request ----------------
    def process(self, entry: Path) -> dict:
        jid = slugify(entry.stem if entry.is_file() else entry.name, 60)
        existing = self.state.data["jobs"].get(jid)
        if existing and existing.get("status") != "queued":  # queued = pre-registered by the UI
            jid = f"{jid}-{now_id()}"
        work = self.paths["work"] / jid
        inp = work / "input"
        inp.mkdir(parents=True, exist_ok=True)
        moved = inp / entry.name
        shutil.move(str(entry), str(moved))
        self.current = jid
        self.state.job(jid, status="running", started=time.time(), error=None)
        self.state.job_log(jid, f"picked up {entry.name}")
        attempts = int(self.cfg.get("agent", {}).get("max_attempts", 2))
        result: dict = {}
        try:
            req = parse_request(moved)
            self.state.job(jid, action=req.action, deck=req.deck, template=req.template,
                           title=(req.instructions[:80] or (req.files[0].name if req.files else req.action)))
            for attempt in range(1, attempts + 1):
                try:
                    result = self.handle(req, jid, work)
                    break
                except Exception as e:
                    self.state.job_log(jid, f"attempt {attempt} failed: {e}")
                    log.exception("job %s attempt %d failed", jid, attempt)
                    if attempt == attempts:
                        raise
            self.state.job(jid, status="done", finished=time.time(), **result)
            self.state.job_log(jid, "done")
        except Exception as e:
            self.state.job(jid, status="failed", finished=time.time(), error=str(e),
                           traceback=traceback.format_exc()[-4000:])
            result = {"error": str(e)}
        finally:
            self.current = None
            done = self.paths["done"] / jid
            done.mkdir(parents=True, exist_ok=True)
            if inp.exists():
                shutil.move(str(inp), str(done / "input"))
            self._write_result(done / "result.md", self.state.data["jobs"][jid])
        return result

    def _write_result(self, path: Path, job: dict) -> None:
        lines = [f"# {job['id']}", "", f"- status: **{job.get('status')}**", f"- action: {job.get('action')}"]
        if job.get("deck"):
            lines.append(f"- deck: {job['deck']} (v{job.get('version', '?')})")
        for k, v in (job.get("outputs") or {}).items():
            lines.append(f"- {k}: {v}")
        if job.get("error"):
            lines += ["", "## Error", "", "```", job.get("traceback") or job["error"], "```"]
        if job.get("warnings"):
            lines += ["", "## Warnings", ""] + [f"- {w}" for w in job["warnings"]]
        lines += ["", "## Log", ""] + [f"    {l}" for l in job.get("log", [])]
        atomic_write_text(path, "\n".join(lines) + "\n")

    def handle(self, req: Request, jid: str, work: Path) -> dict:
        say = lambda msg: self.state.job_log(jid, msg)  # noqa: E731
        decks_root, templates = self.paths["decks"], self.paths["templates"]

        if req.action == "brand":
            name = slugify(req.template or req.deck or jid)
            src = work / "brand-src"
            src.mkdir(parents=True, exist_ok=True)
            for f in req.files:
                shutil.copy2(f, src / f.name)
            if req.instructions:
                (src / "notes.md").write_text(req.instructions, encoding="utf-8")
            say(f"building template '{name}' from {len(req.files)} file(s)")
            out = build_brand(src, templates, self.llm, name=name, cfg=self.cfg)
            return {"template": name, "outputs": {"template": str(out)}}

        if req.action == "create":
            say(f"reading {len(req.files)} file(s), {len(req.urls)} url(s)")
            ing = self.ingestor.run(req.files, req.urls, req.instructions, work / "ingest")
            if not ing.markdown.strip():
                raise ValueError("nothing to build from: add documents, URLs or a written brief")
            brand, brand_dir = load_brand(templates, req.template or self.cfg["defaults"].get("template"))
            say(f"planning deck with template '{brand['name']}' ({len(ing.markdown):,} chars of source)")
            deck = plan_deck(self.llm, ing.markdown, ing.assets_block(), brand,
                             {"instructions": req.instructions, "slides": req.slides, "audience": req.audience}, self.cfg)
            name = slugify(req.deck or deck.title)
            store = DeckStore(decks_root, name)
            k = 2
            while store.exists():
                store = DeckStore(decks_root, f"{name}-{k}")
                k += 1
            store.add_assets(a.path for a in ing.assets)
            store.assets_block({a.name: a.caption for a in ing.assets})
            res = self.produce(store, deck, brand, brand_dir, jid, req, note="created")
            res["warnings"] = ing.warnings + res.get("warnings", [])
            return res

        store = DeckStore(decks_root, req.deck or "")
        if not req.deck or not store.exists():
            raise ValueError(f"deck '{req.deck}' not found (set `deck:` to an existing deck name)")
        deck = store.load()

        if req.action == "export":
            v = store.versions()[-1]
            brand, brand_dir = load_brand(templates, deck.template)
            fmts = req.formats or ["pptx", "pdf"]
            return self.export(store, deck, v, brand, brand_dir, fmts)

        if req.action == "save":  # hand-edited deck JSON from the UI: no LLM involved
            src = next((f for f in req.files if f.name.endswith(".json")), None)
            if not src:
                raise ValueError("save request needs a deck .json file")
            deck = Deck.model_validate_json(src.read_text(encoding="utf-8"))
            if req.template:
                deck.template = slugify(req.template)
            brand, brand_dir = load_brand(templates, deck.template)
            return self.produce(store, deck, brand, brand_dir, jid, req, note="manual edit")

        extra = ""
        if req.files or req.urls:
            ing = self.ingestor.run(req.files, req.urls, "", work / "ingest")
            store.add_assets(a.path for a in ing.assets)
            store.assets_block({a.name: a.caption for a in ing.assets})
            extra = ing.markdown

        if req.action == "revert":
            if not req.version or req.version not in store.versions():
                raise ValueError(f"version {req.version} not found; available: {store.versions()}")
            deck = store.load_version(req.version)
            note = f"reverted to v{req.version}"
        elif req.action == "restyle":
            if req.template:
                deck.template = slugify(req.template)
            if req.instructions:
                say("applying restyle instructions")
                deck = edit_deck(self.llm, deck, req.instructions, store.assets_block(), extra)
            note = f"restyled with '{deck.template}'"
        else:  # edit
            if not req.instructions and not extra:
                raise ValueError("edit request has no instructions")
            say("applying change request")
            deck = edit_deck(self.llm, deck, req.instructions or "Incorporate the new source material.",
                             store.assets_block(), extra)
            if req.template:
                deck.template = slugify(req.template)
            note = "edited: " + (req.instructions[:100] or "new material")
        brand, brand_dir = load_brand(templates, deck.template)
        return self.produce(store, deck, brand, brand_dir, jid, req, note=note)

    # ---------------- render + QA ----------------
    def formats(self, req: Request | None = None) -> tuple[str, ...]:
        fmts = list((self.cfg.get("render") or {}).get("formats", ["html"]))
        if req and req.formats:
            fmts += req.formats
        fmts = [f for f in dict.fromkeys(fmts) if f in ("html", "pptx", "pdf")]
        if "html" not in fmts:
            fmts.insert(0, "html")
        return tuple(fmts)

    def produce(self, store: DeckStore, deck: Deck, brand: dict, brand_dir: Path, jid: str,
                req: Request | None = None, note: str = "") -> dict:
        say = lambda msg: self.state.job_log(jid, msg)  # noqa: E731
        qa = self.cfg.get("qa", {})
        v = store.next_version()
        base = store.dir / f"v{v:03d}"
        fmts = self.formats(req)
        render_fmts = tuple(f for f in fmts if f != "pdf")
        say(f"rendering v{v:03d} ({', '.join(fmts)})")
        outputs, warns = render_deck(deck, brand, brand_dir, base, [store.assets], render_fmts)
        pngs = []
        prev_dir = store.dir / "preview" / f"v{v:03d}"
        if qa.get("render_previews", True):
            pngs = html_to_pngs(outputs["html"], prev_dir, len(deck.slides))
        if pngs and qa.get("vision_review", True) and self.llm.can("review"):
            say("visual QA of rendered slides")
            sheets = []
            for k in range(0, len(pngs), 9):
                sheet = contact_sheet(pngs[k:k + 9], prev_dir / f"sheet-{k // 9 + 1}.png", start=k + 1)
                sheets.append((k + 1, sheet))
            try:
                review = review_slides(self.llm, sheets)
                if review.issues:
                    say(f"QA found {len(review.issues)} issue(s)")
                    warns += [f"QA slide {i.slide}: {i.problem}" for i in review.issues]
                    if qa.get("auto_fix", True):
                        say("applying QA fixes")
                        deck = edit_deck(self.llm, deck, fix_instruction(review), store.assets_block())
                        outputs, warns2 = render_deck(deck, brand, brand_dir, base, [store.assets], render_fmts)
                        warns += warns2
                        pngs = html_to_pngs(outputs["html"], prev_dir, len(deck.slides))
            except Exception as e:
                warns.append(f"visual QA skipped: {e}")
        if "pdf" in fmts:
            pdf = html_to_pdf(outputs["html"], base.with_suffix(".pdf"))
            if pdf:
                outputs["pdf"] = pdf
        warns += static_checks(deck, qa) + brand_checks(brand)
        store.save(deck, v)
        store.history({"version": v, "job": jid, "note": note, "template": deck.template,
                       "outputs": {k: Path(p).name for k, p in outputs.items()}})
        say(f"saved {store.name} v{v:03d}")
        return {"deck": store.name, "version": v, "warnings": warns,
                "outputs": {k: str(p) for k, p in outputs.items()}}

    def export(self, store: DeckStore, deck: Deck, v: int, brand: dict, brand_dir: Path, fmts: list[str]) -> dict:
        base = store.dir / f"v{v:03d}"
        outputs, warns = render_deck(store.load_version(v), brand, brand_dir, base, [store.assets],
                                     tuple(f for f in ["html"] + fmts if f != "pdf"))
        if "pdf" in fmts:
            pdf = html_to_pdf(outputs["html"], base.with_suffix(".pdf"))
            if pdf:
                outputs["pdf"] = pdf
            else:
                warns.append("PDF export needs Playwright: pip install playwright && playwright install chromium")
        return {"deck": store.name, "version": v, "warnings": warns,
                "outputs": {k: str(p) for k, p in outputs.items()}}


def enqueue(cfg: dict, meta: dict, body: str = "", files: list[tuple[str, bytes]] | None = None,
            name: str | None = None) -> str:
    """Create an inbox request folder atomically (used by the UI and CLI). Returns the job id."""
    base = slugify(name or f"{meta.get('action', 'create')}-{meta.get('deck') or 'deck'}", 40) + "-" + now_id()
    jid, k = base, 2
    while (cfg["paths"]["inbox"] / jid).exists() or (cfg["paths"]["done"] / jid).exists() \
            or (cfg["paths"]["inbox"] / f"_{jid}").exists():
        jid = f"{base}-{k}"
        k += 1
    staging = cfg["paths"]["inbox"] / f"_{jid}"
    staging.mkdir(parents=True, exist_ok=True)
    meta = {k: v for k, v in meta.items() if v not in (None, "", [])}
    text = "---\n" + yaml.safe_dump(meta, sort_keys=False, allow_unicode=True) + "---\n" + (body or "") + "\n"
    (staging / "request.md").write_text(text, encoding="utf-8")
    for fname, data in files or []:
        safe = Path(fname).name
        if safe.lower() in ("request.md", "request.txt", "request.yaml"):
            safe = "upload-" + safe
        (staging / safe).write_bytes(data)
    final = cfg["paths"]["inbox"] / jid
    staging.rename(final)
    # backdate so the settle timer doesn't delay UI requests
    old = time.time() - 3600
    for p in [final, *final.rglob("*")]:
        os.utime(p, (old, old))
    return jid
