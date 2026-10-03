from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from pippin.charsets import get_ramp
from pippin.converter import ConvertOptions, convert
from pippin.image_loader import load_image
from pippin.renderer import to_ansi, to_plain
from pippin.cli import main

ASSETS = Path(__file__).parent / "assets"


def _solid(color: tuple[int, int, int], size=(8, 4)) -> Image.Image:
    return Image.new("RGB", size, color)


def test_ramp_ascii_ends():
    ramp = get_ramp("ascii")
    assert ramp[0] == " " and ramp[-1] == "@"


def test_ramp_custom_overrides():
    assert get_ramp("ascii", custom="01") == "01"


def test_ramp_invert():
    assert get_ramp("ascii", invert=True) == get_ramp("ascii")[::-1]


def test_ramp_rejects_short_custom():
    with pytest.raises(ValueError):
        get_ramp("ascii", custom="x")


def test_black_maps_to_first_char_white_to_last():
    ramp = get_ramp("ascii")
    grid_black = convert(_solid((0, 0, 0)), ramp, ConvertOptions(width=4, height=2))
    grid_white = convert(_solid((255, 255, 255)), ramp, ConvertOptions(width=4, height=2))
    assert all(ch == ramp[0] for row in grid_black for ch, _ in row)
    assert all(ch == ramp[-1] for row in grid_white for ch, _ in row)


def test_target_size_preserves_aspect():
    grid = convert(_solid((128, 128, 128), size=(100, 50)), " @", ConvertOptions(width=20))
    assert len(grid[0]) == 20
    # 50/100 * 20 * 0.55 = 5.5 -> 6
    assert len(grid) == 6


def test_explicit_height():
    grid = convert(_solid((0, 0, 0)), " @", ConvertOptions(width=10, height=3))
    assert len(grid) == 3 and len(grid[0]) == 10


def test_plain_has_no_escapes_ansi_has_truecolor():
    grid = convert(_solid((255, 0, 0), size=(4, 2)), " @", ConvertOptions(width=4, height=2))
    plain = to_plain(grid)
    assert "\x1b" not in plain
    ansi = to_ansi(grid)
    assert "\x1b[38;2;255;0;0m" in ansi
    assert ansi.endswith("\x1b[0m\n")


def test_load_png_and_jpg(tmp_path):
    for suffix in (".png", ".jpg"):
        f = tmp_path / f"img{suffix}"
        _solid((10, 20, 30)).save(f)
        assert load_image(f).mode == "RGB"


def test_load_svg(tmp_path):
    pytest.importorskip("cairosvg")
    f = tmp_path / "img.svg"
    f.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10" fill="red"/></svg>')
    img = load_image(f)
    assert img.size[0] > 0


def test_load_missing_raises():
    with pytest.raises(FileNotFoundError):
        load_image("/nonexistent/image.png")


def test_cli_preview_and_export(tmp_path, capsys):
    f = tmp_path / "in.png"
    _solid((200, 200, 200), size=(16, 8)).save(f)
    out = tmp_path / "out.txt"
    rc = main([str(f), "--width", "8", "--charset", "ascii", "--no-color", "--export", str(out)])
    assert rc == 0
    text = out.read_text()
    assert text.strip()
    captured = capsys.readouterr()
    assert captured.out == text  # preview echoes export content


def test_cli_no_preview_no_export_errors(capsys):
    f = ASSETS / "placeholder"  # nonexistent; arg validation fires first
    _ = f
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
        _solid((0, 0, 0)).save(tf.name)
        rc = main([tf.name, "--no-preview"])
    assert rc == 2
