"""CLI: pippin INPUT [options] — preview and/or export ascii/utf8 art."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

from . import __version__
from .anim_export import export_frame_dir, write_anim_meta
from .charsets import CHARSETS, get_ramp
from .converter import ConvertOptions, convert
from .gif import load_gif, resolve_durations
from .image_loader import load_image
from .player import play_frames
from .renderer import render
from .text_gif import font_cell, grids_to_images, resolve_font, save_text_gif, verified_grid_renderer
from .video import (
    VIDEO_INPUT_SUFFIXES,
    VideoData,
    VideoEncoder,
    _worker_init,
    estimate_kept_frames,
    is_video_output_suffix,
    is_video_suffix,
    iter_video_frames,
    load_video,
    mux_audio,
    probe_video,
    render_frame_task,
    resolve_job_count,
    resolve_source_fps,
    resolve_video_fps,
    save_text_video,
    select_video_encoder,
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pippin",
        description="Render png/jpeg/svg images (or gif/video with --animate) as high-resolution ascii/utf8 art.",
    )
    p.add_argument("input", help="Input image path (png, jpg/jpeg, svg, gif) or animation path with --animate (gif, mp4/mpeg/mov/avi/mkv/webm)")
    p.add_argument("-w", "--width", type=int, default=None, help="Base output width in chars at medium quality (default: 100, or the --preset default; scaled by --quality)")
    p.add_argument("-H", "--height", type=int, default=None, help="Output height in chars (default: auto)")
    p.add_argument(
        "--preset",
        choices=("landscape", "portrait"),
        default=None,
        help="One-flag aspect recipe: landscape (16:9, long-form) or portrait (9:16, shorts). Sets width default + center-crops to the aspect; explicit --width/--height still override",
    )
    p.add_argument("--crop", dest="crop", action="store_true", help="Center-crop to the --preset aspect (default with --preset)")
    p.add_argument("--no-crop", dest="crop", action="store_false", help="Stretch to fit instead of center-cropping")
    p.add_argument(
        "--quality",
        choices=("low", "medium", "high"),
        default="medium",
        help="Render quality: grid-size multiplier on the width (low 0.6x, medium 1x, high 1.6x)",
    )
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
    p.add_argument("-o", "--export", default=None, help="Write rendering to file (still: out.ansi/out.txt; --animate: frame dir, out.gif, or video out.mp4/out.mpeg)")
    p.add_argument("--invert", action="store_true", help="Invert luminance ramp")
    p.add_argument("--contrast", type=float, default=1.0, help="Contrast factor (default: 1.0)")
    p.add_argument("--brightness", type=float, default=1.0, help="Brightness factor (default: 1.0)")
    p.add_argument(
        "--aspect",
        type=float,
        default=0.55,
        help="Terminal cell height correction (default: 0.55)",
    )
    p.add_argument("--animate", action="store_true", help="Animation mode: render all frames as text frames (gif or video input)")
    p.add_argument("--fps", type=float, default=12.0, help="Uniform playback/encode rate for --animate (default: 12)")
    p.add_argument("--native-timing", action="store_true", help="With --animate, preserve source timing (gif durations / video fps) instead of uniform --fps")
    p.add_argument("--max-frames", type=int, default=None, help="With --animate, cap frames kept after sampling (default: all)")
    p.add_argument("--sample", type=int, default=1, help="With --animate, keep every Nth frame (default: 1)")
    p.add_argument("--loop", type=int, default=None, help="Animation plays / GIF loop count, 0=infinite (default: infinite preview, source loop for out.gif; ignored for video output)")
    p.add_argument("--gif-font", default=None, help="TTF/OTF path for --animate out.gif / video rasterization (default: system monospace)")
    p.add_argument("--gif-font-size", type=int, default=20, help="Font size for --animate out.gif / video rasterization (default: 20)")
    p.add_argument("--audio", dest="audio", action="store_true", help="Mux source audio into --animate video output (default)")
    p.add_argument("--no-audio", dest="audio", action="store_false", help="Drop audio in --animate video output")
    p.add_argument("--gpu", dest="gpu", action="store_true", help="Use GPU video encode/decode when a working backend exists (default)")
    p.add_argument("--no-gpu", dest="gpu", action="store_false", help="Force software video encode/decode")
    p.add_argument("--jobs", type=int, default=0, help="Parallel frame-render workers for --animate video (0=auto by clip length, 1=serial)")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.set_defaults(color=True, preview=True, audio=True, gpu=True, crop=True)
    return p


PRESETS: dict[str, dict] = {
    # One-flag recipes: char width default + center-crop aspect (W/H).
    "landscape": {"width": 100, "crop_aspect": 16 / 9},
    "portrait": {"width": 60, "crop_aspect": 9 / 16},
}

QUALITY_SCALES: dict[str, float] = {
    # Grid-size multiplier on the resolved base width (preset/--width/100).
    "low": 0.6,
    "medium": 1.0,
    "high": 1.6,
}


def resolve_width(args: argparse.Namespace) -> int:
    """Effective grid width: base (--width, else preset, else 100) × quality scale."""
    if args.width is not None:
        base = args.width
    elif args.preset is not None:
        base = PRESETS[args.preset]["width"]
    else:
        base = 100
    scale = QUALITY_SCALES.get(args.quality or "medium", 1.0)
    return max(1, round(base * scale))


def resolve_convert_options(args: argparse.Namespace) -> ConvertOptions:
    """Build ConvertOptions from CLI args + preset recipe.

    Presets only fill defaults: explicit --width/--height always win, and
    an explicit --height disables the preset crop (fixed grid = your call).
    """
    preset = PRESETS.get(args.preset) if args.preset else None
    crop_aspect = None
    if preset is not None and args.crop and args.height is None:
        crop_aspect = preset["crop_aspect"]
    return ConvertOptions(
        width=resolve_width(args),
        height=args.height,
        aspect=args.aspect,
        contrast=args.contrast,
        brightness=args.brightness,
        crop_aspect=crop_aspect,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    width = resolve_width(args)
    if width < 1 or width > 2000:
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
        grid = convert(img, ramp, resolve_convert_options(args))
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
    if args.jobs < 0:
        print("error: --jobs must be >= 0 (0=auto, 1=serial)", file=sys.stderr)
        return 2
    width = resolve_width(args)
    if width < 1 or width > 2000:
        print("error: --width must be 1..2000", file=sys.stderr)
        return 2

    in_suffix = Path(args.input).suffix.lower()
    is_gif = in_suffix == ".gif"
    is_video = is_video_suffix(in_suffix)
    if not is_gif and not is_video:
        print(
            f"error: --animate requires a .gif or video input ({sorted(['.gif'] + sorted(VIDEO_INPUT_SUFFIXES))}), got {in_suffix!r}",
            file=sys.stderr,
        )
        return 1

    try:
        ramp = get_ramp(args.charset, custom=args.custom_chars, invert=args.invert)
        opts = resolve_convert_options(args)
        if is_video:
            return _main_animated_video(args, ramp, opts)
        data = load_gif(args.input, max_frames=args.max_frames, sample=args.sample)
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
        out_suffix = out.suffix.lower()
        export_loop = args.loop if args.loop is not None else data.loop
        try:
            if out_suffix == ".gif":
                # Self-playing export: rasterize text frames back to an animated GIF.
                font = resolve_font(args.gif_font, args.gif_font_size)
                images = grids_to_images(grids, color=args.color, font=font)
                save_text_gif(images, out, fps=args.fps, loop=export_loop, durations_ms=durations if args.native_timing else None)
            elif is_video_output_suffix(out_suffix):
                font = resolve_font(args.gif_font, args.gif_font_size)
                images = grids_to_images(grids, color=args.color, font=font)
                save_text_video(images, out, fps=args.fps, src_audio_from=None, keep_audio=False, gpu=args.gpu)
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
            if args.native_timing:
                play_frames(texts, fps=args.fps, loop=preview_loop, durations_ms=durations)
            else:
                play_frames(texts, fps=args.fps, loop=preview_loop)
    return 0


def _main_animated_video(args: argparse.Namespace, ramp: str, opts: ConvertOptions) -> int:
    """Video input path: stream decode -> convert -> rasterize -> encode.

    Frames flow one at a time (never buffered), so RAM stays flat
    regardless of clip length or resolution. The only per-frame state
    retained is the preview text (when preview is on) plus one int per
    frame for durations.
    """
    import os
    import tempfile

    out = Path(args.export) if args.export else None
    out_suffix = out.suffix.lower() if out else ""
    want_gif = out is not None and out_suffix == ".gif"
    want_video = out is not None and is_video_output_suffix(out_suffix)
    want_dir = out is not None and not want_gif and not want_video

    tmp_silent: Path | None = None
    try:
        meta = probe_video(args.input)
        out_fps = resolve_source_fps(meta["fps"] or 25.0, args.fps, args.native_timing)
        per_ms = max(1, round(1000.0 / out_fps))

        if want_gif:
            # Rare path (video -> gif): needs all images up front anyway.
            vdata = load_video(args.input, max_frames=args.max_frames, sample=args.sample)
            grids = [convert(frame, ramp, opts) for frame in vdata.frames]
            durations = [per_ms] * len(grids)
            texts = [render(g, color=args.color) for g in grids]
            font = resolve_font(args.gif_font, args.gif_font_size)
            images = grids_to_images(grids, color=args.color, font=font)
            export_loop = args.loop if args.loop is not None else 0
            save_text_gif(images, out, fps=out_fps, loop=export_loop, durations_ms=durations if args.native_timing else None)
        else:
            font = resolve_font(args.gif_font, args.gif_font_size) if want_video else None
            cell = font_cell(font, ramp) if font is not None else None
            render_one = verified_grid_renderer(font, cell[0], cell[1], ramp) if font is not None and cell is not None else None
            ext = ".ansi" if args.color else ".txt"
            if want_dir:
                assert out is not None
                out.mkdir(parents=True, exist_ok=True)
            enc: VideoEncoder | None = None
            if want_video:
                assert out is not None
                with tempfile.NamedTemporaryFile(suffix=out.suffix, dir=str(out.parent), delete=False) as tf:
                    tmp_silent = Path(tf.name)
            texts = []
            durations = []
            n = 0
            width_chars = 0
            height_chars = 0
            # Duplicate-frame cache: static scenes reuse the previous render
            # instead of paying convert+rasterize again. Bounded (8 entries).
            render_cache: dict[bytes, dict] = {}
            cache_order: list[bytes] = []
            do_raster = want_video  # preview/dir only need text, skip images

            def emit(res: dict) -> None:
                nonlocal n, width_chars, height_chars, enc
                text = res["text"]
                if args.preview:
                    texts.append(text)
                durations.append(per_ms)
                if want_dir:
                    assert out is not None
                    (out / f"frame_{n:04d}{ext}").write_text(text, encoding="utf-8")
                if want_video:
                    assert tmp_silent is not None
                    data = res.get("img")
                    assert data is not None
                    if enc is None:
                        enc = VideoEncoder(tmp_silent, out_fps, tuple(res["img_size"]), gpu=args.gpu)
                        print(f"pippin: encoding with {enc.backend} ({'gpu' if enc.gpu else 'software'})", file=sys.stderr)
                    enc.write_bytes(bytes(data))
                if n == 0 and res.get("dims") is not None:
                    width_chars, height_chars = res["dims"]
                n += 1
                if n % 100 == 0:
                    print(f"pippin: {n} frames processed...", file=sys.stderr)

            def remember(digest: bytes, res: dict) -> None:
                img = res.get("img")
                entry = {"text": res["text"],
                         "img": img if isinstance(img, bytes) else (bytes(img) if img is not None else None),
                         "img_size": res.get("img_size"),
                         "dims": res.get("dims")}
                render_cache[digest] = entry
                cache_order.append(digest)
                if len(cache_order) > 8:
                    render_cache.pop(cache_order.pop(0), None)

            workers = resolve_job_count(
                args.jobs,
                estimate_kept_frames(meta, args.sample, args.max_frames),
            )
            pool = None
            try:
                if workers > 1:
                    import multiprocessing as mp
                    from concurrent.futures import ProcessPoolExecutor

                    print(f"pippin: rendering with {workers} workers...", file=sys.stderr)
                    pool = ProcessPoolExecutor(
                        max_workers=workers,
                        mp_context=mp.get_context("spawn"),
                        initializer=_worker_init,
                        initargs=(args.gif_font, args.gif_font_size),
                    )
                inflight: list[tuple[str, object]] = []  # ("hit", res) | ("fut", Future)

                def drain(blocking: bool) -> None:
                    while inflight and (
                        inflight[0][0] == "hit"
                        or blocking
                        or getattr(inflight[0][1], "done")()
                    ):
                        kind, payload = inflight.pop(0)
                        res = payload if kind == "hit" else payload.result()  # type: ignore[union-attr]
                        assert isinstance(res, dict)
                        if kind != "hit":
                            remember(res["digest"], res)
                        emit(res)

                for frame in iter_video_frames(args.input, max_frames=args.max_frames, sample=args.sample, gpu=args.gpu):
                    raw = frame.tobytes()
                    digest = hashlib.md5(raw).digest()
                    if digest in render_cache:
                        inflight.append(("hit", render_cache[digest]))
                    elif pool is not None:
                        w0, h0 = frame.size
                        inflight.append(("fut", pool.submit(render_frame_task, {
                            "index": n + len(inflight),
                            "digest": digest,
                            "raw": raw,
                            "size": (w0, h0),
                            "ramp": ramp,
                            "opts": opts,
                            "color": args.color,
                            "rasterize": do_raster,
                        })))
                    else:
                        grid = convert(frame, ramp, opts)
                        text = render(grid, color=args.color)
                        res = {"index": n + len(inflight), "digest": digest, "text": text,
                               "dims": (len(grid[0]), len(grid)),
                               "img": None, "img_size": None}
                        if do_raster:
                            assert render_one is not None
                            live = render_one(grid, args.color)
                            res["img"] = live.tobytes()
                            res["img_size"] = live.size
                        remember(digest, res)
                        inflight.append(("hit", render_cache[digest]))
                    drain(blocking=False)
                drain(blocking=True)
            except BaseException:
                if enc is not None:
                    enc.abort()
                if pool is not None:
                    pool.shutdown(wait=False, cancel_futures=True)
                    pool = None
                raise
            finally:
                if pool is not None:
                    pool.shutdown(wait=True)
            if want_dir:
                assert out is not None
                export_loop = args.loop if args.loop is not None else 0
                write_anim_meta(
                    out,
                    frames=n,
                    fps=out_fps,
                    loop=export_loop,
                    color=args.color,
                    width_chars=width_chars,
                    height_chars=height_chars,
                    durations_ms=durations,
                    extension=ext,
                )
            if want_video:
                assert out is not None and tmp_silent is not None and enc is not None
                count = enc.close()
                enc = None
                video_sec = count / out_fps
                if args.audio and meta.get("has_audio"):
                    try:
                        mux_audio(tmp_silent, args.input, out, video_sec)
                    except OSError as e:
                        print(f"warning: audio mux failed ({e}); writing silent video", file=sys.stderr)
                        os.replace(tmp_silent, out)
                else:
                    os.replace(tmp_silent, out)
                tmp_silent = None  # consumed by mux or replace
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except (ValueError, ImportError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    finally:
        if tmp_silent is not None and tmp_silent.exists():
            try:
                tmp_silent.unlink()
            except OSError:
                pass

    if args.preview:
        if len(texts) == 1:
            sys.stdout.write(texts[0])
        elif texts:
            preview_loop = args.loop if args.loop is not None else 0
            if args.native_timing:
                play_frames(texts, fps=out_fps, loop=preview_loop, durations_ms=durations)
            else:
                play_frames(texts, fps=out_fps, loop=preview_loop)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
