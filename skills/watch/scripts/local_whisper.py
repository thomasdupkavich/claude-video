#!/usr/bin/env python3
"""Local whisper.cpp transcription backend for /watch.

Added on top of the upstream claude-video plugin, which only ships cloud
backends (Groq / OpenAI). This runs whisper.cpp on the machine instead, so
audio never leaves it and no API key is needed.

Wired into watch.py ahead of the cloud fallback: captions -> local -> cloud.

Config (~/.config/watch/.env, absolute paths required):
    WHISPER_CPP_BIN=/opt/homebrew/bin/whisper-cli
    WHISPER_CPP_MODEL=/Users/<you>/.local/share/whisper-models/ggml-large-v3-turbo.bin
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from config import read_env_file
from transcribe import parse_vtt


def _resolve(name: str) -> str | None:
    """Environment wins, then ~/.config/watch/.env."""
    value = os.environ.get(name) or read_env_file().get(name)
    return value.strip() if value and value.strip() else None


def locate() -> tuple[str, str] | tuple[None, None]:
    """Return (binary, model) if local transcription is usable, else (None, None)."""
    binary = _resolve("WHISPER_CPP_BIN") or shutil.which("whisper-cli") or shutil.which("whisper")
    model = _resolve("WHISPER_CPP_MODEL")
    if not binary or not Path(binary).exists():
        return None, None
    if not model or not Path(model).exists():
        return None, None
    return binary, model


def extract_wav(video_path: str, out_path: Path) -> Path:
    """whisper.cpp wants 16 kHz mono PCM; give it exactly that."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vn", "-ac", "1", "-ar", "16000",
        "-c:a", "pcm_s16le",
        str(out_path),
    ]
    result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if result.returncode != 0 or not out_path.exists():
        raise SystemExit(
            f"ffmpeg could not extract audio for local whisper: "
            f"{result.stderr.decode('utf-8', 'replace')[-400:]}"
        )
    return out_path


def transcribe_video(video_path: str, work_dir: Path) -> tuple[list[dict], str]:
    """Full local flow: extract audio -> whisper.cpp -> VTT -> segments.

    Returns (segments, backend_label). Raises SystemExit on failure so watch.py
    can catch it and fall through to the cloud backend exactly as before.
    """
    binary, model = locate()
    if not binary or not model:
        raise SystemExit("local whisper.cpp not configured")

    wav = extract_wav(video_path, work_dir / "audio-16k.wav")
    prefix = work_dir / "local-transcript"

    print(
        f"[watch] transcribing locally with whisper.cpp ({Path(model).name})…",
        file=sys.stderr,
    )
    cmd = [
        binary,
        "-m", model,
        "-f", str(wav),
        "-ovtt",
        "-of", str(prefix),
        "-pp",              # progress to stderr so a long run isn't silent
        "-t", str(max(1, (os.cpu_count() or 4) - 2)),
    ]
    result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=sys.stderr)

    vtt = prefix.with_suffix(".vtt")
    if result.returncode != 0 or not vtt.exists():
        raise SystemExit(f"whisper.cpp failed (exit {result.returncode})")

    segments = parse_vtt(str(vtt))
    if not segments:
        raise SystemExit("whisper.cpp produced an empty transcript")

    print(f"[watch] transcribed {len(segments)} segments locally", file=sys.stderr)
    return segments, "whisper.cpp (local)"


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: local_whisper.py <video-path> [work-dir]", file=sys.stderr)
        raise SystemExit(2)
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path.cwd()
    segs, label = transcribe_video(sys.argv[1], out)
    print(f"{label}: {len(segs)} segments")
