#!/usr/bin/env python3
"""Download a video via yt-dlp, or resolve a local file path.

Also fetches subtitles (manual first, then auto-generated) in VTT format so
transcribe.py can parse them without needing Whisper.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

from media import run as run_cmd


VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".mov", ".m4v", ".avi", ".flv", ".wmv"}


class DownloadFailed(SystemExit):
    """yt-dlp produced no file. Carries the raw stderr so the caller can say why.

    Subclasses SystemExit so every existing caller that treats a failed download
    as fatal keeps working unchanged; the added stderr is what lets a caller that
    wants to explain the failure do so.
    """

    def __init__(self, stderr: str, returncode: int) -> None:
        super().__init__(f"yt-dlp produced no video file (exit {returncode})")
        self.stderr = stderr
        self.returncode = returncode


def is_url(source: str) -> bool:
    if source.startswith("-"):
        return False
    parsed = urlparse(source)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def resolve_local(path: str) -> dict:
    p = Path(path).expanduser().resolve()
    if not p.exists():
        raise SystemExit(f"File not found: {p}")
    if p.suffix.lower() not in VIDEO_EXTS:
        print(
            f"[watch] warning: {p.suffix} is not a known video extension, proceeding anyway",
            file=sys.stderr,
        )
    return {
        "video_path": str(p),
        "subtitle_path": None,
        "info": {"title": p.name, "url": str(p)},
        "downloaded": False,
    }


def _pick_subtitle(out_dir: Path) -> Path | None:
    candidates = sorted(out_dir.glob("video*.vtt"))
    if not candidates:
        return None
    preferred = [
        c for c in candidates
        if any(marker in c.name for marker in (".en.", ".en-US.", ".en-GB.", ".en-orig."))
    ]
    return preferred[0] if preferred else candidates[0]


def _pick_video(out_dir: Path) -> Path | None:
    for ext in (".mp4", ".mkv", ".webm", ".mov", ".m4a", ".mp3", ".opus"):
        for candidate in out_dir.glob(f"video*{ext}"):
            return candidate
    for candidate in out_dir.glob("video.*"):
        if candidate.suffix.lower() in VIDEO_EXTS:
            return candidate
    return None


def fetch_captions(url: str, out_dir: Path) -> dict:
    """Fetch metadata and best available VTT captions without downloading video."""
    if shutil.which("yt-dlp") is None:
        raise SystemExit("yt-dlp is not installed. Install with: brew install yt-dlp")

    out_dir.mkdir(parents=True, exist_ok=True)
    output_template = str(out_dir / "video.%(ext)s")
    cmd = [
        "yt-dlp",
        "--skip-download",
        "--write-info-json",
        "--write-subs",
        "--write-auto-subs",
        "--sub-langs", "en.*",
        "--sub-format", "vtt",
        "--convert-subs", "vtt",
        "--no-playlist",
        "--ignore-errors",
        "-o", output_template,
        "--",
        url,
    ]
    run_cmd(cmd, stdout=sys.stderr, stderr=sys.stderr)
    subtitle = _pick_subtitle(out_dir)
    info = _read_info(out_dir / "video.info.json", url)
    return {
        "video_path": None,
        "subtitle_path": str(subtitle) if subtitle else None,
        "info": info or {"url": url},
        "downloaded": False,
    }


def _read_info(info_path: Path, url: str) -> dict:
    info: dict = {}
    if info_path.exists():
        try:
            raw = json.loads(info_path.read_text(encoding="utf-8"))
            info = {
                "title": raw.get("title"),
                "uploader": raw.get("uploader") or raw.get("channel"),
                "duration": raw.get("duration"),
                "url": raw.get("webpage_url") or url,
            }
        except Exception as exc:
            print(f"[watch] info.json parse failed: {exc}", file=sys.stderr)
            info = {"url": url}
    return info


# A ceiling so a mis-typed link cannot quietly pull tens of gigabytes. Generous
# enough that ordinary long-form video passes untouched.
MAX_DOWNLOAD_BYTES = int(os.environ.get("WATCH_MAX_BYTES", str(2_000_000_000)))


def source_height_for(frame_width: int) -> int:
    """Smallest source that still exceeds the frame width being extracted.

    Frames are downscaled anyway, so pulling 720p to make 512px JPEGs costs
    download time and -- far more -- decode time, for no visible gain. Measured
    on an 18-minute clip: 480p H.264 detected the same 157 scene changes as
    720p AV1 in 5.5s instead of 13.5s, from a 21 MB file instead of 52 MB.
    """
    if frame_width <= 512:
        return 480
    if frame_width <= 768:
        return 720
    return 1080


def _video_format(max_height: int) -> str:
    """Prefer H.264 at the chosen height; fall back rather than fail.

    H.264 decodes several times faster than AV1 in software, and hardware
    decode is not a way out: videotoolbox on AV1 measured 3x SLOWER than plain
    software decode because of the copy-back overhead.
    """
    return (
        f"bv*[height<={max_height}][vcodec^=avc1]+ba/"
        f"b[height<={max_height}][vcodec^=avc1]/"
        f"bv*[height<={max_height}]+ba/b[height<={max_height}]/"
        f"bv*+ba/b"
    )


def download_url(
    url: str,
    out_dir: Path,
    audio_only: bool = False,
    max_height: int = 480,
) -> dict:
    if shutil.which("yt-dlp") is None:
        raise SystemExit("yt-dlp is not installed. Install with: brew install yt-dlp")

    out_dir.mkdir(parents=True, exist_ok=True)
    output_template = str(out_dir / "video.%(ext)s")

    fmt = "ba/bestaudio" if audio_only else _video_format(max_height)
    cmd = [
        "yt-dlp",
        "-N", "8",
        "--max-filesize", str(MAX_DOWNLOAD_BYTES),
        "-f", fmt,
        "--merge-output-format", "mp4",
        "--write-info-json",
        "--write-subs",
        "--write-auto-subs",
        "--sub-langs", "en.*",
        "--sub-format", "vtt",
        "--convert-subs", "vtt",
        "--no-playlist",
        "--ignore-errors",
        "-o", output_template,
        "--",
        url,
    ]

    # yt-dlp may exit non-zero if a subtitle variant fails (e.g. 429) even when
    # the video itself downloaded fine. Treat "video file present" as success.
    #
    # stderr is captured rather than streamed so a failure can be classified into
    # a plain-English cause; it is echoed either way, so nothing is hidden.
    result = run_cmd(cmd, stdout=sys.stderr, stderr=subprocess.PIPE, text=True)
    if result.stderr:
        print(result.stderr, file=sys.stderr, end="")
    video = _pick_video(out_dir)
    if video is None:
        raise DownloadFailed(result.stderr or "", result.returncode)

    subtitle = _pick_subtitle(out_dir)
    info = _read_info(out_dir / "video.info.json", url)

    return {
        "video_path": str(video),
        "subtitle_path": str(subtitle) if subtitle else None,
        "info": info or {"url": url},
        "downloaded": True,
    }


def download(
    source: str,
    out_dir: Path,
    audio_only: bool = False,
    max_height: int = 480,
) -> dict:
    if is_url(source):
        return download_url(source, out_dir, audio_only=audio_only, max_height=max_height)
    return resolve_local(source)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: download.py <url-or-path> <out-dir>", file=sys.stderr)
        raise SystemExit(2)
    result = download(sys.argv[1], Path(sys.argv[2]))
    print(json.dumps(result, indent=2))


def download_proxy(url: str, out_dir: Path, height: int = 240) -> Path | None:
    """A tiny copy used only to locate scene changes.

    Never shown to anyone -- it exists so the expensive decode can be replaced
    by a cheap one. Returns None on any failure; the caller falls back to
    single-pass extraction rather than losing the run over an optimisation.
    """
    if shutil.which("yt-dlp") is None:
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    template = str(out_dir / "proxy.%(ext)s")
    result = run_cmd(
        [
            "yt-dlp", "-q", "--no-warnings",
            "-f", f"bv*[height<={height}][vcodec^=avc1]/bv*[height<={height}]/worstvideo",
            "--no-playlist", "--no-cache-dir",
            "-o", template, "--", url,
        ],
        capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0:
        return None
    for candidate in sorted(out_dir.glob("proxy.*")):
        if candidate.suffix.lower() in VIDEO_EXTS:
            return candidate
    return None
