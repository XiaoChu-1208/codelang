"""Windows-specific helpers via ctypes (no pywin32 dep)."""
from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes

# Virtual-key codes
VK_LMENU = 0xA4  # Left Alt
VK_RMENU = 0xA5  # Right Alt
VK_MENU = 0x12   # Either Alt
VK_CONTROL = 0x11
VK_C = 0x43

# SendInput structs
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT), ("hi", _HARDWAREINPUT)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUT_UNION)]


_user32 = ctypes.windll.user32
_user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(_INPUT), ctypes.c_int]
_user32.SendInput.restype = wintypes.UINT
_user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
_user32.GetAsyncKeyState.restype = ctypes.c_short


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


def set_dpi_aware() -> None:
    """Per-monitor DPI awareness so tooltip looks crisp on high-DPI displays."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def get_cursor_pos() -> tuple[int, int]:
    pt = POINT()
    _user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def alt_pressed() -> bool:
    """True if either Alt key is currently held."""
    return bool(_user32.GetAsyncKeyState(VK_MENU) & 0x8000)


def _send_key(vk: int, up: bool = False) -> None:
    inp = _INPUT()
    inp.type = INPUT_KEYBOARD
    inp.u.ki = _KEYBDINPUT(
        wVk=vk,
        wScan=0,
        dwFlags=KEYEVENTF_KEYUP if up else 0,
        time=0,
        dwExtraInfo=None,
    )
    _user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))


def send_ctrl_c() -> None:
    """Simulate Ctrl+C with a brief Alt UP/DOWN dance.

    Why the dance: when the user holds Alt and we naively send Ctrl+C, the
    focused application receives Alt+Ctrl+C, not pure Ctrl+C. Modern apps
    (Chrome, Cursor, VS Code) tolerate this and still copy, but older Win32
    apps (Notepad, Word, file explorer dialogs) do NOT — they interpret Alt
    as menu activation and Ctrl+C falls into a black hole. Result: clipboard
    doesn't update, the app appears completely dead.

    The fix: synthesize Alt-UP just before Ctrl+C so the focused app sees a
    clean Ctrl+C. After Ctrl+C, re-synthesize Alt-DOWN to restore the user's
    continuous physical hold (important for Alt+double-click flows where the
    second click also needs Alt-held).

    Known small risk: if the user physically releases Alt within our ~10ms
    dance window, the trailing synthetic Alt-DOWN can leave a phantom Alt-held
    in OS state. The race window is tiny. Mitigation: tray menu has a
    "释放卡住的 Alt" emergency button. The earlier "no Alt dance" version
    avoided this race but broke Notepad/Word entirely — far worse.
    """
    alt_was_down = alt_pressed()
    if alt_was_down:
        _send_key(VK_LMENU, up=True)
        _send_key(VK_RMENU, up=True)
    _send_key(VK_CONTROL, up=False)
    _send_key(VK_C, up=False)
    time.sleep(0.005)
    _send_key(VK_C, up=True)
    _send_key(VK_CONTROL, up=True)
    if alt_was_down:
        # Restore user's physical Alt hold so subsequent triggers (Alt+double-click
        # second click) still see Alt as held.
        _send_key(VK_LMENU, up=False)


def force_release_alt() -> None:
    """Emergency: synthesize Alt-UP to clear a phantom Alt-DOWN state.

    Safe to call when Alt is already up — Windows accepts redundant UP events.
    Exposed via the tray menu so the user can recover from any process (this
    app's earlier version, another tool, or a flaky hardware key) that left
    the OS thinking Alt is held when it isn't.
    """
    _send_key(VK_LMENU, up=True)
    _send_key(VK_RMENU, up=True)
    _send_key(VK_MENU, up=True)


_MONITOR_DEFAULTTONEAREST = 0x00000002


class _MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", RECT),
        ("rcWork", RECT),
        ("dwFlags", wintypes.DWORD),
    ]


def get_monitor_work_rect(x: int, y: int) -> tuple[int, int, int, int]:
    """Return (left, top, right, bottom) of the work area on the monitor containing (x,y)."""
    pt = POINT(x, y)
    hmon = _user32.MonitorFromPoint(pt, _MONITOR_DEFAULTTONEAREST)
    info = _MONITORINFO()
    info.cbSize = ctypes.sizeof(_MONITORINFO)
    if _user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
        r = info.rcWork
        return r.left, r.top, r.right, r.bottom
    # Fallback: primary screen size
    sw = _user32.GetSystemMetrics(0)
    sh = _user32.GetSystemMetrics(1)
    return 0, 0, sw, sh


if __name__ == "__main__":
    set_dpi_aware()
    print("cursor:", get_cursor_pos())
    print("alt pressed:", alt_pressed())
    print("monitor at cursor:", get_monitor_work_rect(*get_cursor_pos()))
    sys.exit(0)
