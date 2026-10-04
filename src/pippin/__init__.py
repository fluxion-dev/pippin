"""pippin — high resolution ascii/utf8 image renderer."""

__version__ = "0.2.0"

from .anim_export import export_frame_dir
from .charsets import CHARSETS, get_ramp
from .converter import ConvertOptions, convert
from .gif import GifData, load_gif, resolve_durations, uniform_durations
from .image_loader import load_image
from .player import play_frames
from .renderer import render, to_ansi, to_plain
from .text_gif import grids_to_images, resolve_font, save_text_gif

__all__ = [
    "__version__",
    "CHARSETS",
    "ConvertOptions",
    "GifData",
    "convert",
    "export_frame_dir",
    "get_ramp",
    "grids_to_images",
    "load_gif",
    "load_image",
    "play_frames",
    "render",
    "resolve_durations",
    "resolve_font",
    "save_text_gif",
    "to_ansi",
    "to_plain",
    "uniform_durations",
]
