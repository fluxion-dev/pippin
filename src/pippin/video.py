"""Video animation support: generic video (mp4/mpeg/...) -> text video via ffmpeg.

Decoding and encoding shell out to the system ``ffmpeg``/``ffprobe``
binaries, so no new Python dependencies are required.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

VIDEO_INPUT_SUFFIXES = frozenset(
    {".mp4", ".mpeg", ".mpg", ".mpe", ".m4v", ".mov", ".avi", ".mkv", ".webm"}
)
VIDEO_OUTPUT_SUFFIXES = frozenset(
    {".mp4", ".mpeg", ".mpg", ".mpe", ".m4v", ".mov", ".avi", ".mkv", ".webm"}
)


def is_video_suffix(suffix: str) -> bool:
    return suffix.lower() in VIDEO_INPUT_SUFFIXES


def is_video_output_suffix(suffix: str) -> bool:
    return suffix.lower() in VIDEO_OUTPUT_SUFFIXES


def require_ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if exe is None:
        raise OSError(
            "video support requires the 'ffmpeg' binary on PATH "
            "(install ffmpeg, e.g. 'sudo dnf install ffmpeg' / 'sudo apt install ffmpeg')"
        )
    return exe


def _ffprobe() -> str | None:
    return shutil.which("ffprobe")


def _parse_fps(rate: str | None, fallback: float = 25.0) -> float:
    """Parse an ffmpeg r_frame_rate/avg_frame_rate string like '30000/1001'."""
    if not rate:
        return fallback
    try:
        if "/" in rate:
            num, den = rate.split("/", 1)
            fps = float(num) / float(den)
        else:
            fps = float(rate)
        if fps > 0 and fps <= 120:
            return fps
    except (ValueError, ZeroDivisionError):
        pass
    return fallback


@dataclass
class VideoData:
    frames: list[Image.Image]  # RGB, all same size
    fps: float  # source frame rate
    durations_ms: list[int]  # uniform per-frame durations derived from fps
    size: tuple[int, int] = (0, 0)
    duration_sec: float = 0.0
    has_audio: bool = False


def probe_video(path: str | Path) -> dict:
    """Probe a video file with ffprobe (fallback: parse `ffmpeg -i` output).

    Returns dict with width, height, fps, nb_frames, duration_sec, has_audio.
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"input file not found: {p}")
    probe = _ffprobe()
    if probe is not None:
        cmd = [
            probe,
            "-v",
            "error",
            "-show_entries",
            "stream=index,codec_type,codec_name,width,height,r_frame_rate,avg_frame_rate,nb_frames,duration",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(p),
        ]
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, check=True)
            info = json.loads(out.stdout or "{}")
        except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
            raise ValueError(f"could not probe video {p}: {e}") from e
        streams = info.get("streams", [])
        vstreams = [s for s in streams if s.get("codec_type") == "video"]
        if not vstreams:
            raise ValueError(f"no video stream found in {p}")
        v = vstreams[0]
        width = int(v.get("width", 0) or 0)
        height = int(v.get("height", 0) or 0)
        fps = _parse_fps(v.get("avg_frame_rate") or v.get("r_frame_rate"))
        has_audio = any(s.get("codec_type") == "audio" for s in streams)
        duration_sec = 0.0
        try:
            duration_sec = float(v.get("duration") or info.get("format", {}).get("duration") or 0.0)
        except (ValueError, TypeError):
            duration_sec = 0.0
        nb_frames = 0
        try:
            nb_frames = int(v.get("nb_frames", 0) or 0)
        except (ValueError, TypeError):
            nb_frames = 0
        return {
            "width": width,
            "height": height,
            "fps": fps,
            "nb_frames": nb_frames,
            "duration_sec": duration_sec,
            "has_audio": has_audio,
        }
    # Fallback without ffprobe: parse `ffmpeg -i` stderr.
    ffmpeg = require_ffmpeg()
    proc = subprocess.run([ffmpeg, "-hide_banner", "-i", str(p)], capture_output=True, text=True)
    text = proc.stderr or ""
    import re

    m = re.search(r"Video:.*?, (\d+)x(\d+)[,\s].*?([\d.]+)\s*fps", text)
    if not m:
        raise ValueError(f"could not probe video {p} (install ffprobe for reliable probing)")
    width, height, fps = int(m.group(1)), int(m.group(2)), float(m.group(3))
    has_audio = "Audio:" in text
    m2 = re.search(r"Duration: (\d+):(\d+):([\d.]+)", text)
    duration_sec = 0.0
    if m2:
        duration_sec = int(m2.group(1)) * 3600 + int(m2.group(2)) * 60 + float(m2.group(3))
    return {
        "width": width,
        "height": height,
        "fps": fps or 25.0,
        "nb_frames": 0,
        "duration_sec": duration_sec,
        "has_audio": has_audio,
    }


