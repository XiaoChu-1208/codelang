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

def _primary_screen_height() -> float:
    """Height of the PRIMARY screen (frame origin == (0,0), the menu-bar
    display). This is the correct reference for flipping AppKit's global
    bottom-left coordinates to the top-left convention ui.py uses.

    Do NOT use NSScreen.mainScreen() here: "main" is the screen with the
    active/key window, which on a multi-monitor setup is frequently a SECONDARY
    display of a different height. Using its height makes the y-flip come out
    hundreds of px off, so tooltip / OCR cards land in the wrong spot ("flying
    around the screen"). The global coordinate origin is always the primary's
    bottom-left, regardless of which screen is currently active.
    """
    screens = NSScreen.screens()
    for s in screens:
        o = s.frame().origin
        if int(o.x) == 0 and int(o.y) == 0:
            return s.frame().size.height
    return screens[0].frame().size.height if screens else 0.0


def get_cursor_pos() -> tuple[int, int]:
    """Cursor position in **top-left origin** screen coordinates, matching the
    Windows convention used by ui.py for tooltip placement.

    NSEvent.mouseLocation() is in bottom-left origin relative to the primary
    screen; we flip y by the primary screen height (NOT mainScreen — see
    _primary_screen_height).
    """
    if not _HAVE_PYOBJC:
        return (0, 0)
    loc = NSEvent.mouseLocation()
    h = _primary_screen_height()
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
    if not screens:
        return (0, 0, 1920, 1080)
    # Flip reference is the PRIMARY screen height, not mainScreen() — see
    # _primary_screen_height. Using mainScreen() here breaks the y-flip (and
    # thus the screen hit-test below) whenever the active window is on a
    # secondary monitor, which is the multi-monitor "card flies away" bug.
    main_h = _primary_screen_height()

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
        chosen = NSScreen.mainScreen() or screens[0]

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


# ---------- App Translocation detection ----------

def is_translocated() -> bool:
    """Return True if this app is running from a macOS *App Translocation*
    path (a randomized, read-only `…/AppTranslocation/…` location).

    Gatekeeper translocates any quarantined app that wasn't moved into place
    by Finder — and a translocated bundle gets a fresh random path on every
    launch. That breaks Accessibility/Input-Monitoring permission outright:
    even after the user grants it, the next launch is a "different" app from
    macOS's point of view, so the grant never sticks and ⌥-drag stays dead.

    The only real fix is to strip the quarantine xattr from the bundle
    (`xattr -dr com.apple.quarantine /Applications/codelang.app`) and relaunch
    from a stable path — which is exactly what the bundled
    「① 修复并启动.command」helper does.
    We surface this to the user instead of letting them chase a permission
    toggle that can never take effect.
    """
    # When frozen by py2app, sys.executable points inside the .app bundle;
    # a translocated bundle carries the marker in that path. Check a couple
    # of path sources to be robust across launch methods.
    for p in (sys.executable, getattr(sys, "_MEIPASS", ""), __file__):
        if p and "/AppTranslocation/" in p:
            return True
    return False


if __name__ == "__main__":
    print("pyobjc available:", _HAVE_PYOBJC)
    print("cursor:", get_cursor_pos())
    print("option pressed:", alt_pressed())
    print("monitor at cursor:", get_monitor_work_rect(*get_cursor_pos()))
    print("frontmost app:", get_foreground_window_info())
    print("accessibility trusted:", is_accessibility_trusted())
    print("translocated:", is_translocated())
    sys.exit(0)
