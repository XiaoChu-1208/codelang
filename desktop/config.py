"""Persistent config + LLM cache at ~/.codelang/."""
from __future__ import annotations

import json
import os
from pathlib import Path

CONFIG_DIR = Path(os.path.expanduser("~")) / ".codelang"
CONFIG_FILE = CONFIG_DIR / "config.json"
CACHE_FILE = CONFIG_DIR / "llm_cache.json"
MISSING_FILE = CONFIG_DIR / "missing_log.txt"

DEFAULTS = {
    "provider": "anthropic",      # anthropic | openai
    "api_key": "",
    "model": "",                  # empty = provider default
    "llm_fallback_enabled": False,  # only call LLM at runtime if True
    "selection_max_len": 32,
    "loading_dot_interval_ms": 250,
    "error_auto_close_ms": 1800,
}


def _ensure_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> dict:
    _ensure_dir()
    if not CONFIG_FILE.exists():
        save_config(DEFAULTS)
        return dict(DEFAULTS)
    try:
        with CONFIG_FILE.open(encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}
    out = dict(DEFAULTS)
    out.update(data)
    return out


def save_config(cfg: dict) -> None:
    _ensure_dir()
    with CONFIG_FILE.open("w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def load_cache() -> dict:
    if not CACHE_FILE.exists():
        return {}
    try:
        with CACHE_FILE.open(encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_cache(cache: dict) -> None:
    _ensure_dir()
    tmp = CACHE_FILE.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    tmp.replace(CACHE_FILE)


def log_missing(term: str) -> None:
    """Append a not-found term so user can review and add to dict later."""
    _ensure_dir()
    with MISSING_FILE.open("a", encoding="utf-8") as f:
        f.write(term + "\n")