def _check_video_args(
    path: str | Path,
    max_frames: int | None,
    sample: int,
) -> Path:
    if sample < 1:
        raise ValueError("--sample must be >= 1")
    if max_frames is not None and max_frames < 1:
        raise ValueError("--max-frames must be >= 1")
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"input file not found: {p}")
    if p.suffix.lower() not in VIDEO_INPUT_SUFFIXES:
        raise ValueError(
            f"--animate video input must be one of {sorted(VIDEO_INPUT_SUFFIXES)}, got {p.suffix!r}"
        )
    return p


def iter_video_frames(
    path: str | Path,
    max_frames: int | None = None,
    sample: int = 1,
    gpu: bool = True,
):
    """Yield decoded RGB frames one at a time (constant memory).

    Unlike :func:`load_video`, this streams frames through the ffmpeg pipe
    instead of buffering the whole clip, so long/high-resolution videos
    don't balloon RAM (raw RGB24 is ~6 MiB/frame at 1080p).

    With ``gpu=True`` (default), hardware decoding (``-hwaccel auto``) is
    probed first and used when it works, else software decoding.
    """
    p = _check_video_args(path, max_frames, sample)
    ffmpeg = require_ffmpeg()
    meta = probe_video(p)
    width, height = meta["width"], meta["height"]
    if width <= 0 or height <= 0:
        raise ValueError(f"could not determine video dimensions for {p}")

    use_hw = bool(gpu) and _probe_hw_decode(p)
    # Decode to raw RGB24 on stdout. -vsync 0 keeps every source frame.
    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
    ]
    if use_hw:
        cmd += ["-hwaccel", "auto"]
    cmd += [
        "-i",
        str(p),
        "-vsync",
        "0",
        "-pix_fmt",
        "rgb24",
        "-f",
        "rawvideo",
        "-",
    ]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError as e:
        raise OSError(f"could not launch ffmpeg: {e}") from e
    assert proc.stdout is not None and proc.stderr is not None

    frame_size = width * height * 3
    buf = b""
    kept = 0
    decoded = 0
    try:
        while True:
            while len(buf) < frame_size:
                chunk = proc.stdout.read(frame_size - len(buf))
                if not chunk:
                    break
                buf += chunk
            if len(buf) < frame_size:
                break
            raw, buf = buf[:frame_size], buf[frame_size:]
            if decoded % sample == 0:
                yield Image.frombytes("RGB", (width, height), bytes(raw))
                kept += 1
                if max_frames is not None and kept >= max_frames:
                    break
            decoded += 1
    finally:
        # Drain leftover state: close the pipe and reap the child so a
        # --max-frames early exit doesn't leave a zombie ffmpeg.
        try:
            proc.stdout.close()
        except (OSError, ValueError):
            pass
        if proc.poll() is None:
            proc.kill()
        stderr = proc.stderr.read()
        rc = proc.wait()
    if rc != 0 and not (max_frames is not None and kept >= max_frames):
        err = (stderr or b"").decode("utf-8", "replace")[:500]
        raise OSError(f"ffmpeg failed to decode {p}: {err}")
    if kept == 0:
        raise ValueError(f"video contains no frames: {p}")


