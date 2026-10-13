"""Core conversion: image -> grid of (char, rgb) cells."""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageEnhance


@dataclass
class ConvertOptions:
    width: int = 100
    height: int | None = None  # None => preserve aspect with correction
    aspect: float = 0.55  # terminal cell H/W correction (<1 compresses height)
    contrast: float = 1.0
    brightness: float = 1.0
    crop_aspect: float | None = None  # None => no crop; else center-crop to W/H ratio first


def _center_crop(img: Image.Image, target_aspect: float) -> Image.Image:
    """Center-crop to a W/H aspect ratio (crop, don't stretch)."""
    src_w, src_h = img.size
    if src_w == 0 or src_h == 0:
        raise ValueError("image has zero dimension")
    if abs(src_w / src_h - target_aspect) < 1e-6:
        return img
    if src_w / src_h > target_aspect:
        # Too wide: trim sides (landscape clip -> vertical shorts).
        new_w = max(1, round(src_h * target_aspect))
        x0 = (src_w - new_w) // 2
        return img.crop((x0, 0, x0 + new_w, src_h))
    # Too tall: trim top/bottom.
    new_h = max(1, round(src_w / target_aspect))
    y0 = (src_h - new_h) // 2
    return img.crop((0, y0, src_w, y0 + new_h))


def convert(img: Image.Image, ramp: str, opts: ConvertOptions) -> list[list[tuple[str, tuple[int, int, int]]]]:
    """Resize, adjust, and map an RGB image to a char/color grid.

    Returns rows[y][x] = (character, (r, g, b)).
    """
    if opts.width < 1:
        raise ValueError("--width must be >= 1")
    if opts.crop_aspect is not None:
        img = _center_crop(img, opts.crop_aspect)
    w, h = _target_size(img, opts.width, opts.height, opts.aspect)

    work = img.resize((w, h), Image.LANCZOS)
    if opts.contrast != 1.0:
        work = ImageEnhance.Contrast(work).enhance(opts.contrast)
    if opts.brightness != 1.0:
        work = ImageEnhance.Brightness(work).enhance(opts.brightness)

    gray = work.convert("L")
    px_gray = gray.load()
    px_rgb = work.load()

    n = len(ramp)
    rows: list[list[tuple[str, tuple[int, int, int]]]] = []
    for y in range(h):
        row: list[tuple[str, tuple[int, int, int]]] = []
        for x in range(w):
            lum = px_gray[x, y] / 255.0  # 0=dark, 1=light
            idx = min(int(lum * n), n - 1)
            r, g, b = px_rgb[x, y]
            row.append((ramp[idx], (r, g, b)))
        rows.append(row)
    return rows


def _target_size(img: Image.Image, width: int, height: int | None, aspect: float) -> tuple[int, int]:
    src_w, src_h = img.size
    if src_w == 0 or src_h == 0:
        raise ValueError("image has zero dimension")
    if height is not None:
        if height < 1:
            raise ValueError("--height must be >= 1")
        return width, height
    h = max(1, round(src_h / src_w * width * aspect))
    return width, h
