"""codelang desktop app.

Architecture:
- Mouse hook (boppreh/mouse) lives in a daemon thread, posts events to a thread-safe Queue.
- Main thread runs tk mainloop, polls the queue every 15ms via after().
- On Alt+mouse-up: snapshot clipboard → set sentinel → SendInput Ctrl+C →
  poll clipboard until changed → restore old clipboard → smart_lookup → show tooltip.
- LLM (if enabled) runs in worker thread, posts result back via queue.

Run:  py -m desktop.app
"""
from __future__ import annotations

import queue
import sys
import threading
import time
import tkinter as tk

import mouse
import pyperclip

from . import config, win as winhelp
from .lookup import (
    DictIndex,
    Entry,
    LookupResult,
    Translator,
    append_user_entry,
    llm_lookup,
    rebuild_dict_json,
)
from .ui import Tooltip


SENTINEL = "\x00\x00CODELANG_SENTINEL\x00\x00"
CLIPBOARD_POLL_MS = 5
CLIPBOARD_TIMEOUT_MS = 200


def _safe_paste() -> str:
    try:
        v = pyperclip.paste()
    except Exception:
        return ""
    return v if isinstance(v, str) else ""


def _safe_copy(text: str) -> None:
    try:
        pyperclip.copy(text)
    except Exception:
        pass


def grab_selection(prev_clip: str) -> str | None:
    """Set sentinel → Ctrl+C → poll for change → restore. Returns selected text or None."""
    _safe_copy(SENTINEL)
    winhelp.send_ctrl_c()
    deadline = time.perf_counter() + CLIPBOARD_TIMEOUT_MS / 1000.0
    got: str | None = None
    while time.perf_counter() < deadline:
        cur = _safe_paste()
        if cur and cur != SENTINEL:
            got = cur
            break
        time.sleep(CLIPBOARD_POLL_MS / 1000.0)
    _safe_copy(prev_clip)
    return got


def is_reasonable(text: str, max_len: int) -> bool:
    t = text.strip()
    if not t:
        return False
    if len(t) > max_len:
        return False
    # Allow short multi-token selections (no newlines)
    if "\n" in t or "\r" in t:
        return False
    return True


