"""Render codelang's tray-style icon as PNG files at multiple sizes.

We bypass SVG → PNG conversion (cairo headaches on Windows) and instead
draw the same shapes directly with Pillow. The output matches the
"blueprint" SVG design in assets/logo/icon-blueprint.svg.

Outputs:
  assets/logo/icon-{16,32,64,128,256}.png
  assets/logo/icon.ico    (multi-resolution Windows icon)
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "assets" / "logo"
SIZES = [16, 32, 64, 128, 256, 512]


def render_icon(size: int) -> Image.Image:
    """Render the blueprint-style codelang icon at `size`×`size`.

    Shapes (mapped from icon-blueprint.svg, all coords in a 100×100 system):
      - Rounded blue background (#2563EB), corner radius 16
      - Faint blueprint grid (#60A5FA at low alpha)
      - White outline UFO body: cap (path) + base (ellipse)
      - White antenna with small white ball
      - White rounded "glasses" rectangles with dots inside (the "two eyes")
      - White mouth line
      - Two construction crosshair lines (lightblue, dashed)
    """
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    s = size / 100.0  # scale factor from 100x100 logical to pixel size

    BG = (37, 99, 235, 255)  # #2563EB
    GRID = (96, 165, 250, 90)  # #60A5FA at low alpha
    WHITE = (255, 255, 255, 255)
    CONSTRUCTION = (147, 197, 253, 200)  # #93C5FD

    # 1) Rounded background
    radius = int(16 * s)
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=BG)

    # 2) Blueprint grid lines (every 10 logical units)
    for i in range(10, 100, 10):
        x = int(i * s)
        y = int(i * s)
        draw.line([(x, 0), (x, size)], fill=GRID, width=1)
        draw.line([(0, y), (size, y)], fill=GRID, width=1)

    # Helpers to scale & convert tuples
    def P(x, y):
        return (x * s, y * s)

    def W(lw):
        return max(1, int(round(lw * s)))

    stroke = W(2.5)

    # 3) Construction dashed crosshair (under the figure)
    # Horizontal at y=65
    y = int(65 * s)
    seg_len = max(2, int(2 * s))
    gap_len = max(1, int(3 * s))
    x = 0
    while x < size:
        draw.line([(x, y), (min(x + seg_len, size), y)], fill=CONSTRUCTION, width=W(1))
        x += seg_len + gap_len
    # Vertical at x=50
    x = int(50 * s)
    y = 0
    while y < size:
        draw.line([(x, y), (x, min(y + seg_len, size))], fill=CONSTRUCTION, width=W(1))
        y += seg_len + gap_len

    # 4) UFO body: top cap (rounded "C" arc from (25,55) up to (75,55)) + base ellipse

    # Approximate the SVG cubic Bezier "M 25 55 C 25 15, 75 15, 75 55 Z" as an arc:
    # It's a half-dome from (25,55) curving up and back. Equivalent to top half of an
    # ellipse centered at (50, 55) with rx=25, ry=40.
    cap_box = [int(25 * s), int(15 * s), int(75 * s), int(95 * s)]
    # The arc from 180° to 360° draws the top half. width = stroke
    draw.arc(cap_box, start=180, end=360, fill=WHITE, width=stroke)
    # Bottom line of dome closing it (from 25,55 to 75,55)
    draw.line([P(25, 55), P(75, 55)], fill=WHITE, width=stroke)

    # Base ellipse: cx=50, cy=65, rx=45, ry=15
    base_box = [int((50 - 45) * s), int((65 - 15) * s), int((50 + 45) * s), int((65 + 15) * s)]
    draw.ellipse(base_box, outline=WHITE, width=stroke)

    # 5) Antenna line + ball
    draw.line([P(50, 20), P(50, 5)], fill=WHITE, width=stroke)
    r = 4 * s
    draw.ellipse([P(50 - 4, 5 - 4)[0], P(50 - 4, 5 - 4)[1],
                  P(50 + 4, 5 + 4)[0], P(50 + 4, 5 + 4)[1]], fill=WHITE)

    # 6) Glasses (left + right)
    glass_radius = max(2, int(4 * s))
    draw.rounded_rectangle([int(28 * s), int(35 * s), int(46 * s), int(53 * s)],
                           radius=glass_radius, outline=WHITE, width=stroke)
    draw.rounded_rectangle([int(54 * s), int(35 * s), int(72 * s), int(53 * s)],
                           radius=glass_radius, outline=WHITE, width=stroke)
    # Bridge
    draw.line([P(46, 44), P(54, 44)], fill=WHITE, width=stroke)
    # Eye dots
    dot_r = 2 * s
    for cx in (37, 63):
        draw.ellipse([(cx - 2) * s, (44 - 2) * s, (cx + 2) * s, (44 + 2) * s], fill=WHITE)

    # 7) Mouth
    draw.line([P(40, 70), P(60, 70)], fill=WHITE, width=stroke)

    return img


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    images = {}
    for size in SIZES:
        img = render_icon(size)
        out = OUT_DIR / f"icon-{size}.png"
        img.save(out, "PNG")
        images[size] = img
        print(f"wrote {out.relative_to(ROOT)} ({size}x{size})")

    # Build multi-res ico from the four common Windows sizes
    ico_sizes = [16, 32, 48, 256]
    # 48 isn't in our set; render it on the fly
    if 48 not in images:
        images[48] = render_icon(48)
    ico_imgs = [images[s] for s in ico_sizes]
    ico_path = OUT_DIR / "icon.ico"
    ico_imgs[0].save(ico_path, format="ICO",
                     sizes=[(s, s) for s in ico_sizes],
                     append_images=ico_imgs[1:])
    print(f"wrote {ico_path.relative_to(ROOT)} (multi-res ICO)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
