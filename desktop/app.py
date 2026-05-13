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

# Preflight: if third-party deps are missing the shortcut would otherwise
# silently fail under pythonw (no console = no visible ImportError). Show a
# real dialog so the user can fix it. Must happen BEFORE the heavy imports
# below or this module won't even load.
from . import deps_error as _deps_error

_missing = _deps_error.check_required()
if _missing:
    _deps_error.show(_missing)
    sys.exit(1)

import mouse
import pyperclip

from . import config, dict_updater, win as winhelp
from .welcome import show_welcome, should_show as _welcome_should_show
from .logging_setup import setup_logging, LOG_FILE
from .lookup import (
    DictIndex,
    Entry,
    LookupResult,
    Translator,
    USER_DICT_YAML,
    append_user_entry,
    llm_lookup,
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


def _migrate_legacy_user_yaml() -> None:
    """One-shot: move pre-refactor user additions from dict/user.yaml (in the
    project tree, clobbered by remote updates/reinstalls) into
    ~/.codelang/user_dict.yaml (safe in the user dir). Idempotent — once the
    legacy file has been moved we rename it .yaml.migrated so we don't try
    again on subsequent startups.

    The size threshold (>80 bytes) is to distinguish a real user dict from a
    template containing just the comment header. False positives are harmless
    (we'd just copy a slightly larger comment file once).
    """
    from pathlib import Path
    legacy = Path(__file__).resolve().parent.parent / "dict" / "user.yaml"
    if not legacy.exists() or legacy.stat().st_size <= 80:
        return
    try:
        USER_DICT_YAML.parent.mkdir(parents=True, exist_ok=True)
        if not USER_DICT_YAML.exists():
            USER_DICT_YAML.write_text(legacy.read_text(encoding="utf-8"), encoding="utf-8")
            print(f"[codelang] migrated user dict: {legacy} → {USER_DICT_YAML}", file=sys.stderr)
        legacy.rename(legacy.with_suffix(".yaml.migrated"))
    except OSError as e:
        print(f"[codelang] user dict migration skipped: {e}", file=sys.stderr)


class App:
    def __init__(self):
        setup_logging()
        winhelp.set_dpi_aware()
        self.cfg = config.load_config()
        _migrate_legacy_user_yaml()
        self.dict = DictIndex()
        self.translator = Translator()
        # Remote-update state, populated by _silent_check_for_update().
        # has_update flips True when a newer dict.json is available on main;
        # pending_update holds the already-downloaded payload so the "下载"
        # menu click is instant (no second network roundtrip).
        self.has_update: bool = False
        self.pending_update: "dict | None" = None

        self.root = tk.Tk()
        self.root.withdraw()
        self.tooltip = Tooltip(
            self.root,
            dot_interval_ms=int(self.cfg.get("loading_dot_interval_ms", 250)),
            error_close_ms=int(self.cfg.get("error_auto_close_ms", 1800)),
            on_user_save=self._on_user_save,
            on_chip_click=self._on_chip_click,
            find_refs_fn=self.dict.find_referenced_terms,
        )

        self.queue: "queue.Queue[tuple]" = queue.Queue()
        self._hook_thread_started = False
        self._tray_icon = None
        # Track the timestamp of the last real mouse activity. The background Alt
        # cleanup thread uses this to decide whether to nuke a stuck Alt state:
        # if we haven't seen any mouse motion/click for a few seconds AND Alt
        # currently shows as "down" in OS state, it's almost certainly phantom
        # Alt left over from our send_ctrl_c dance — clean it.
        self._last_mouse_activity = time.monotonic()

        translator_status = (
            f"+ECDICT({self.translator.count})" if self.translator.available else ""
        )
        print(
            f"[codelang] dict loaded: {self.dict.count} entries {translator_status}",
            file=sys.stderr,
        )

    # ---------- mouse hook ----------

    def start_mouse_hook(self) -> None:
        """Original-style synchronous mouse hook: on Alt+mouse-up we do the
        clipboard dance inline. The earlier "deferred to worker thread" attempt
        broke취ing in real-world apps (Claude / Chrome), even though it was
        theoretically cleaner. Reverting to what worked.

        Phantom Alt cleanup is handled separately by the background idle thread —
        see start_alt_idle_cleanup.
        """
        def on_event(event):
            try:
                if not isinstance(event, mouse.ButtonEvent):
                    if isinstance(event, mouse.MoveEvent):
                        self._last_mouse_activity = time.monotonic()
                    return
                # Any mouse event resets the idle timer
                self._last_mouse_activity = time.monotonic()
                if event.event_type != mouse.UP or event.button != mouse.LEFT:
                    return
                if not winhelp.alt_pressed():
                    return
                title, cls = winhelp.get_foreground_window_info()
                print(f"[codelang] trigger in '{title}' (class={cls})", file=sys.stderr)
                cx, cy = winhelp.get_cursor_pos()
                prev_clip = _safe_paste()
                selected = grab_selection(prev_clip)
                if not selected:
                    # Silent failure — Alt+double-click fires this hook twice
                    # (once on each mouse-up), and the first click usually has
                    # no selection yet. Any visible "no selection" UI here
                    # would pop up mid-gesture and feel like a bug. Just log.
                    print(f"[codelang] no selection captured at ({cx},{cy})", file=sys.stderr)
                    return
                print(f"[codelang] grabbed: {selected[:50]!r}", file=sys.stderr)
                if not is_reasonable(selected, int(self.cfg.get("selection_max_len", 32))):
                    return
                self.queue.put(("trigger", cx, cy, selected.strip()))
            except Exception as e:
                import traceback
                print(f"[codelang] hook error: {e}", file=sys.stderr)
                traceback.print_exc(file=sys.stderr)

        mouse.hook(on_event)
        self._hook_thread_started = True
        print("[codelang] mouse hook installed (Alt+drag, sync)", file=sys.stderr)

    def start_alt_idle_cleanup(self) -> None:
        """Background daemon: silently force-release Alt when no mouse activity
        for a while.

        The premise: real users hold Alt only when actively moving the mouse to
        select text. If Alt looks held in OS state but the user hasn't moved the
        mouse for a few seconds, it's almost certainly phantom — leftover from
        send_ctrl_c's Alt UP/DOWN dance racing the user's physical release.

        We periodically (every 1s) check this condition. The cleanup is a single
        synthetic Alt-UP; harmless if Alt was already up. If a user is genuinely
        idle with Alt physically held (rare), they'd need to re-press to do the
        next codelang trigger — acceptable trade.
        """
        IDLE_THRESHOLD = 2.0  # seconds of mouse idle before considering Alt phantom

        def loop():
            while True:
                try:
                    time.sleep(1.0)
                    if not winhelp.alt_pressed():
                        continue
                    if time.monotonic() - self._last_mouse_activity < IDLE_THRESHOLD:
                        continue
                    # Alt looks held + no recent mouse activity → almost certainly phantom
                    winhelp.force_release_alt()
                    print("[codelang] silently cleared phantom Alt (idle>2s)", file=sys.stderr)
                except Exception as e:
                    print(f"[codelang] alt-cleanup error: {e}", file=sys.stderr)

        threading.Thread(target=loop, daemon=True).start()
        print("[codelang] alt idle-cleanup thread started", file=sys.stderr)

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
        elif kind == "show_info":
            _, title, body = msg
            from tkinter import messagebox
            messagebox.showinfo(title, body)
        elif kind == "quit":
            self.root.destroy()

    def _llm_worker(self, gen: int, term: str) -> None:
        try:
            entry = llm_lookup(term, self.cfg)
            self.queue.put(("llm_result", gen, entry))
        except Exception as e:
            self.queue.put(("llm_error", gen, str(e)[:80]))

    def _on_chip_click(self, term: str) -> None:
        """User clicked a "相关" chip in the tooltip. Look up the term and append
        a stacked sub-card below the current chain. Runs on tk main thread (chip
        is a tk widget binding), so it's safe to do the lookup synchronously.
        """
        try:
            result = self.dict.smart_lookup(term)
            if result.is_hit:
                self.tooltip.append_stacked_card(term, result.entries)
                return
            tr = self.translator.lookup(term)
            if tr:
                self.tooltip.append_stacked_card(term, [tr])
                return
            self.tooltip.append_stacked_card(term, [], missing=True)
        except Exception as e:
            print(f"[codelang] chip lookup error: {e}", file=sys.stderr)

    def _on_user_save(self, gen: int, term: str, meaning: str, example: str) -> None:
        """Called from UI when user submits a manual entry. Persist to the
        user YAML overlay and reload — no subprocess build step anymore, since
        DictIndex._load() reads user_dict.yaml directly at runtime."""
        def worker():
            try:
                append_user_entry(term, meaning, example)
                self.dict.reload()
                self.queue.put(("user_save_done", gen, True, f"saved «{term}»"))
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

        # Load the real codelang icon. Falls back to a drawn placeholder if
        # the asset file is missing (e.g. user ran without running render_icons.py).
        from pathlib import Path
        icon_path = Path(__file__).resolve().parent.parent / "assets" / "logo" / "icon-64.png"
        if icon_path.exists():
            img = Image.open(icon_path)
        else:
            img = Image.new("RGB", (64, 64), color=(29, 78, 216))
            d = ImageDraw.Draw(img)
            d.rectangle([12, 12, 52, 52], outline=(255, 255, 255), width=4)
            print(f"[codelang] using placeholder tray icon (asset missing at {icon_path})", file=sys.stderr)

        def on_reload(icon, item):
            self.dict.reload()
            print(f"[codelang] reloaded dict: {self.dict.count} entries", file=sys.stderr)

        def on_release_alt(icon, item):
            winhelp.force_release_alt()
            print("[codelang] forced Alt release", file=sys.stderr)

        def on_open_logs(icon, item):
            import subprocess
            try:
                # Create file if missing so notepad doesn't bark
                if not LOG_FILE.exists():
                    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
                    LOG_FILE.touch()
                subprocess.Popen(["notepad.exe", str(LOG_FILE)])
            except Exception as e:
                print(f"[codelang] open-logs failed: {e}", file=sys.stderr)

        def on_open_log_folder(icon, item):
            import subprocess
            try:
                subprocess.Popen(["explorer.exe", str(LOG_FILE.parent)])
            except Exception as e:
                print(f"[codelang] open-folder failed: {e}", file=sys.stderr)

        def on_quit(icon, item):
            icon.stop()
            self.queue.put(("quit",))

        def on_check_update(icon, item):
            # User-triggered: fetch and report result via messagebox.
            # Runs on pystray's own thread, safe to do the blocking GET here.
            payload = dict_updater.check_remote(self.dict.version)
            from tkinter import messagebox
            if payload is None:
                # Either we're up to date or the request failed — try a HEAD-style
                # distinction by re-fetching for "definitely no update" vs error.
                # Simpler: just tell the user no update available; check_remote's
                # internal print already logged any error.
                self.queue.put(("show_info", "词库更新", f"已是最新（{self.dict.count} 条）"))
            else:
                self.has_update = True
                self.pending_update = payload
                self._tray_icon.update_menu()
                self.queue.put((
                    "show_info",
                    "词库更新",
                    f"发现新词库 {self.dict.count} → {payload.get('count', '?')} 条\n"
                    f"远程时间 {str(payload.get('version', ''))[:19]}\n"
                    "点托盘菜单「下载新词库」即可应用。",
                ))

        def on_download_update(icon, item):
            payload = self.pending_update
            if not payload:
                return
            try:
                dict_updater.save_atomic(USER_DICT_JSON, payload)
                self.dict.reload()
                count = self.dict.count
                self.has_update = False
                self.pending_update = None
                self._tray_icon.update_menu()
                self._tray_icon.notify(f"已更新到 {count} 条", "codelang")
                print(f"[codelang] dict updated → {count} entries", file=sys.stderr)
            except Exception as e:
                self.queue.put(("show_info", "下载失败", f"写入失败：{e}"))

        def update_label(item):
            v = self.dict.version[:10] if self.dict.version else "—"
            return f"词库: {self.dict.count} 条 · {v}"

        def download_label(item):
            n = self.pending_update.get("count", "?") if self.pending_update else "?"
            return f"下载新词库 ({n} 条)"

        menu = pystray.Menu(
            pystray.MenuItem("codelang", lambda *_: None, enabled=False),
            pystray.MenuItem(update_label, lambda *_: None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("查看日志", on_open_logs),
            pystray.MenuItem("打开配置目录", on_open_log_folder),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("检查词库更新", on_check_update),
            pystray.MenuItem(
                download_label,
                on_download_update,
                visible=lambda _: self.has_update,
            ),
            pystray.MenuItem("重新加载词典", on_reload),
            pystray.MenuItem("释放卡住的 Alt", on_release_alt),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", on_quit),
        )
        icon = pystray.Icon("codelang", img, "codelang (Alt+划词)", menu)
        self._tray_icon = icon
        threading.Thread(target=icon.run, daemon=True).start()

    # ---------- remote dict update ----------

    def _silent_check_for_update(self) -> None:
        """Background daemon: probe GitHub once at startup. Surfaces an
        update via tray notification + dynamic 'download' menu item; stays
        completely quiet when up to date or offline."""
        try:
            payload = dict_updater.check_remote(self.dict.version)
            if not payload:
                return
            self.has_update = True
            self.pending_update = payload
            if self._tray_icon is not None:
                self._tray_icon.notify(
                    f"发现新词库 {self.dict.count} → {payload.get('count', '?')} 条，"
                    "点托盘菜单下载",
                    "codelang",
                )
                self._tray_icon.update_menu()
        except Exception as e:
            print(f"[codelang] silent update check error: {e}", file=sys.stderr)

    # ---------- run ----------

    def run(self) -> int:
        self.start_mouse_hook()
        self.start_outside_click_hook()
        self.start_alt_idle_cleanup()
        self.start_tray()
        # Silent dict-update probe (opt-out via config). Daemon, so quitting
        # before the request returns doesn't hang shutdown.
        if self.cfg.get("dict_update_check_on_startup", True):
            threading.Thread(
                target=self._silent_check_for_update, daemon=True
            ).start()
        self.poll_queue()
        # First-run welcome card (only shows once — see desktop/welcome.py).
        # Defer to after the mainloop spins up so the window has a stable
        # parent and the tray icon's already in place by the time the user
        # reads "右下角灰白色小飞碟".
        if _welcome_should_show():
            self.root.after(400, lambda: show_welcome(self.root))
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            pass
        return 0


def main() -> int:
    return App().run()


if __name__ == "__main__":
    raise SystemExit(main())
