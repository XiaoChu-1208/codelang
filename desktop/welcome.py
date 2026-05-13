"""First-run welcome window.

Layout closely follows the reference mock: left half is a soft-blue tinted
panel with a large mascot illustration; right half is white and contains the
title, subtitle, two feature cards, a stats chip, and the primary CTA at the
bottom-right paired with a small hint at the bottom-left.

Pillow is required (welcome only runs after `deps_error.check_required()`
passes, so PIL/ImageTk are guaranteed to be importable here).

Persistence: `config["welcome_shown"] = True` after dismissal so the card
never appears again until the user manually flips it back.
"""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import font as tkfont

from PIL import Image, ImageTk, ImageDraw, ImageFilter, ImageChops

from . import config
from . import platform_compat as winhelp


ICON_PATH = Path(__file__).resolve().parent.parent / "assets" / "logo" / "icon-512.png"

WIN_W, WIN_H = 500, 230
RIGHT_W = 370  # right text panel; left area = WIN_W - RIGHT_W for mascot

BG          = "#ffffff"
BORDER      = "#d9dfe8"

BLUE        = "#2956E6"
BLUE_HOVER  = "#1f43c1"
TEXT_DARK   = "#1a1a1a"
TEXT_META   = "#6b7280"
TEXT_HINT   = "#9aa0a6"

CARD_BG     = "#fbfcfe"
CARD_BORDER = "#e7eaf0"

ICON1_BG    = "#e7eeff"
ICON1_FG    = "#2956E6"
ICON2_BG    = "#e6f4ec"
ICON2_FG    = "#1e7a3a"

CHIP_BG     = "#eef4ff"
CHIP_FG     = "#2956E6"


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


