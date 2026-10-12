from __future__ import annotations

import copy
import threading
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yaml"
# Settings changed from the web UI go here, so config.yaml (and its comments) stays untouched.
LOCAL_PATH = ROOT / "settings.local.yaml"

_lock = threading.Lock()


def deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def load_config(path: Path | None = None) -> dict:
    """Load config.yaml (+ settings.local.yaml, + .env), resolve paths and create folders."""
    load_dotenv(ROOT / ".env")
    path = path or CONFIG_PATH
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    if path == CONFIG_PATH and LOCAL_PATH.exists():
        with open(LOCAL_PATH, "r", encoding="utf-8") as f:
            cfg = deep_merge(cfg, yaml.safe_load(f) or {})
    resolved = {}
    for key, rel in (cfg.get("paths") or {}).items():
        p = Path(rel)
        resolved[key] = p if p.is_absolute() else ROOT / p
    cfg["paths"] = resolved
    for key, p in resolved.items():
        if key != "state":
            p.mkdir(parents=True, exist_ok=True)
    return cfg


def save_local_override(cfg: dict, section: str, value: dict) -> None:
    """Persist one top-level section (e.g. `llm`) to settings.local.yaml and apply it live."""
    with _lock:
        data = {}
        if LOCAL_PATH.exists():
            with open(LOCAL_PATH, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        data[section] = value
        with open(LOCAL_PATH, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)
        cfg[section] = copy.deepcopy(value)
