#!/usr/bin/env python3
"""Shared media helpers: stream probing, audio recovery, subprocess limits.

Two problems live here.

**Unmerged downloads.** yt-dlp routinely returns adaptive-streaming sources as a
video-only file and a separate audio file. Picking the video half and handing it
to ffmpeg for audio extraction fails with "Output file does not contain any
stream" -- a message that names the symptom and hides the cause. Look for the
companion file instead.

**Runaway subprocesses.** A stalled yt-dlp or ffmpeg with no timeout hangs
forever, and the caller cannot tell a slow download from a dead one.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path


# Generous by design: local transcription of a multi-hour recording legitimately
# runs for many minutes. The point is that it ends, not that it ends quickly.
SUBPROCESS_TIMEOUT = int(os.environ.get("WATCH_SUBPROCESS_TIMEOUT", "3600"))

_AUDIO_EXTS = {".m4a", ".mp3", ".opus", ".ogg", ".webm", ".aac", ".wav", ".flac"}
_SKIP_EXTS = {".json", ".vtt", ".srt", ".part", ".ytdl", ".jpg", ".png"}


def run(cmd: list[str], *, timeout: int | None = None, **kwargs) -> subprocess.CompletedProcess:
    """subprocess.run with a timeout that is always set.

    A TimeoutExpired is converted to a normal failed result carrying an
    explanatory stderr, so every caller's existing returncode check handles a
    hang the same way it handles any other failure.
    """
    limit = SUBPROCESS_TIMEOUT if timeout is None else timeout
    try:
        return subprocess.run(cmd, timeout=limit, **kwargs)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=124,  # conventional timeout status
            stdout="" if kwargs.get("text") else b"",
            stderr=(
                f"{Path(cmd[0]).name} was killed after {limit}s without finishing. "
                f"Raise WATCH_SUBPROCESS_TIMEOUT if this source legitimately takes longer."
            )
            if kwargs.get("text")
            else b"timed out",
        )


def probe_streams(path: Path | str) -> set[str]:
    """Which stream kinds ffprobe finds: {"video"}, {"audio"}, both, or empty.

    An EMPTY set means "could not tell" -- no ffprobe, or an unreadable file --
    and is never treated as "no audio". Refusing on an unknown would turn a
    diagnostic gap into a failure.
    """
    if shutil.which("ffprobe") is None:
        return set()
    result = run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "stream=codec_type",
            "-of", "json", str(path),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        return set()
    try:
        streams = json.loads(result.stdout).get("streams", [])
    except (ValueError, AttributeError):
        return set()
    return {s.get("codec_type") for s in streams if s.get("codec_type")}


def resolve_audio_source(video_path: Path | str, work_dir: Path | str) -> Path:
    """The file to actually pull audio from.

    Returns the original unless it demonstrably has no audio track AND a sibling
    in the same directory does -- the unmerged-download case. Anything uncertain
    returns the original and lets ffmpeg decide.
    """
    video = Path(video_path)
    streams = probe_streams(video)
    if not streams or "audio" in streams:
        return video

    work = Path(work_dir)
    candidates = sorted(
        p for p in work.rglob("*")
        if p.is_file()
        and p != video
        and p.suffix.lower() not in _SKIP_EXTS
    )
    # Prefer files that look like audio before probing everything else.
    candidates.sort(key=lambda p: p.suffix.lower() not in _AUDIO_EXTS)

    for candidate in candidates:
        if "audio" in probe_streams(candidate):
            return candidate
    return video
