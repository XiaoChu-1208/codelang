"""Redirect stdout/stderr to a rotating log file in ~/.codelang/codelang.log.

Why this exists: the app's hook events and diagnostics are written via
`print(..., file=sys.stderr)` from throughout desktop/. When the user runs us
via pythonw (no console) we'd lose all that. When run via py (console
attached) the visible cmd window looks unprofessional. So:

- Always write to file (~/.codelang/codelang.log).
- If a real terminal is attached, also echo to it (tee) so devs can see live.
- Tray menu offers a one-click "open log file" for normal users.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from . import config

LOG_FILE = config.CONFIG_DIR / "codelang.log"
ROTATE_AT_BYTES = 1_000_000  # 1 MB
HEADER = "=== codelang started at {ts} ==="


class _TeeStream:
    """Write each chunk to multiple underlying streams. Failures on any one
    stream are swallowed so a dead/broken stream (e.g. pythonw's null stderr)
    doesn't break the others."""

    def __init__(self, *streams):
        self.streams = [s for s in streams if s is not None]

    def write(self, data):
        for s in self.streams:
            try:
                s.write(data)
                s.flush()
            except Exception:
                pass

    def flush(self):
        for s in self.streams:
            try:
                s.flush()
            except Exception:
                pass

    def isatty(self):
        return False


def setup_logging() -> Path:
    """Rotate, open, and install the log file as our stderr/stdout sink.

    Returns the path to the active log file so callers (tray menu) can
    point notepad at it.
    """
    config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    if LOG_FILE.exists() and LOG_FILE.stat().st_size > ROTATE_AT_BYTES:
        rotated = LOG_FILE.with_suffix(".log.old")
        try:
            if rotated.exists():
                rotated.unlink()
            LOG_FILE.rename(rotated)
        except Exception:
            pass

    try:
        log_fp = open(LOG_FILE, "a", encoding="utf-8", buffering=1)
    except Exception:
        # If we can't open the file (permission, full disk), bail out
        # gracefully — keep existing stderr so messages aren't lost.
        return LOG_FILE

    log_fp.write("\n" + HEADER.format(ts=datetime.now().isoformat(timespec="seconds")) + "\n")
    log_fp.flush()

    # Preserve original streams in case anything checks them later
    orig_stderr = sys.stderr if sys.stderr and hasattr(sys.stderr, "write") else None
    orig_stdout = sys.stdout if sys.stdout and hasattr(sys.stdout, "write") else None
    sys.stderr = _TeeStream(orig_stderr, log_fp)
    sys.stdout = _TeeStream(orig_stdout, log_fp)
    return LOG_FILE
