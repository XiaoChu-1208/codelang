"""Build a macOS iconset directory iconutil can turn into a .icns.

Why this exists: the committed `assets/logo/icon-*.png` set was rendered at
the UFO mascot's natural ~16:15 aspect ratio (16×15, 32×29, …, 512×459), not
square. Apple's `iconutil` silently rejects any non-square slice with just
"Failed to generate ICNS" — no clue which file is at fault. So we pre-pad
every slice onto a transparent square canvas before handing it to iconutil.

Usage:
    python installer/make_iconset.py <iconset_output_dir>

Reads assets/logo/icon-{16,32,…,512}.png relative to the repo root.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parent.parent
SRC_DIR = REPO / "assets" / "logo"

# Every slot Apple's modern .icns layout expects, with the pixel size each
# needs. iconutil treats `512x512@2x` (1024px) as required on macOS 11+.
SLICES: list[tuple[int, str]] = [
    (16,   "16x16"),
    (32,   "16x16@2x"),
    (32,   "32x32"),
    (64,   "32x32@2x"),
    (128,  "128x128"),
    (256,  "128x128@2x"),
    (256,  "256x256"),
    (512,  "256x256@2x"),
    (512,  "512x512"),
    (1024, "512x512@2x"),
]

# Native PNG sizes available in assets/logo/.
AVAILABLE_NATIVE = [16, 32, 64, 128, 256, 512]


def best_source(target: int) -> Path:
    """Pick the source whose native size is the smallest one ≥ target; if
    target exceeds everything we have (e.g. 1024), use the largest (512)
    and let pad_square upscale via LANCZOS."""
    chosen = next((n for n in AVAILABLE_NATIVE if n >= target), AVAILABLE_NATIVE[-1])
    return SRC_DIR / f"icon-{chosen}.png"


def pad_square(img: Image.Image, size: int) -> Image.Image:
    """Scale-to-fit inside size×size preserving aspect, then center on a
    fully-transparent square canvas. The mascot keeps its natural proportions
    and gets a touch of vertical padding instead of being stretched."""
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    src_w, src_h = img.size
    scale = min(size / src_w, size / src_h)
    new_w = max(1, round(src_w * scale))
    new_h = max(1, round(src_h * scale))
    if (new_w, new_h) != (src_w, src_h):
        img = img.resize((new_w, new_h), Image.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(img, ((size - new_w) // 2, (size - new_h) // 2), img)
    return canvas


def main(out_dir: str) -> int:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for size, name in SLICES:
        src = best_source(size)
        with Image.open(src) as img:
            squared = pad_square(img, size)
        dest = out / f"icon_{name}.png"
        squared.save(dest, format="PNG")
        print(f"  {dest.name:24s} ({size}x{size}) ← {src.name}")
    print(f"wrote {len(SLICES)} slices to {out}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: make_iconset.py <iconset_output_dir>", file=sys.stderr)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
