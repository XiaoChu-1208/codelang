"""Interactive screen-region capture on macOS.

We shell out to the system `screencapture -i` rather than grabbing pixels
ourselves with CGWindowListCreateImage. Two reasons:

  1. UX: `-i` gives the user the exact Cmd+Shift+4 crosshair they already know
     — drag a box, release, done. (Space toggles window-capture mode for free.)
  2. Permissions: `screencapture` is Apple-signed and runs the capture in its
     own context, so we sidestep prompting for the *Screen Recording* TCC
     permission that a self-grab from our process would require.

The capture lands in a temp PNG; the caller OCRs it and deletes it.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile

SCREENCAPTURE = "/usr/sbin/screencapture"


def capture_region_to_file() -> str | None:
    """Show the interactive crosshair and capture the dragged region to a temp
    PNG. Returns the file path, or None if the user pressed Esc / captured
    nothing. Caller owns the file and must delete it.
    """
    fd, path = tempfile.mkstemp(suffix=".png", prefix="codelang_ocr_")
    os.close(fd)  # screencapture writes the file itself
    try:
        # -i interactive selection, -x silent (no shutter sound). We deliberately
        # omit -o: combined with some capture modes it can fail with "could not
        # create image from rect", and its only effect is dropping the window
        # shadow in the (rarely used) space-to-capture-window sub-mode.
        subprocess.run([SCREENCAPTURE, "-i", "-x", path], check=False)
    except Exception as e:
        print(f"[codelang] screencapture failed: {e}", file=sys.stderr)
        _unlink(path)
        return None

    # On Esc/cancel, screencapture leaves our 0-byte temp file untouched.
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    _unlink(path)
    return None


def _unlink(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass
