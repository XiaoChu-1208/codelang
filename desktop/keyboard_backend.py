"""Cross-platform global hotkey for the OCR trigger.

Currently macOS-only (the OCR feature ships mac-first). On other platforms
install_hotkey() is a no-op that returns None, so callers don't need to
branch — the feature is simply inert until a Windows backend lands.

macOS uses pynput's keyboard Listener, which — like the mouse hook — needs
Accessibility permission granted to the running Python binary. We detect the
modifier via the caller-supplied `modifier_down` callback (reusing the same
CGEventSourceFlagsState check app.py already uses for Option) rather than
tracking modifier state inside pynput, which is fiddly and drifts.

The trigger key is the backtick/tilde key (⌥ + `). We match on the hardware
virtual keycode (50) rather than the produced character, because Option+`
emits a dead-key accent rather than a literal backtick.
"""
from __future__ import annotations

import sys
from typing import Callable

# macOS hardware keycode for the `~ key (HIToolbox Events.h: kVK_ANSI_Grave).
_KC_GRAVE = 50

HotkeyCallback = Callable[[], None]
ModifierCheck = Callable[[], bool]


def install_hotkey(on_hotkey: HotkeyCallback, modifier_down: ModifierCheck):
    """Install the global OCR hotkey (⌥+`). Returns the listener handle (held
    by the caller to keep it alive), or None on unsupported platforms."""
    if sys.platform != "darwin":
        return None
    return _install_mac(on_hotkey, modifier_down)


def _install_mac(on_hotkey: HotkeyCallback, modifier_down: ModifierCheck):
    from pynput import keyboard as _kb  # type: ignore[import-not-found]

    # Debounce: key auto-repeat fires on_press repeatedly while held. Only act
    # on the leading edge; re-arm on release of the grave key.
    armed = {"down": False}

    def _on_press(key):
        try:
            if getattr(key, "vk", None) != _KC_GRAVE:
                return
            if not modifier_down():
                return
            if armed["down"]:
                return
            armed["down"] = True
            on_hotkey()
        except Exception as e:
            print(f"[codelang] hotkey cb error: {e}", file=sys.stderr)

    def _on_release(key):
        try:
            if getattr(key, "vk", None) == _KC_GRAVE:
                armed["down"] = False
        except Exception:
            pass

    listener = _kb.Listener(on_press=_on_press, on_release=_on_release)
    listener.daemon = True
    listener.start()
    return listener