def load_video(
    path: str | Path,
    max_frames: int | None = None,
    sample: int = 1,
    gpu: bool = True,
) -> VideoData:
    """Decode a video file into full RGB frames via ffmpeg.

    Args:
        path: input video path (mp4/mpeg/mov/avi/mkv/webm/...).
        max_frames: cap on frames kept *after* sampling (None = all).
        sample: keep every Nth decoded frame (stride >= 1).
        gpu: probe hardware decoding first, fall back to software.

    Note: this buffers every kept frame in RAM. For long videos prefer
    :func:`iter_video_frames`, which streams one frame at a time.
    """
    p = _check_video_args(path, max_frames, sample)
    meta = probe_video(p)
    fps = meta["fps"] or 25.0
    frames = list(iter_video_frames(p, max_frames=max_frames, sample=sample, gpu=gpu))

    per_ms = max(1, round(1000.0 / fps))
    durations = [per_ms] * len(frames)
    return VideoData(
        frames=frames,
        fps=fps,
        durations_ms=durations,
        size=(meta["width"], meta["height"]),
        duration_sec=meta.get("duration_sec", 0.0),
        has_audio=meta.get("has_audio", False),
    )


def resolve_source_fps(source_fps: float, fps: float, native_timing: bool) -> float:
    """Uniform --fps by default; --native-timing preserves source fps."""
    if native_timing:
        if source_fps <= 0:
            raise ValueError("could not determine source fps")
        return source_fps
    if fps <= 0:
        raise ValueError("--fps must be > 0")
    return fps


def resolve_video_fps(data: VideoData, fps: float, native_timing: bool) -> float:
    """Uniform --fps by default; --native-timing preserves source fps."""
    return resolve_source_fps(data.fps, fps, native_timing)


