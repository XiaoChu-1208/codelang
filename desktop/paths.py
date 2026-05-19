"""Resolve the codelang resource root in both run modes.

- Run from source (`python3 -m desktop.app`): resources (assets/,
  extension-browser/, dict/) live one directory above the desktop/ package.
- Run frozen inside codelang.app (built by installer/build_mac.sh via py2app):
  those trees are copied into Contents/Resources/, and py2app exports the
  RESOURCEPATH environment variable pointing at that directory.

Kept stdlib-only on purpose: desktop/deps_error.py imports this before the
heavy third-party imports, so it must not pull anything extra in.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    """True when running inside a py2app bundle (sys.frozen == 'macosx_app')."""
    return bool(getattr(sys, "frozen", False))


def resource_root() -> Path:
    """Directory that contains the bundled `assets/` and `extension-browser/`
    trees — the repo root when run from source, Contents/Resources/ when
    frozen into codelang.app."""
    if is_frozen():
        rp = os.environ.get("RESOURCEPATH")
        if rp:
            return Path(rp)
        # Fallback if RESOURCEPATH is somehow unset: the executable lives at
        # codelang.app/Contents/MacOS/codelang → climb to Contents/Resources.
        return Path(sys.executable).resolve().parent.parent / "Resources"
    return Path(__file__).resolve().parent.parent
