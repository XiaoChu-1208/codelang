"""Remote dict update: pull a newer dict.json from GitHub raw if available.

Privacy / "100% 本地" stance:
  - Only ever talks to one URL (the repo's raw dict.json on main).
  - Only called on user action (manual menu click) or, if user hasn't disabled
    it, once at startup. Never on a recurring timer.
  - All network errors are swallowed silently — the app must keep working
    offline. Failures only surface to the user when they explicitly clicked
    "check for updates".

Storage:
  Downloaded payloads are written atomically to ~/.codelang/dict.json so the
  read-only bundled copy is untouched and reinstalls of the .exe can't clobber
  what the user pulled.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional

import requests

DICT_RAW_URL = (
    "https://raw.githubusercontent.com/XiaoChu-1208/codelang/main/extension-browser/dict.json"
)
TIMEOUT_S = 8  # matches the LLM call timeout in lookup.py


def check_remote(local_version: str) -> Optional[dict]:
    """Return the remote payload if its `version` is strictly newer than
    `local_version`, otherwise None. Network/parse failures also return None
    (caller decides whether to surface them based on context).
    """
    try:
        r = requests.get(DICT_RAW_URL, timeout=TIMEOUT_S)
    except requests.RequestException as e:
        print(f"[codelang] update check network error: {e}", file=sys.stderr)
        return None
    if not r.ok:
        print(f"[codelang] update check HTTP {r.status_code}", file=sys.stderr)
        return None
    try:
        payload = r.json()
    except ValueError as e:
        print(f"[codelang] update check parse error: {e}", file=sys.stderr)
        return None
    if not isinstance(payload, dict):
        return None
    remote_version = str(payload.get("version", "") or "")
    if not remote_version:
        return None
    # ISO 8601 strings sort lexicographically the same as chronologically
    # when produced by the same source (build_dict.py always uses UTC +00:00).
    if remote_version <= (local_version or ""):
        return None
    return payload


def save_atomic(path: Path, payload: dict) -> None:
    """Write JSON to `path` via a .tmp + os.replace so we never leave a
    half-written file if the process dies mid-flush."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            # fsync isn't critical here — atomicity comes from replace, fsync
            # just makes the durability story stronger. Some filesystems balk.
            pass
    os.replace(tmp, path)
