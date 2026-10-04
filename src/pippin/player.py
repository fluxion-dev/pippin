"""Terminal playback of pre-rendered text frames at uniform fps."""

from __future__ import annotations

import sys
import time

_HIDE = "\x1b[?25l"
_SHOW = "\x1b[?25h"
_HOME = "\x1b[H"


def play_frames(
    texts: list[str],
    fps: float,
    loop: int = 0,
    stream=None,
    durations_ms: list[int] | None = None,
) -> None:
    """Play text frames in-place.

    Args:
        texts: rendered frames (each ends with newline, may contain ANSI).
        fps: uniform playback rate (ignored when durations_ms given).
        loop: total plays (0 = infinite until Ctrl-C).
        stream: file-like (defaults to sys.stdout).
        durations_ms: optional per-frame delays (for --native-timing).
    """
    if not texts:
        return
    if durations_ms is None:
        if fps <= 0:
            raise ValueError("--fps must be > 0")
        delays = [1.0 / fps] * len(texts)
    else:
        delays = [max(0.001, d / 1000.0) for d in durations_ms]
    out = stream if stream is not None else sys.stdout

    # Number of terminal lines per frame (for cursor-up redraw).
    nlines = texts[0].count("\n")

    out.write(_HIDE)
    out.flush()
    try:
        plays = 0
        first = True
        while True:
            for idx, text in enumerate(texts):
                if not first:
                    # Move cursor up so the next frame overwrites the last.
                    out.write(f"\x1b[{nlines}A")
                out.write(text)
                out.flush()
                first = False
                time.sleep(delays[idx])
            plays += 1
            if loop != 0 and plays >= loop:
                break
    except KeyboardInterrupt:
        pass
    finally:
        out.write(_SHOW)
        out.flush()
