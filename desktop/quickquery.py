"""Borderless quick-query input box.

Universal fallback when the normal Alt+drag flow can't grab text — terminals
where Alt+drag is reserved for block selection, PDFs with selection disabled,
images, OCR-less screenshots, or anywhere else the clipboard dance fails.

The box pops up next to the mouse cursor; user types or pastes a term and
hits Enter. Submission is reported via callback, so the caller can route the
text through the normal lookup pipeline (`smart_lookup` → tooltip). No state
is stored in this module — show() spawns a fresh window each time and tears
itself down on submit / Esc / focus-out.

Activation paths:
- Alt+drag in a terminal → grab fails → app falls through to this dialog
- Alt+Q hotkey anywhere → directly opens this dialog
"""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from typing import Callable

from . import win as winhelp


def show(root: tk.Tk, on_submit: Callable[[str], None], x: int | None = None, y: int | None = None) -> None:
    """Pop up a single-line input near (x, y); call `on_submit(text)` when
    user presses Enter with non-empty content. Closes on Esc / focus-out.

    `root` must be the live tk root (so the Toplevel has a parent) — pass
    `app.root`. Window is `withdraw()`'d during construction so users don't
    see a flash, then deiconified after layout.
    """
    if x is None or y is None:
        x, y = winhelp.get_cursor_pos()
        x += 12  # offset so the dialog doesn't sit under the cursor
        y += 12

    win = tk.Toplevel(root)
    win.withdraw()
    win.overrideredirect(True)        # no titlebar, no decoration
    win.attributes("-topmost", True)
    win.configure(bg="#1f2937")       # navy frame (matches icon ink color)

    # Inner frame draws a 1px border by inset
    frame = tk.Frame(win, bg="#ffffff", bd=0)
    frame.pack(padx=1, pady=1, ipadx=10, ipady=8)

    big = tkfont.Font(family="Microsoft YaHei UI", size=11)
    small = tkfont.Font(family="Microsoft YaHei UI", size=8)

    hint = tk.Label(
        frame,
        text="敲词查解释  ·  Enter 确认  ·  Esc 关闭",
        font=small,
        fg="#6b7280",
        bg="#ffffff",
        anchor="w",
    )
    hint.pack(fill="x", padx=2, pady=(0, 4))

    var = tk.StringVar()
    entry = tk.Entry(
        frame,
        textvariable=var,
        font=big,
        bg="#ffffff",
        fg="#1f2937",
        bd=1,
        relief="solid",
        width=26,
        insertbackground="#1f2937",
        highlightthickness=1,
        highlightbackground="#d1d5db",
        highlightcolor="#3b82f6",
    )
    entry.pack(ipady=4)

    submitted = {"v": False}

    def close():
        try:
            win.destroy()
        except Exception:
            pass

    def commit(_event=None):
        if submitted["v"]:
            return
        text = var.get().strip()
        if not text:
            close()
            return
        submitted["v"] = True
        close()
        # Route through caller's lookup pipeline. They schedule onto the tk
        # main thread themselves if needed.
        try:
            on_submit(text)
        except Exception as e:
            import sys
            print(f"[codelang] quick-query submit error: {e}", file=sys.stderr)

    def on_escape(_event=None):
        close()

    def on_focus_out(_event=None):
        # Tiny delay so a transient focus-flicker during deiconify doesn't
        # immediately destroy the window before the user can interact.
        win.after(100, close)

    entry.bind("<Return>", commit)
    entry.bind("<Escape>", on_escape)
    entry.bind("<FocusOut>", on_focus_out)

    # Position with edge clamping so the box stays on-screen even when the
    # user invoked it from the bottom-right corner.
    win.update_idletasks()
    w = win.winfo_reqwidth()
    h = win.winfo_reqheight()
    left, top, right, bottom = winhelp.get_monitor_work_rect(x, y)
    x = min(max(x, left + 4), right - w - 4)
    y = min(max(y, top + 4), bottom - h - 4)
    win.geometry(f"+{x}+{y}")
    win.deiconify()
    win.lift()
    entry.focus_force()
