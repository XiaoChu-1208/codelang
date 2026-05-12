"""Render codelang's icon as PNG files at multiple sizes.

Two designs available:
  - minimal-gray (default, user-facing): clean light-gray UFO with white
    glasses and dark outlines, slight left tilt. Used for tray + README banner.
  - blueprint: blue grid background, white outline. Internal/config use only.

Outputs:
  assets/logo/icon-{16,32,64,128,256,512}.png         (minimal-gray)
  assets/logo/icon-blueprint-{16,32,64,128,256,512}.png  (blueprint backup)
  assets/logo/icon.ico                                 (multi-res, gray-based)

Run: py tools/render_icons.py
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "assets" / "logo"
SIZES = [16, 32, 64, 128, 256, 512]


# ---------- Blueprint design (kept for internal/config use) ----------

def render_blueprint(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    s = size / 100.0

    BG = (37, 99, 235, 255)
    GRID = (96, 165, 250, 90)
    WHITE = (255, 255, 255, 255)
    CONSTRUCTION = (147, 197, 253, 200)

    radius = int(16 * s)
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=BG)

    for i in range(10, 100, 10):
        x = int(i * s)
        y = int(i * s)
        draw.line([(x, 0), (x, size)], fill=GRID, width=1)
        draw.line([(0, y), (size, y)], fill=GRID, width=1)

    def P(x, y):
        return (x * s, y * s)

    def W(lw):
        return max(1, int(round(lw * s)))

    stroke = W(2.5)

    # Construction dashed crosshair
    y = int(65 * s)
    seg_len = max(2, int(2 * s))
    gap_len = max(1, int(3 * s))
    x = 0
    while x < size:
        draw.line([(x, y), (min(x + seg_len, size), y)], fill=CONSTRUCTION, width=W(1))
        x += seg_len + gap_len
    x = int(50 * s)
    y = 0
    while y < size:
        draw.line([(x, y), (x, min(y + seg_len, size))], fill=CONSTRUCTION, width=W(1))
        y += seg_len + gap_len

    cap_box = [int(25 * s), int(15 * s), int(75 * s), int(95 * s)]
    draw.arc(cap_box, start=180, end=360, fill=WHITE, width=stroke)
    draw.line([P(25, 55), P(75, 55)], fill=WHITE, width=stroke)

    base_box = [int((50 - 45) * s), int((65 - 15) * s),
                int((50 + 45) * s), int((65 + 15) * s)]
    draw.ellipse(base_box, outline=WHITE, width=stroke)

    draw.line([P(50, 20), P(50, 5)], fill=WHITE, width=stroke)
    r = 4 * s
    draw.ellipse([P(50, 5)[0] - r, P(50, 5)[1] - r,
                  P(50, 5)[0] + r, P(50, 5)[1] + r], fill=WHITE)

    glass_radius = max(2, int(4 * s))
    draw.rounded_rectangle([int(28 * s), int(35 * s), int(46 * s), int(53 * s)],
                           radius=glass_radius, outline=WHITE, width=stroke)
    draw.rounded_rectangle([int(54 * s), int(35 * s), int(72 * s), int(53 * s)],
                           radius=glass_radius, outline=WHITE, width=stroke)
    draw.line([P(46, 44), P(54, 44)], fill=WHITE, width=stroke)
    for cx in (37, 63):
        draw.ellipse([(cx - 2) * s, (44 - 2) * s,
                      (cx + 2) * s, (44 + 2) * s], fill=WHITE)
    draw.line([P(40, 70), P(60, 70)], fill=WHITE, width=stroke)

    return img


# ---------- Minimal-gray design (default, user-facing) ----------

def render_gray(size: int) -> Image.Image:
    """Draw the minimal-gray UFO on a padded canvas, rotate -15°, then crop.

    The rotation needs padding so the tilted shape doesn't clip at the corners.
    Padding equal to size keeps things safe even at extreme aspect ratios.
    """
    pad = int(size * 0.4)
    work = size + 2 * pad
    img = Image.new("RGBA", (work, work), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    s = size / 100.0

    BODY = (241, 245, 249, 230)   # #F1F5F9 @ 0.9 opacity
    BASE = (203, 213, 225, 255)   # #CBD5E1
    DARK = (30, 41, 59, 255)      # #1E293B
    RED = (239, 68, 68, 255)      # #EF4444
    WHITE = (255, 255, 255, 255)

    # logical (0..100) → pixel coords, accounting for translate(0, 5)
    def P(x, y):
        return (x * s + pad, (y + 5) * s + pad)

    def W(lw):
        return max(1, round(lw * s))

    # Body cap (filled)
    cap_box = [*P(25, 15), *P(75, 95)]
    draw.pieslice(cap_box, start=180, end=360, fill=BODY)

    # Base ellipse (filled)
    base_box = [*P(5, 50), *P(95, 80)]
    draw.ellipse(base_box, fill=BASE)

    # Antenna line
    draw.line([P(50, 20), P(50, 5)], fill=DARK, width=W(3))
    # Red ball
    r = 4 * s
    cx, cy = P(50, 5)
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=RED)

    # Glasses (white fill + dark outline)
    sw = W(4)
    rad = max(2, round(4 * s))
    g_left = [*P(28, 35), *P(46, 53)]
    g_right = [*P(54, 35), *P(72, 53)]
    draw.rounded_rectangle(g_left, radius=rad, fill=WHITE, outline=DARK, width=sw)
    draw.rounded_rectangle(g_right, radius=rad, fill=WHITE, outline=DARK, width=sw)
    # Bridge
    draw.line([P(46, 44), P(54, 44)], fill=DARK, width=sw)

    # Eye dots
    for cx_e in (37, 63):
        cx, cy = P(cx_e, 44)
        r = 3 * s
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=DARK)

    # Mouth (white line on top of body)
    draw.line([P(40, 70), P(60, 70)], fill=WHITE, width=W(3))

    # Rotate -15° (counter-clockwise by 15 → use angle=15 in PIL)
    rotated = img.rotate(15, resample=Image.BICUBIC, center=(work / 2, work / 2))

    # Crop centered to target size
    left = (work - size) // 2
    return rotated.crop((left, left, left + size, left + size))


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    gray_images = {}
    blueprint_images = {}

    for size in SIZES:
        # Minimal gray (default)
        g = render_gray(size)
        gout = OUT_DIR / f"icon-{size}.png"
        g.save(gout, "PNG")
        gray_images[size] = g
        print(f"wrote {gout.relative_to(ROOT)} ({size}x{size}, gray)")

        # Blueprint (backup)
        b = render_blueprint(size)
        bout = OUT_DIR / f"icon-blueprint-{size}.png"
        b.save(bout, "PNG")
        blueprint_images[size] = b
        print(f"wrote {bout.relative_to(ROOT)} ({size}x{size}, blueprint)")

    # Multi-resolution ICO from gray (user-facing Windows icon)
    ico_sizes = [16, 32, 48, 256]
    if 48 not in gray_images:
        gray_images[48] = render_gray(48)
    ico_imgs = [gray_images[s] for s in ico_sizes]
    ico_path = OUT_DIR / "icon.ico"
    ico_imgs[0].save(
        ico_path,
        format="ICO",
        sizes=[(s, s) for s in ico_sizes],
        append_images=ico_imgs[1:],
    )
    print(f"wrote {ico_path.relative_to(ROOT)} (multi-res ICO, gray)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
