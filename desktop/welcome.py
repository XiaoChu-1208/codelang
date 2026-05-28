"""First-run welcome window.

A deliberately plain, Mac-native-feeling onboarding card: a single centered
column — app icon, title, one-line subtitle, a thin divider, two concise
setup hints, and one primary button. No illustration, no colored feature
cards, no stats chip; the visual language matches desktop/dialog.py and
desktop/deps_error.py so every codelang popup looks like one family.

Pillow is required (welcome only runs after `deps_error.check_required()`
passes, so PIL/ImageTk are guaranteed importable here).

Persistence: `config["welcome_shown"] = True` after dismissal so the card
never appears again until the user manually flips it back.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont

from PIL import Image, ImageTk

from . import config
from . import platform_compat as winhelp
from .paths import resource_root


ICON_PATH = resource_root() / "assets" / "logo" / "icon-512.png"
ICON_SIDE = 60

# Design tokens — kept in sync with desktop/dialog.py + deps_error.py.
# Neutral, Apple-system-like palette instead of the old brand blue.
BG        = "#ffffff"
BORDER    = "#d2d2d7"
BLUE      = "#007aff"   # macOS system accent
BLUE_DOWN = "#0066d6"
TEXT_DARK = "#1d1d1f"
TEXT_META = "#6e6e73"
SEP       = "#e5e5ea"


def _pick_family() -> str:
    families = set(tkfont.families())
    if winhelp.IS_MAC:
        for candidate in ("PingFang SC", "Helvetica Neue", "Lucida Grande"):
            if candidate in families:
                return candidate
        return "TkDefaultFont"
    if "Microsoft YaHei UI" in families:
        return "Microsoft YaHei UI"
    if "Segoe UI" in families:
        return "Segoe UI"
    return "TkDefaultFont"


def _load_icon(parent: tk.Widget) -> tk.Label | None:
    """A plain centered app icon, downscaled with LANCZOS. Returns None if the
    asset is missing so the caller can simply skip it."""
    if not ICON_PATH.exists():
        return None
    try:
        img = Image.open(ICON_PATH).convert("RGBA")
        img = img.resize((ICON_SIDE, ICON_SIDE), Image.LANCZOS)
        photo = ImageTk.PhotoImage(img)
    except Exception:
        return None
    lbl = tk.Label(parent, image=photo, bg=BG, bd=0)
    lbl.image = photo  # anchor against GC
    return lbl


def _primary_button(parent: tk.Widget, text: str, family: str, command) -> tk.Frame:
    """A filled accent-blue button built from a Frame+Label. tk.Button ignores
    `bg` under macOS's aqua theme, so we fake it — this renders identically on
    both platforms and reads as a flat Mac-style button."""
    f = tkfont.Font(family=family, size=11, weight="bold")
    btn = tk.Frame(parent, bg=BLUE, cursor="hand2")
    lbl = tk.Label(btn, text=text, bg=BLUE, fg="white", font=f, padx=22, pady=7)
    lbl.pack()

    def _down(_e=None):
        btn.config(bg=BLUE_DOWN)
        lbl.config(bg=BLUE_DOWN)

    def _up(_e=None):
        btn.config(bg=BLUE)
        lbl.config(bg=BLUE)

    for w in (btn, lbl):
        w.bind("<Button-1>", _down)
        w.bind("<ButtonRelease-1>", lambda e: (_up(), command(e)))
    return btn


def show_welcome(root: tk.Tk) -> None:
    win = tk.Toplevel(root)
    win.withdraw()
    win.overrideredirect(True)
    win.attributes("-topmost", True)
    try:
        win.attributes("-toolwindow", True)
    except tk.TclError:
        pass

    family = _pick_family()
    f_title = tkfont.Font(family=family, size=18, weight="bold")
    f_sub   = tkfont.Font(family=family, size=10)
    f_hint  = tkfont.Font(family=family, size=9)

    border = tk.Frame(win, bg=BORDER)
    border.pack(fill="both", expand=True)
    shell = tk.Frame(border, bg=BG)
    shell.pack(fill="both", expand=True, padx=1, pady=1)

    inner = tk.Frame(shell, bg=BG, padx=34, pady=26)
    inner.pack(fill="both", expand=True)

    icon = _load_icon(inner)
    if icon is not None:
        icon.pack(pady=(0, 12))

    tk.Label(
        inner, text="codelang", bg=BG, fg=TEXT_DARK, font=f_title,
    ).pack()

    trigger_key = "Option" if winhelp.IS_MAC else "Alt"
    tk.Label(
        inner, text=f"按住 {trigger_key} 划词，鼠标旁立刻弹出大白话解释",
        bg=BG, fg=TEXT_META, font=f_sub,
    ).pack(pady=(5, 0))

    tk.Frame(inner, bg=SEP, height=1).pack(fill="x", pady=18)

    # Two concise setup hints, platform-specific wording. Plain text rows with
    # a subtle bullet — no cards, no colored icon chips.
    if winhelp.IS_MAC:
        hints = [
            "菜单栏的小飞碟图标可查看日志、重新加载词典、退出",
            "首次使用请到 系统设置 → 隐私与安全性 → 辅助功能 勾选 codelang",
        ]
    else:
        hints = [
            "右下角托盘的小飞碟图标可查看日志、重新加载词典、退出",
            "想开机自启：Win+R 输入 shell:startup，把快捷方式拖进去",
        ]
    for h in hints:
        row = tk.Frame(inner, bg=BG)
        row.pack(fill="x", anchor="w", pady=(0, 6))
        tk.Label(row, text="•", bg=BG, fg=TEXT_META, font=f_hint).pack(
            side="left", anchor="n", padx=(0, 7)
        )
        tk.Label(
            row, text=h, bg=BG, fg=TEXT_META, font=f_hint,
            anchor="w", justify="left", wraplength=300,
        ).pack(side="left", fill="x", expand=True)

    def _dismiss(_e=None):
        try:
            cfg = config.load_config()
            cfg["welcome_shown"] = True
            config.save_config(cfg)
        except Exception:
            pass
        try:
            win.destroy()
        except tk.TclError:
            pass

    _primary_button(inner, "开始使用", family, _dismiss).pack(pady=(16, 0))

    win.bind("<Escape>", _dismiss)
    win.bind("<Return>", _dismiss)

    # ---- center on the monitor that contains the cursor ----
    win.update_idletasks()
    w = win.winfo_reqwidth()
    h = win.winfo_reqheight()
    try:
        cx, cy = winhelp.get_cursor_pos()
        left_m, top_m, right_m, bottom_m = winhelp.get_monitor_work_rect(cx, cy)
        px = left_m + ((right_m - left_m) - w) // 2
        py = top_m + ((bottom_m - top_m) - h) // 2 - 40
    except Exception:
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        px = (sw - w) // 2
        py = (sh - h) // 2 - 40
    win.geometry(f"{w}x{h}+{px}+{py}")
    win.deiconify()
    win.lift()
    try:
        win.attributes("-topmost", True)
    except tk.TclError:
        pass


def should_show() -> bool:
    try:
        cfg = config.load_config()
    except Exception:
        return False
    return not bool(cfg.get("welcome_shown", False))
