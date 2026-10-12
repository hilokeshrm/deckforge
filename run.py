"""DeckForge command line.

  python run.py ui                      web UI + background agent (http://127.0.0.1:8000)
  python run.py watch                   agent loop only (inbox/ + brand-inbox/)
  python run.py once                    process whatever is waiting, then exit
  python run.py make a.pdf b.docx --template acme --slides 12 --brief "Board update"
  python run.py edit q3-review "Slide 4: turn the bullets into a chart"
  python run.py brand path/to/brand-folder --name acme
  python run.py gpu-check               detect GPU, pull models, verify GPU offload
  python run.py providers               which LLM providers are usable right now
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from engine.config import load_config
from engine.util import setup_logging


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="deckforge", description="Animated HTML presentation agent")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("ui", help="web UI + background agent")
    p.add_argument("--host")
    p.add_argument("--port", type=int)
    p.add_argument("--no-agent", action="store_true", help="UI only, don't start the worker")

    sub.add_parser("watch", help="run the agent loop")
    sub.add_parser("once", help="process pending requests once")

    p = sub.add_parser("make", help="create a deck from files right now")
    p.add_argument("files", nargs="*", type=Path)
    p.add_argument("--brief", default="")
    p.add_argument("--template")
    p.add_argument("--slides", type=int)
    p.add_argument("--deck")
    p.add_argument("--audience")
    p.add_argument("--url", action="append", default=[])
    p.add_argument("--pptx", action="store_true", help="also export .pptx")

    p = sub.add_parser("edit", help="change an existing deck")
    p.add_argument("deck")
    p.add_argument("instruction")
    p.add_argument("--files", nargs="*", type=Path, default=[])

    p = sub.add_parser("brand", help="build a template from a brand folder")
    p.add_argument("folder", type=Path)
    p.add_argument("--name")

    p = sub.add_parser("gpu-check", help="GPU + Ollama model check")
    p.add_argument("--no-pull", action="store_true")

    sub.add_parser("providers", help="show LLM provider status")

    args = ap.parse_args(argv)
    cfg = load_config()
    setup_logging(cfg["paths"]["logs"])

    if args.cmd == "ui":
        from ui.server import serve

        serve(cfg, host=args.host, port=args.port, agent=not args.no_agent)
        return 0

    if args.cmd == "gpu-check":
        from engine.gpu import gpu_check

        print(json.dumps(gpu_check(cfg, pull=not args.no_pull), indent=2))
        return 0

    from engine.agent import Agent, enqueue

    if args.cmd == "providers":
        from engine.llm import LLM

        print(json.dumps(LLM(cfg).status(), indent=2, default=str))
        return 0

    agent = Agent(cfg)
    if args.cmd == "watch":
        agent.run_forever()
        return 0
    if args.cmd == "once":
        print(f"processed {agent.tick()} request(s)")
        return 0
    if args.cmd == "brand":
        from engine.brand import build_brand

        out = build_brand(args.folder, cfg["paths"]["templates"], agent.llm, name=args.name, cfg=cfg)
        print(f"template written to {out}")
        return 0

    if args.cmd == "make":
        meta = {"action": "create", "deck": args.deck, "template": args.template, "slides": args.slides,
                "audience": args.audience, "urls": args.url, "formats": ["pptx"] if args.pptx else []}
        files = [(f.name, f.read_bytes()) for f in args.files]
    else:  # edit
        meta = {"action": "edit", "deck": args.deck}
        files = [(f.name, f.read_bytes()) for f in args.files]
    body = args.brief if args.cmd == "make" else args.instruction
    jid = enqueue(cfg, meta, body, files)
    agent.tick()
    job = agent.state.data["jobs"].get(jid, {})
    print(json.dumps({k: job.get(k) for k in ("status", "deck", "version", "outputs", "error", "warnings")},
                     indent=2, default=str))
    return 0 if job.get("status") == "done" else 1


if __name__ == "__main__":
    sys.exit(main())
