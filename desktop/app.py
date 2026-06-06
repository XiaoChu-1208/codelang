"""codelang desktop app.

Architecture:
- Mouse hook (Windows: boppreh/mouse, macOS: pynput) lives in a daemon thread,
  posts events to a thread-safe Queue.
- Main thread runs tk mainloop, polls the queue every 15ms via after().
- On Alt(Win) / Option(Mac) + mouse-up: snapshot clipboard → set sentinel →
  synthesize Ctrl+C (Win) / Cmd+C (Mac) → poll clipboard until changed →
  restore old clipboard → smart_lookup → show tooltip.
- LLM (if enabled) runs in worker thread, posts result back via queue.

Run:  py -m desktop.app    (Windows)
      python3 -m desktop.app   (macOS / Linux)
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

import pyperclip

from . import config, dialog, dict_updater, keyboard_backend, mouse_backend, platform_compat as winhelp
from .paths import resource_root
from .welcome import show_welcome, should_show as _welcome_should_show
from .logging_setup import setup_logging, LOG_FILE
from .lookup import (
    DictIndex,
    Entry,
    LookupResult,
    Translator,
    USER_DICT_JSON,
    USER_DICT_YAML,
    append_user_entry,
    llm_lookup,
)
from .ui import Tooltip

IS_MAC = winhelp.IS_MAC

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
    """Set sentinel → synthesize copy hotkey → poll for change → restore.
    Returns the captured selection or None if nothing was copied within
    CLIPBOARD_TIMEOUT_MS. The copy hotkey is Ctrl+C on Windows and Cmd+C on
    macOS (platform_compat handles the difference)."""
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
            dev_mode=bool(self.cfg.get("dev_mode", False)),
            on_vocab_save=self._on_vocab_save,
        )

        self.queue: "queue.Queue[tuple]" = queue.Queue()
        self._mouse_hook = None
        self._kb_hook = None
        self._ocr_busy = False  # guards against re-entrant captures while one is open
        self._tray_icon = None
        self._mac_status_item = None  # NSStatusItem on Mac; held to prevent GC
        self._mac_menu_handler = None
        self._mac_version_item = None   # NSMenuItem showing dict count/version
        self._mac_download_item = None  # NSMenuItem "下载新词库" (hidden until update)
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

    # ---------- mouse hook (cross-platform) ----------

    def start_mouse_hook(self) -> None:
        """Install a single global mouse hook that drives both the trigger
        flow (Alt/Option + drag) and the outside-click dismiss. We previously
        had two separate hooks installed via the `mouse` package's additive
        API, but pynput on macOS uses a single Listener per process, so we
        consolidate.
        """
        def on_event(evt: str) -> None:
            try:
                if evt == mouse_backend.EVT_MOVE:
                    self._last_mouse_activity = time.monotonic()
                    return
                # Any button event also counts as activity for idle tracking.
                self._last_mouse_activity = time.monotonic()

                if evt == mouse_backend.EVT_DOWN_LEFT:
                    # Outside-click dismiss: capture cursor position, let main
                    # thread decide whether it falls inside any visible card.
                    x, y = winhelp.get_cursor_pos()
                    self.queue.put(("outside_click", x, y))
                    return

                if evt != mouse_backend.EVT_UP_LEFT:
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

        self._mouse_hook = mouse_backend.install_hook(on_event)
        mod_name = "Option" if IS_MAC else "Alt"
        print(f"[codelang] mouse hook installed ({mod_name}+drag)", file=sys.stderr)

    def start_alt_idle_cleanup(self) -> None:
        """Background daemon: silently force-release Alt/Option when no mouse
        activity for a while.

        The premise: real users hold the modifier only while actively moving
        the mouse to select text. If it looks held in OS state but the user
        hasn't moved the mouse for a few seconds, it's almost certainly
        phantom — leftover from the Ctrl+C dance racing the user's physical
        release on Windows. (On Mac we don't do the Alt-up/down dance, so
        phantom Option is much rarer; the cleanup still acts as a safety net.)

        We periodically (every 1s) check this condition. The cleanup is a
        single synthetic Alt/Option-UP; harmless if it was already up.
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
                    mod_name = "Option" if IS_MAC else "Alt"
                    print(f"[codelang] silently cleared phantom {mod_name} (idle>2s)", file=sys.stderr)
                except Exception as e:
                    print(f"[codelang] alt-cleanup error: {e}", file=sys.stderr)

        threading.Thread(target=loop, daemon=True).start()
        print("[codelang] alt idle-cleanup thread started", file=sys.stderr)

    # ---------- OCR capture (macOS) ----------

    def start_ocr_hotkey(self) -> None:
        """Install the global ⌥+` hotkey that captures a screen region, OCRs
        it, and feeds the text through the same lookup pipeline as a selection.
        macOS-only for now; no-op elsewhere. Lets the user look up text that
        can't be selected/copied — images, PDFs, video, locked-down fields.
        """
        if not IS_MAC or not self.cfg.get("ocr_enabled", True):
            return

        def on_hotkey():
            # Fires on the pynput listener thread. Do the slow work (crosshair +
            # OCR) on a worker so the listener stays responsive, and drop the
            # event entirely if a capture is already in progress.
            if self._ocr_busy:
                return
            self._ocr_busy = True
            threading.Thread(target=self._ocr_worker, daemon=True).start()

        self._kb_hook = keyboard_backend.install_hotkey(on_hotkey, winhelp.alt_pressed)
        if self._kb_hook is not None:
            print("[codelang] OCR hotkey installed (Option+`)", file=sys.stderr)

    def _ocr_worker(self) -> None:
        """Crosshair-capture a region → Vision OCR → queue a lookup trigger.
        Runs on a daemon worker thread."""
        from . import capture_mac, ocr_mac
        try:
            # Screenshot OCR needs Screen Recording permission (separate from
            # Accessibility). Preflight first — without it the capture comes
            # back blank/black and OCR silently finds nothing. Prompt + explain
            # once, then bail; the grant only applies after a restart.
            srt = getattr(winhelp, "is_screen_recording_trusted", None)
            if srt is not None and not srt(prompt=False):
                srt(prompt=True)
                self.queue.put((
                    "show_info", "codelang 需要屏幕录制权限",
                    "截图取词（Option+`）需要「屏幕录制」权限才能看到屏幕内容。\n\n"
                    "请打开：系统设置 → 隐私与安全性 → 屏幕录制\n"
                    "把当前运行 codelang 的 Python（或 codelang）勾上，"
                    "勾完后重启 codelang 即可。",
                ))
                return
            path = capture_mac.capture_region_to_file()
            if not path:
                print("[codelang] OCR capture cancelled", file=sys.stderr)
                return
            # Snapshot the cursor the instant the drag ends (the selection box's
            # release corner) — BEFORE the ~100ms OCR, during which the pointer
            # drifts away. This anchors the card at the box corner instead of
            # wherever the mouse happened to be after recognition finished.
            cx, cy = winhelp.get_cursor_pos()
            try:
                raw = ocr_mac.ocr_image_file(path)
            finally:
                capture_mac._unlink(path)

            term = self._clean_ocr_text(raw)
            if not term:
                print("[codelang] OCR found no usable text", file=sys.stderr)
                return
            print(f"[codelang] OCR captured: {term[:60]!r}", file=sys.stderr)
            self.queue.put(("trigger", cx, cy, term))
        except Exception as e:
            import traceback
            print(f"[codelang] OCR worker error: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
        finally:
            self._ocr_busy = False

    def _clean_ocr_text(self, raw: str) -> str:
        """Normalize multi-line OCR output into a single lookup query: collapse
        whitespace/newlines to single spaces. Reject empties and anything past
        ocr_max_len (almost certainly a captured paragraph, not a term — the
        downstream smart_lookup/LLM path isn't meant for that)."""
        if not raw:
            return ""
        term = " ".join(raw.split())
        if not term:
            return ""
        if len(term) > int(self.cfg.get("ocr_max_len", 80)):
            print(
                f"[codelang] OCR text too long ({len(term)} chars), ignoring",
                file=sys.stderr,
            )
            return ""
        return term

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
            dialog.show_info(self.root, title, body)
        elif kind == "mac_menu_refresh":
            # Posted by background threads so the AppKit menu mutation lands
            # on the main thread (here, inside the tk queue poll).
            self._mac_refresh_menu()
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

    def _on_vocab_save(self, term: str) -> None:
        """Developer-only (存储词汇 button): stash a missed word to
        ~/.codelang/saved_vocab.txt for a later dictionary-expansion pass.
        Runs on the tk main thread; the file append is trivial so no worker."""
        config.save_vocab(term)
        print(f"[codelang] stashed vocab: {term!r}", file=sys.stderr)

    # ---------- tray ----------

    def start_tray(self) -> None:
        """Install a system-tray (Windows) or menu bar (macOS) icon. On Mac
        we go through PyObjC directly instead of pystray — pystray's macOS
        backend requires the NSStatusBar item to be created on the main
        thread, which conflicts with tk's mainloop on the same thread.
        Talking to AppKit directly lets us add the menu inline before tk's
        mainloop starts.
        """
        if IS_MAC:
            self._start_mac_tray()
        else:
            self._start_win_tray()

    def _start_win_tray(self) -> None:
        try:
            import pystray
            from PIL import Image, ImageDraw
        except Exception as e:
            print(f"[codelang] tray disabled: {e}", file=sys.stderr)
            return

        # Load the real codelang icon. Falls back to a drawn placeholder if
        # the asset file is missing (e.g. user ran without running render_icons.py).
        from pathlib import Path
        icon_path = resource_root() / "assets" / "logo" / "icon-64.png"
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
            if payload is None:
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

    def _start_mac_tray(self) -> None:
        """Create an NSStatusBar menu-bar item directly via PyObjC.

        Coexists with tk's mainloop because tk on macOS is itself built on
        Cocoa — both share the same NSApplication run loop. All NSMenu
        actions land on the main thread, so callbacks can safely touch the
        tk tree directly; we still post via the queue for consistency with
        the Windows path.
        """
        try:
            from AppKit import NSStatusBar, NSMenu, NSMenuItem, NSImage
            from Foundation import NSObject
        except ImportError as e:
            print(f"[codelang] menubar disabled (pyobjc missing: {e})", file=sys.stderr)
            return

        from pathlib import Path
        icon_path = resource_root() / "assets" / "logo" / "icon-32.png"

        # Capture references for the inner NSObject subclass — we can't easily
        # close over `self` because PyObjC selectors need NSObject methods.
        app_ref = self

        class _Handler(NSObject):
            def reload_(self, _sender):
                app_ref.dict.reload()
                print(f"[codelang] reloaded dict: {app_ref.dict.count} entries", file=sys.stderr)
                # Menu action → on the main thread, safe to touch AppKit directly.
                app_ref._mac_refresh_menu()

            def releaseAlt_(self, _sender):
                winhelp.force_release_alt()
                print("[codelang] forced Option release", file=sys.stderr)

            def openLogs_(self, _sender):
                import subprocess
                try:
                    if not LOG_FILE.exists():
                        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
                        LOG_FILE.touch()
                    subprocess.Popen(["open", str(LOG_FILE)])
                except Exception as e:
                    print(f"[codelang] open-logs failed: {e}", file=sys.stderr)

            def openFolder_(self, _sender):
                import subprocess
                try:
                    subprocess.Popen(["open", str(LOG_FILE.parent)])
                except Exception as e:
                    print(f"[codelang] open-folder failed: {e}", file=sys.stderr)

            def checkUpdate_(self, _sender):
                # Run network probe in a background thread so the menu click
                # returns immediately and the menubar UI doesn't beachball.
                def worker():
                    payload = dict_updater.check_remote(app_ref.dict.version)
                    if payload is None:
                        app_ref.queue.put((
                            "show_info", "词库更新",
                            f"已是最新（{app_ref.dict.count} 条）",
                        ))
                    else:
                        app_ref.has_update = True
                        app_ref.pending_update = payload
                        # Refresh on the main thread — this worker is a bg thread
                        # and AppKit menu mutation must not happen off-main.
                        app_ref.queue.put(("mac_menu_refresh",))
                        app_ref.queue.put((
                            "show_info", "词库更新",
                            f"发现新词库 {app_ref.dict.count} → "
                            f"{payload.get('count', '?')} 条\n"
                            "点菜单栏「下载新词库」即可应用。",
                        ))
                threading.Thread(target=worker, daemon=True).start()

            def downloadUpdate_(self, _sender):
                payload = app_ref.pending_update
                if not payload:
                    return
                try:
                    dict_updater.save_atomic(USER_DICT_JSON, payload)
                    app_ref.dict.reload()
                    app_ref.has_update = False
                    app_ref.pending_update = None
                    # Menu action → main thread; refresh count + hide download item.
                    app_ref._mac_refresh_menu()
                    app_ref.queue.put((
                        "show_info", "词库更新",
                        f"已更新到 {app_ref.dict.count} 条",
                    ))
                except Exception as e:
                    app_ref.queue.put(("show_info", "下载失败", f"写入失败：{e}"))

            def quit_(self, _sender):
                app_ref.queue.put(("quit",))

        handler = _Handler.alloc().init()
        self._mac_menu_handler = handler  # strong ref to prevent GC

        bar = NSStatusBar.systemStatusBar()
        item = bar.statusItemWithLength_(-1)  # NSVariableStatusItemLength
        button = item.button()

        img = None
        if icon_path.exists():
            try:
                img = NSImage.alloc().initWithContentsOfFile_(str(icon_path))
            except Exception as e:
                print(f"[codelang] menubar icon load failed: {e}", file=sys.stderr)
        if img is not None:
            try:
                img.setSize_((18, 18))
                # template=False so the icon keeps its gray-white color in
                # both light and dark menubars instead of being tinted black.
                img.setTemplate_(False)
                button.setImage_(img)
            except Exception:
                button.setTitle_("🛸")
        else:
            button.setTitle_("🛸")

        menu = NSMenu.alloc().init()
        menu.setAutoenablesItems_(False)

        def _disabled_item(title: str):
            mi = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, None, "")
            mi.setEnabled_(False)
            return mi

        def _action_item(title: str, selector: str):
            mi = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, selector, "")
            mi.setTarget_(handler)
            return mi

        v = self.dict.version[:10] if self.dict.version else "—"
        # Hold references to the two dynamic items so _mac_refresh_menu() can
        # update them later. NSMenu has no pystray-style callable labels —
        # items are static once added, so we mutate them in place.
        version_item = _disabled_item(f"词库: {self.dict.count} 条 · {v}")
        download_item = _action_item("下载新词库", "downloadUpdate:")
        download_item.setHidden_(True)  # only revealed once an update is found
        self._mac_version_item = version_item
        self._mac_download_item = download_item

        menu.addItem_(_disabled_item("codelang"))
        menu.addItem_(version_item)
        menu.addItem_(NSMenuItem.separatorItem())
        menu.addItem_(_action_item("查看日志", "openLogs:"))
        menu.addItem_(_action_item("打开配置目录", "openFolder:"))
        menu.addItem_(NSMenuItem.separatorItem())
        menu.addItem_(_action_item("检查词库更新", "checkUpdate:"))
        menu.addItem_(download_item)
        menu.addItem_(_action_item("重新加载词典", "reload:"))
        menu.addItem_(_action_item("释放卡住的 Option", "releaseAlt:"))
        menu.addItem_(NSMenuItem.separatorItem())
        menu.addItem_(_action_item("退出", "quit:"))

        item.setMenu_(menu)
        self._mac_status_item = item  # strong ref
        # An update may already have been detected before the menu existed
        # (the silent probe races menu construction) — sync state now.
        self._mac_refresh_menu()
        print("[codelang] macOS menubar item installed", file=sys.stderr)

    def _mac_refresh_menu(self) -> None:
        """Sync the macOS menubar item titles + the download item's visibility
        to the current dict count / pending-update state.

        MUST run on the main thread (AppKit menu mutation is not thread-safe);
        background callers post a ('mac_menu_refresh',) queue message instead.
        """
        if not IS_MAC:
            return
        version_item = self._mac_version_item
        if version_item is not None:
            v = self.dict.version[:10] if self.dict.version else "—"
            version_item.setTitle_(f"词库: {self.dict.count} 条 · {v}")
        download_item = self._mac_download_item
        if download_item is not None:
            if self.has_update and self.pending_update:
                n = self.pending_update.get("count", "?")
                download_item.setTitle_(f"下载新词库 ({n} 条)")
                download_item.setHidden_(False)
            else:
                download_item.setHidden_(True)

    # ---------- remote dict update ----------

    def _silent_check_for_update(self) -> None:
        """Background daemon: probe GitHub once at startup. Surfaces an
        update via tray notification (Windows) or in-app messagebox (macOS);
        stays completely quiet when up to date or offline."""
        try:
            payload = dict_updater.check_remote(self.dict.version)
            if not payload:
                return
            self.has_update = True
            self.pending_update = payload
            if not IS_MAC and self._tray_icon is not None:
                self._tray_icon.notify(
                    f"发现新词库 {self.dict.count} → {payload.get('count', '?')} 条，"
                    "点托盘菜单下载",
                    "codelang",
                )
                self._tray_icon.update_menu()
            elif IS_MAC:
                # No native banner without bundling — surface via in-app dialog,
                # and reveal the "下载新词库" menu item (refresh on main thread).
                self.queue.put(("mac_menu_refresh",))
                self.queue.put((
                    "show_info", "词库更新可用",
                    f"发现新词库 {self.dict.count} → "
                    f"{payload.get('count', '?')} 条\n"
                    "点菜单栏 codelang → 「下载新词库」即可应用。",
                ))
        except Exception as e:
            print(f"[codelang] silent update check error: {e}", file=sys.stderr)

    # ---------- accessibility prompt (macOS) ----------

    def _maybe_prompt_accessibility(self) -> None:
        """On Mac, surface the Accessibility-permission requirement to the
        user the first time. Silent on Windows / already-trusted Mac.

        We can't grant the permission ourselves — the user has to add the
        Python binary to System Settings → Privacy → Accessibility. The
        dialog points them there and tells them what to look for.
        """
        if not IS_MAC:
            return
        # If we're running from a macOS App Translocation path, the Accessibility
        # grant can never stick (every launch is a fresh random read-only path),
        # so prompting for it just sends the user in circles. Surface the real
        # fix — strip the quarantine xattr — instead.
        is_transloc = getattr(winhelp, "is_translocated", None)
        if is_transloc is not None and is_transloc():
            dialog.show_warning(
                self.root,
                "codelang 没法正常授权（应用易位）",
                "codelang 正在一个 macOS 的临时随机路径下运行（App "
                "Translocation / 应用易位），这种情况下「辅助功能」权限永远存不住，"
                "Option + 划词 会一直没反应。\n\n"
                "修复办法（任选其一）：\n"
                "① 退出 codelang，双击 DMG（或应用程序旁）的"
                "「① 修复并启动.command」。若提示「身份不明的开发者」打不开，"
                "右键点它 →「打开」即可；或\n"
                "② 打开「终端」，粘贴这一行回车：\n"
                "    xattr -dr com.apple.quarantine /Applications/codelang.app\n"
                "然后重新打开 codelang 即可。",
            )
            return
        check = getattr(winhelp, "is_accessibility_trusted", None)
        if check is None:
            return
        if check(prompt=False):
            return
        # Trigger the system prompt and also show our own explainer dialog.
        try:
            check(prompt=True)
        except Exception:
            pass
        dialog.show_warning(
            self.root,
            "codelang 需要辅助功能权限",
            "codelang 还没有获得「辅助功能（Accessibility）」权限，"
            "Option + 划词 会没反应。\n\n"
            "请打开：系统设置 → 隐私与安全性 → 辅助功能\n"
            "把当前用来跑 codelang 的 Python（或终端 App）勾上，"
            "勾完后重新启动 codelang 即可。\n\n"
            "首次勾选系统会让你输密码确认，正常操作。",
        )

    # ---------- run ----------

    def run(self) -> int:
        self.start_mouse_hook()
        self.start_alt_idle_cleanup()
        self.start_ocr_hotkey()
        self.start_tray()
        # Silent dict-update probe (opt-out via config). Daemon, so quitting
        # before the request returns doesn't hang shutdown.
        if self.cfg.get("dict_update_check_on_startup", True):
            threading.Thread(
                target=self._silent_check_for_update, daemon=True
            ).start()
        self.poll_queue()
        # On Mac, prompt for Accessibility permission once mainloop is up so
        # the messagebox parent has a real NSApp behind it.
        if IS_MAC:
            self.root.after(800, self._maybe_prompt_accessibility)
        # First-run welcome card (only shows once — see desktop/welcome.py).
        # Defer to after the mainloop spins up so the window has a stable
        # parent and the tray icon's already in place by the time the user
        # reads "灰白色小飞碟".
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
