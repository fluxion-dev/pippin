from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from pippin.anim_export import export_frame_dir
from pippin.charsets import get_ramp
from pippin.cli import main
from pippin.converter import ConvertOptions, convert
from pippin.gif import load_gif, resolve_durations
from pippin.text_gif import grids_to_images, save_text_gif


def _anim_gif(path: Path) -> Path:
    frames = []
    for i, col in enumerate([(255, 0, 0), (0, 255, 0), (0, 0, 255)]):
        im = Image.new("RGB", (60, 30), col)
        d = ImageDraw.Draw(im)
        d.rectangle([5 + i * 10, 5, 20 + i * 10, 20], fill=(255, 255, 255))
        frames.append(im)
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=[100, 200, 300], loop=0)
    return path


def test_load_gif_frames_and_timings(tmp_path):
    src = _anim_gif(tmp_path / "in.gif")
    data = load_gif(src)
    assert len(data.frames) == 3
    assert data.durations_ms == [100, 200, 300]
    assert all(f.mode == "RGB" for f in data.frames)
    assert resolve_durations(data, 12, False) == [83, 83, 83]
    assert resolve_durations(data, 12, True) == [100, 200, 300]


def test_load_gif_sample_and_max_frames(tmp_path):
    src = _anim_gif(tmp_path / "in.gif")
    assert len(load_gif(src, sample=2).frames) == 2
    assert len(load_gif(src, max_frames=2).frames) == 2


def test_load_gif_static_single_frame(tmp_path):
    src = tmp_path / "static.gif"
    Image.new("RGB", (20, 10), (1, 2, 3)).save(src)
    assert len(load_gif(src).frames) == 1


def test_frame_texts_differ_per_frame(tmp_path):
    src = _anim_gif(tmp_path / "in.gif")
    data = load_gif(src)
    ramp = get_ramp("ascii")
    opts = ConvertOptions(width=30, height=10)
    grids = [convert(f, ramp, opts) for f in data.frames]
    assert len(grids) == 3
    assert len({tuple("".join(ch for ch, _ in row) for row in g) for g in grids}) > 1


def test_export_frame_dir_and_meta(tmp_path):
    src = _anim_gif(tmp_path / "in.gif")
    data = load_gif(src)
    grids = [convert(f, get_ramp("ascii"), ConvertOptions(width=20, height=6)) for f in data.frames]
    out = tmp_path / "frames"
    paths = export_frame_dir(grids, out, color=False, fps=12, loop=1, durations_ms=[83, 83, 83])
    assert len(paths) == 3 and all(p.suffix == ".txt" for p in paths)
    assert (out / "meta.json").is_file()


def test_text_gif_roundtrip_self_playing(tmp_path):
    src = _anim_gif(tmp_path / "in.gif")
    data = load_gif(src)
    grids = [convert(f, get_ramp("ascii"), ConvertOptions(width=20, height=6)) for f in data.frames]
    images = grids_to_images(grids, color=False)
    out = tmp_path / "out.gif"
    save_text_gif(images, out, fps=12, loop=1)
    chk = Image.open(out)
    assert getattr(chk, "n_frames", 1) == 3


def test_cli_animate_frame_dir_and_gif(tmp_path):
    src = _anim_gif(tmp_path / "in.gif")
    rc = main([str(src), "--animate", "--width", "20", "--charset", "ascii", "--no-color",
               "--fps", "12", "--loop", "1", "--no-preview", "-o", str(tmp_path / "frames")])
    assert rc == 0
    assert len(list((tmp_path / "frames").glob("frame_*.txt"))) == 3
    rc = main([str(src), "--animate", "--width", "20", "--no-color",
               "--fps", "12", "--loop", "1", "--no-preview", "-o", str(tmp_path / "out.gif")])
    assert rc == 0
    assert Image.open(tmp_path / "out.gif").n_frames == 3


def test_cli_animate_rejects_non_gif(tmp_path):
    png = tmp_path / "x.png"
    Image.new("RGB", (10, 10), (0, 0, 0)).save(png)
    rc = main([str(png), "--animate", "--no-preview", "-o", str(tmp_path / "frames")])
    assert rc == 1


def test_cli_animate_validates_fps(tmp_path):
    src = _anim_gif(tmp_path / "in.gif")
    assert main([str(src), "--animate", "--fps", "0", "--no-preview", "-o", str(tmp_path / "o")]) == 2
