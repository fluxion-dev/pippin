"""Image loading: png/jpeg via Pillow, svg via cairosvg."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

SUPPORTED_SUFFIXES = {".png", ".jpg", ".jpeg", ".svg", ".bmp", ".gif", ".webp", ".tiff", ".tif"}


def load_image(path: str | Path) -> Image.Image:
    """Load an image file into an RGB Pillow image.

    SVG files are rasterized with cairosvg at high resolution so edges
    stay sharp when downsampled to character cells.
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"input file not found: {p}")
    suffix = p.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError(f"unsupported format {suffix!r}, supported: {sorted(SUPPORTED_SUFFIXES)}")

    if suffix == ".svg":
        return _load_svg(p)
    img = Image.open(p)
    return _to_rgb(img)


def _load_svg(path: Path, render_width: int = 2048) -> Image.Image:
    try:
        import cairosvg
    except ImportError as e:
        raise ImportError("svg support requires 'cairosvg' (pip install cairosvg + system cairo)") from e
    png_bytes = cairosvg.svg2png(url=str(path), output_width=render_width)
    img = Image.open(io.BytesIO(png_bytes))
    return _to_rgb(img)


def _to_rgb(img: Image.Image) -> Image.Image:
    # Composite transparency onto black for predictable luminance.
    if img.mode in ("RGBA", "LA"):
        bg = Image.new("RGB", img.size, (0, 0, 0))
        alpha = img.split()[-1]
        bg.paste(img.convert("RGB"), mask=alpha)
        return bg
    if img.mode == "P" and "transparency" in img.info:
        bg = Image.new("RGB", img.size, (0, 0, 0))
        bg.paste(img.convert("RGB"), mask=img.convert("RGBA").split()[-1])
        return bg
    return img.convert("RGB")
