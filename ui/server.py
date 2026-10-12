"""DeckForge web UI: FastAPI backend + the agent running in a background thread."""
from __future__ import annotations

import copy
import threading
from pathlib import Path

import yaml
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from engine.agent import Agent, enqueue
from engine.brand import list_templates
from engine.config import save_local_override
from engine.gpu import gpu_check
from engine.llm.router import PROVIDERS, TASKS
from engine.schema import LAYOUTS, Deck
from engine.store import DeckStore, list_decks
from engine.util import log, slugify

STATIC = Path(__file__).parent / "static"


def create_app(cfg: dict, agent: Agent | None = None) -> FastAPI:
    agent = agent or Agent(cfg)
    paths = cfg["paths"]
    app = FastAPI(title="DeckForge", docs_url="/api/docs")
    gpu_cache: dict = {}

    def safe_file(root: Path, rel: str) -> Path:
        p = (root / rel).resolve()
        if not p.is_relative_to(root.resolve()) or not p.is_file():
            raise HTTPException(404, "not found")
        return p

    def submit(meta: dict, body: str = "", files: list[tuple[str, bytes]] | None = None, name: str | None = None) -> dict:
        jid = enqueue(cfg, meta, body, files, name)
        with agent.state.lock:  # the worker may already have picked it up
            if jid not in agent.state.data["jobs"]:
                agent.state.job(jid, status="queued", action=meta.get("action"), deck=meta.get("deck"),
                                template=meta.get("template"), title=(body or meta.get("action", ""))[:80])
        agent.wake.set()
        return {"id": jid}

    # ---------- pages ----------
    @app.get("/", response_class=HTMLResponse)
    def index():
        return (STATIC / "index.html").read_text(encoding="utf-8")

    @app.get("/static/{rel:path}")
    def static(rel: str):
        return FileResponse(safe_file(STATIC, rel))

    # ---------- status ----------
    @app.get("/api/status")
    def status():
        queued = [p.name for p in paths["inbox"].iterdir() if not p.name.startswith((".", "_"))]
        return {"busy": agent.busy.locked(), "current": agent.current, "queued": len(queued),
                "providers": agent.llm.status(), "gpu": gpu_cache.get("report")}

    @app.post("/api/gpu-check")
    def run_gpu_check(pull: bool = False):
        report = gpu_check(cfg, pull=pull)
        gpu_cache["report"] = report
        return report

    # ---------- jobs ----------
    @app.get("/api/jobs")
    def jobs():
        return agent.state.jobs()

    @app.get("/api/jobs/{jid}")
    def job(jid: str):
        j = agent.state.data["jobs"].get(jid)
        if not j:
            raise HTTPException(404, "job not found")
        return j

    @app.post("/api/jobs")
    async def create_job(
        action: str = Form("create"),
        deck: str = Form(""),
        template: str = Form(""),
        slides: str = Form(""),
        audience: str = Form(""),
        instructions: str = Form(""),
        urls: str = Form(""),
        formats: str = Form(""),
        version: str = Form(""),
        files: list[UploadFile] = File(default=[]),
    ):
        meta = {"action": action, "deck": deck or None, "template": template or None,
                "slides": int(slides) if slides.strip().isdigit() else None,
                "audience": audience or None, "version": int(version) if version.strip().isdigit() else None,
                "urls": [u.strip() for u in urls.splitlines() if u.strip()],
                "formats": [f.strip() for f in formats.split(",") if f.strip()]}
        data = [(f.filename or "upload", await f.read()) for f in files if f.filename]
        if action == "create" and not data and not instructions.strip() and not meta["urls"]:
            raise HTTPException(400, "add files, URLs or a brief")
        return submit(meta, instructions, data, name=f"{action}-{deck or template or 'deck'}")

    # ---------- decks ----------
    @app.get("/api/decks")
    def decks():
        return list_decks(paths["decks"])

    @app.get("/api/decks/{name}")
    def deck_detail(name: str, version: int | None = None):
        store = DeckStore(paths["decks"], name)
        if not store.exists():
            raise HTTPException(404, "deck not found")
        versions = store.versions()
        v = version or (versions[-1] if versions else None)
        deck = store.load_version(v) if v else store.load()
        files = sorted(p.name for p in store.dir.glob(f"v{v:03d}.*")) if v else []
        prev = store.dir / "preview" / f"v{v:03d}"
        thumbs = sorted(p.name for p in prev.glob("slide-*.png")) if prev.exists() else []
        return {"name": store.name, "version": v, "versions": versions, "deck": deck.model_dump(),
                "files": files, "thumbs": thumbs, "history": store.read_history()[::-1],
                "assets": sorted(p.name for p in store.assets.glob("*")) if store.assets.exists() else []}

    @app.put("/api/decks/{name}")
    async def save_deck(name: str, body: dict):
        store = DeckStore(paths["decks"], name)
        if not store.exists():
            raise HTTPException(404, "deck not found")
        try:
            deck = Deck.model_validate(body)
        except Exception as e:
            raise HTTPException(422, f"invalid deck: {e}")
        return submit({"action": "save", "deck": store.name}, "manual edit",
                      [("deck.json", deck.model_dump_json(indent=2).encode())], name=f"save-{store.name}")

    @app.get("/files/decks/{name}/{rel:path}")
    def deck_file(name: str, rel: str, download: bool = False):
        p = safe_file(paths["decks"] / slugify(name), rel)
        return FileResponse(p, filename=p.name if download else None)

    # ---------- templates ----------
    @app.get("/api/templates")
    def templates():
        return list_templates(paths["templates"])

    @app.post("/api/templates")
    async def create_template(
        name: str = Form(...),
        primary: str = Form(""), accent: str = Form(""), accent2: str = Form(""),
        background: str = Form(""), text: str = Form(""),
        heading_font: str = Form(""), body_font: str = Form(""), font_css: str = Form(""),
        tone: str = Form(""), footer: str = Form(""),
        transition: str = Form(""), animation: str = Form(""),
        title_background: str = Form(""), logo_position: str = Form(""),
        logo: UploadFile | None = File(None),
        files: list[UploadFile] = File(default=[]),
    ):
        colors = {k: v for k, v in dict(primary=primary, accent=accent, accent2=accent2,
                                        background=background, text=text).items() if v}
        fonts = {k: v for k, v in dict(heading=heading_font, body=body_font).items() if v}
        brand_yaml = {k: v for k, v in dict(
            colors=colors, fonts=fonts, tone=tone, footer=footer, transition=transition, animation=animation,
            title_background=title_background, logo_position=logo_position,
            font_css=[u.strip() for u in font_css.splitlines() if u.strip()]).items() if v}
        data = [("brand.yaml", yaml.safe_dump(brand_yaml, sort_keys=False).encode())]
        if logo is not None and logo.filename:
            data.append(("logo" + Path(logo.filename).suffix.lower(), await logo.read()))
        data += [(f.filename, await f.read()) for f in files if f.filename]
        return submit({"action": "brand", "template": slugify(name)}, "", data, name=f"brand-{name}")

    @app.get("/files/templates/{name}/{rel:path}")
    def template_file(name: str, rel: str):
        return FileResponse(safe_file(paths["templates"] / slugify(name), rel))

    # ---------- settings ----------
    @app.get("/api/settings")
    def settings():
        return {"llm": cfg["llm"], "tasks": TASKS, "providers": PROVIDERS, "layouts": LAYOUTS,
                "render": cfg.get("render", {}), "qa": cfg.get("qa", {})}

    @app.put("/api/settings")
    def put_settings(body: dict):
        llm = copy.deepcopy(cfg["llm"])
        for k, v in (body.get("llm") or {}).items():
            if isinstance(v, dict) and isinstance(llm.get(k), dict):
                llm[k].update(v)
            else:
                llm[k] = v
        save_local_override(cfg, "llm", llm)
        for section in ("qa", "render"):
            if isinstance(body.get(section), dict):
                merged = {**cfg.get(section, {}), **body[section]}
                save_local_override(cfg, section, merged)
        agent.llm.cfg = cfg
        agent.llm.reload()
        return {"ok": True, "llm": cfg["llm"]}

    @app.exception_handler(Exception)
    async def errors(_, exc: Exception):
        log.exception("UI error")
        return JSONResponse({"detail": str(exc)}, status_code=500)

    app.state.agent = agent
    return app


def serve(cfg: dict, host: str | None = None, port: int | None = None, agent: bool = True) -> None:
    import uvicorn

    ui = cfg.get("ui", {})
    worker = Agent(cfg)
    app = create_app(cfg, worker)
    if agent:
        threading.Thread(target=worker.run_forever, name="deck-agent", daemon=True).start()
    host = host or ui.get("host", "127.0.0.1")
    port = port or int(ui.get("port", 8000))
    log.info("DeckForge UI on http://%s:%s", host, port)
    uvicorn.run(app, host=host, port=port, log_level="warning")
