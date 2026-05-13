"""Stdlib-only dependency error dialog.

Used when third-party Python deps are missing. This is the failure that
historically caused "shortcut clicked but nothing happened": pythonw has no
console, so the ImportError was invisible. Now we catch it and show a real
window the user can act on.

This module MUST stay stdlib-only — it is the fallback when third-party
imports fail, so it cannot rely on anything beyond tkinter / pathlib / sys.
Tk 8.6+ supports PNG via tk.PhotoImage without PIL, which is what we use
for the icon.

Visual style mirrors desktop/welcome.py (borderless, 1px outer border, blue
accent, flat buttons, text-link secondaries) so all codelang popups share a
language.
"""
from __future__ import annotations

import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import font as tkfont

ICON_PATH_128 = Path(__file__).resolve().parent.parent / "assets" / "logo" / "icon-128.png"
ICON_PATH_64 = Path(__file__).resolve().parent.parent / "assets" / "logo" / "icon-64.png"
ICON_PATH_ICO = Path(__file__).resolve().parent.parent / "assets" / "logo" / "icon.ico"

IS_MAC = sys.platform == "darwin"

# pip command the dialog suggests / runs. Windows uses the py launcher;
# macOS / Linux use python3.
if IS_MAC:
    PIP_CMD = "python3 -m pip install --user -r requirements.txt"
else:
    PIP_CMD = "py -m pip install --user -r requirements.txt"


# Modules to require, per platform. Each entry is (display name, import name).
_REQUIRED_WIN = [
    ("mouse", "mouse"),
    ("pyperclip", "pyperclip"),
    ("pystray", "pystray"),
    ("Pillow", "PIL"),
]
_REQUIRED_MAC = [
    ("pynput", "pynput"),
    ("pyperclip", "pyperclip"),
    ("Pillow", "PIL"),
    ("pyobjc-framework-Quartz", "Quartz"),
    ("pyobjc-framework-Cocoa", "AppKit"),
]


# Design tokens — kept in sync with desktop/welcome.py
BG          = "#ffffff"
BORDER      = "#d9dfe8"
BLUE        = "#2956E6"
BLUE_HOVER  = "#1f43c1"
TEXT_DARK   = "#1a1a1a"
TEXT_META   = "#6b7280"
TEXT_HINT   = "#9aa0a6"
CARD_BG     = "#fbfcfe"
CARD_BORDER = "#e7eaf0"
ALERT_FG    = "#b91c1c"
ALERT_BG    = "#fef2f2"


def _pick_family(families: set[str]) -> tuple[str, str]:
    """Return (text_family, mono_family) based on platform fonts."""
    if IS_MAC:
        text = next((f for f in ("PingFang SC", "Helvetica Neue") if f in families), "TkDefaultFont")
        mono = next((f for f in ("Menlo", "Monaco") if f in families), "TkFixedFont")
    else:
        text = ("Microsoft YaHei UI" if "Microsoft YaHei UI" in families else
                ("Segoe UI" if "Segoe UI" in families else "TkDefaultFont"))
        mono = "Consolas" if "Consolas" in families else "TkFixedFont"
    return text, mono


