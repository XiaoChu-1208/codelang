"""Generate Inno Setup wizard BMPs from logo assets.

Outputs (in installer/):
  wizard-large.bmp  (164x314, 24-bit) — left panel on Welcome / Finished pages.
                     A composed illustration: soft blue gradient + UFO icon +
                     "codelang" wordmark + Chinese tagline + decorative dots.
  wizard-small.bmp  (55x58,  24-bit) — top-right corner on other pages.
                     Pure white background so it blends seamlessly with Inno's
                     modern wizard header (which is white) — looks "transparent".

Run:
  py tools/build_installer_assets.py
"""
from __future__ import annotations

import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
ICON_BIG = ROOT / "assets" / "logo" / "icon-512.png"
ICON_SMALL = ROOT / "assets" / "logo" / "icon-128.png"
OUT_DIR = ROOT / "installer"

LARGE = (164, 314)
SMALL = (55, 58)

# Palette tuned to the icon's pale-blue UFO background.
BG_TOP = (244, 248, 253)
BG_BOT = (213, 224, 240)
INK = (24, 32, 48)           # dark navy — matches icon's outline
MUTED = (96, 112, 134)       # mid-gray for subtitle
ACCENT = (239, 68, 68)       # red of the icon's antenna ball
DOT_LIGHT = (255, 255, 255)  # for soft highlight dots
DOT_DARK = (181, 199, 222)   # for subtle shadow dots

# Microsoft YaHei ships with Windows and renders Chinese cleanly.
FONT_BOLD = "C:/Windows/Fonts/msyhbd.ttc"
FONT_REG = "C:/Windows/Fonts/msyh.ttc"


def make_gradient(size: tuple[int, int], top: tuple[int, int, int], bot: tuple[int, int, int]) -> Image.Image:
    w, h = size
    img = Image.new("RGB", size)
    px = img.load()
    for y in range(h):
        t = y / max(h - 1, 1)
        r = round(top[0] * (1 - t) + bot[0] * t)
        g = round(top[1] * (1 - t) + bot[1] * t)
        b = round(top[2] * (1 - t) + bot[2] * t)
        for x in range(w):
            px[x, y] = (r, g, b)
    return img


def paste_icon(bg: Image.Image, icon_path: Path, target_w: int, center_xy: tuple[int, int]) -> None:
    """Paste icon at given target width, centered on (cx, cy)."""
    icon = Image.open(icon_path).convert("RGBA")
    ratio = target_w / icon.width
    target_h = max(1, round(icon.height * ratio))
    icon = icon.resize((target_w, target_h), Image.LANCZOS)
    cx, cy = center_xy
    bg.paste(icon, (cx - target_w // 2, cy - target_h // 2), icon)


def draw_soft_dot(canvas: Image.Image, center: tuple[int, int], radius: int, color: tuple[int, int, int], alpha: int) -> None:
    """Anti-aliased translucent circle, composited onto canvas."""
    d = radius * 2
    dot = Image.new("RGBA", (d * 4, d * 4), (0, 0, 0, 0))
    dd = ImageDraw.Draw(dot)
    dd.ellipse((0, 0, d * 4 - 1, d * 4 - 1), fill=(*color, alpha))
    dot = dot.resize((d, d), Image.LANCZOS)
    cx, cy = center
    canvas.paste(dot, (cx - radius, cy - radius), dot)


def draw_centered_text(canvas: Image.Image, draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, y: int, fill: tuple[int, int, int]) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    x = (canvas.width - tw) // 2 - bbox[0]
    draw.text((x, y), text, fill=fill, font=font)


def build_large() -> Image.Image:
    """Welcome-page illustration: gradient + decorative dots + UFO + wordmark."""
    canvas = make_gradient(LARGE, BG_TOP, BG_BOT).convert("RGBA")

    # Decorative dots — seeded so output is deterministic across runs.
    rng = random.Random(20260513)
    # Lighter dots scattered, denser near top
    for _ in range(22):
        x = rng.randint(8, LARGE[0] - 8)
        y = rng.randint(8, LARGE[1] - 8)
        r = rng.randint(2, 5)
        # weight: lighter dots toward top, darker faint dots in lower half
        if y < LARGE[1] * 0.55:
            draw_soft_dot(canvas, (x, y), r, DOT_LIGHT, alpha=rng.randint(110, 200))
        else:
            draw_soft_dot(canvas, (x, y), r, DOT_DARK, alpha=rng.randint(70, 130))

    # Two larger soft "cloud" highlights to add depth
    draw_soft_dot(canvas, (24, 26), 28, DOT_LIGHT, alpha=140)
    draw_soft_dot(canvas, (LARGE[0] - 18, 56), 36, DOT_LIGHT, alpha=110)

    # Hero icon — large, slightly upper area
    paste_icon(canvas, ICON_BIG, target_w=int(LARGE[0] * 0.78), center_xy=(LARGE[0] // 2, 100))

    # Wordmark + tagline
    draw = ImageDraw.Draw(canvas)
    font_brand = ImageFont.truetype(FONT_BOLD, 24)
    font_sub = ImageFont.truetype(FONT_REG, 11)
    font_micro = ImageFont.truetype(FONT_REG, 9)

    draw_centered_text(canvas, draw, "codelang", font_brand, y=190, fill=INK)
    draw_centered_text(canvas, draw, "划词秒变人话", font_sub, y=222, fill=MUTED)

    # Red accent divider
    cx = LARGE[0] // 2
    draw.rounded_rectangle((cx - 16, 245, cx + 16, 248), radius=2, fill=ACCENT)

    # Footer micro-tagline
    draw_centered_text(canvas, draw, "Alt + 划词 · 2421 词 · 100% 本地", font_micro, y=260, fill=MUTED)

    return canvas.convert("RGB")


def build_small() -> Image.Image:
    """Top-right header icon. Pure white BG to blend with modern wizard header."""
    canvas = Image.new("RGB", SMALL, (255, 255, 255))
    # Icon centered, sized to fill comfortably
    icon = Image.open(ICON_SMALL).convert("RGBA")
    target_w = int(SMALL[0] * 0.85)
    ratio = target_w / icon.width
    target_h = max(1, round(icon.height * ratio))
    icon = icon.resize((target_w, target_h), Image.LANCZOS)
    canvas.paste(icon, ((SMALL[0] - target_w) // 2, (SMALL[1] - target_h) // 2), icon)
    return canvas


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    large_path = OUT_DIR / "wizard-large.bmp"
    build_large().save(large_path, "BMP")
    print(f"Wrote {large_path}  ({LARGE[0]}x{LARGE[1]})")

    small_path = OUT_DIR / "wizard-small.bmp"
    build_small().save(small_path, "BMP")
    print(f"Wrote {small_path}  ({SMALL[0]}x{SMALL[1]})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
