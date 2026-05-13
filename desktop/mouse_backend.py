"""Cross-platform global mouse hook.

- Windows: `mouse` package. Works without elevated permissions.
- macOS:   `pynput` package. Needs Accessibility permission granted to
           whichever Python binary is running this process.

Both backends invoke the caller-supplied callback on a private daemon
thread with one of three event strings:

  EVT_DOWN_LEFT  — left mouse button pressed
  EVT_UP_LEFT    — left mouse button released
  EVT_MOVE       — mouse moved (used by the idle-Alt-cleanup heuristic)

We don't surface other events. The Windows `mouse` package and pynput have
incompatible event-object shapes, so we normalize down to bare strings —
the rest of app.py asks for cursor position / Alt state via platform_compat
at the moment it needs them, not from the event object.
"""
from __future__ import annotations

import sys
from typing import Callable

EVT_DOWN_LEFT = "down_left"
EVT_UP_LEFT = "up_left"
EVT_MOVE = "move"

EventCallback = Callable[[str], None]


def install_hook(on_event: EventCallback):
    """Install a global mouse hook. Returns whatever the backend returns
    (the listener / hook handle). Caller doesn't need to do anything with
    it — both backends keep the hook alive internally — but holding a
    reference is harmless and keeps the listener from being GC'd."""
    if sys.platform == "darwin":
        return _install_mac(on_event)
    return _install_win(on_event)


def _install_win(on_event: EventCallback):
    import mouse as _m  # type: ignore[import-not-found]

    def _cb(event):
        try:
            if isinstance(event, _m.MoveEvent):
                on_event(EVT_MOVE)
                return
            if isinstance(event, _m.ButtonEvent):
                if event.button != _m.LEFT:
                    return
                if event.event_type == _m.UP:
                    on_event(EVT_UP_LEFT)
                elif event.event_type == _m.DOWN:
                    on_event(EVT_DOWN_LEFT)
        except Exception as e:
            print(f"[codelang] mouse cb error: {e}", file=sys.stderr)

    _m.hook(_cb)
    return _cb


def _install_mac(on_event: EventCallback):
    from pynput import mouse as _pm  # type: ignore[import-not-found]

    def _on_click(x, y, button, pressed):
        try:
            if button != _pm.Button.left:
                return
            on_event(EVT_DOWN_LEFT if pressed else EVT_UP_LEFT)
        except Exception as e:
            print(f"[codelang] mouse cb error: {e}", file=sys.stderr)

    def _on_move(x, y):
        try:
            on_event(EVT_MOVE)
        except Exception:
            pass

    listener = _pm.Listener(on_click=_on_click, on_move=_on_move)
    listener.daemon = True
    listener.start()
    return listener
