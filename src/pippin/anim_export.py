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

    meta = {
        "frames": len(grids),
        "fps": fps,
        "loop": loop,
        "color": color,
        "width_chars": len(grids[0][0]) if grids and grids[0] else 0,
        "height_chars": len(grids[0]) if grids else 0,
        "extension": ext,
    }
    if durations_ms is not None:
        meta["durations_ms"] = durations_ms
    (out / "meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return written
