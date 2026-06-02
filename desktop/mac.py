"""macOS-specific helpers via PyObjC (Quartz + AppKit).

Public surface mirrors desktop/win.py so platform_compat.py can re-export
either one transparently. Wherever a Windows term doesn't quite map to mac
(Alt → Option, Ctrl+C → Cmd+C) we keep the Windows-flavored function name
for symmetry; comments call out the difference.

Requires pyobjc-framework-Quartz and pyobjc-framework-Cocoa, both of which
ship as separately installable PyPI packages.

We also expose `is_accessibility_trusted()` which has no Windows counterpart
— Mac needs the user to grant Accessibility permission in System Settings
before global key state and synthetic events work at all.
"""
from __future__ import annotations

import sys
import time

try:
    from Quartz import (
        CGEventCreateKeyboardEvent,
        CGEventPost,
        CGEventSetFlags,
        CGEventSourceFlagsState,
        kCGEventFlagMaskCommand,
        kCGEventFlagMaskAlternate,
        kCGEventSourceStateHIDSystemState,
        kCGHIDEventTap,
    )
    from AppKit import NSWorkspace, NSScreen, NSEvent
    _HAVE_PYOBJC = True
except ImportError as _e:  # pragma: no cover — pyobjc missing path is exercised at runtime
    _HAVE_PYOBJC = False
    _IMPORT_ERROR = _e
    print(f"[codelang] WARNING: pyobjc not available ({_e}); mac.py running in degraded mode",
          file=sys.stderr)


# Mac virtual key codes (from HIToolbox/Events.h).
_KC_C = 0x08
_KC_CMD = 0x37        # Left Command (⌘)
_KC_OPTION = 0x3A     # Left Option (⌥)
_KC_OPTION_R = 0x3D   # Right Option


# ---------- DPI ----------

def set_dpi_aware() -> None:
    """No-op on macOS — Retina handled by AppKit / Quartz natively."""
    return None


# ---------- cursor ----------

def get_cursor_pos() -> tuple[int, int]:
    """Cursor position in **top-left origin** screen coordinates, matching the
    Windows convention used by ui.py for tooltip placement.

    NSEvent.mouseLocation() is in bottom-left origin relative to the main
    screen; we flip y by the main screen height.
    """
    if not _HAVE_PYOBJC:
        return (0, 0)
    loc = NSEvent.mouseLocation()
    main = NSScreen.mainScreen()
    if main is None:
        return (int(loc.x), int(loc.y))
    h = main.frame().size.height
    return (int(loc.x), int(h - loc.y))


# ---------- modifier key state ----------

def alt_pressed() -> bool:
    """True if Option (⌥) is currently held.

    On Mac the natural physical equivalent of Windows Alt is Option, in the
    same key position. We keep the Windows-flavored function name so the
    caller (app.py) doesn't need to branch.
    """
    if not _HAVE_PYOBJC:
        return False
    flags = CGEventSourceFlagsState(kCGEventSourceStateHIDSystemState)
    return bool(flags & kCGEventFlagMaskAlternate)


# ---------- synthetic key events ----------

def _post_key(keycode: int, down: bool, flags: int = 0) -> None:
    """Post a single keyboard event via the HID event tap."""
    ev = CGEventCreateKeyboardEvent(None, keycode, down)
    if flags:
        CGEventSetFlags(ev, flags)
    CGEventPost(kCGHIDEventTap, ev)


def send_ctrl_c() -> None:
    """Synthesize the platform's "copy" hotkey — Cmd+C on macOS.

    Unlike Windows, we don't have the Alt+Ctrl+C breakage problem here: most
    Mac apps only honor Cmd+C for copy, and Option being held alongside is
    benign in standard text contexts (in some apps Cmd+Option+C is "copy
    pathname" or similar, but selection-copy is overwhelmingly Cmd+C alone).
    To be safe we still set the Cmd flag explicitly on the C event so the
    receiver sees a clean Cmd+C even while Option is physically held.

    The function name stays `send_ctrl_c` so platform_compat.py can re-export
    it without conditional branches in callers.
    """
    if not _HAVE_PYOBJC:
        return
    _post_key(_KC_CMD, True)
    _post_key(_KC_C, True, kCGEventFlagMaskCommand)
    time.sleep(0.005)
    _post_key(_KC_C, False, kCGEventFlagMaskCommand)
    _post_key(_KC_CMD, False)


def force_release_alt() -> None:
    """Emergency: synthesize Option-up to clear a phantom Option-held state.

    Less load-bearing on Mac than on Windows (we don't synthesize Option
    up/down around the copy event), but exposed for parity so the user-
    visible "release stuck Option" command always exists.
    """
    if not _HAVE_PYOBJC:
        return
    _post_key(_KC_OPTION, False)
    _post_key(_KC_OPTION_R, False)


