"""Styled info / warning dialogs in the same visual language as welcome.py
and deps_error.py: borderless Toplevel, 1px outer BORDER, white bg, flat blue
primary button, Esc/Enter to dismiss.

Replaces tkinter.messagebox.showinfo / showwarning for codelang popups so all
in-app notifications share one design.

Stdlib-only (uses tk.PhotoImage for the optional icon — Tk 8.6+ handles PNG
natively without PIL).
"""
from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import font as tkfont

from .paths import resource_root

IS_MAC = sys.platform == "darwin"

ICON_PATH = resource_root() / "assets" / "logo" / "icon-128.png"

# Design tokens — kept in sync with desktop/welcome.py + deps_error.py.
# Neutral, Apple-system-like palette.
BG          = "#ffffff"
BORDER      = "#d2d2d7"
BLUE        = "#007aff"   # macOS system accent
BLUE_HOVER  = "#0066d6"
TEXT_DARK   = "#1d1d1f"
TEXT_META   = "#6e6e73"
TEXT_HINT   = "#9aa0a6"
ALERT_FG    = "#d70015"


def _pick_family() -> str:
    families = set(tkfont.families())
    if IS_MAC:
        for c in ("PingFang SC", "Helvetica Neue", "Lucida Grande"):
            if c in families:
                return c
        return "TkDefaultFont"
    if "Microsoft YaHei UI" in families:
        return "Microsoft YaHei UI"
    if "Segoe UI" in families:
        return "Segoe UI"
    return "TkDefaultFont"


def _show(
    parent: tk.Misc | None,
    title: str,
    body: str,
    *,
    title_fg: str = TEXT_DARK,
    btn_text: str = "知道了",
    icon_size: int = 40,
) -> None:
    """Build and show the dialog modally. `parent` may be a Tk/Toplevel or
    None — when None we spawn a hidden root (matches messagebox semantics)."""
    owns_root = parent is None
    if owns_root:
        parent = tk.Tk()
        parent.withdraw()

    win = tk.Toplevel(parent)
    win.withdraw()
    win.overrideredirect(True)
    win.attributes("-topmost", True)
    try:
        win.attributes("-toolwindow", True)
    except tk.TclError:
        pass

    family = _pick_family()
    f_title = tkfont.Font(family=family, size=12, weight="bold")
    f_body = tkfont.Font(family=family, size=9)
    f_btn = tkfont.Font(family=family, size=9, weight="bold")

    border = tk.Frame(win, bg=BORDER)
    border.pack(fill="both", expand=True)
    shell = tk.Frame(border, bg=BG)
    shell.pack(fill="both", expand=True, padx=1, pady=1)

    inner = tk.Frame(shell, bg=BG, padx=22, pady=18)
    inner.pack(fill="both", expand=True)

    # Header: small UFO icon + title
    header = tk.Frame(inner, bg=BG)
    header.pack(fill="x", anchor="w")

    if ICON_PATH.exists() and icon_size > 0:
        try:
            photo = tk.PhotoImage(file=str(ICON_PATH))
            # 128px source → subsample down to roughly icon_size
            sub = max(1, round(128 / icon_size))
            photo = photo.subsample(sub, sub)
            icon_lbl = tk.Label(header, image=photo, bg=BG, bd=0)
            icon_lbl.image = photo  # GC anchor
            icon_lbl.pack(side="left", padx=(0, 12), anchor="n")
        except tk.TclError:
            pass

    text_col = tk.Frame(header, bg=BG)
    text_col.pack(side="left", fill="x", expand=True, anchor="w")
    tk.Label(
        text_col, text=title,
        bg=BG, fg=title_fg, font=f_title, anchor="w",
    ).pack(anchor="w")
    tk.Label(
        text_col, text=body,
        bg=BG, fg=TEXT_META, font=f_body, anchor="w",
        justify="left", wraplength=340,
    ).pack(anchor="w", pady=(4, 0))

    # Button row
    btn_row = tk.Frame(inner, bg=BG)
    btn_row.pack(fill="x", pady=(16, 0))

    def _dismiss(_e=None):
        try:
            win.destroy()
        except tk.TclError:
            pass
        if owns_root:
            try:
                parent.destroy()
            except tk.TclError:
                pass

    # Faux button: tk.Button ignores `bg` under macOS's aqua theme and renders
    # as a default gray button, so we build a flat filled button from a
    # Frame+Label instead — renders identically on both platforms.
    btn = tk.Frame(btn_row, bg=BLUE, cursor="hand2")
    btn_lbl = tk.Label(btn, text=btn_text, bg=BLUE, fg="white", font=f_btn, padx=18, pady=6)
    btn_lbl.pack()
    for w in (btn, btn_lbl):
        w.bind("<Button-1>", lambda _e: (btn.config(bg=BLUE_HOVER), btn_lbl.config(bg=BLUE_HOVER)))
        w.bind("<ButtonRelease-1>", lambda e: _dismiss(e))
    btn.pack(side="right")

    win.bind("<Escape>", _dismiss)
    win.bind("<Return>", _dismiss)
    win.protocol("WM_DELETE_WINDOW", _dismiss)

    # Center on screen
    win.update_idletasks()
    w = max(win.winfo_reqwidth(), 420)
    h = win.winfo_reqheight()
    sw = win.winfo_screenwidth()
    sh = win.winfo_screenheight()
    win.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2 - 40}")
    win.deiconify()
    win.lift()
    win.focus_force()

    if owns_root:
        parent.mainloop()


def show_info(parent: tk.Misc | None, title: str, body: str) -> None:
    """Styled replacement for tkinter.messagebox.showinfo."""
    _show(parent, title, body, title_fg=TEXT_DARK, btn_text="知道了")


def show_warning(parent: tk.Misc | None, title: str, body: str) -> None:
    """Styled replacement for tkinter.messagebox.showwarning. Title rendered
    in the alert red used elsewhere in codelang."""
    _show(parent, title, body, title_fg=ALERT_FG, btn_text="知道了")


if __name__ == "__main__":
    show_info(None, "词库更新", "已是最新（2453 条）")
