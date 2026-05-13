"""First-run welcome window.

Shown once after a fresh install so the user knows the app is actually running
(it's a tray-only app — without this, after clicking the shortcut nothing
visible happens). Pure stdlib (tk + tk.PhotoImage) so it never breaks even if
Pillow has issues. Persistence: `config["welcome_shown"] = True` after dismissal.
"""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import font as tkfont

from . import config
from . import win as winhelp


ICON_PATH = Path(__file__).resolve().parent.parent / "assets" / "logo" / "icon-128.png"


def show_welcome(root: tk.Tk) -> None:
    """Show the welcome card centered on the primary monitor. Non-blocking —
    the user dismisses it with the button or Esc. Marks welcome_shown=True
    in config once dismissed so it never reappears."""
    win = tk.Toplevel(root)
    win.withdraw()
    win.overrideredirect(True)
    win.attributes("-topmost", True)
    try:
        win.attributes("-toolwindow", True)
    except tk.TclError:
        pass

    border = "#c6c6c6"
    bg = "#fdfdfd"
    text_dark = "#1a1a1a"
    text_meta = "#5a5a5a"
    accent = "#1d4ed8"
    accent_hover = "#1948c5"
    chip_bg = "#eef4ff"

    outer = tk.Frame(win, bg=border)
    outer.pack(fill="both", expand=True)
    inner = tk.Frame(outer, bg=bg, padx=22, pady=18)
    inner.pack(fill="both", expand=True, padx=1, pady=1)

    families = set(tkfont.families())
    family = "Microsoft YaHei UI" if "Microsoft YaHei UI" in families else (
        "Segoe UI" if "Segoe UI" in families else "TkDefaultFont"
    )
    f_title = tkfont.Font(family=family, size=15, weight="bold")
    f_sub = tkfont.Font(family=family, size=10)
    f_body = tkfont.Font(family=family, size=9)
    f_chip = tkfont.Font(family=family, size=8)
    f_btn = tkfont.Font(family=family, size=10, weight="bold")
    f_meta = tkfont.Font(family=family, size=8)

    body = tk.Frame(inner, bg=bg)
    body.pack(fill="both", expand=True)

    # ---- left: icon ----
    icon_holder = tk.Frame(body, bg=bg)
    icon_holder.pack(side="left", padx=(0, 18), anchor="n")
    img = None
    if ICON_PATH.exists():
        try:
            img = tk.PhotoImage(file=str(ICON_PATH))
        except tk.TclError:
            img = None
    if img is not None:
        lbl_icon = tk.Label(icon_holder, image=img, bg=bg, bd=0)
        lbl_icon.image = img  # keep ref so GC doesn't eat it
        lbl_icon.pack()
    else:
        # Fallback: a small drawn placeholder so layout doesn't collapse
        ph = tk.Canvas(icon_holder, width=96, height=96, bg=bg, highlightthickness=0)
        ph.create_oval(8, 24, 88, 72, fill="#e6e6e6", outline="#bdbdbd")
        ph.pack()

    # ---- right: text ----
    txt = tk.Frame(body, bg=bg)
    txt.pack(side="left", fill="both", expand=True, anchor="n")

    tk.Label(
        txt, text="codelang 已经在运行 ✓".replace("✓", "·"),
        bg=bg, fg=text_dark, font=f_title, anchor="w",
    ).pack(anchor="w")

    tk.Label(
        txt, text="按住 Alt + 划词，立刻弹出代码黑话解释",
        bg=bg, fg=text_meta, font=f_sub, anchor="w",
    ).pack(anchor="w", pady=(2, 12))

    def bullet(parent: tk.Frame, head: str, tail: str) -> None:
        row = tk.Frame(parent, bg=bg)
        row.pack(fill="x", anchor="w", pady=(0, 6))
        tk.Label(row, text="▸", bg=bg, fg=accent, font=f_body).pack(side="left", anchor="n")
        col = tk.Frame(row, bg=bg)
        col.pack(side="left", fill="x", expand=True, padx=(6, 0))
        tk.Label(col, text=head, bg=bg, fg=text_dark, font=f_body,
                 anchor="w", justify="left", wraplength=320).pack(anchor="w")
        if tail:
            tk.Label(col, text=tail, bg=bg, fg=text_meta, font=f_meta,
                     anchor="w", justify="left", wraplength=320).pack(anchor="w")

    bullet(
        txt,
        "右下角托盘 灰白色小飞碟 图标",
        "右键可以 查看日志 / 重新加载词典 / 退出",
    )
    bullet(
        txt,
        "想开机自启？",
        "Win+R 输入 shell:startup，把桌面快捷方式拖进去",
    )

    # 词库统计 chip
    try:
        from .lookup import DictIndex
        n = DictIndex().count
        stats_text = f"词库 {n} 条 + 通用翻译 + AI 兜底（可选）"
    except Exception:
        stats_text = "本地词库 + 通用翻译 + AI 兜底（可选）"
    chip_row = tk.Frame(txt, bg=bg)
    chip_row.pack(anchor="w", pady=(6, 14))
    tk.Label(
        chip_row, text=stats_text,
        bg=chip_bg, fg=accent, font=f_chip, padx=8, pady=3,
    ).pack(side="left")

    # ---- button row ----
    btn_row = tk.Frame(inner, bg=bg)
    btn_row.pack(fill="x", pady=(4, 0))

    hint = tk.Label(
        btn_row, text="可以先在浏览器选段中文/英文，按住 Alt 试试 ↗",
        bg=bg, fg=text_meta, font=f_meta,
    )
    hint.pack(side="left")

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

    btn = tk.Button(
        btn_row, text="知道了，开干",
        font=f_btn, bg=accent, fg="white", bd=0, padx=18, pady=6,
        cursor="hand2", activebackground=accent_hover, activeforeground="white",
        command=_dismiss,
    )
    btn.pack(side="right")
    btn.focus_set()

    win.bind("<Escape>", _dismiss)
    win.bind("<Return>", _dismiss)

    # ---- center on the monitor that contains the cursor ----
    win.update_idletasks()
    w = win.winfo_reqwidth()
    h = win.winfo_reqheight()
    try:
        cx, cy = winhelp.get_cursor_pos()
        left, top, right, bottom = winhelp.get_monitor_work_rect(cx, cy)
        px = left + ((right - left) - w) // 2
        py = top + ((bottom - top) - h) // 2 - 40
    except Exception:
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        px = (sw - w) // 2
        py = (sh - h) // 2 - 40
    win.geometry(f"+{px}+{py}")
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