def show(missing: list[str]) -> None:
    """Block until the user dismisses the dialog. Side effect: copies the pip
    command to clipboard so the user can paste it into a terminal."""
    root = tk.Tk()
    root.withdraw()

    win = tk.Toplevel(root)
    win.withdraw()
    win.overrideredirect(True)
    win.attributes("-topmost", True)
    try:
        win.attributes("-toolwindow", True)
    except tk.TclError:
        pass

    families = set(tkfont.families())
    text_family, mono_family = _pick_family(families)
    f_title  = tkfont.Font(family=text_family, size=14, weight="bold")
    f_body   = tkfont.Font(family=text_family, size=9)
    f_small  = tkfont.Font(family=text_family, size=8)
    f_mono   = tkfont.Font(family=mono_family, size=9)
    f_btn    = tkfont.Font(family=text_family, size=9, weight="bold")
    f_link   = tkfont.Font(family=text_family, size=9)
    f_alert  = tkfont.Font(family=text_family, size=11, weight="bold")

    # 1px outer border so the borderless card stands out on light desktops
    border = tk.Frame(win, bg=BORDER)
    border.pack(fill="both", expand=True)
    shell = tk.Frame(border, bg=BG)
    shell.pack(fill="both", expand=True, padx=1, pady=1)

    inner = tk.Frame(shell, bg=BG, padx=24, pady=20)
    inner.pack(fill="both", expand=True)

    # ---- header row: small icon + title ----
    header = tk.Frame(inner, bg=BG)
    header.pack(fill="x", anchor="w")

    # Tk 8.6+ loads PNG natively; .subsample shrinks 128→48 quickly w/o PIL.
    icon_lbl = None
    if ICON_PATH_128.exists():
        try:
            photo = tk.PhotoImage(file=str(ICON_PATH_128))
            # Shrink 128 → ~42 (subsample 3 → 128/3 ≈ 43)
            photo = photo.subsample(3, 3)
            icon_lbl = tk.Label(header, image=photo, bg=BG, bd=0)
            icon_lbl.image = photo  # anchor against GC
            icon_lbl.pack(side="left", padx=(0, 14))
        except tk.TclError:
            icon_lbl = None

    title_col = tk.Frame(header, bg=BG)
    title_col.pack(side="left", fill="x", expand=True, anchor="w")
    tk.Label(
        title_col, text="codelang 还差几个 Python 包",
        bg=BG, fg=ALERT_FG, font=f_alert, anchor="w",
    ).pack(anchor="w")
    tk.Label(
        title_col, text="装上就能起飞。下面给你两条路。",
        bg=BG, fg=TEXT_META, font=f_body, anchor="w",
    ).pack(anchor="w", pady=(2, 0))

    # ---- missing-packages card ----
    miss_outer = tk.Frame(inner, bg=CARD_BORDER)
    miss_outer.pack(fill="x", pady=(14, 12))
    miss_inner = tk.Frame(miss_outer, bg=ALERT_BG, padx=12, pady=8)
    miss_inner.pack(fill="both", expand=True, padx=1, pady=1)
    tk.Label(
        miss_inner, text="缺少",
        bg=ALERT_BG, fg=TEXT_META, font=f_small, anchor="w",
    ).pack(anchor="w")
    tk.Label(
        miss_inner, text=",  ".join(missing),
        bg=ALERT_BG, fg=ALERT_FG, font=f_body, anchor="w", justify="left",
    ).pack(anchor="w", pady=(2, 0))

    # ---- instruction + command box ----
    hint_text = (
        "在终端里粘贴这条命令，回车："
        if IS_MAC
        else "在 CMD / PowerShell 里粘贴这条命令，回车："
    )
    tk.Label(
        inner, text=hint_text,
        bg=BG, fg=TEXT_META, font=f_body, anchor="w",
    ).pack(anchor="w")

    cmd_outer = tk.Frame(inner, bg=CARD_BORDER)
    cmd_outer.pack(fill="x", pady=(4, 6))
    cmd_box = tk.Entry(
        cmd_outer, font=f_mono, bd=0, relief="flat",
        bg=CARD_BG, readonlybackground=CARD_BG,
        fg=TEXT_DARK, highlightthickness=0,
    )
    cmd_box.insert(0, PIP_CMD)
    cmd_box.config(state="readonly")
    cmd_box.pack(fill="x", padx=1, pady=1, ipady=7, ipadx=10)

    note = tk.Label(
        inner,
        text="命令已复制到剪贴板，去终端 Ctrl+V / Cmd+V 即可。",
        bg=BG, fg=TEXT_HINT, font=f_small, anchor="w",
    )
    note.pack(anchor="w")

    # ---- bottom action row ----
    project_root = Path(__file__).resolve().parent.parent

    def _copy():
        try:
            win.clipboard_clear()
            win.clipboard_append(PIP_CMD)
        except tk.TclError:
            pass
        note.config(text="复制成功 ✓ 去终端粘贴吧。")

    def _auto_install():
        try:
            if IS_MAC:
                note.config(text="正在打开终端跑 pip，装完后重新启动 codelang。")
                shell_cmd = (
                    f'cd "{project_root}" && '
                    "python3 -m pip install --user -r requirements.txt && "
                    'echo "" && echo "装好了！重新启动 codelang 即可。"'
                )
                escaped = shell_cmd.replace('\\', '\\\\').replace('"', '\\"')
                osa = (
                    f'tell application "Terminal" to do script "{escaped}"\n'
                    f'tell application "Terminal" to activate'
                )
                subprocess.Popen(["osascript", "-e", osa])
            else:
                note.config(text="正在打开 CMD 跑 pip，装完后重新双击 codelang。")
                cmd = (
                    f'cd /d "{project_root}" && '
                    "py -m pip install --user -r requirements.txt && "
                    "echo. && echo 装好了！重新双击桌面 codelang 启动即可。"
                )
                subprocess.Popen(["cmd.exe", "/K", cmd])
        except Exception as e:
            note.config(text=f"启动 pip 失败：{e}")

    def _close():
        try:
            win.destroy()
            root.destroy()
        except tk.TclError:
            pass

    btn_row = tk.Frame(inner, bg=BG)
    btn_row.pack(fill="x", pady=(16, 0))

    # Primary blue button (flat, no chrome) — left side
    install = tk.Button(
        btn_row, text="一键安装  →",
        font=f_btn, bg=BLUE, fg="white",
        activebackground=BLUE_HOVER, activeforeground="white",
        bd=0, relief="flat", padx=16, pady=6, cursor="hand2",
        highlightthickness=0,
        command=_auto_install,
    )
    install.pack(side="left")

    # Right-side text links
    close_link = tk.Label(
        btn_row, text="关闭",
        bg=BG, fg=TEXT_HINT, font=f_link, cursor="hand2",
    )
    close_link.pack(side="right")
    close_link.bind("<Button-1>", lambda _e: _close())
    close_link.bind("<Enter>", lambda _e: close_link.config(fg=TEXT_META))
    close_link.bind("<Leave>", lambda _e: close_link.config(fg=TEXT_HINT))

    copy_link = tk.Label(
        btn_row, text="只复制命令",
        bg=BG, fg=BLUE, font=f_link, cursor="hand2",
    )
    copy_link.pack(side="right", padx=(0, 16))
    copy_link.bind("<Button-1>", lambda _e: _copy())
    copy_link.bind("<Enter>", lambda _e: copy_link.config(fg=BLUE_HOVER))
    copy_link.bind("<Leave>", lambda _e: copy_link.config(fg=BLUE))

    win.bind("<Escape>", lambda _e: _close())
    win.bind("<Return>", lambda _e: _auto_install())
    win.protocol("WM_DELETE_WINDOW", _close)

    # Pre-copy to clipboard for convenience
    win.update_idletasks()
    _copy()

    # Center on screen (no monitor-aware logic — stdlib only)
    w = max(win.winfo_reqwidth(), 480)
    h = win.winfo_reqheight()
    sw = win.winfo_screenwidth()
    sh = win.winfo_screenheight()
    win.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2 - 40}")
    win.deiconify()
    win.lift()
    win.focus_force()
    root.mainloop()


def check_required() -> list[str]:
    """Return the list of missing third-party modules. Empty list = all good."""
    required = _REQUIRED_MAC if IS_MAC else _REQUIRED_WIN
    missing = []
    for display, import_name in required:
        try:
            __import__(import_name)
        except ImportError:
            missing.append(display)
    return missing


if __name__ == "__main__":
    show(["mouse", "pystray"] if not IS_MAC else ["pynput", "Quartz"])
    sys.exit(0)