def _available_encoders() -> set[str]:
    try:
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg is None:
            return set()
        proc = subprocess.run(
            [ffmpeg, "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=30
        )
        return set((proc.stdout or "").split())
    except (subprocess.SubprocessError, OSError):
        return set()


def _ffmpeg_hwaccels() -> set[str]:
    """Hardware accel methods reported by `ffmpeg -hwaccels` (e.g. cuda, vaapi, qsv)."""
    try:
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg is None:
            return set()
        proc = subprocess.run(
            [ffmpeg, "-hide_banner", "-hwaccels"], capture_output=True, text=True, timeout=30
        )
        return {line.strip() for line in (proc.stdout or "").splitlines() if line.strip()} - {
            "Hardware",
            "acceleration",
            "methods:",
        }
    except (subprocess.SubprocessError, OSError):
        return set()


def _vaapi_device() -> str | None:
    """DRM render node for VAAPI, if one exists on this machine."""
    import os

    override = os.environ.get("PIPPIN_VAAPI_DEVICE")
    if override:
        return override
    for cand in ("/dev/dri/renderD128", "/dev/dri/renderD129"):
        if Path(cand).exists():
            return cand
    return None


# Preferred GPU encoders per container family, strongest first.
_GPU_CANDIDATES: dict[str, tuple[str, ...]] = {
    "h264": ("h264_nvenc", "h264_qsv", "h264_amf", "h264_videotoolbox", "h264_vaapi"),
    "mpeg2": ("mpeg2_vaapi", "mpeg2_qsv"),
    "vp9": ("vp9_vaapi", "vp9_qsv"),
}

_GPU_PROBE_CACHE: dict[tuple, bool] = {}
_DISK_PROBES: dict[str, bool] | None = None


def _probe_cache_file() -> Path | None:
    import os

    try:
        base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
        d = base / "pippin"
        d.mkdir(parents=True, exist_ok=True)
        return d / "gpu_probes.json"
    except OSError:
        return None


def _ffmpeg_build_id() -> str:
    try:
        proc = subprocess.run(
            [require_ffmpeg(), "-version"], capture_output=True, text=True, timeout=15
        )
        first = (proc.stdout or "").splitlines()
        return first[0] if first else ""
    except (subprocess.SubprocessError, OSError):
        return ""


def _disk_probe_get(key: str) -> bool | None:
    global _DISK_PROBES
    if _DISK_PROBES is None:
        _DISK_PROBES = {}
        fp = _probe_cache_file()
        if fp is not None and fp.is_file():
            try:
                import json

                data = json.loads(fp.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    _DISK_PROBES = {str(k): bool(v) for k, v in data.items()}
            except (OSError, ValueError):
                pass
    return _DISK_PROBES.get(key)


def _disk_probe_set(key: str, value: bool) -> None:
    global _DISK_PROBES
    if _DISK_PROBES is None:
        _DISK_PROBES = {}
    _DISK_PROBES[key] = value
    fp = _probe_cache_file()
    if fp is None:
        return
    try:
        import json

        fp.write_text(json.dumps(_DISK_PROBES), encoding="utf-8")
    except OSError:
        pass


def _gpu_encoder_chain(
    encoder: str, w: int, h: int, fps: float
) -> tuple[list[str], list[str], str]:
    """Build (pre_input_args, video_filter, pix_fmt) for a GPU encoder.

    VAAPI consumes hardware frames, so its chain uploads after the
    even-size scale; every other GPU encoder takes system memory like
    the software path.
    """
    even = "scale=trunc(iw/2)*2:trunc(ih/2)*2"
    if encoder.endswith("_vaapi"):
        device = _vaapi_device()
        pre = ["-vaapi_device", device] if device else []
        return pre, [f"{even},format=nv12,hwupload"], "vaapi"
    return [], [even], "yuv420p"


def _probe_gpu_encoder(encoder: str, w: int, h: int, fps: float) -> bool:
    """Actually try a 2-frame GPU encode; capability lists lie (no device, VMs)."""
    key = (encoder, w, h, round(float(fps), 3))
    if key in _GPU_PROBE_CACHE:
        return _GPU_PROBE_CACHE[key]
    disk_key = f"{_ffmpeg_build_id()}|{encoder}|{w}x{h}@{round(float(fps), 3):g}"
    disk_hit = _disk_probe_get(disk_key)
    if disk_hit is not None:
        _GPU_PROBE_CACHE[key] = disk_hit
        return disk_hit
    ok = False
    try:
        ffmpeg = require_ffmpeg()
        pre, vf, pix_fmt = _gpu_encoder_chain(encoder, w, h, fps)
        cmd = [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            *pre,
            "-f",
            "lavfi",
            "-i",
            f"nullsrc=s={w}x{h}:r={fps:g}:d={2.0 / max(fps, 0.001):.6f}",
            "-vf",
            ",".join(vf),
            "-c:v",
            encoder,
        ]
        if pix_fmt != "vaapi":
            cmd += ["-pix_fmt", pix_fmt]
        cmd += ["-frames:v", "2", "-f", "null", "-"]
        proc = subprocess.run(cmd, capture_output=True, timeout=60)
        ok = proc.returncode == 0
    except (subprocess.SubprocessError, OSError):
        ok = False
    _GPU_PROBE_CACHE[key] = ok
    _disk_probe_set(disk_key, ok)
    return ok


def _probe_hw_decode(path: Path) -> bool:
    """Check `-hwaccel auto` decode works before committing the stream to it."""
    try:
        ffmpeg = require_ffmpeg()
        cmd = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-hwaccel",
            "auto",
            "-i",
            str(path),
            "-frames:v",
            "1",
            "-f",
            "null",
            "-",
        ]
        proc = subprocess.run(cmd, capture_output=True, timeout=60)
        return proc.returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


def _video_codec_for(suffix: str, encoders: set[str]) -> tuple[str, str]:
    """Return (video_codec, pixel_format) for an output suffix."""
    s = suffix.lower()
    if s in (".mpeg", ".mpg", ".mpe"):
        # mpeg2video (not mpeg1video): mpeg1 only allows broadcast frame
        # rates (23.976/24/25/29.97/30/...), while mpeg2 in a program
        # stream accepts arbitrary rates like the 12fps default.
        return ("mpeg2video", "yuv420p")
    if s == ".webm":
        if "libvpx-vp9" in encoders:
            return ("libvpx-vp9", "yuv420p")
        if "libvpx" in encoders:
            return ("libvpx", "yuv420p")
        return ("mpeg4", "yuv420p")
    # mp4/mov/m4v/avi/mkv and anything else: MPEG-4 Part 2. It encodes
    # high-frequency text ~2x faster than OpenH264 with similar size,
    # keeps edges crisper, and plays everywhere.
    return ("mpeg4", "yuv420p")


def select_video_encoder(
    suffix: str,
    w: int,
    h: int,
    fps: float,
    gpu: bool = True,
) -> tuple[str, list[str], list[str], str, str]:
    """Pick (vcodec, pre_input_args, video_filter, pix_fmt, kind) for output.

    With ``gpu=True`` (default), working GPU encoders are preferred and
    verified by a real probe encode; anything missing or broken falls
    back to the software codec. Returns kind ``"gpu"`` or ``"software"``.
    """
    encoders = _available_encoders()
    if gpu:
        s = suffix.lower()
        family = "mpeg2" if s in (".mpeg", ".mpg", ".mpe") else "vp9" if s == ".webm" else "h264"
        for cand in _GPU_CANDIDATES[family]:
            if cand in encoders and _probe_gpu_encoder(cand, w, h, fps):
                pre, vf, pix_fmt = _gpu_encoder_chain(cand, w, h, fps)
                return cand, pre, vf, pix_fmt, "gpu"
    vcodec, pix_fmt = _video_codec_for(suffix, encoders)
    return vcodec, [], ["scale=trunc(iw/2)*2:trunc(ih/2)*2"], pix_fmt, "software"


class VideoEncoder:
    """Streaming video encoder: feed RGB frames, memory stays flat.

    Frames are piped to ffmpeg as raw RGB24 one at a time, so encoding a
    700-frame clip never materializes the whole filmstrip in RAM.
    The output is silent; use :func:`mux_audio` afterwards when the
    source audio should be preserved.
    """

    def __init__(
        self,
        out_path: str | Path,
        fps: float,
        frame_size: tuple[int, int],
        crf: int | None = None,
        gpu: bool = True,
    ) -> None:
        if fps <= 0 or fps > 120:
            raise ValueError("--fps must be 0 < fps <= 120")
        out = Path(out_path)
        if out.suffix.lower() not in VIDEO_OUTPUT_SUFFIXES:
            raise ValueError(
                f"unsupported video output {out.suffix!r}, expected one of {sorted(VIDEO_OUTPUT_SUFFIXES)}"
            )
        w, h = frame_size
        if w < 1 or h < 1:
            raise ValueError("frame size must be positive")
        ffmpeg = require_ffmpeg()
        out.parent.mkdir(parents=True, exist_ok=True)
        vcodec, pre, vf, pix_fmt, kind = select_video_encoder(out.suffix, w, h, fps, gpu)
        self.backend = vcodec
        """Actual encoder in use (e.g. h264_nvenc, or a software codec)."""
        self.gpu = kind == "gpu"
        """True when a hardware encoder was engaged."""

        cmd = [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            *pre,
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            f"{w}x{h}",
            "-r",
            f"{fps:g}",
            "-i",
            "-",
            "-vf",
            ",".join(vf),
            "-c:v",
            vcodec,
        ]
        if pix_fmt != "vaapi":
            cmd += ["-pix_fmt", pix_fmt]
        if vcodec in ("libopenh264", "libx264", "libx265", "libvpx-vp9", "libvpx"):
            if crf is not None:
                cmd += ["-crf", str(crf)]
            if vcodec == "libvpx-vp9":
                cmd += ["-b:v", "0"]
        cmd += [str(out)]
        try:
            self._proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        except OSError as e:
            raise OSError(f"could not launch ffmpeg: {e}") from e
        self._size = (w, h)
        self._closed = False
        self.frames_written = 0

    def write(self, img: Image.Image) -> None:
        """Pipe one frame to the encoder."""
        if self._closed:
            raise ValueError("encoder is closed")
        if img.size != self._size:
            img = img.resize(self._size)
        # convert() is a full-frame copy when already RGB — skip it.
        data = img.tobytes() if img.mode == "RGB" else img.convert("RGB").tobytes()
        self.write_bytes(data)

    def write_bytes(self, data: bytes) -> None:
        """Pipe one pre-encoded RGB frame (len == w*h*3) to the encoder."""
        if self._closed:
            raise ValueError("encoder is closed")
        try:
            assert self._proc.stdin is not None
            self._proc.stdin.write(data)
        except BrokenPipeError as e:
            raise OSError(f"ffmpeg encoding failed: {self._stderr_tail()}") from e
        self.frames_written += 1

    def _stderr_tail(self, limit: int = 1000) -> str:
        try:
            assert self._proc.stderr is not None
            self._proc.wait(timeout=60)
            err = self._proc.stderr.read() or b""
        except (subprocess.TimeoutExpired, OSError):
            err = b""
        return err.decode("utf-8", "replace")[-limit:]

    def close(self) -> int:
        """Flush, wait for ffmpeg, and return frames written."""
        if self._closed:
            return self.frames_written
        self._closed = True
        try:
            assert self._proc.stdin is not None
            self._proc.stdin.close()
        except (BrokenPipeError, OSError, ValueError):
            pass
        try:
            rc = self._proc.wait(timeout=600)
        except subprocess.TimeoutExpired as e:
            self._proc.kill()
            raise OSError("ffmpeg encoding timed out") from e
        if rc != 0:
            raise OSError(f"ffmpeg encoding failed: {self._stderr_tail()}")
        if self.frames_written == 0:
            raise ValueError("no frames to encode")
        return self.frames_written

    def __enter__(self) -> VideoEncoder:
        return self

    def __exit__(self, *exc: object) -> None:
        if exc[0] is None:
            self.close()
        else:
            self.abort()

    def abort(self) -> None:
        """Kill the encoder without waiting for a clean flush (error paths)."""
        if not self._closed:
            self._closed = True
            try:
                self._proc.kill()
            except OSError:
                pass


def mux_audio(
    silent_video: str | Path,
    src_audio_from: str | Path,
    out_path: str | Path,
    duration_sec: float,
) -> Path:
    """Mux source audio onto a silent video via stream copy (fast, no re-encode).

    Args:
        silent_video: video-only file (e.g. from :class:`VideoEncoder`).
        src_audio_from: source clip to take the audio track from.
        out_path: final output path.
        duration_sec: trim the output to this length so a sampled/shortened
            text video doesn't inherit the full-length source audio.
    """
    ffmpeg = require_ffmpeg()
    silent = Path(silent_video)
    src = Path(src_audio_from)
    out = Path(out_path)
    if not silent.is_file():
        raise FileNotFoundError(f"video file not found: {silent}")
    if not src.is_file():
        raise FileNotFoundError(f"audio source not found: {src}")
    out.parent.mkdir(parents=True, exist_ok=True)
    acodec = "mp2" if out.suffix.lower() in (".mpeg", ".mpg", ".mpe") else "aac"
    cmd = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(silent),
        "-i",
        str(src),
        "-map",
        "0:v",
        "-map",
        "1:a?",
        "-c:v",
        "copy",
        "-c:a",
        acodec,
        "-t",
        f"{duration_sec:.6f}",
        str(out),
    ]
    proc = subprocess.run(cmd, capture_output=True, timeout=300)
    if proc.returncode != 0:
        err = (proc.stderr or b"").decode("utf-8", "replace")[:1000]
        raise OSError(f"ffmpeg audio mux failed for {out}: {err}")
    return out


