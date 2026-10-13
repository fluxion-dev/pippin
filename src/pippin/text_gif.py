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
    chars: str | None = None,
) -> list[Image.Image]:
    """Rasterize text grids to RGB images on a fixed monospace cell grid.

    Args:
        chars: optional character set to size the cell from (e.g. the full
            luminance ramp for streaming, where not all grids are known up
            front). Defaults to the glyphs observed in ``grids``.
    """
    if not grids:
        raise ValueError("no frames to encode")
    if font is None:
        font = resolve_font(None, font_size)

    if chars is None:
        chars = "".join({ch for grid in grids for row in grid for ch, _ in row})
    cell_w, cell_h = font_cell(font, chars)
    render_one = verified_grid_renderer(font, cell_w, cell_h, chars)

    return [render_one(grid, color) for grid in grids]


def font_cell(font: ImageFont.FreeTypeFont, chars: str) -> tuple[int, int]:
    """Fixed monospace cell size fitting the widest glyph in ``chars``."""
    ascent, descent = font.getmetrics()
    # Widest advance among used glyphs so columns align even if the
    # fallback font is proportional.
    advances = [font.getlength(c) for c in set(chars) if c.strip()]
    cell_w = max(1, int(max(advances, default=10.0)) + 2)
    cell_h = max(1, ascent + descent)
    return cell_w, cell_h


def _padded_stamps(
    font: ImageFont.FreeTypeFont, cell_w: int, cell_h: int, chars: str, pad: int
) -> dict[str, Image.Image | None]:
    """One alpha mask per char, glyph drawn with ``pad`` px margin.

    Masks cover ink that spills past the cell box (negative bearings,
    overhangs); blitting at ``(x - pad, y - pad)`` reproduces exactly
    what direct ``text()`` inks, since hinter output is translation
    invariant on integer pixel positions.
    """
    stamps: dict[str, Image.Image | None] = {}
    for ch in set(chars):
        if not ch.strip():
            stamps[ch] = None
            continue
        mask = Image.new("L", (cell_w + 2 * pad, cell_h + 2 * pad), 0)
        ImageDraw.Draw(mask).text((pad, pad), ch, font=font, fill=255)
        stamps[ch] = mask
    return stamps


def _grid_to_image_stamped(
    grid: Grid,
    color: bool,
    cell_w: int,
    cell_h: int,
    stamps: dict[str, Image.Image | None],
    pad: int,
) -> Image.Image:
    cols = len(grid[0])
    rows = len(grid)
    img = Image.new("RGB", (cols * cell_w, rows * cell_h), (0, 0, 0))
    d = ImageDraw.Draw(img)
    for y, row in enumerate(grid):
        for x, (ch, rgb) in enumerate(row):
            mask = stamps.get(ch)
            if mask is None:
                continue
            fill = tuple(rgb) if color else (255, 255, 255)
            d.bitmap((x * cell_w - pad, y * cell_h - pad), mask, fill=fill)
    return img


def verified_grid_renderer(
    font: ImageFont.FreeTypeFont,
    cell_w: int,
    cell_h: int,
    chars: str,
) -> object:
    """Fast grid renderer, verified pixel-identical for this font.

    Builds padded glyph stamps (growing margins) and checks one probe
    grid containing every character against reference per-cell
    ``text()``; returns the fast renderer only if identical, else a
    closure over the slow reference path. The returned callable takes
    ``(grid, color)``.
    """
    chars = chars or " "
    probe = [[(ch, (200, 100, 50)) for ch in chars[i : i + 64]] for i in range(0, len(chars), 64)]

    def render_slow(grid: Grid, color: bool) -> Image.Image:
        return grid_to_image(grid, color, font, cell_w, cell_h)

    ref = grid_to_image(probe, True, font, cell_w, cell_h)
    for pad in (4, 8, 16):
        stamps = _padded_stamps(font, cell_w, cell_h, chars, pad)
        fast = _grid_to_image_stamped(probe, True, cell_w, cell_h, stamps, pad)
        if ref.tobytes() == fast.tobytes():
            def render_fast(grid: Grid, color: bool, _s: object = stamps, _p: int = pad) -> Image.Image:
                return _grid_to_image_stamped(grid, color, cell_w, cell_h, _s, _p)  # type: ignore[arg-type]

            return render_fast
    return render_slow


def grid_to_image(
    grid: Grid,
    color: bool,
    font: ImageFont.FreeTypeFont,
    cell_w: int,
    cell_h: int,
    bg: tuple[int, int, int] = (0, 0, 0),
    fg: tuple[int, int, int] = (255, 255, 255),
) -> Image.Image:
    """Rasterize a single text grid on the fixed ``cell_w`` x ``cell_h`` grid."""
    cols = len(grid[0])
    rows = len(grid)
    img = Image.new("RGB", (cols * cell_w, rows * cell_h), bg)
    d = ImageDraw.Draw(img)
    for y, row in enumerate(grid):
        for x, (ch, rgb) in enumerate(row):
            fill = tuple(rgb) if color else fg
            d.text((x * cell_w, y * cell_h), ch, font=font, fill=fill)
    return img


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
