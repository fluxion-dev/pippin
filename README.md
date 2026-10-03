# Pippin

[![CI](https://github.com/fluxion-dev/pippin/actions/workflows/ci.yml/badge.svg)](https://github.com/fluxion-dev/pippin/actions) [![Release](https://img.shields.io/github/v/release/fluxion-dev/pippin?include_prereleases=true)](https://github.com/fluxion-dev/pippin/releases) [![License](https://img.shields.io/badge/license-MIT-blue)](./LICENSE) [![Python](https://img.shields.io/badge/python-3.10%2B-3776AB)](https://www.python.org/)

`pippin` consumes images (`png`, `jpeg`, `svg`) and outputs high-resolution
ASCII / UTF-8 representations to your terminal.

## Features

- Input: `png`, `jpeg`, `svg` (plus anything Pillow opens: bmp, gif, webp, tiff)
- Charsets: `ascii`, `utf8`, `blocks` (+ `--custom-chars`)
- Preview to terminal (ANSI truecolor optional) and export to `.txt` / `.ansi`
- Color coding of characters (foreground truecolor sampled from source)
- Contrast / brightness / invert / aspect correction

## Install

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
```

## CLI reference

```
pippin INPUT [-w WIDTH] [-H HEIGHT] [--charset {ascii,utf8,blocks} | --custom-chars STR]
             [--color | --no-color] [--preview | --no-preview]
             [-o FILE] [--invert] [--contrast F] [--brightness F] [--aspect F]
```

| Flag | Default | Meaning |
|------|---------|---------|
| `INPUT` | — | Input image path |
| `-w, --width` | `100` | Output width in characters (1–2000) |
| `-H, --height` | auto | Output height in characters; auto preserves aspect with correction |
| `--charset` | `utf8` | `ascii`, `utf8`, or `blocks` ramp |
| `--custom-chars` | — | Overrides `--charset` with your own dark→light ramp |
| `--color` / `--no-color` | `color` | ANSI truecolor foreground per character |
| `--preview` / `--no-preview` | `preview` | Print to stdout |
| `-o, --export` | — | Write rendering to file (`.txt`/`.ansi`) |
| `--invert` | off | Invert luminance ramp |
| `--contrast` | `1.0` | Pillow contrast factor |
| `--brightness` | `1.0` | Pillow brightness factor |
| `--aspect` | `0.55` | Height correction for terminal cell aspect (char H ≈ 2× W). Lower = taller image. |

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
