"""Export animation frames to a directory of text files + manifest."""

from __future__ import annotations

import json
from pathlib import Path

from .renderer import Grid, render


def export_frame_dir(
    grids: list[Grid],
    out_dir: str | Path,
    color: bool,
    fps: float,
    loop: int,
    durations_ms: list[int] | None = None,
) -> list[Path]:
    """Write one text file per frame plus meta.json.

    Returns list of frame file paths written.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    ext = ".ansi" if color else ".txt"
    written: list[Path] = []
    for i, grid in enumerate(grids):
        fp = out / f"frame_{i:04d}{ext}"
        fp.write_text(render(grid, color=color), encoding="utf-8")
        written.append(fp)

    write_anim_meta(
        out,
        frames=len(grids),
        fps=fps,
        loop=loop,
        color=color,
        width_chars=len(grids[0][0]) if grids and grids[0] else 0,
        height_chars=len(grids[0]) if grids else 0,
        durations_ms=durations_ms,
        extension=ext,
    )
    return written


def frame_filename(out_dir: Path, index: int, color: bool) -> Path:
    """Path for the i-th streaming frame file (matches export_frame_dir)."""
    ext = ".ansi" if color else ".txt"
    return out_dir / f"frame_{index:04d}{ext}"


def write_anim_meta(
    out_dir: str | Path,
    *,
    frames: int,
    fps: float,
    loop: int,
    color: bool,
    width_chars: int,
    height_chars: int,
    durations_ms: list[int] | None = None,
    extension: str,
) -> Path:
    """Write meta.json for a frame directory (streaming-friendly)."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    meta = {
        "frames": frames,
        "fps": fps,
        "loop": loop,
        "color": color,
        "width_chars": width_chars,
        "height_chars": height_chars,
        "extension": extension,
    }
    if durations_ms is not None:
        meta["durations_ms"] = durations_ms
    fp = out / "meta.json"
    fp.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return fp
