"""pippin — high resolution ascii/utf8 image renderer."""

__version__ = "0.3.1"

from .anim_export import export_frame_dir, write_anim_meta
from .charsets import CHARSETS, get_ramp
from .converter import ConvertOptions, convert
from .gif import GifData, load_gif, resolve_durations, uniform_durations
from .image_loader import load_image
from .player import play_frames
from .renderer import render, to_ansi, to_plain
from .text_gif import font_cell, grid_to_image, grids_to_images, resolve_font, save_text_gif, verified_grid_renderer
from .video import (
    VIDEO_INPUT_SUFFIXES,
    VIDEO_OUTPUT_SUFFIXES,
    VideoData,
    VideoEncoder,
    _worker_init,
    estimate_kept_frames,
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

__all__ = [
    "__version__",
    "CHARSETS",
    "ConvertOptions",
    "GifData",
    "VideoData",
    "VIDEO_INPUT_SUFFIXES",
    "VIDEO_OUTPUT_SUFFIXES",
    "VideoEncoder",
    "convert",
    "estimate_kept_frames",
    "export_frame_dir",
    "font_cell",
    "get_ramp",
    "verified_grid_renderer",
    "grid_to_image",
    "grids_to_images",
    "iter_video_frames",
    "load_gif",
    "load_image",
    "load_video",
    "mux_audio",
    "play_frames",
    "probe_video",
    "render",
    "render_frame_task",
    "resolve_job_count",
    "resolve_durations",
    "resolve_font",
    "resolve_source_fps",
    "resolve_video_fps",
    "save_text_gif",
    "save_text_video",
    "select_video_encoder",
    "to_ansi",
    "to_plain",
    "uniform_durations",
    "write_anim_meta",
]
