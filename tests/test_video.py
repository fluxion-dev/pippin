from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from pippin.charsets import get_ramp
from pippin.cli import main
from pippin.converter import ConvertOptions, convert
from pippin.text_gif import font_cell, grid_to_image, grids_to_images, resolve_font
from pippin.video import (
    VideoEncoder,
    estimate_kept_frames,
    is_video_output_suffix,
    is_video_suffix,
    iter_video_frames,
    load_video,
    mux_audio,
    probe_video,
    resolve_job_count,
    resolve_video_fps,
    save_text_video,
    select_video_encoder,
)

needs_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None, reason="ffmpeg binary not on PATH"
)


def _frames(n: int = 4) -> list[Image.Image]:
    out = []
    for i in range(n):
        im = Image.new("RGB", (64, 32), [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)][i % 4])
        d = ImageDraw.Draw(im)
        d.rectangle([5 + i * 8, 5, 20 + i * 8, 20], fill=(255, 255, 255))
        out.append(im)
    return out


def _make_video(path: Path, fps: int = 12, with_audio: bool = False) -> Path:
    """Encode solid test frames with ffmpeg (no dependency on pippin itself)."""
    pngs = _frames()
    for i, im in enumerate(pngs):
        im.save(path.parent / f"src_{i:02d}.png")
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-framerate",
        str(fps),
        "-i",
        str(path.parent / "src_%02d.png"),
    ]
    if with_audio:
        cmd += ["-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-shortest"]
    cmd += ["-pix_fmt", "yuv420p", "-c:v", "libopenh264" if path.suffix == ".mp4" else "mpeg2video"]
    if with_audio:
        cmd += ["-c:a", "aac"]
    cmd += [str(path)]
    subprocess.run(cmd, check=True)
    return path


def _stream_types(path: Path) -> set[str]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return {line.strip() for line in out.stdout.splitlines() if line.strip()}


def _count_frames(path: Path) -> int:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-count_frames",
         "-show_entries", "stream=nb_read_frames", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return int(out.stdout.strip().splitlines()[0])