def _compose_mascot(max_side: int) -> Image.Image | None:
    """Build a vertical composition: UFO mascot on top, soft blue light beam
    fanning out underneath (gradient trapezoid, tilted slightly to match the
    saucer's lean). Turns the previous square icon-only image into a
    portrait composition so the left column doesn't read as an awkward
    floating dot in the middle.

    The beam is rendered by:
      1. drawing a solid-white trapezoid as a shape mask;
      2. drawing a vertical gradient (bright at top, fading to 0 at bottom);
      3. ANDing the two via ImageChops.multiply to get the final alpha;
      4. Gaussian-blurring to soften the trapezoid's hard edges;
      5. putalpha onto a solid blue fill, then alpha_composite under the UFO.
    """
    if not ICON_PATH.exists():
        return None
    try:
        icon_raw = Image.open(ICON_PATH).convert("RGBA")
    except Exception:
        return None

    # The bundled icon is drawn with the UFO rotated ~15° to one side. For the
    # welcome composition we want it upright + a straight vertical beam, so
    # rotate -15° here to undo it. expand=True grows the canvas to fit the
    # rotated bbox so corners don't get clipped.
    icon = icon_raw.rotate(-15, resample=Image.BICUBIC, expand=True)
    iw, ih = icon.size  # ~613 x 576 after the 15° rotation
    beam_extra = int(ih * 0.62)

    # Beam geometry — straight vertical trapezoid (no rotation). Earlier we
    # matched the icon's 15° clockwise tilt, but that made the source canvas
    # rightward-extended and the displayed mascot too wide. With straight
    # beam the image stays narrow and the right text panel gets more room.
    ufo_bottom_y = int(ih * 0.60)
    cx = iw // 2
    # Reduced widths: the rotated canvas is ~20% wider than the original icon,
    # so the previous 0.30/0.92 ratios would make the beam wider than the
    # saucer plate. New ratios scale the same absolute widths.
    top_w = int(iw * 0.25)
    bot_w = int(iw * 0.74)
    canvas_w = iw
    canvas_h = ih + beam_extra
    canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    beam_h = canvas_h - ufo_bottom_y

    tl = (cx - top_w // 2, ufo_bottom_y)
    tr = (cx + top_w // 2, ufo_bottom_y)
    br = (cx + bot_w // 2, canvas_h)
    bl = (cx - bot_w // 2, canvas_h)

    shape_mask = Image.new("L", (canvas_w, canvas_h), 0)
    ImageDraw.Draw(shape_mask).polygon([tl, tr, br, bl], fill=255)

    # Brightness gradient: bright near saucer, fades to 0 at canvas bottom.
    # Capped at ~170/255 so the beam reads as soft light, not a solid block.
    MAX_ALPHA = 165
    grad = Image.new("L", (canvas_w, canvas_h), 0)
    gd = ImageDraw.Draw(grad)
    for y in range(ufo_bottom_y, canvas_h):
        p = (y - ufo_bottom_y) / beam_h
        alpha = int(MAX_ALPHA * (1.0 - p) ** 1.6)
        gd.line([(0, y), (canvas_w, y)], fill=alpha)

    combined_alpha = ImageChops.multiply(shape_mask, grad)
    combined_alpha = combined_alpha.filter(ImageFilter.GaussianBlur(radius=16))

    # Cyan-tinted sky blue — lighter and more transparent than the brand blue
    beam_rgb = (130, 200, 235)
    beam = Image.new("RGBA", (canvas_w, canvas_h), beam_rgb + (0,))
    beam.putalpha(combined_alpha)

    canvas.alpha_composite(beam)
    # Rotating the icon by -15° around its bbox center leaves the saucer's
    # underside center offset to the LEFT of the rotated canvas center. Pasting
    # the icon shifted RIGHT realigns the saucer with the (centered) beam.
    saucer_shift_x = int(iw * 0.038)  # ~23 px for the typical 613-wide rotated icon
    canvas.paste(icon, (saucer_shift_x, 0), icon)

    scale = max_side / max(canvas_w, canvas_h)
    new_size = (max(1, int(canvas_w * scale)), max(1, int(canvas_h * scale)))
    return canvas.resize(new_size, Image.LANCZOS)


def _load_mascot(parent: tk.Widget, max_side: int) -> tk.Label | None:
    """Return a Label hosting the mascot+beam composition, or None on failure.
    .image is anchored to the Label so the PhotoImage isn't GC'd."""
    img = _compose_mascot(max_side)
    if img is None:
        return None
    try:
        photo = ImageTk.PhotoImage(img)
    except Exception:
        return None
    lbl = tk.Label(parent, image=photo, bg=BG, bd=0)
    lbl.image = photo  # anchor against GC
    return lbl


def _build_card(
    parent: tk.Widget,
    icon_text: str,
    icon_bg: str,
    icon_fg: str,
    title: str,
    body: str,
    family: str,
) -> tk.Frame:
    """Feature card: colored square icon on left, two-line text on right.
    Uses a 1px solid border (sharp corners — tk can't render rounded)."""
    f_title = tkfont.Font(family=family, size=9, weight="bold")
    f_body = tkfont.Font(family=family, size=8)
    f_icon = tkfont.Font(family=family, size=11, weight="bold")

    outer = tk.Frame(parent, bg=CARD_BORDER)
    inner = tk.Frame(outer, bg=CARD_BG, padx=8, pady=6)
    inner.pack(fill="both", expand=True, padx=1, pady=1)

    icon = tk.Label(
        inner, text=icon_text, bg=icon_bg, fg=icon_fg, font=f_icon,
        width=3, height=2, bd=0,
    )
    icon.pack(side="left", padx=(0, 9))

    txt = tk.Frame(inner, bg=CARD_BG)
    txt.pack(side="left", fill="x", expand=True)
    tk.Label(
        txt, text=title, bg=CARD_BG, fg=TEXT_DARK, font=f_title,
        anchor="w", justify="left",
    ).pack(anchor="w")
    tk.Label(
        txt, text=body, bg=CARD_BG, fg=TEXT_META, font=f_body,
        anchor="w", justify="left", wraplength=300,
    ).pack(anchor="w", pady=(2, 0))

    return outer


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
    f_chip = tkfont.Font(family=family, size=9)
    f_hint = tkfont.Font(family=family, size=8)

    # 1px outer border so the card stands out on light desktops
    border = tk.Frame(win, bg=BORDER)
    border.pack(fill="both", expand=True)
    shell = tk.Frame(border, bg=BG)
    shell.pack(fill="both", expand=True, padx=1, pady=1)

    # ---- Z-LAYER 0 (bottom): mascot covers entire shell, anchored top-left.
    # The right text panel sits on top of it (lift()), z-ordered above.
    mascot = _load_mascot(shell, max_side=200)
    if mascot is not None:
        # Beam is now vertical, so the composed image is symmetric horizontally
        # and the UFO sits at image center. Place leftward; tiny overlap with
        # the right panel's left edge falls on fully-transparent pixels.
        mascot.place(x=8, y=18)
    else:
        # Fallback oval, placed in the left area
        canvas = tk.Canvas(shell, width=240, height=160, bg=BG, highlightthickness=0)
        canvas.create_oval(20, 60, 220, 140, fill="#dee4ee", outline="#c6cdd9", width=2)
        canvas.place(x=20, y=90)

    # ---- Z-LAYER 1 (top): right text panel — overlays the mascot if they
    # overlap. bg=BG so any beam pixels behind the text are masked cleanly.
    right = tk.Frame(shell, bg=BG, padx=20, pady=16)
    right.place(relx=1.0, y=0, anchor="ne", relheight=1.0, width=RIGHT_W)
    right.lift()

    # Title + subtitle removed — that message is now compressed into the
    # bottom-row hint so the welcome card stays compact.

    # Cards — the wording differs slightly between platforms because
    # the menu lives in the menubar on Mac, system tray on Windows, and
    # "open at login" works through different mechanisms.
    if winhelp.IS_MAC:
        card1_title = "屏幕顶部菜单栏 灰白色小飞碟 图标"
        card1_body = "点一下可以 查看日志 / 重新加载词典 / 退出"
        card2_title = "想开机自启？"
        card2_body = "系统设置 → 通用 → 登录项 → 把 codelang 启动脚本加进去"
    else:
        card1_title = "右下角托盘 灰白色小飞碟 图标"
        card1_body = "右键可以 查看日志 / 重新加载词典 / 退出"
        card2_title = "想开机自启？"
        card2_body = "Win+R 输入 shell:startup，把桌面快捷方式拖进去"

    _build_card(
        right,
        icon_text="⌨",
        icon_bg=ICON1_BG, icon_fg=ICON1_FG,
        title=card1_title,
        body=card1_body,
        family=family,
    ).pack(fill="x", pady=(0, 5))

    _build_card(
        right,
        icon_text=">_",
        icon_bg=ICON2_BG, icon_fg=ICON2_FG,
        title=card2_title,
        body=card2_body,
        family=family,
    ).pack(fill="x", pady=(0, 8))

    # Stats chip — own row, left-aligned, fills width like in the mock
    try:
        from .lookup import DictIndex
        n = DictIndex().count
        stats_text = f"✦  词库 {n} 条  +  通用翻译  +  AI 兜底（可选）"
    except Exception:
        stats_text = "✦  本地词库  +  通用翻译  +  AI 兜底（可选）"

    chip = tk.Label(
        right, text=stats_text,
        bg=CHIP_BG, fg=CHIP_FG, font=f_chip,
        padx=12, pady=5, anchor="center",
    )
    chip.pack(fill="x")

    # ---- bottom row: single line, hint on left + text-link "开始吧" on right.
    # Both use the same font size so their baselines align; the link is just
    # colored blue (no button chrome) for compactness.
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

    bottom = tk.Frame(right, bg=BG)
    bottom.pack(fill="x", pady=(10, 0))

    trigger_key = "Option" if winhelp.IS_MAC else "Alt"
    tk.Label(
        bottom, text=f"codelang 已经在运行，按住 {trigger_key} 试试  ↗",
        bg=BG, fg=TEXT_HINT, font=f_hint, anchor="w",
    ).pack(side="left")

    start = tk.Label(
        bottom, text="开始吧  →",
        bg=BG, fg=BLUE, font=f_hint, cursor="hand2",
    )
    start.pack(side="right")
    start.bind("<Button-1>", _dismiss)
    start.bind("<Enter>", lambda _e: start.config(fg=BLUE_HOVER))
    start.bind("<Leave>", lambda _e: start.config(fg=BLUE))

    win.bind("<Escape>", _dismiss)
    win.bind("<Return>", _dismiss)

    # ---- center on the monitor that contains the cursor ----
    win.update_idletasks()
    w = max(win.winfo_reqwidth(), WIN_W)
    h = max(win.winfo_reqheight(), WIN_H)
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
