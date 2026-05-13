"""Stdlib-only dependency error dialog.

Used when third-party Python deps are missing. This is the failure that
historically caused "shortcut clicked but nothing happened": pythonw has no
console, so the ImportError was invisible. Now we catch it and show a real
window the user can act on.

This module MUST stay stdlib-only — it is the fallback when third-party
imports fail, so it cannot rely on anything beyond tkinter / pathlib / sys.
"""
from __future__ import annotations

import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import font as tkfont

ICON_PATH = Path(__file__).resolve().parent.parent / "assets" / "logo" / "icon-128.png"

IS_MAC = sys.platform == "darwin"

# pip command the dialog suggests / runs. Windows uses the py launcher;
# macOS / Linux use python3.
if IS_MAC:
    PIP_CMD = "python3 -m pip install --user -r requirements.txt"
else:
    PIP_CMD = "py -m pip install --user -r requirements.txt"


# Modules to require, per platform. Each entry is (display name, import name).
# Windows uses the `mouse` package; macOS uses pynput + the pyobjc frameworks.
# pystray works on Windows; on Mac we talk to NSStatusBar directly so it's
# only soft-required (no entry here).
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


def show(missing: list[str]) -> None:
    """Block until the user dismisses the dialog. Side effect: copies the
    pip command to clipboard so the user can paste it into a terminal."""
    root = tk.Tk()
    root.withdraw()

    win = tk.Toplevel(root)
    win.title("codelang 启动失败")
    win.attributes("-topmost", True)
    try:
        ico = ICON_PATH.with_suffix(".ico")
        if not IS_MAC and ico.exists():
            win.iconbitmap(str(ico))
    except tk.TclError:
        pass

    bg = "#fdfdfd"
    text_dark = "#1a1a1a"
    text_meta = "#5a5a5a"
    accent = "#b91c1c"
    btn_bg = "#1d4ed8"

    families = set(tkfont.families())
    if IS_MAC:
        family = next((f for f in ("PingFang SC", "Helvetica Neue") if f in families), "TkDefaultFont")
        mono_family = next((f for f in ("Menlo", "Monaco") if f in families), "TkFixedFont")
    else:
        family = "Microsoft YaHei UI" if "Microsoft YaHei UI" in families else (
            "Segoe UI" if "Segoe UI" in families else "TkDefaultFont"
        )
        mono_family = "Consolas" if "Consolas" in families else "TkFixedFont"
    f_title = tkfont.Font(family=family, size=13, weight="bold")
    f_body = tkfont.Font(family=family, size=10 if IS_MAC else 9)
    f_mono = tkfont.Font(family=mono_family, size=10 if IS_MAC else 9)
    f_btn = tkfont.Font(family=family, size=10 if IS_MAC else 9, weight="bold")

    inner = tk.Frame(win, bg=bg, padx=20, pady=18)
    inner.pack(fill="both", expand=True)

    tk.Label(
        inner, text="codelang 还缺一些 Python 包，没法启动",
        bg=bg, fg=accent, font=f_title, anchor="w",
    ).pack(anchor="w")

    tk.Label(
        inner, text=f"缺少：{', '.join(missing)}",
        bg=bg, fg=text_dark, font=f_body, anchor="w",
    ).pack(anchor="w", pady=(6, 12))

    hint_text = (
        "在终端里粘贴下面这条命令，回车即可："
        if IS_MAC
        else "在 CMD 或 PowerShell 里粘贴下面这条命令，回车即可："
    )
    tk.Label(
        inner, text=hint_text,
        bg=bg, fg=text_meta, font=f_body, anchor="w",
    ).pack(anchor="w")

    cmd_box = tk.Entry(inner, font=f_mono, width=52, relief="solid", bd=1)
    cmd_box.insert(0, PIP_CMD)
    cmd_box.config(state="readonly")
    cmd_box.pack(fill="x", pady=(4, 10))

    note = tk.Label(
        inner,
        text="（命令已自动复制到剪贴板，Cmd+V / Ctrl+V 即可粘贴）",
        bg=bg, fg=text_meta, font=f_body, anchor="w",
    )
    note.pack(anchor="w")

    btn_row = tk.Frame(inner, bg=bg)
    btn_row.pack(fill="x", pady=(14, 0))

    project_root = Path(__file__).resolve().parent.parent

    def _copy():
        win.clipboard_clear()
        win.clipboard_append(PIP_CMD)
        note.config(text="（已复制 ✓ 去终端粘贴吧）")

    def _auto_install():
        # Open a terminal window that actually runs the install (so user sees
        # progress and any pip errors). Mac: osascript opens Terminal.app and
        # runs the command. Windows: /K cmd window stays open afterwards.
        try:
            if IS_MAC:
                note.config(text="（正在打开终端跑 pip install，装完后重新启动 codelang）")
                shell_cmd = (
                    f'cd "{project_root}" && '
                    "python3 -m pip install --user -r requirements.txt && "
                    'echo "" && echo "装好了！重新跑 codelang 即可。"'
                )
                # Escape for AppleScript string
                escaped = shell_cmd.replace('\\', '\\\\').replace('"', '\\"')
                osa = f'tell application "Terminal" to do script "{escaped}"\n' \
                      f'tell application "Terminal" to activate'
                subprocess.Popen(["osascript", "-e", osa])
            else:
                note.config(text="（正在打开 CMD 跑 pip install，装完后请重新双击 codelang 启动）")
                cmd = (
                    f'cd /d "{project_root}" && py -m pip install --user -r requirements.txt && '
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

    tk.Button(
        btn_row, text="一键安装（推荐）", font=f_btn, bg=btn_bg, fg="white",
        bd=0, padx=14, pady=5, cursor="hand2",
        activebackground="#1948c5", activeforeground="white",
        command=_auto_install,
    ).pack(side="left")
    tk.Button(
        btn_row, text="只复制命令", font=f_btn,
        bg="#e6e6e6", fg=text_dark,
        bd=0, padx=14, pady=5, cursor="hand2",
        activebackground="#d0d0d0",
        command=_copy,
    ).pack(side="left", padx=(8, 0))
    tk.Button(
        btn_row, text="关闭", font=f_btn,
        bg="#e6e6e6", fg=text_dark,
        bd=0, padx=14, pady=5, cursor="hand2",
        activebackground="#d0d0d0",
        command=_close,
    ).pack(side="right")

    win.protocol("WM_DELETE_WINDOW", _close)
    _copy()  # pre-copy on open for convenience

    win.update_idletasks()
    w = win.winfo_reqwidth()
    h = win.winfo_reqheight()
    sw = win.winfo_screenwidth()
    sh = win.winfo_screenheight()
    win.geometry(f"+{(sw - w) // 2}+{(sh - h) // 2 - 40}")
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
