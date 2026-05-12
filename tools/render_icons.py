"""Render codelang icons by rasterizing the original Gemini-authored SVG files.

We rely on resvg-py (Rust-based, statically linked) to render the exact SVG
shapes. This replaces an earlier hand-drawn-with-Pillow approach which only
approximated the design.

Outputs (in assets/logo/):
  icon-{16,32,64,128,256,512}.png            (from icon-minimal-gray.svg)
  icon-blueprint-{16,32,64,128,256,512}.png  (from icon-blueprint.svg)
  icon.ico                                   (multi-res ICO, gray-based)

Requires: pip install resvg-py Pillow
Run: py tools/render_icons.py
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

from PIL import Image

try:
    import resvg_py
except ImportError:
    sys.stderr.write(
        "Need resvg-py. Install: py -m pip install resvg-py\n"
        "It's a Rust-based, statically-linked SVG renderer — no cairo needed.\n"
    )
    sys.exit(1)


ROOT = Path(__file__).resolve().parent.parent
LOGO_DIR = ROOT / "assets" / "logo"

SIZES = [16, 32, 64, 128, 256, 512]
ICO_SIZES = [16, 32, 48, 256]

# Map output prefix → source SVG file. icon-{size}.png comes from the
# user-facing minimal-gray design; icon-blueprint-{size}.png is the
# alternative blueprint design.
DESIGNS = {
    "icon": LOGO_DIR / "icon-minimal-gray.svg",
    "icon-blueprint": LOGO_DIR / "icon-blueprint.svg",
}


def render_svg(svg_path: Path, size: int) -> Image.Image:
    """Rasterize an SVG to a PIL Image at `size`×`size`."""
    png_bytes = resvg_py.svg_to_bytes(
        svg_path=str(svg_path),
        width=size,
        height=size,
    )
    return Image.open(io.BytesIO(bytes(png_bytes))).convert("RGBA")


def main() -> int:
    LOGO_DIR.mkdir(parents=True, exist_ok=True)

    for prefix, svg_path in DESIGNS.items():
        if not svg_path.exists():
            sys.stderr.write(f"missing source SVG: {svg_path}\n")
            return 1
        for size in SIZES:
            img = render_svg(svg_path, size)
            out = LOGO_DIR / f"{prefix}-{size}.png"
            img.save(out, "PNG")
            print(f"wrote {out.relative_to(ROOT)} ({size}x{size}) from {svg_path.name}")

    # Multi-resolution ICO from gray design (user-facing Windows icon)
    ico_imgs = [render_svg(DESIGNS["icon"], s) for s in ICO_SIZES]
    ico_path = LOGO_DIR / "icon.ico"
    ico_imgs[0].save(
        ico_path,
        format="ICO",
        sizes=[(s, s) for s in ICO_SIZES],
        append_images=ico_imgs[1:],
    )
    print(f"wrote {ico_path.relative_to(ROOT)} (multi-res ICO from minimal-gray)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
