"""CLI: pippin INPUT [options] — preview and/or export ascii/utf8 art."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .anim_export import export_frame_dir
from .charsets import CHARSETS, get_ramp
from .converter import ConvertOptions, convert
from .gif import load_gif, resolve_durations
from .image_loader import load_image
from .player import play_frames
from .renderer import render
from .text_gif import grids_to_images, resolve_font, save_text_gif


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pippin",
        description="Render png/jpeg/svg images (or animated gif with --animate) as high-resolution ascii/utf8 art.",
    )
    p.add_argument("input", help="Input image path (png, jpg/jpeg, svg, gif)")
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
    p.add_argument("--preview", dest="preview", action="store_true", help="Print to stdout / play animation (default)")
    p.add_argument("--no-preview", dest="preview", action="store_false", help="Suppress stdout preview")
    p.add_argument("-o", "--export", default=None, help="Write rendering to file (still: out.ansi/out.txt; --animate: frame dir or out.gif)")
    p.add_argument("--invert", action="store_true", help="Invert luminance ramp")
    p.add_argument("--contrast", type=float, default=1.0, help="Contrast factor (default: 1.0)")
    p.add_argument("--brightness", type=float, default=1.0, help="Brightness factor (default: 1.0)")
    p.add_argument(
        "--aspect",
        type=float,
        default=0.55,
        help="Terminal cell height correction (default: 0.55)",
    )
    p.add_argument("--animate", action="store_true", help="GIF animation mode: render all frames as text frames")
    p.add_argument("--fps", type=float, default=12.0, help="Uniform playback/encode rate for --animate (default: 12)")
    p.add_argument("--native-timing", action="store_true", help="With --animate, preserve source per-frame durations instead of uniform --fps")
    p.add_argument("--max-frames", type=int, default=None, help="With --animate, cap frames kept after sampling (default: all)")
    p.add_argument("--sample", type=int, default=1, help="With --animate, keep every Nth frame (default: 1)")
    p.add_argument("--loop", type=int, default=None, help="Animation plays / GIF loop count, 0=infinite (default: infinite preview, source loop for out.gif)")
    p.add_argument("--gif-font", default=None, help="TTF/OTF path for --animate out.gif rasterization (default: system monospace)")
    p.add_argument("--gif-font-size", type=int, default=20, help="Font size for --animate out.gif rasterization (default: 20)")
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
    if args.animate:
        return _main_animated(args)

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


def _main_animated(args: argparse.Namespace) -> int:
    if args.fps <= 0 or args.fps > 60:
        print("error: --fps must be 0 < fps <= 60", file=sys.stderr)
        return 2
    if args.sample < 1:
        print("error: --sample must be >= 1", file=sys.stderr)
        return 2
    if args.max_frames is not None and args.max_frames < 1:
        print("error: --max-frames must be >= 1", file=sys.stderr)
        return 2
    if args.loop is not None and args.loop < 0:
        print("error: --loop must be >= 0 (0=infinite)", file=sys.stderr)
        return 2
    if args.gif_font_size < 8 or args.gif_font_size > 72:
        print("error: --gif-font-size must be 8..72", file=sys.stderr)
        return 2

    try:
        ramp = get_ramp(args.charset, custom=args.custom_chars, invert=args.invert)
        data = load_gif(args.input, max_frames=args.max_frames, sample=args.sample)
        opts = ConvertOptions(width=args.width, height=args.height, aspect=args.aspect, contrast=args.contrast, brightness=args.brightness)
        grids = [convert(frame, ramp, opts) for frame in data.frames]
        durations = resolve_durations(data, args.fps, args.native_timing)
        texts = [render(g, color=args.color) for g in grids]
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except (ValueError, ImportError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    if args.export:
        out = Path(args.export)
        export_loop = args.loop if args.loop is not None else data.loop
        try:
            if out.suffix.lower() == ".gif":
                # Self-playing export: rasterize text frames back to an animated GIF.
                font = resolve_font(args.gif_font, args.gif_font_size)
                images = grids_to_images(grids, color=args.color, font=font)
                save_text_gif(images, out, fps=args.fps, loop=export_loop, durations_ms=durations if args.native_timing else None)
            else:
                export_frame_dir(grids, out, color=args.color, fps=args.fps, loop=export_loop, durations_ms=durations)
        except (ValueError, OSError) as e:
            print(f"error: {e}", file=sys.stderr)
            return 1

    if args.preview:
        if len(texts) == 1:
            sys.stdout.write(texts[0])
        else:
            preview_loop = args.loop if args.loop is not None else 0
            play_frames(texts, fps=args.fps, loop=preview_loop, durations_ms=durations if args.native_timing else None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
