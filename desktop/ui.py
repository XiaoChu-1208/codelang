"""Tooltip-style popup (tkinter, pre-warmed). Supports multi-entry stacking, miss state with inline input form.

Generation counter pattern: every new trigger increments self._gen. Background workers
embed the gen they were started with; updates with a mismatched gen are discarded.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from typing import Callable, Optional

from . import platform_compat as winhelp
from .lookup import Entry

CATEGORY_LABEL = {
    "devterm": "开发术语",
    "jargon": "互联网黑话",
    "abbr": "缩写",
    "slang": "职场俚语",
    "translation": "通用翻译",
    "user": "自录入",
    "llm": "AI 解释",
    "llm-cache": "AI 解释(缓存)",
    "misc": "其他",
}

SOURCE_LABEL = {
    "local": "本地词库",
    "translation": "通用翻译·非术语词典",
    "user": "自录入",
    "llm": "AI 解释",
    "llm-cache": "AI 缓存",
}

DOT_FRAMES = ["·    ", "· ·  ", "· · ·"]


MAX_STACK_DEPTH = 4  # primary + up to 3 stacked sub-cards (4 total)


class Tooltip:
    def __init__(
        self,
        root: tk.Tk,
        dot_interval_ms: int = 250,
        error_close_ms: int = 1800,
        on_user_save: Optional[Callable[[int, str, str, str], None]] = None,
        on_chip_click: Optional[Callable[[str], None]] = None,
        find_refs_fn: Optional[Callable[[str, set[str]], list[str]]] = None,
    ):
        self.root = root
        self.dot_interval_ms = dot_interval_ms
        self.error_close_ms = error_close_ms
        self.on_user_save = on_user_save
        self.on_chip_click = on_chip_click  # callback(term) when user clicks a 相关 chip
        self.find_refs_fn = find_refs_fn    # callable(text, exclude_set) -> list[str]

        self._gen = 0
        self._loading = False
        self._dot_idx = 0
        self._dot_after_id: str | None = None
        self._auto_close_after_id: str | None = None
        self._current_term: str = ""
        self._input_visible = False
        # Stacked sub-cards: each is a (Toplevel, term) — empty when no drill-down active.
        # The primary self.top window is implicitly stack depth 0.
        self.sub_windows: list[tuple[tk.Toplevel, str]] = []

        self.top = tk.Toplevel(root)
        self.top.withdraw()
        self.top.overrideredirect(True)
        self.top.attributes("-topmost", True)
        try:
            self.top.attributes("-toolwindow", True)
        except tk.TclError:
            pass

        self.bg = "#fdfdfd"
        self.border = "#c6c6c6"
        self.text_dark = "#1a1a1a"
        self.text_meta = "#767676"
        self.text_translation_meta = "#a07020"  # 暖色提示"非术语"
        self.cat_bg = "#eef4ff"
        self.cat_fg = "#1d4ed8"
        self.user_cat_bg = "#e8f7e8"
        self.user_cat_fg = "#1e7a1e"
        self.translation_cat_bg = "#fff4d6"
        self.translation_cat_fg = "#a07020"

        # 1px border via outer frame
        self.outer = tk.Frame(self.top, bg=self.border)
        self.outer.pack(fill="both", expand=True)
        self.inner = tk.Frame(self.outer, bg=self.bg, padx=10, pady=8)
        self.inner.pack(fill="both", expand=True, padx=1, pady=1)

        families = set(tkfont.families())
        # Pick a platform-appropriate UI font. Mac's stock San Francisco
        # variants render badly in tk on some setups; Helvetica Neue +
        # PingFang SC is the most reliable mac combo and tk falls back to
        # PingFang for CJK glyphs automatically. Windows keeps the existing
        # Segoe / YaHei pair.
        if winhelp.IS_MAC:
            for candidate in ("PingFang SC", "Helvetica Neue", "Lucida Grande"):
                if candidate in families:
                    family = candidate
                    break
            else:
                family = "TkDefaultFont"
        else:
            family = "Segoe UI" if "Segoe UI" in families else (
                "Microsoft YaHei UI" if "Microsoft YaHei UI" in families else "TkDefaultFont"
            )
        self.font_title = tkfont.Font(family=family, size=11, weight="bold")
        self.font_cat = tkfont.Font(family=family, size=8)
        self.font_label = tkfont.Font(family=family, size=8)
        self.font_body = tkfont.Font(family=family, size=9)
        self.font_btn = tkfont.Font(family=family, size=8, underline=True)

        # Body Label wraplength, computed from actual font metrics so the card
        # scales with whatever DPI / font size the user's system produces.
        # Old behavior was a hardcoded 320 pixels which on HiDPI displays gave
        # ~25 CJK chars per line — way too narrow, making typical 2-sentence
        # meanings wrap into 4-5 visually noisy lines, and mixed CJK+ASCII
        # sometimes broke into "two-words-per-line" looking stacks.
        # 40 CJK chars per line keeps lines reading naturally without forcing
        # the card to dominate the screen. measure("一") returns the actual
        # rendered glyph width in physical pixels at the current font scale.
        cjk_char_w = max(self.font_body.measure("一"), 8)
        self.body_wraplength = cjk_char_w * 40

        # Loading row (used when waiting on LLM)
        self.lbl_loading = tk.Label(
            self.inner, text="", bg=self.bg, fg=self.text_meta, font=self.font_body, anchor="w"
        )

        # Container for entry blocks (cleared/repopulated on each show)
        self.entries_frame = tk.Frame(self.inner, bg=self.bg)
        self.entries_frame.pack(fill="x", anchor="w")

        # Miss / input form (also created lazily)
        self.miss_frame = tk.Frame(self.inner, bg=self.bg)
        self.input_frame: Optional[tk.Frame] = None

        # Source footer
        self.lbl_source = tk.Label(
            self.inner, text="", bg=self.bg, fg=self.text_meta, font=self.font_cat, anchor="w"
        )

        self.top.bind("<Escape>", lambda _e: self.hide())

    # ---------- public API ----------

    def new_generation(self) -> int:
        self._gen += 1
        return self._gen

    def current_generation(self) -> int:
        return self._gen

    def show_loading(self, x: int, y: int, term: str) -> int:
        gen = self.new_generation()
        self._cancel_auto_close()
        self._clear_entries()
        self._hide_miss()
        self._current_term = term
        self.lbl_loading.config(text=DOT_FRAMES[0])
        self.lbl_loading.pack(fill="x", pady=(2, 0), anchor="w")
        self.lbl_source.pack_forget()
        self._position(x, y)
        self.top.deiconify()
        self.top.lift()
        self._start_dots()
        return gen

    def show_entries(
        self,
        gen: int,
        entries: list[Entry],
        x: Optional[int] = None,
        y: Optional[int] = None,
        raw_query: str = "",
        cleanup: str = "",
    ) -> None:
        if gen != self._gen:
            return
        self._stop_dots()
        self._cancel_auto_close()
        self.lbl_loading.pack_forget()
        self._hide_miss()
        self._clear_entries()
        self._destroy_sub_windows()  # new top-level lookup wipes any drill-down stack

        if not entries:
            return

        # If selection was cleaned up, show a note at the top
        if cleanup == "split" and raw_query and len(entries) >= 2:
            note = tk.Label(
                self.entries_frame,
                text=f"选区里识别到 {len(entries)} 个词：",
                bg=self.bg,
                fg=self.text_meta,
                font=self.font_cat,
                anchor="w",
            )
            note.pack(fill="x", pady=(0, 4), anchor="w")
        elif cleanup == "stripped" and raw_query:
            note = tk.Label(
                self.entries_frame,
                text=f"选区清洗为「{entries[0].term}」",
                bg=self.bg,
                fg=self.text_meta,
                font=self.font_cat,
                anchor="w",
            )
            note.pack(fill="x", pady=(0, 4), anchor="w")

        for i, entry in enumerate(entries):
            block = self._render_entry_block(self.entries_frame, entry, compact=(len(entries) > 1))
            block.pack(fill="x", pady=(0, 0) if i == 0 else (6, 0), anchor="w")
            if i < len(entries) - 1:
                sep = tk.Frame(self.entries_frame, bg="#eaeaea", height=1)
                sep.pack(fill="x", pady=(6, 0))

        # Track primary card's term for stacked exclude filtering
        self._current_term = entries[0].term if entries else ""

        # Chip row: drill into terms referenced inside the meaning text
        self._render_chip_row(self.entries_frame, entries, depth=0)

        # Source footer: aggregate sources across entries
        sources = {e.source for e in entries}
        src_label = " · ".join(SOURCE_LABEL.get(s, s) for s in sources if s and SOURCE_LABEL.get(s))
        if src_label:
            self.lbl_source.config(
                text=src_label,
                fg=self.text_translation_meta if "translation" in sources else self.text_meta,
            )
            self.lbl_source.pack(fill="x", pady=(8, 0))
        else:
            self.lbl_source.pack_forget()

        if x is not None and y is not None:
            self._position(x, y)
        else:
            self._reposition_if_needed()
        self.top.deiconify()
        self.top.lift()

    def show_miss(self, gen: int, term: str, x: Optional[int] = None, y: Optional[int] = None) -> None:
        if gen != self._gen:
            return
        self._stop_dots()
        self._cancel_auto_close()
        self.lbl_loading.pack_forget()
        self._clear_entries()
        self._current_term = term

        # Header: term + 未收录 badge
        head = tk.Frame(self.entries_frame, bg=self.bg)
        head.pack(fill="x", anchor="w")
        tk.Label(head, text=self._truncate(term, 24), bg=self.bg, fg=self.text_dark,
                 font=self.font_title).pack(side="left")
        tk.Label(head, text="未收录", bg="#fef0f0", fg="#b91c1c",
                 font=self.font_cat, padx=6, pady=1).pack(side="left", padx=(8, 0))

        # Miss frame: explanation + "录入" hyperlink
        self.miss_frame.pack(fill="x", anchor="w", pady=(6, 0))
        for w in self.miss_frame.winfo_children():
            w.destroy()
        tk.Label(self.miss_frame, text="词库和通用翻译都没找到这个词。",
                 bg=self.bg, fg=self.text_meta, font=self.font_body, anchor="w").pack(fill="x", anchor="w")

        btn_row = tk.Frame(self.miss_frame, bg=self.bg)
        btn_row.pack(fill="x", anchor="w", pady=(4, 0))
        link = tk.Label(btn_row, text="我录入这个词", bg=self.bg, fg=self.cat_fg,
                        font=self.font_btn, cursor="hand2")
        link.pack(side="left")
        link.bind("<Button-1>", lambda _e: self._show_input_form(gen, term))

        self.lbl_source.pack_forget()

        if x is not None and y is not None:
            self._position(x, y)
        else:
            self._reposition_if_needed()
        self.top.deiconify()
        self.top.lift()

    def show_error(self, gen: int, msg: str) -> None:
        if gen != self._gen:
            return
        self._stop_dots()
        self._clear_entries()
        self._hide_miss()
        self.lbl_loading.pack_forget()
        err = tk.Label(self.entries_frame, text="出错了", bg=self.bg, fg=self.text_dark,
                       font=self.font_title)
        err.pack(anchor="w")
        body = tk.Label(self.entries_frame, text=msg, bg=self.bg, fg="#b91c1c",
                        font=self.font_body, wraplength=self.body_wraplength, justify="left", anchor="w")
        body.pack(fill="x", pady=(4, 0), anchor="w")
        self.lbl_source.pack_forget()
        self._reposition_if_needed()
        self._schedule_auto_close(self.error_close_ms)

    def on_user_save_done(self, gen: int, ok: bool, info: str) -> None:
        if gen != self._gen:
            return
        if not ok:
            self.show_error(gen, "录入失败：" + info)
            return
        # Re-trigger a lookup-style display by manufacturing an Entry from the form
        if self.input_frame is not None and self._input_visible:
            # Read what user typed
            meaning_widget = getattr(self, "_input_meaning_widget", None)
            example_widget = getattr(self, "_input_example_widget", None)
            meaning = meaning_widget.get("1.0", "end").strip() if meaning_widget else ""
            example = example_widget.get().strip() if example_widget else ""
            entry = Entry(
                term=self._current_term,
                category="user",
                literal="",
                meaning=meaning,
                example=example,
                source="user",
            )
            self.show_entries(gen, [entry])
        else:
            self.hide()

    def hide(self) -> None:
        self._stop_dots()
        self._cancel_auto_close()
        self._input_visible = False
        self._destroy_sub_windows()
        self.top.withdraw()

    def is_visible(self) -> bool:
        try:
            return self.top.state() == "normal"
        except tk.TclError:
            return False

    def contains_point(self, x: int, y: int) -> bool:
        """True if (x, y) is inside the primary card OR any stacked sub-card."""
        if not self.is_visible():
            return False
        try:
            for win in (self.top, *(w for w, _ in self.sub_windows)):
                x0 = win.winfo_rootx()
                y0 = win.winfo_rooty()
                x1 = x0 + win.winfo_width()
                y1 = y0 + win.winfo_height()
                if x0 <= x <= x1 and y0 <= y <= y1:
                    return True
            return False
        except tk.TclError:
            return False

    # ---------- stacked drill-down cards ----------

    def stack_depth(self) -> int:
        """0 = only primary visible; N = primary + N stacked sub-cards."""
        return len(self.sub_windows)

    def stacked_terms(self) -> set[str]:
        """All terms currently shown in the stack (primary + subs), for exclude filtering."""
        terms = {self._current_term} if self._current_term else set()
        terms.update(t for _, t in self.sub_windows)
        return terms

    def append_stacked_card(
        self,
        term: str,
        entries: list[Entry],
        missing: bool = False,
    ) -> None:
        """Add a new card below the bottom-most visible card.
        - `entries` non-empty: render entries + chip row (unless at max depth).
        - `entries` empty + missing=True: render a small "未收录" placeholder card.
        """
        if not self.is_visible():
            return
        new_depth = len(self.sub_windows) + 1
        if new_depth > MAX_STACK_DEPTH - 1:
            # already at max; the chip row should've been suppressed but guard anyway
            return

        sub = tk.Toplevel(self.root)
        sub.withdraw()
        sub.overrideredirect(True)
        sub.attributes("-topmost", True)
        try:
            sub.attributes("-toolwindow", True)
        except tk.TclError:
            pass

        outer = tk.Frame(sub, bg=self.border)
        outer.pack(fill="both", expand=True)
        inner = tk.Frame(outer, bg=self.bg, padx=10, pady=8)
        inner.pack(fill="both", expand=True, padx=1, pady=1)

        # Depth badge in header so user knows where they are in the drill chain
        depth_head = tk.Frame(inner, bg=self.bg)
        depth_head.pack(fill="x", anchor="w")
        tk.Label(
            depth_head,
            text=f"↳ 第 {new_depth + 1} 层",
            bg=self.bg,
            fg=self.text_meta,
            font=self.font_cat,
            anchor="w",
        ).pack(side="left")
        close_lbl = tk.Label(
            depth_head,
            text="× 关闭这层",
            bg=self.bg,
            fg=self.text_meta,
            font=self.font_btn,
            cursor="hand2",
        )
        close_lbl.pack(side="right")
        close_lbl.bind("<Button-1>", lambda _e, w=sub: self._close_sub_window(w))

        body = tk.Frame(inner, bg=self.bg)
        body.pack(fill="x", anchor="w", pady=(4, 0))

        if missing or not entries:
            # Miss placeholder card
            tk.Label(
                body,
                text=self._truncate(term, 24),
                bg=self.bg,
                fg=self.text_dark,
                font=self.font_title,
                anchor="w",
            ).pack(anchor="w")
            tk.Label(
                body,
                text="未收录这个词。",
                bg=self.bg,
                fg=self.text_meta,
                font=self.font_body,
                anchor="w",
            ).pack(anchor="w", pady=(2, 0))
        else:
            for i, e in enumerate(entries):
                block = self._render_entry_block(body, e, compact=(len(entries) > 1))
                block.pack(fill="x", pady=(0, 0) if i == 0 else (6, 0), anchor="w")
                if i < len(entries) - 1:
                    sep = tk.Frame(body, bg="#eaeaea", height=1)
                    sep.pack(fill="x", pady=(6, 0))
            # Chip row — suppressed at the last allowed depth (advise AI instead)
            self._render_chip_row(body, entries, depth=new_depth)

        # Position: directly below the bottom-most window, same x
        last_win = self.sub_windows[-1][0] if self.sub_windows else self.top
        try:
            last_win.update_idletasks()
            sub.update_idletasks()
        except tk.TclError:
            pass
        last_x = last_win.winfo_rootx()
        last_y = last_win.winfo_rooty()
        last_h = last_win.winfo_height()
        new_x = last_x
        new_y = last_y + last_h + 6

        # Clamp to screen
        sub_w = max(sub.winfo_reqwidth(), 280)
        sub_h = max(sub.winfo_reqheight(), 60)
        left, top_e, right, bottom = winhelp.get_monitor_work_rect(
            new_x + sub_w // 2, new_y + sub_h // 2
        )
        if new_y + sub_h > bottom - 4:
            # No room below; place above the chain (above the primary)
            new_y = max(top_e + 4, self.top.winfo_rooty() - sub_h - 6)
        if new_x + sub_w > right - 4:
            new_x = right - 4 - sub_w
        if new_x < left + 4:
            new_x = left + 4

        sub.geometry(f"+{new_x}+{new_y}")
        sub.deiconify()
        sub.lift()
        self.sub_windows.append((sub, term))

    def _close_sub_window(self, w: tk.Toplevel) -> None:
        """Close this sub-card AND any deeper sub-cards stacked below it."""
        idx = None
        for i, (win, _t) in enumerate(self.sub_windows):
            if win is w:
                idx = i
                break
        if idx is None:
            return
        # Destroy from this point down
        for win, _t in self.sub_windows[idx:]:
            try:
                win.destroy()
            except tk.TclError:
                pass
        self.sub_windows = self.sub_windows[:idx]

    def _destroy_sub_windows(self) -> None:
        for win, _t in self.sub_windows:
            try:
                win.destroy()
            except tk.TclError:
                pass
        self.sub_windows.clear()

    # ---------- entry rendering ----------

    def _render_entry_block(self, parent: tk.Frame, entry: Entry, compact: bool = False) -> tk.Frame:
        block = tk.Frame(parent, bg=self.bg)
        head = tk.Frame(block, bg=self.bg)
        head.pack(fill="x", anchor="w")
        tk.Label(head, text=self._truncate(entry.term, 24), bg=self.bg, fg=self.text_dark,
                 font=self.font_title).pack(side="left")
        cat_label = CATEGORY_LABEL.get(entry.category, entry.category)
        if entry.source == "translation":
            cat_bg, cat_fg = self.translation_cat_bg, self.translation_cat_fg
        elif entry.source == "user":
            cat_bg, cat_fg = self.user_cat_bg, self.user_cat_fg
        else:
            cat_bg, cat_fg = self.cat_bg, self.cat_fg
        tk.Label(head, text=cat_label, bg=cat_bg, fg=cat_fg,
                 font=self.font_cat, padx=6, pady=1).pack(side="left", padx=(8, 0))

        def row(label_text: str, value: str, muted: bool = False) -> None:
            if not value:
                return
            row_frame = tk.Frame(block, bg=self.bg)
            row_frame.pack(fill="x", pady=(2, 0), anchor="w")
            tk.Label(row_frame, text=label_text, bg=self.bg, fg=self.text_meta,
                     font=self.font_label, width=4, anchor="w").pack(side="left", anchor="n", pady=(2, 0))
            tk.Label(row_frame, text=value, bg=self.bg,
                     fg=self.text_meta if muted else self.text_dark,
                     font=self.font_body, wraplength=self.body_wraplength,
                     justify="left", anchor="w").pack(
                side="left", fill="x", expand=True
            )

        if entry.literal:
            row("字面", entry.literal)
        if entry.meaning:
            row("含义", entry.meaning)
        if entry.example and not compact:
            row("例句", entry.example, muted=True)

        return block

    def _render_chip_row(self, parent: tk.Frame, entries: list[Entry], depth: int) -> None:
        """Render the "相关" chip row at the bottom of a card.

        - At final allowed depth, suppress chips and show "更深就建议问 AI" hint.
        - For entries with translation/fuzzy/llm source, skip chips (too noisy).
        - Aggregates referenced terms across all entries' meaning text.
        """
        if self.find_refs_fn is None:
            return

        # Skip chip row for non-local entries (translation/fuzzy/llm) — meanings
        # there are auto-generated or generic, refs are usually noise.
        meaningful = [e for e in entries if e.source in ("local", "user") and e.meaning]
        if not meaningful:
            return

        # At the deepest allowed sub-card depth, show "去问 AI 吧" hint instead of chips
        if depth >= MAX_STACK_DEPTH - 1:
            row = tk.Frame(parent, bg=self.bg)
            row.pack(fill="x", pady=(8, 0), anchor="w")
            tk.Label(
                row,
                text="💡 概念套娃太深了，建议丢给 ChatGPT/Claude 整体讲一下",
                bg=self.bg,
                fg=self.text_meta,
                font=self.font_cat,
                anchor="w",
            ).pack(anchor="w")
            return

        exclude = self.stacked_terms()
        for e in entries:
            if e.term:
                exclude.add(e.term)

        # Aggregate refs from all entries' meanings, preserving order
        all_refs: list[str] = []
        seen = set()
        for e in meaningful:
            try:
                refs = self.find_refs_fn(e.meaning, exclude)
            except Exception:
                refs = []
            for r in refs:
                if r in seen:
                    continue
                seen.add(r)
                all_refs.append(r)
                if len(all_refs) >= 5:
                    break
            if len(all_refs) >= 5:
                break

        if not all_refs:
            return

        # Label + chips on one line
        row = tk.Frame(parent, bg=self.bg)
        row.pack(fill="x", pady=(8, 0), anchor="w")
        tk.Label(
            row,
            text="相关",
            bg=self.bg,
            fg=self.text_meta,
            font=self.font_label,
            width=4,
            anchor="w",
        ).pack(side="left", anchor="n", pady=(2, 0))

        # Chip container that allows wrapping if needed (use a sub-frame and pack chips with side='left')
        chips = tk.Frame(row, bg=self.bg)
        chips.pack(side="left", fill="x", expand=True, anchor="w")
        for term in all_refs:
            chip = tk.Label(
                chips,
                text=term,
                bg="#eef4ff",
                fg=self.cat_fg,
                font=self.font_cat,
                padx=7,
                pady=2,
                cursor="hand2",
            )
            chip.pack(side="left", padx=(0, 4), pady=2)
            chip.bind(
                "<Button-1>",
                lambda _e, t=term: self.on_chip_click(t) if self.on_chip_click else None,
            )
            # Hover effect: subtle bg change
            chip.bind("<Enter>", lambda _e, c=chip: c.config(bg="#dde7ff"))
            chip.bind("<Leave>", lambda _e, c=chip: c.config(bg="#eef4ff"))

    def _clear_entries(self) -> None:
        for w in self.entries_frame.winfo_children():
            w.destroy()
        self.lbl_source.pack_forget()

    def _hide_miss(self) -> None:
        self.miss_frame.pack_forget()
        for w in self.miss_frame.winfo_children():
            w.destroy()
        if self.input_frame is not None:
            self.input_frame.pack_forget()
            self.input_frame.destroy()
            self.input_frame = None
        self._input_visible = False

    def _show_input_form(self, gen: int, term: str) -> None:
        if gen != self._gen:
            return
        # Hide the "录入" hyperlink, show input fields
        if self.input_frame is not None:
            self.input_frame.destroy()
        self.input_frame = tk.Frame(self.inner, bg=self.bg)
        self.input_frame.pack(fill="x", anchor="w", pady=(8, 0))
        self._input_visible = True

        tk.Label(self.input_frame, text=f"录入「{term}」", bg=self.bg, fg=self.text_dark,
                 font=self.font_label).pack(anchor="w")

        tk.Label(self.input_frame, text="含义：", bg=self.bg, fg=self.text_meta,
                 font=self.font_label).pack(anchor="w", pady=(4, 0))
        meaning_widget = tk.Text(self.input_frame, height=2, width=44,
                                  font=self.font_body, wrap="word",
                                  bd=1, relief="solid", highlightthickness=0)
        meaning_widget.pack(fill="x", pady=(2, 0))
        meaning_widget.focus_set()
        self._input_meaning_widget = meaning_widget

        tk.Label(self.input_frame, text="例句（可选）：", bg=self.bg, fg=self.text_meta,
                 font=self.font_label).pack(anchor="w", pady=(6, 0))
        example_widget = tk.Entry(self.input_frame, font=self.font_body,
                                   bd=1, relief="solid", highlightthickness=0)
        example_widget.pack(fill="x", pady=(2, 0))
        self._input_example_widget = example_widget

        btn_row = tk.Frame(self.input_frame, bg=self.bg)
        btn_row.pack(fill="x", anchor="w", pady=(6, 0))
        save_btn = tk.Button(
            btn_row, text="保存", font=self.font_label,
            bg=self.cat_fg, fg="white", bd=0, padx=10, pady=2, cursor="hand2",
            activebackground="#1948c5", activeforeground="white",
            command=lambda: self._submit_input(gen, term),
        )
        save_btn.pack(side="left")
        cancel_btn = tk.Label(btn_row, text="取消", bg=self.bg, fg=self.text_meta,
                              font=self.font_btn, cursor="hand2")
        cancel_btn.pack(side="left", padx=(10, 0))
        cancel_btn.bind("<Button-1>", lambda _e: self.hide())

        # Ctrl+Enter to save
        meaning_widget.bind("<Control-Return>", lambda _e: self._submit_input(gen, term))
        example_widget.bind("<Return>", lambda _e: self._submit_input(gen, term))

        self._reposition_if_needed()

    def _submit_input(self, gen: int, term: str) -> str:
        if gen != self._gen:
            return "break"
        meaning = self._input_meaning_widget.get("1.0", "end").strip() if hasattr(self, "_input_meaning_widget") else ""
        example = self._input_example_widget.get().strip() if hasattr(self, "_input_example_widget") else ""
        if not meaning:
            # No-op if empty
            return "break"
        # Disable widgets to indicate saving
        try:
            self._input_meaning_widget.config(state="disabled")
            self._input_example_widget.config(state="disabled")
        except tk.TclError:
            pass
        if self.on_user_save:
            self.on_user_save(gen, term, meaning, example)
        return "break"

    # ---------- dots animation ----------

    def _start_dots(self) -> None:
        self._loading = True
        self._dot_idx = 0
        self._tick_dots()

    def _stop_dots(self) -> None:
        self._loading = False
        if self._dot_after_id is not None:
            try:
                self.top.after_cancel(self._dot_after_id)
            except tk.TclError:
                pass
            self._dot_after_id = None

    def _tick_dots(self) -> None:
        if not self._loading:
            return
        self.lbl_loading.config(text=DOT_FRAMES[self._dot_idx % len(DOT_FRAMES)])
        self._dot_idx += 1
        self._dot_after_id = self.top.after(self.dot_interval_ms, self._tick_dots)

    def _schedule_auto_close(self, ms: int) -> None:
        self._cancel_auto_close()
        self._auto_close_after_id = self.top.after(ms, self.hide)

    def _cancel_auto_close(self) -> None:
        if self._auto_close_after_id is not None:
            try:
                self.top.after_cancel(self._auto_close_after_id)
            except tk.TclError:
                pass
            self._auto_close_after_id = None

    # ---------- positioning ----------

    def _position(self, x: int, y: int) -> None:
        self.top.update_idletasks()
        w = max(self.top.winfo_reqwidth(), 280)
        h = max(self.top.winfo_reqheight(), 60)
        margin = 14
        left, top, right, bottom = winhelp.get_monitor_work_rect(x, y)
        px = x + 14
        py = y + 18
        if px + w > right - margin:
            px = max(left + margin, right - margin - w)
        if py + h > bottom - margin:
            py = max(top + margin, y - h - 14)
        self.top.geometry(f"+{px}+{py}")

    def _reposition_if_needed(self) -> None:
        try:
            self.top.update_idletasks()
        except tk.TclError:
            return
        x = self.top.winfo_rootx()
        y = self.top.winfo_rooty()
        w = self.top.winfo_width()
        h = self.top.winfo_height()
        left, top, right, bottom = winhelp.get_monitor_work_rect(x + w // 2, y + h // 2)
        new_x, new_y = x, y
        if x + w > right - 4:
            new_x = right - 4 - w
        if y + h > bottom - 4:
            new_y = bottom - 4 - h
        if new_x < left + 4:
            new_x = left + 4
        if new_y < top + 4:
            new_y = top + 4
        if (new_x, new_y) != (x, y):
            self.top.geometry(f"+{new_x}+{new_y}")

    # ---------- helpers ----------

    @staticmethod
    def _truncate(s: str, n: int) -> str:
        return s if len(s) <= n else s[:n] + "…"
