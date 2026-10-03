"""CLI: pippin INPUT [options] — preview and/or export ascii/utf8 art."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .charsets import CHARSETS, get_ramp
from .converter import ConvertOptions, convert
from .image_loader import load_image
from .renderer import render


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pippin",
        description="Render png/jpeg/svg images as high-resolution ascii/utf8 art.",
    )
    p.add_argument("input", help="Input image path (png, jpg/jpeg, svg)")
    p.add_argument("-w", "--width", type=int, default=100, help="Output width in chars (default: 100)")
    p.add_argument("-H", "--height", type=int, default=None, help="Output height in chars (default: auto)")
    p.add_argument(
        "--charset",
        choices=sorted(CHARSETS),
        default="utf8",
        help="Character ramp: ascii (7-bit), utf8 (70 levels), blocks (default: utf8)",
    )
    p.add_argument("--custom-chars", default=None, help="Custom dark->light ramp, overrides --charset")
    p.add_argument("--color", dest="color", action="store_true", help="ANSI truecolor output (default)")
    p.add_argument("--no-color", dest="color", action="store_false", help="Plain text output")
    p.add_argument("--preview", dest="preview", action="store_true", help="Print to stdout (default)")
    p.add_argument("--no-preview", dest="preview", action="store_false", help="Suppress stdout preview")
    p.add_argument("-o", "--export", default=None, help="Write rendering to file (e.g. out.ansi, out.txt)")
    p.add_argument("--invert", action="store_true", help="Invert luminance ramp")
    p.add_argument("--contrast", type=float, default=1.0, help="Contrast factor (default: 1.0)")
    p.add_argument("--brightness", type=float, default=1.0, help="Brightness factor (default: 1.0)")
    p.add_argument(
        "--aspect",
        type=float,
        default=0.55,
        help="Terminal cell height correction (default: 0.55)",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.set_defaults(color=True, preview=True)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.width < 1 or args.width > 2000:
        print("error: --width must be 1..2000", file=sys.stderr)
        return 2
    if args.height is not None and not 1 <= args.height <= 2000:
        print("error: --height must be 1..2000", file=sys.stderr)
        return 2
    if not args.preview and not args.export:
        print("error: nothing to do (both --no-preview and no --export given)", file=sys.stderr)
        return 2

    try:
        ramp = get_ramp(args.charset, custom=args.custom_chars, invert=args.invert)
        img = load_image(args.input)
        grid = convert(img, ramp, ConvertOptions(width=args.width, height=args.height, aspect=args.aspect, contrast=args.contrast, brightness=args.brightness))
        text = render(grid, color=args.color)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except (ValueError, ImportError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    if args.export:
        out = Path(args.export)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")

    if args.preview:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