class App:
    def __init__(self):
        winhelp.set_dpi_aware()
        self.cfg = config.load_config()
        self.dict = DictIndex()
        self.translator = Translator()

        self.root = tk.Tk()
        self.root.withdraw()
        self.tooltip = Tooltip(
            self.root,
            dot_interval_ms=int(self.cfg.get("loading_dot_interval_ms", 250)),
            error_close_ms=int(self.cfg.get("error_auto_close_ms", 1800)),
            on_user_save=self._on_user_save,
        )

        self.queue: "queue.Queue[tuple]" = queue.Queue()
        self._hook_thread_started = False
        self._tray_icon = None
        # Track whether Alt was held when the left mouse button went down.
        # We only trigger on mouse-up if Alt was held *throughout*, which avoids
        # false triggers when Alt is held only briefly (e.g. Alt+Tab finishing
        # right before a click).
        self._alt_at_mouse_down = False

        translator_status = (
            f"+ECDICT({self.translator.count})" if self.translator.available else ""
        )
        print(
            f"[codelang] dict loaded: {self.dict.count} entries {translator_status}",
            file=sys.stderr,
        )

    # ---------- mouse hook ----------

    def start_mouse_hook(self) -> None:
        def on_event(event):
            try:
                if not isinstance(event, mouse.ButtonEvent):
                    return
                if event.button != mouse.LEFT:
                    return
                # Track Alt at mouse-down so we know whether Alt was held throughout
                # the drag. Rules out false triggers from Alt+Tab → click sequences.
                if event.event_type == mouse.DOWN:
                    self._alt_at_mouse_down = winhelp.alt_pressed()
                    if self._alt_at_mouse_down:
                        print("[codelang] mouse-down with Alt held, watching for up", file=sys.stderr)
                    return
                if event.event_type != mouse.UP:
                    return
                if not self._alt_at_mouse_down:
                    return
                if not winhelp.alt_pressed():
                    print("[codelang] mouse-up: Alt released mid-drag, skip", file=sys.stderr)
                    self._alt_at_mouse_down = False
                    return
                cx, cy = winhelp.get_cursor_pos()
                prev_clip = _safe_paste()
                print(f"[codelang] triggering at ({cx},{cy}), prev_clip_len={len(prev_clip)}", file=sys.stderr)
                selected = grab_selection(prev_clip)
                self._alt_at_mouse_down = False
                if not selected:
                    print("[codelang] clipboard did not change — selection was empty or Ctrl+C blocked", file=sys.stderr)
                    return
                print(f"[codelang] grabbed: {selected[:50]!r}", file=sys.stderr)
                if not is_reasonable(selected, int(self.cfg.get("selection_max_len", 32))):
                    print(f"[codelang] selection rejected (len={len(selected)} or contains newline)", file=sys.stderr)
                    return
                self.queue.put(("trigger", cx, cy, selected.strip()))
            except Exception as e:
                import traceback
                print(f"[codelang] hook error: {e}", file=sys.stderr)
                traceback.print_exc(file=sys.stderr)

        mouse.hook(on_event)
        self._hook_thread_started = True
        print("[codelang] mouse hook installed (Alt+drag/double-click, Alt-dance restored)", file=sys.stderr)

    # ---------- queue polling on main thread ----------

    def poll_queue(self) -> None:
        try:
            while True:
                msg = self.queue.get_nowait()
                self._handle(msg)
        except queue.Empty:
            pass
        self.root.after(15, self.poll_queue)

    def _handle(self, msg: tuple) -> None:
        kind = msg[0]
        if kind == "trigger":
            _, cx, cy, term = msg
            result = self.dict.smart_lookup(term)
            if result.is_hit:
                gen = self.tooltip.new_generation()
                self.tooltip.show_entries(gen, result.entries, x=cx, y=cy, raw_query=term, cleanup=result.cleanup)
                return
            # Local miss → try translator (instant, in-memory)
            tr = self.translator.lookup(term)
            if tr:
                gen = self.tooltip.new_generation()
                self.tooltip.show_entries(gen, [tr], x=cx, y=cy, raw_query=term)
                return
            # Truly missing → show miss with input form (if LLM disabled), or trigger LLM
            if self.cfg.get("llm_fallback_enabled") and self.cfg.get("api_key"):
                gen = self.tooltip.show_loading(cx, cy, term)
                threading.Thread(target=self._llm_worker, args=(gen, term), daemon=True).start()
            else:
                gen = self.tooltip.new_generation()
                self.tooltip.show_miss(gen, term, x=cx, y=cy)
                config.log_missing(term)
        elif kind == "llm_result":
            _, gen, entry = msg
            self.tooltip.show_entries(gen, [entry])
        elif kind == "llm_error":
            _, gen, err = msg
            self.tooltip.show_error(gen, err)
        elif kind == "outside_click":
            _, x, y = msg
            if self.tooltip.is_visible() and not self.tooltip.contains_point(x, y):
                self.tooltip.hide()
        elif kind == "user_save_done":
            _, gen, ok, info = msg
            self.tooltip.on_user_save_done(gen, ok, info)
        elif kind == "quit":
            self.root.destroy()

    def _llm_worker(self, gen: int, term: str) -> None:
        try:
            entry = llm_lookup(term, self.cfg)
            self.queue.put(("llm_result", gen, entry))
        except Exception as e:
            self.queue.put(("llm_error", gen, str(e)[:80]))

    def _on_user_save(self, gen: int, term: str, meaning: str, example: str) -> None:
        """Called from UI when user submits a manual entry. Persist + reload + show."""
        def worker():
            try:
                append_user_entry(term, meaning, example)
                ok, info = rebuild_dict_json()
                if ok:
                    self.dict.reload()
                self.queue.put(("user_save_done", gen, ok, info))
            except Exception as e:
                self.queue.put(("user_save_done", gen, False, str(e)[:120]))

        threading.Thread(target=worker, daemon=True).start()

    # ---------- close-on-outside-click ----------

    def start_outside_click_hook(self) -> None:
        def on_event(event):
            try:
                if not isinstance(event, mouse.ButtonEvent):
                    return
                if event.event_type != mouse.DOWN or event.button != mouse.LEFT:
                    return
                x, y = winhelp.get_cursor_pos()
                self.queue.put(("outside_click", x, y))
            except Exception:
                pass

        mouse.hook(on_event)

    # ---------- tray ----------

    def start_tray(self) -> None:
        try:
            import pystray
            from PIL import Image, ImageDraw
        except Exception as e:
            print(f"[codelang] tray disabled: {e}", file=sys.stderr)
            return

        img = Image.new("RGB", (64, 64), color=(29, 78, 216))
        d = ImageDraw.Draw(img)
        d.rectangle([12, 12, 52, 52], outline=(255, 255, 255), width=4)

        def on_reload(icon, item):
            self.dict.reload()
            print(f"[codelang] reloaded dict: {self.dict.count} entries", file=sys.stderr)

        def on_release_alt(icon, item):
            winhelp.force_release_alt()
            print("[codelang] forced Alt release", file=sys.stderr)

        def on_quit(icon, item):
            icon.stop()
            self.queue.put(("quit",))

        menu = pystray.Menu(
            pystray.MenuItem("codelang", lambda *_: None, enabled=False),
            pystray.MenuItem(lambda item: f"词库: {self.dict.count} 条", lambda *_: None, enabled=False),
            pystray.MenuItem("重新加载词典", on_reload),
            pystray.MenuItem("释放卡住的 Alt", on_release_alt),
            pystray.MenuItem("退出", on_quit),
        )
        icon = pystray.Icon("codelang", img, "codelang (Alt+划词)", menu)
        self._tray_icon = icon
        threading.Thread(target=icon.run, daemon=True).start()

    # ---------- run ----------

    def run(self) -> int:
        self.start_mouse_hook()
        self.start_outside_click_hook()
        self.start_tray()
        self.poll_queue()
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            pass
        return 0


def main() -> int:
    return App().run()


if __name__ == "__main__":
    raise SystemExit(main())
