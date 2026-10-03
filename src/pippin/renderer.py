"""Render a char/color grid to plain text or ANSI truecolor."""

from __future__ import annotations

Cell = tuple[str, tuple[int, int, int]]
Grid = list[list[Cell]]


def to_plain(grid: Grid) -> str:
    """Render without color escapes."""
    return "\n".join("".join(ch for ch, _ in row) for row in grid) + "\n"


def to_ansi(grid: Grid) -> str:
    """Render with per-character foreground truecolor + reset per line.

    Format per cell: \\x1b[38;2;R;G;Bm<char>. Each line ends with \\x1b[0m
    so exported .ansi files don't leak color.
    """
    lines: list[str] = []
    for row in grid:
        parts = [f"\x1b[38;2;{r};{g};{b}m{ch}" for ch, (r, g, b) in row]
        lines.append("".join(parts) + "\x1b[0m")
    return "\n".join(lines) + "\n"


def render(grid: Grid, color: bool) -> str:
    return to_ansi(grid) if color else to_plain(grid)
