# Pippin

[![CI](https://github.com/fluxion-dev/pippin/actions/workflows/ci.yml/badge.svg)](https://github.com/fluxion-dev/pippin/actions) [![Release](https://img.shields.io/github/v/release/fluxion-dev/pippin?include_prereleases=true)](https://github.com/fluxion-dev/pippin/releases) [![License](https://img.shields.io/badge/license-MIT-blue)](./LICENSE) [![Python](https://img.shields.io/badge/python-3.10%2B-3776AB)](https://www.python.org/)

`pippin` consumes images (`png`, `jpeg`, `svg`) and outputs high-resolution
ASCII / UTF-8 representations to your terminal. With `--animate` it consumes
an animated `gif` and re-renders every frame as text — exporting a frame
directory or a self-playing text-animation `gif`.

## Features

- Input: `png`, `jpeg`, `svg` (plus anything Pillow opens: bmp, gif, webp, tiff)
- Charsets: `ascii`, `utf8`, `blocks` (+ `--custom-chars`)
- Preview to terminal (ANSI truecolor optional) and export to `.txt` / `.ansi`
- Color coding of characters (foreground truecolor sampled from source)
- Contrast / brightness / invert / aspect correction
- GIF animation mode (`--animate`): live terminal playback, frame-directory
  export, and self-playing text-animation `.gif` re-export

## Install

No Python install required: each `v*` tag ships self-contained single-file
binaries (`.github/workflows/release.yml`, matrix `linux-x64|osx-arm64|win-x64`)
attached to that tag's GitHub Release. SVG works out of the box — cairo is
bundled inside the binary.

```bash
curl -fSL -o /tmp/pippin-dl/pippin-linux-x64 https://github.com/fluxion-dev/pippin/releases/download/v0.1.0/pippin-linux-x64
chmod +x /tmp/pippin-dl/pippin-linux-x64
/tmp/pippin-dl/pippin-linux-x64 --version
# 0.1.0
```

```bash
gh release download v0.1.0 -p 'pippin-linux-x64' -D /tmp/pippin-dl --repo fluxion-dev/pippin
chmod +x /tmp/pippin-dl/pippin-linux-x64
/tmp/pippin-dl/pippin-linux-x64 --version
# 0.1.0
```

Direct asset URLs (each `v*` tag attaches the three binaries plus the sdist/wheel):

- https://github.com/fluxion-dev/pippin/releases/download/v0.1.0/pippin-linux-x64
- https://github.com/fluxion-dev/pippin/releases/download/v0.1.0/pippin-osx-arm64
- https://github.com/fluxion-dev/pippin/releases/download/v0.1.0/pippin-win-x64.exe

| RID | Binary | Size (attached asset) |
|-----|--------|----------------------------|
| `linux-x64` | `pippin-linux-x64` | 36,280,472 bytes (~34.6 MiB) |
| `osx-arm64` | `pippin-osx-arm64` | 16,520,016 bytes (~15.8 MiB) |
| `win-x64` | `pippin-win-x64.exe` | 23,468,705 bytes (~22.4 MiB) |

Notes:

- macOS builds are arm64 (Apple silicon) only. Downloaded binaries are
  unsigned — on macOS run `xattr -d com.apple.quarantine pippin-osx-arm64`
  after downloading; Windows may show a SmartScreen prompt.
- Prefer pip? `pip install pippin-art` (or `pipx install pippin-art`), then
  `pippin --version`. SVG via pip needs system cairo (see below).

From source (editable install with dev extras):

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

System deps for SVG (`cairosvg` needs cairo):

```bash
# Fedora
sudo dnf install cairo pango gdk-pixbuf2
# Debian/Ubuntu
sudo apt install libcairo2 libpango-1.0-0 libgdk-pixbuf2.0-0
```

## Usage

```bash
# Preview (UTF-8 + color by default)
pippin photo.jpg

# ASCII, no color, fixed width
pippin logo.png --charset ascii --no-color --width 80

# Preview + export (ANSI escapes preserved when --color)
pippin input.svg --charset utf8 --color --width 120 --export out.ansi

# Export only (no terminal preview)
pippin input.jpg --export out.txt --no-preview

# Tweak rendering
pippin input.png --width 160 --contrast 1.2 --brightness 1.1 --invert
pippin input.png --charset blocks --custom-chars " .:-=+*#%@"

# Animate (uniform 12fps playback/encode by default)
pippin anim.gif --animate --width 100
pippin anim.gif --animate --width 100 --no-preview -o frames/        # frame_*.txt/.ansi + meta.json
pippin anim.gif --animate --width 100 --no-preview -o text_anim.gif  # self-playing text gif
pippin anim.gif --animate --native-timing --width 80                 # preserve source frame timing
```

## CLI reference

```
pippin INPUT [-w WIDTH] [-H HEIGHT] [--charset {ascii,utf8,blocks} | --custom-chars STR]
             [--color | --no-color] [--preview | --no-preview]
             [-o FILE] [--invert] [--contrast F] [--brightness F] [--aspect F]
             [--animate] [--fps FPS] [--native-timing] [--max-frames N] [--sample N]
             [--loop N] [--gif-font PATH] [--gif-font-size N]
```

| Flag | Default | Meaning |
|------|---------|---------|
| `INPUT` | — | Input image path (`--animate` requires `.gif`) |
| `-w, --width` | `100` | Output width in characters (1–2000) |
| `-H, --height` | auto | Output height in characters; auto preserves aspect with correction |
| `--charset` | `utf8` | `ascii`, `utf8`, or `blocks` ramp |
| `--custom-chars` | — | Overrides `--charset` with your own dark→light ramp |
| `--color` / `--no-color` | `color` | ANSI truecolor foreground per character |
| `--preview` / `--no-preview` | `preview` | Print to stdout (still) / play animation (`--animate`) |
| `-o, --export` | — | Still: rendering file (`.txt`/`.ansi`); `--animate`: frame dir or `.gif` |
| `--invert` | off | Invert luminance ramp |
| `--contrast` | `1.0` | Pillow contrast factor |
| `--brightness` | `1.0` | Pillow brightness factor |
| `--aspect` | `0.55` | Height correction for terminal cell aspect (char H ≈ 2× W). Lower = taller image. |
| `--animate` | off | GIF mode: render all frames as text frames |
| `--fps` | `12` | Uniform playback/encode rate (0 < fps ≤ 60); ignored with `--native-timing` |
| `--native-timing` | off | Preserve source per-frame durations instead of uniform `--fps` |
| `--max-frames` | all | Cap frames kept after sampling |
| `--sample` | `1` | Keep every Nth frame |
| `--loop` | infinite preview / source loop for `.gif` | Animation plays / GIF loop count, `0`=infinite |
| `--gif-font` | system monospace | TTF/OTF path for `out.gif` rasterization |
| `--gif-font-size` | `20` | Font size for `out.gif` rasterization (8–72) |

Export format: if `--color` is on, the export file contains ANSI escapes
(`.ansi`-ready). With `--no-color` it is plain text.

## Ramps

- `ascii`: ` .:-=+*#%@` (10 levels, pure 7-bit)
- `utf8`: ``  `^\",:;Il!i~+_-?][}{1)(|\\/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$ `` (70 levels)
- `blocks`: ` ░▒▓█` (5 levels, uniform blocks)

## Notes

- SVG is rasterized via `cairosvg` at 3× target width, then downsampled —
  so vector edges stay sharp at high resolutions.
- Transparency is composited onto black (use `--invert` for light terminals,
  compositing background is fixed black for predictable luminance).
- For best quality use `--width 120–240` with `--charset utf8`.
