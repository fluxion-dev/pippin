"""GIF animation loading: extract full-canvas RGB frames + timing."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image


@dataclass
class GifData:
    frames: list[Image.Image]  # RGB, all same size (GIF logical canvas)
    durations_ms: list[int]  # per-frame duration
    loop: int = 0  # 0 = infinite (GIF NETSCAPE semantics)
    size: tuple[int, int] = (0, 0)


def load_gif(
    path: str | Path,
    max_frames: int | None = None,
    sample: int = 1,
) -> GifData:
    """Load an animated GIF into full-canvas RGB frames.

    Args:
        path: input .gif path.
        max_frames: cap on frames kept *after* sampling (None = all).
        sample: keep every Nth frame (stride >= 1).

    Pillow's ``seek()`` already composites partial/delta frames onto the
    full canvas for standard GIFs, so ``frame.copy()`` after each seek
    gives a complete frame. Each frame is composited onto black for
    predictable luminance (same rule as stills in image_loader._to_rgb).
    """
    from .image_loader import _to_rgb

    if sample < 1:
        raise ValueError("--sample must be >= 1")
    if max_frames is not None and max_frames < 1:
        raise ValueError("--max-frames must be >= 1")

    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"input file not found: {p}")
    if p.suffix.lower() != ".gif":
        raise ValueError(f"--animate requires a .gif input, got {p.suffix!r}")

    img = Image.open(p)
    if not getattr(img, "is_animated", False):
        # Static GIF (or single frame): treat as 1-frame animation.
        rgb = _to_rgb(img.copy())
        return GifData(frames=[rgb], durations_ms=[100], loop=0, size=rgb.size)

    n = getattr(img, "n_frames", 1)
    loop = int(img.info.get("loop", 0))

    frames: list[Image.Image] = []
    durations: list[int] = []
    for i in range(n):
        if i % sample != 0:
            continue
        img.seek(i)
        durations.append(int(img.info.get("duration", 100) or 100))
        frames.append(_to_rgb(img.copy()))
        if max_frames is not None and len(frames) >= max_frames:
            break

    if not frames:
        raise ValueError("gif contains no frames")
    size = frames[0].size
    return GifData(frames=frames, durations_ms=durations, loop=loop, size=size)


def uniform_durations(n: int, fps: float) -> list[int]:
    """Per-frame durations (ms) for a uniform frame rate."""
    if fps <= 0:
        raise ValueError("--fps must be > 0")
    ms = max(1, round(1000.0 / fps))
    return [ms] * n


def resolve_durations(data: GifData, fps: float, native_timing: bool) -> list[int]:
    """Uniform --fps by default; --native-timing preserves source durations."""
    if native_timing:
        return list(data.durations_ms)
    return uniform_durations(len(data.frames), fps)
