"""Re-encode text grids as an animated (self-playing) GIF."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .renderer import Grid

_FONT_CANDIDATES = (
    "DejaVuSansMono.ttf",
    "DejaVuSansMono-Bold.ttf",
    "LiberationMono-Regular.ttf",
    "AdwaitaMono-Regular.ttf",
    "NimbusMonoPS-Regular.otf",
    "Courier_New.ttf",
    "cour.ttf",
)


def resolve_font(font_path: str | Path | None, font_size: int) -> ImageFont.FreeTypeFont:
    """Resolve a monospace-capable font.

    Explicit --gif-font wins, else first available system monospace,
    else Pillow's default (rendered on a forced fixed-cell grid so
    columns stay aligned even with a proportional fallback).
    """
    if font_path is not None:
        return ImageFont.truetype(str(font_path), font_size)
    for name in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(name, font_size)
        except OSError:
            continue
    return ImageFont.load_default(size=font_size)


def grids_to_images(
    grids: list[Grid],
    color: bool,
    font: ImageFont.FreeTypeFont | None = None,
    font_size: int = 20,
    bg: tuple[int, int, int] = (0, 0, 0),
    fg: tuple[int, int, int] = (255, 255, 255),
) -> list[Image.Image]:
    """Rasterize text grids to RGB images on a fixed monospace cell grid."""
    if not grids:
        raise ValueError("no frames to encode")
    if font is None:
        font = resolve_font(None, font_size)

    ascent, descent = font.getmetrics()
    # Fixed cell: widest advance among used glyphs so columns align
    # even if the fallback font is proportional.
    glyphs = {ch for grid in grids for row in grid for ch, _ in row}
    advances = [font.getlength(c) for c in glyphs if c.strip()]
    cell_w = max(1, int(max(advances, default=10.0)) + 2)
    cell_h = max(1, ascent + descent)

    cols = len(grids[0][0])
    rows = len(grids[0])
    images: list[Image.Image] = []
    for grid in grids:
        img = Image.new("RGB", (cols * cell_w, rows * cell_h), bg)
        d = ImageDraw.Draw(img)
        for y, row in enumerate(grid):
            for x, (ch, rgb) in enumerate(row):
                fill = tuple(rgb) if color else fg
                d.text((x * cell_w, y * cell_h), ch, font=font, fill=fill)
        images.append(img)
    return images


def save_text_gif(
    images: list[Image.Image],
    out_path: str | Path,
    fps: float,
    loop: int = 0,
    durations_ms: list[int] | None = None,
) -> Path:
    """Save rasterized text frames as an animated GIF (self-playing export)."""
    if not images:
        raise ValueError("no frames to encode")
    if fps <= 0:
        raise ValueError("--fps must be > 0")
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    if durations_ms is None:
        durations_ms = [max(1, round(1000.0 / fps))] * len(images)
    first, rest = images[0], images[1:]
    first.save(
        out,
        save_all=True,
        append_images=rest,
        duration=durations_ms,
        loop=loop,
        optimize=False,
    )
    return out
