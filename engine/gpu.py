"""GPU detection, VRAM-based model choice and an Ollama offload check."""
from __future__ import annotations

import shutil
import subprocess

import requests

from .util import log

# (min VRAM in GB, text model, vision model) - Q4 quantised sizes leave room for context.
TIERS = [
    (22, "qwen3:32b", "gemma3:27b"),
    (15, "qwen3:14b", "gemma3:12b"),
    (11, "qwen3:8b", "gemma3:12b"),
    (7, "qwen3:8b", "gemma3:4b"),
    (0, "qwen3:4b", "gemma3:4b"),
]


def detect_gpus() -> list[dict]:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return []
    try:
        out = subprocess.run(
            [exe, "--query-gpu=name,memory.total,memory.used,driver_version",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=15, check=True,
        ).stdout
    except (subprocess.SubprocessError, OSError) as e:
        log.warning("nvidia-smi failed: %s", e)
        return []
    gpus = []
    for line in out.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 4:
            gpus.append({
                "name": parts[0],
                "vram_gb": round(float(parts[1]) / 1024, 1),
                "used_gb": round(float(parts[2]) / 1024, 1),
                "driver": parts[3],
            })
    return gpus


def pick_models(gpus: list[dict] | None = None) -> dict:
    gpus = detect_gpus() if gpus is None else gpus
    vram = max((g["vram_gb"] for g in gpus), default=0)
    for min_gb, text, vision in TIERS:
        if vram >= min_gb:
            return {"text": text, "vision": vision, "vram_gb": vram}
    return {"text": TIERS[-1][1], "vision": TIERS[-1][2], "vram_gb": vram}


def ollama_tags(url: str) -> list[str]:
    try:
        r = requests.get(url.rstrip("/") + "/api/tags", timeout=5)
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]
    except requests.RequestException:
        return []


def ollama_loaded(url: str) -> list[dict]:
    """Models currently in memory with how much of each sits in VRAM."""
    try:
        r = requests.get(url.rstrip("/") + "/api/ps", timeout=5)
        r.raise_for_status()
    except requests.RequestException:
        return []
    out = []
    for m in r.json().get("models", []):
        size, vram = m.get("size", 0) or 0, m.get("size_vram", 0) or 0
        out.append({
            "name": m.get("name"),
            "size_gb": round(size / 1e9, 1),
            "vram_gb": round(vram / 1e9, 1),
            "gpu_pct": round(100 * vram / size) if size else 0,
        })
    return out


def ollama_pull(url: str, model: str) -> None:
    log.info("pulling %s (first time can take a while)...", model)
    r = requests.post(url.rstrip("/") + "/api/pull", json={"model": model, "name": model, "stream": False}, timeout=7200)
    r.raise_for_status()


def gpu_check(cfg: dict, pull: bool = True) -> dict:
    """Detect GPU, make sure models exist, load them and report GPU offload."""
    oc = cfg["llm"].get("ollama", {})
    url = oc.get("url", "http://localhost:11434")
    gpus = detect_gpus()
    picked = pick_models(gpus)
    text = oc.get("text_model", "auto")
    vision = oc.get("vision_model", "auto")
    text = picked["text"] if text == "auto" else text
    vision = picked["vision"] if vision == "auto" else vision
    report = {"gpus": gpus, "text_model": text, "vision_model": vision, "ollama": False,
              "installed": [], "loaded": [], "warnings": []}
    if not gpus:
        report["warnings"].append("No NVIDIA GPU found (nvidia-smi missing). Models will run on CPU.")
    tags = ollama_tags(url)
    if not tags and not _ollama_up(url):
        report["warnings"].append(f"Ollama is not reachable at {url}. Start it with `ollama serve`.")
        return report
    report["ollama"] = True
    for m in (text, vision):
        if not any(t == m or t == m + ":latest" for t in tags):
            if pull:
                ollama_pull(url, m)
            else:
                report["warnings"].append(f"Model {m} not installed: ollama pull {m}")
    report["installed"] = ollama_tags(url)
    for m in dict.fromkeys((text, vision)):
        try:
            requests.post(url.rstrip("/") + "/api/generate", json={
                "model": m, "prompt": "Reply with OK.", "stream": False,
                "options": {"num_gpu": int(oc.get("num_gpu", 999)), "num_ctx": int(oc.get("num_ctx", 16384)),
                            "num_predict": 8},
                "keep_alive": "5m",
            }, timeout=900).raise_for_status()
        except requests.RequestException as e:
            report["warnings"].append(f"Could not load {m}: {e}")
    report["loaded"] = ollama_loaded(url)
    for m in report["loaded"]:
        if m["gpu_pct"] < 100:
            report["warnings"].append(
                f"{m['name']} is only {m['gpu_pct']}% on the GPU (rest on CPU = slow). "
                "Use a smaller model, lower num_ctx, or set OLLAMA_KV_CACHE_TYPE=q8_0.")
    return report


def _ollama_up(url: str) -> bool:
    try:
        return requests.get(url.rstrip("/") + "/api/version", timeout=3).ok
    except requests.RequestException:
        return False