# ---------- foreground app info (diagnostic) ----------

def get_foreground_window_info() -> tuple[str, str]:
    """Return (localized app name, bundle id) of the frontmost application.

    Used purely for diagnostics — many "doesn't work" reports come down to
    "you tested in Terminal.app which has its own selection model" or
    similar. Logging the frontmost app makes that visible immediately.
    """
    if not _HAVE_PYOBJC:
        return ("", "")
    try:
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        if app is None:
            return ("", "")
        return (str(app.localizedName() or ""), str(app.bundleIdentifier() or ""))
    except Exception:
        return ("", "")


# ---------- screen geometry ----------

def get_monitor_work_rect(x: int, y: int) -> tuple[int, int, int, int]:
    """Return the visibleFrame (left, top, right, bottom) of the screen
    containing (x, y), in **top-left origin** to match Windows.

    NSScreen reports visibleFrame in AppKit's bottom-left origin relative to
    the main screen's bottom-left; we flip every y back to top-left.
    """
    if not _HAVE_PYOBJC:
        return (0, 0, 1920, 1080)

    screens = NSScreen.screens()
    main = NSScreen.mainScreen()
    if main is None or not screens:
        return (0, 0, 1920, 1080)
    main_h = main.frame().size.height

    # Convert input cursor (which we report top-left) to AppKit's bottom-left
    y_bl = main_h - y

    chosen = None
    for screen in screens:
        f = screen.frame()
        sx, sy = f.origin.x, f.origin.y
        sw, sh = f.size.width, f.size.height
        if sx <= x <= sx + sw and sy <= y_bl <= sy + sh:
            chosen = screen
            break
    if chosen is None:
        chosen = main

    vf = chosen.visibleFrame()
    vx, vy = vf.origin.x, vf.origin.y
    vw, vh = vf.size.width, vf.size.height
    left = int(vx)
    right = int(vx + vw)
    # Flip the top/bottom y back to top-left coords
    top = int(main_h - (vy + vh))
    bottom = int(main_h - vy)
    return (left, top, right, bottom)


# ---------- accessibility permission ----------

def is_accessibility_trusted(prompt: bool = False) -> bool:
    """Return True if this process is in the Accessibility trusted-clients
    list (i.e. allowed to listen to global keys and post synthetic events).

    Mac requires this for the whole feature to work. If `prompt=True`, macOS
    will pop up its built-in "Allow accessibility" dialog the first time.
    """
    try:
        import HIServices  # via pyobjc-framework-Quartz / Cocoa
        try:
            # kAXTrustedCheckOptionPrompt is the key name; pass as plain string
            # to avoid pulling in the CoreFoundation constants on this code path.
            opts = {"AXTrustedCheckOptionPrompt": bool(prompt)}
            return bool(HIServices.AXIsProcessTrustedWithOptions(opts))
        except AttributeError:
            return bool(HIServices.AXIsProcessTrusted())
    except ImportError:
        # No pyobjc, or the framework isn't available; assume trusted so the
        # caller doesn't pester the user with a broken check.
        return True
    except Exception:
        return True


# ---------- screen recording permission (macOS, for OCR capture) ----------

def is_screen_recording_trusted(prompt: bool = False) -> bool:
    """Return True if this process may capture screen contents.

    Screenshot OCR needs the *Screen Recording* TCC permission, which is
    separate from Accessibility. If `prompt=True`, macOS shows its built-in
    "allow screen recording" dialog the first time (the grant only takes
    effect after the app restarts — macOS limitation).

    Falls back to True if the CoreGraphics preflight API is unavailable (older
    macOS), so we never block the feature on a missing check.
    """
    if not _HAVE_PYOBJC:
        return True
    try:
        from Quartz import (
            CGPreflightScreenCaptureAccess,
            CGRequestScreenCaptureAccess,
        )
    except ImportError:
        return True
    try:
        if CGPreflightScreenCaptureAccess():
            return True
        if prompt:
            # Triggers the system dialog + registers us in the Screen Recording
            # list. Returns the (usually still-False) immediate state.
            return bool(CGRequestScreenCaptureAccess())
        return False
    except Exception:
        return True


if __name__ == "__main__":
    print("pyobjc available:", _HAVE_PYOBJC)
    print("cursor:", get_cursor_pos())
    print("option pressed:", alt_pressed())
    print("monitor at cursor:", get_monitor_work_rect(*get_cursor_pos()))
    print("frontmost app:", get_foreground_window_info())
    print("accessibility trusted:", is_accessibility_trusted())
    sys.exit(0)