def save_text_video(
    images: list[Image.Image],
    out_path: str | Path,
    fps: float,
    src_audio_from: str | Path | None = None,
    keep_audio: bool = True,
    crf: int | None = None,
    gpu: bool = True,
) -> Path:
    """Encode rasterized text frames as a video file (mp4/mpeg/...).

    Args:
        images: RGB frames to encode (all same size).
        out_path: output video path; codec is picked from the suffix.
        fps: output frame rate.
        src_audio_from: optional source video to mux audio from.
        keep_audio: when True and the source has an audio stream, mux it
            (best-effort; output is silent when the source has no audio
            or muxing fails and ``keep_audio`` falls back to silent).
        crf: optional quality hint (only used by codecs that accept -crf).
        gpu: prefer a working hardware encoder, fall back to software.
    """
    import os
    import tempfile

    if not images:
        raise ValueError("no frames to encode")
    out = Path(out_path)
    if out.suffix.lower() not in VIDEO_OUTPUT_SUFFIXES:
        raise ValueError(
            f"unsupported video output {out.suffix!r}, expected one of {sorted(VIDEO_OUTPUT_SUFFIXES)}"
        )
    w, h = images[0].size
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=out.suffix, dir=str(out.parent), delete=False) as tf:
        tmp_silent = Path(tf.name)
    try:
        with VideoEncoder(tmp_silent, fps, (w, h), crf, gpu) as enc:
            for img in images:
                enc.write(img)
        n = enc.frames_written
        audio_src = Path(src_audio_from) if src_audio_from is not None else None
        if keep_audio and audio_src is not None and audio_src.is_file():
            try:
                mux_audio(tmp_silent, audio_src, out, n / fps)
                return out
            except OSError:
                pass  # best-effort: fall back to the silent encode below
        os.replace(tmp_silent, out)
        return out
    finally:
        try:
            if tmp_silent.exists() and tmp_silent.resolve() != out.resolve():
                tmp_silent.unlink()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Parallel frame rendering: decode stays on the main thread (single ffmpeg
# pipe), convert + rasterize fan out to a process pool. Frames are CPU-bound
# in Pillow/FreeType, which holds the GIL, so threads would not help.
# ---------------------------------------------------------------------------

_WORKER_FONT = None
_WORKER_RENDERERS: dict = {}


def _worker_init(font_path: str | None, font_size: int) -> None:
    """Per-process init: resolve the raster font once (not per frame)."""
    global _WORKER_FONT
    from .text_gif import resolve_font

    _WORKER_FONT = resolve_font(font_path, font_size)


def render_frame_task(task: dict) -> dict:
    """Convert + rasterize one decoded frame. Runs in a worker process.

    Task keys: index, digest, raw (bytes), size (w, h), ramp,
    opts (ConvertOptions), color, rasterize. Returns index, digest, grid
    dims, text, and — when rasterize — the RGB bytes + size of the text
    image. The rasterizer (fast row-batch when verified for this font,
    else reference) is built once per worker and cached.
    """
    from PIL import Image

    from .converter import convert
    from .renderer import render
    from .text_gif import font_cell, verified_grid_renderer

    assert _WORKER_FONT is not None
    frame = Image.frombytes("RGB", tuple(task["size"]), bytes(task["raw"]))
    grid = convert(frame, task["ramp"], task["opts"])
    text = render(grid, color=task["color"])
    result: dict = {
        "index": task["index"],
        "digest": task["digest"],
        "dims": (len(grid[0]), len(grid)),
        "text": text,
        "img": None,
        "img_size": None,
    }
    if task["rasterize"]:
        key = task["ramp"]
        renderer = _WORKER_RENDERERS.get(key)
        if renderer is None:
            cell = font_cell(_WORKER_FONT, task["ramp"])
            renderer = verified_grid_renderer(_WORKER_FONT, cell[0], cell[1], task["ramp"])
            _WORKER_RENDERERS[key] = renderer
        img = renderer(grid, task["color"])
        result["img"] = img.tobytes()
        result["img_size"] = img.size
    return result


def estimate_kept_frames(
    meta: dict, sample: int = 1, max_frames: int | None = None
) -> int | None:
    """Estimate frames kept after sampling (None when probe lacks nb_frames)."""
    nb = meta.get("nb_frames") or 0
    if nb <= 0:
        return None
    kept = (nb + sample - 1) // max(sample, 1)
    if max_frames is not None:
        kept = min(kept, max_frames)
    return kept


def resolve_job_count(
    jobs: int, estimated_frames: int | None, threshold: int = 32
) -> int:
    """Workers to use: explicit --jobs wins; 0 = auto (pool only past threshold)."""
    import os

    if jobs < 0:
        raise ValueError("--jobs must be >= 0 (0=auto, 1=serial)")
    if jobs >= 1:
        return jobs
    cpus = os.cpu_count() or 2
    if estimated_frames is not None and estimated_frames >= threshold and cpus > 1:
        return min(cpus, 16)
    return 1
