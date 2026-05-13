"""Platform-dispatching facade for desktop OS helpers.

Importing this module gives you the same public API as desktop/win.py, but
on macOS it transparently uses desktop/mac.py instead. Callers (app.py,
ui.py, welcome.py) just `from . import platform_compat as winhelp` and stay
platform-agnostic.

We intentionally keep the Windows-flavored function names (alt_pressed,
send_ctrl_c, force_release_alt) — on Mac these mean Option, Cmd+C, and
"release Option" respectively. Renaming would force every caller to branch.
"""
from __future__ import annotations

import sys

IS_MAC = sys.platform == "darwin"
IS_WINDOWS = sys.platform == "win32"

if IS_MAC:
    from . import mac as _impl
else:
    from . import win as _impl

# Re-export the shared surface.
set_dpi_aware = _impl.set_dpi_aware
get_cursor_pos = _impl.get_cursor_pos
alt_pressed = _impl.alt_pressed
send_ctrl_c = _impl.send_ctrl_c
force_release_alt = _impl.force_release_alt
get_foreground_window_info = _impl.get_foreground_window_info
get_monitor_work_rect = _impl.get_monitor_work_rect

# Mac-only extra; exposed conditionally so callers can `getattr` check.
if IS_MAC:
    is_accessibility_trusted = _impl.is_accessibility_trusted  # type: ignore[attr-defined]