def _dims(path: Path) -> tuple[int, int]:
    out = subprocess.run(
        ["ffprobe", "-v", "error",
         "-show_entries", "stream=width,height", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    w, h = (int(x) for x in out.stdout.strip().splitlines()[:2])
    return w, h


def test_suffix_helpers():
    assert is_video_suffix(".mp4") and is_video_suffix(".MPEG")
    assert not is_video_suffix(".gif")
    assert is_video_output_suffix(".mpeg") and is_video_output_suffix(".mp4")
    assert not is_video_output_suffix(".gif")


@needs_ffmpeg
def test_probe_and_load_video(tmp_path):
    src = _make_video(tmp_path / "in.mp4", fps=12)
    meta = probe_video(src)
    assert meta["width"] == 64 and meta["height"] == 32
    assert meta["fps"] == pytest.approx(12.0)
    assert not meta["has_audio"]
    data = load_video(src)
    assert len(data.frames) == 4
    assert data.fps == pytest.approx(12.0)
    assert all(f.mode == "RGB" for f in data.frames)
    assert resolve_video_fps(data, 10, False) == 10
    assert resolve_video_fps(data, 10, True) == pytest.approx(12.0)


@needs_ffmpeg
def test_load_video_sample_and_max_frames(tmp_path):
    src = _make_video(tmp_path / "in.mp4")
    assert len(load_video(src, sample=2).frames) == 2
    assert len(load_video(src, max_frames=2).frames) == 2


@needs_ffmpeg
def test_video_frame_texts_differ(tmp_path):
    src = _make_video(tmp_path / "in.mp4")
    data = load_video(src)
    grids = [convert(f, get_ramp("ascii"), ConvertOptions(width=20, height=6)) for f in data.frames]
    assert len({tuple("".join(ch for ch, _ in row) for row in g) for g in grids}) > 1


@needs_ffmpeg
def test_save_text_video_mp4_frame_for_frame(tmp_path):
    src = _make_video(tmp_path / "in.mp4")
    data = load_video(src)
    grids = [convert(f, get_ramp("ascii"), ConvertOptions(width=20, height=6)) for f in data.frames]
    images = grids_to_images(grids, color=False)
    out = tmp_path / "out.mp4"
    save_text_video(images, out, fps=12)
    assert _count_frames(out) == len(images)


@needs_ffmpeg
def test_save_text_video_mpeg_frame_for_frame(tmp_path):
    src = _make_video(tmp_path / "in.mp4")
    data = load_video(src)
    grids = [convert(f, get_ramp("ascii"), ConvertOptions(width=20, height=6)) for f in data.frames]
    images = grids_to_images(grids, color=False)
    out = tmp_path / "out.mpeg"
    save_text_video(images, out, fps=12)
    assert _count_frames(out) == len(images)


@needs_ffmpeg
def test_mpeg_to_mpeg_roundtrip_native_timing(tmp_path):
    src = _make_video(tmp_path / "in.mpeg", fps=25)
    rc = main([str(src), "--animate", "--width", "20", "--no-color",
               "--native-timing", "--no-preview", "-o", str(tmp_path / "out.mpeg")])
    assert rc == 0
    assert _count_frames(tmp_path / "out.mpeg") == 4


@needs_ffmpeg
def test_cli_mp4_to_mp4_and_audio_preserved(tmp_path):
    src = _make_video(tmp_path / "in.mp4", with_audio=True)
    assert "audio" in _stream_types(src)
    rc = main([str(src), "--animate", "--width", "20", "--no-color",
               "--fps", "12", "--no-preview", "-o", str(tmp_path / "out.mp4")])
    assert rc == 0
    assert _count_frames(tmp_path / "out.mp4") == 4
    assert _stream_types(tmp_path / "out.mp4") == {"video", "audio"}
    # Opt-out drops audio.
    rc = main([str(src), "--animate", "--width", "20", "--no-color",
               "--fps", "12", "--no-preview", "--no-audio", "-o", str(tmp_path / "silent.mp4")])
    assert rc == 0
    assert _stream_types(tmp_path / "silent.mp4") == {"video"}


@needs_ffmpeg
def test_cli_rejects_non_animation_input(tmp_path):
    png = tmp_path / "x.png"
    Image.new("RGB", (10, 10), (0, 0, 0)).save(png)
    assert main([str(png), "--animate", "--no-preview", "-o", str(tmp_path / "o")]) == 1


@needs_ffmpeg
def test_iter_video_frames_matches_load(tmp_path):
    src = _make_video(tmp_path / "in.mp4")
    eager = load_video(src)
    streamed = list(iter_video_frames(src))
    assert len(streamed) == len(eager.frames) == 4
    assert all(a.tobytes() == b.tobytes() for a, b in zip(streamed, eager.frames))
    assert [f.size for f in iter_video_frames(src, sample=2)] == [eager.frames[0].size] * 2
    assert len(list(iter_video_frames(src, max_frames=1))) == 1


@needs_ffmpeg
def test_video_encoder_streaming_roundtrip(tmp_path):
    src = _make_video(tmp_path / "in.mp4")
    data = load_video(src)
    grids = [convert(f, get_ramp("ascii"), ConvertOptions(width=20, height=6)) for f in data.frames]
    font = resolve_font(None, 20)
    cell = font_cell(font, get_ramp("ascii"))
    out = tmp_path / "stream.mp4"
    enc = VideoEncoder(out, 12, grid_to_image(grids[0], False, font, *cell).size)
    with enc:
        for g in grids:
            enc.write(grid_to_image(g, False, font, *cell))
    assert enc.frames_written == 4
    assert _count_frames(out) == 4


@needs_ffmpeg
def test_mux_audio_stream_copy(tmp_path):
    src = _make_video(tmp_path / "in.mp4", with_audio=True)
    data = load_video(src)
    grids = [convert(f, get_ramp("ascii"), ConvertOptions(width=20, height=6)) for f in data.frames]
    images = grids_to_images(grids, color=False)
    silent = tmp_path / "silent.mp4"
    save_text_video(images, silent, fps=12, keep_audio=False)
    out = tmp_path / "muxed.mp4"
    mux_audio(silent, src, out, len(images) / 12)
    assert _count_frames(out) == len(images)
    assert _stream_types(out) == {"video", "audio"}


@needs_ffmpeg
def test_cli_streams_frame_dir_without_buffering_all_grids(tmp_path):
    src = _make_video(tmp_path / "in.mp4")
    rc = main([str(src), "--animate", "--width", "20", "--no-color",
               "--fps", "12", "--no-preview", "-o", str(tmp_path / "frames")])
    assert rc == 0
    assert len(list((tmp_path / "frames").glob("frame_*.txt"))) == 4
    import json
    meta = json.loads((tmp_path / "frames" / "meta.json").read_text())
    assert meta["frames"] == 4 and meta["fps"] == 12


def test_select_software_encoder_when_gpu_off():
    vcodec, _pre, vf, _pix, kind = select_video_encoder(".mp4", 320, 240, 12, gpu=False)
    assert kind == "software"
    assert vcodec == "mpeg4"
    assert vf == ["scale=trunc(iw/2)*2:trunc(ih/2)*2"]


def test_select_falls_back_when_gpu_probe_fails(monkeypatch):
    import pippin.video as video_mod

    monkeypatch.setattr(video_mod, "_probe_gpu_encoder", lambda *a: False)
    vcodec, _pre, _vf, _pix, kind = select_video_encoder(".mp4", 320, 240, 12, gpu=True)
    assert kind == "software"


def test_select_uses_gpu_encoder_when_probe_passes(monkeypatch):
    import pippin.video as video_mod

    monkeypatch.setattr(video_mod, "_available_encoders",
                        lambda: {"h264_nvenc", "libopenh264"})
    monkeypatch.setattr(video_mod, "_probe_gpu_encoder", lambda *a: True)
    vcodec, _pre, _vf, _pix, kind = select_video_encoder(".mp4", 320, 240, 12, gpu=True)
    assert (vcodec, kind) == ("h264_nvenc", "gpu")


@needs_ffmpeg
def test_cli_no_gpu_flag_still_encodes(tmp_path):
    src = _make_video(tmp_path / "in.mp4")
    rc = main([str(src), "--animate", "--width", "20", "--no-color",
               "--fps", "12", "--no-preview", "--no-gpu", "-o", str(tmp_path / "out.mp4")])
    assert rc == 0
    assert _count_frames(tmp_path / "out.mp4") == 4


@needs_ffmpeg
def test_cli_preset_portrait_produces_vertical_video(tmp_path):
    src = _make_video(tmp_path / "in.mp4")  # 64x32 landscape source
    rc = main([str(src), "--animate", "--preset", "portrait", "--no-color",
               "--fps", "12", "--max-frames", "2",
               "--no-preview", "-o", str(tmp_path / "out.mp4")])
    assert rc == 0
    w, h = _dims(tmp_path / "out.mp4")
    assert h > w  # center-cropped 9:16, not stretched landscape


@needs_ffmpeg
def test_cli_preset_landscape_produces_horizontal_video(tmp_path):
    src = _make_video(tmp_path / "in.mp4")
    rc = main([str(src), "--animate", "--preset", "landscape", "--no-color",
               "--fps", "12", "--max-frames", "2",
               "--no-preview", "-o", str(tmp_path / "out.mp4")])
    assert rc == 0
    w, h = _dims(tmp_path / "out.mp4")
    assert w > h


@needs_ffmpeg
def test_cli_preset_width_override_and_no_crop(tmp_path):
    src = _make_video(tmp_path / "in.mp4")
    rc = main([str(src), "--animate", "--preset", "portrait", "--width", "30", "--no-color",
               "--no-preview", "-o", str(tmp_path / "frames")])
    assert rc == 0
    import json
    meta = json.loads((tmp_path / "frames" / "meta.json").read_text())
    assert meta["width_chars"] == 30  # explicit --width beats preset default (60)
    assert meta["height_chars"] > 17  # cropped tall grid, not stretched 30x17

    rc = main([str(src), "--animate", "--preset", "portrait", "--no-crop", "--no-color",
               "--no-preview", "-o", str(tmp_path / "stretched")])
    assert rc == 0
    meta = json.loads((tmp_path / "stretched" / "meta.json").read_text())
    assert meta["height_chars"] == 16  # 64x32 stretched to 60 cols, no crop


@needs_ffmpeg
def test_cli_quality_scales_video_grid(tmp_path):
    src = _make_video(tmp_path / "in.mp4")
    import json
    for quality, cols in (("low", 12), ("medium", 20), ("high", 32)):
        rc = main([str(src), "--animate", "--width", "20", "--no-color",
                   "--quality", quality, "--no-preview", "-o", str(tmp_path / f"frames_{quality}")])
        assert rc == 0
        meta = json.loads((tmp_path / f"frames_{quality}" / "meta.json").read_text())
        assert meta["width_chars"] == cols


@needs_ffmpeg
def test_cli_preset_and_quality_compose(tmp_path):
    src = _make_video(tmp_path / "in.mp4")
    import json
    rc = main([str(src), "--animate", "--preset", "portrait", "--quality", "high",
               "--no-color", "--no-preview", "-o", str(tmp_path / "frames")])
    assert rc == 0
    meta = json.loads((tmp_path / "frames" / "meta.json").read_text())
    assert meta["width_chars"] == 96  # portrait base 60 x high 1.6


def test_resolve_job_count():
    import pytest as _pytest

    assert resolve_job_count(1, 5865) == 1  # explicit serial
    assert resolve_job_count(4, 4) == 4  # explicit pool, even for tiny clips
    assert resolve_job_count(0, 5865) >= 2  # auto: long clip -> pool
    assert resolve_job_count(0, 4) == 1  # auto: short clip -> serial
    assert resolve_job_count(0, None) == 1  # auto: unknown length -> serial
    with _pytest.raises(ValueError):
        resolve_job_count(-1, 100)


def test_estimate_kept_frames():
    assert estimate_kept_frames({"nb_frames": 100}, sample=2) == 50
    assert estimate_kept_frames({"nb_frames": 100}, sample=2, max_frames=10) == 10
    assert estimate_kept_frames({"nb_frames": 0}) is None
    assert estimate_kept_frames({}) is None


@needs_ffmpeg
def test_pool_matches_serial_output(tmp_path):
    src = _make_video(tmp_path / "in.mp4")
    base = [str(src), "--animate", "--width", "20", "--no-color",
            "--fps", "12", "--no-preview"]
    assert main(base + ["-o", str(tmp_path / "serial")]) == 0
    assert main(base + ["--jobs", "4", "-o", str(tmp_path / "pooled")]) == 0
    for i in range(4):
        a = (tmp_path / "serial" / f"frame_{i:04d}.txt").read_text()
        b = (tmp_path / "pooled" / f"frame_{i:04d}.txt").read_text()
        assert a == b


@needs_ffmpeg
def test_duplicate_frames_reuse_render(tmp_path):
    import subprocess

    red = Image.new("RGB", (64, 32), (255, 0, 0))
    blue = Image.new("RGB", (64, 32), (0, 0, 255))
    for i, im in enumerate([red, blue, red, blue, red, blue]):
        im.save(tmp_path / f"dup_{i:02d}.png")
    src = tmp_path / "dup.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-framerate", "12", "-i", str(tmp_path / "dup_%02d.png"),
         "-pix_fmt", "yuv420p", "-c:v", "libopenh264", str(src)],
        check=True,
    )
    rc = main([str(src), "--animate", "--width", "20", "--no-color",
               "--fps", "12", "--no-preview", "-o", str(tmp_path / "frames")])
    assert rc == 0
    texts = [(tmp_path / "frames" / f"frame_{i:04d}.txt").read_text() for i in range(6)]
    assert texts[0] == texts[2] == texts[4]
    assert texts[1] == texts[3] == texts[5]
    assert texts[0] != texts[1]


@needs_ffmpeg
def test_jobs_validation(tmp_path):
    src = _make_video(tmp_path / "in.mp4")
    assert main([str(src), "--animate", "--jobs", "-1",
                 "--no-preview", "-o", str(tmp_path / "o")]) == 2
