"""yt-dlp argv construction for download.py.

Regression guard: ``--sub-langs all`` makes yt-dlp fetch YouTube's hundreds of
auto-translated caption tracks, which can take minutes and stalls before the
video download even starts. We only support English, so the request must stay
bounded to the English-only pattern.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "skills" / "watch" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import download  # noqa: E402

URL = "https://www.youtube.com/watch?v=rlOpbu3Enkw"


def _capture_argv(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Stub subprocess.run inside download.py and record every argv."""
    calls: list[list[str]] = []

    class _Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd, *args, **kwargs):
        calls.append(list(cmd))
        return _Result()

    monkeypatch.setattr(download.subprocess, "run", fake_run)
    return calls


def _sub_langs(argv: list[str]) -> str:
    idx = argv.index("--sub-langs")
    return argv[idx + 1]


def _assert_english_only(langs: str) -> None:
    tokens = langs.split(",")
    assert "all" not in tokens, f"sub-langs must not request all languages, got {langs!r}"
    assert all(t.startswith("en") for t in tokens), f"sub-langs must be English-only, got {langs!r}"


def test_fetch_captions_requests_english_only(monkeypatch, tmp_path):
    calls = _capture_argv(monkeypatch)
    download.fetch_captions(URL, tmp_path / "download")
    _assert_english_only(_sub_langs(calls[0]))


def test_download_url_requests_english_only(monkeypatch, tmp_path):
    calls = _capture_argv(monkeypatch)
    # _pick_video returns None with no real file, which raises SystemExit after
    # the yt-dlp argv is already built — that's all we need to inspect.
    with pytest.raises(SystemExit):
        download.download_url(URL, tmp_path / "download")
    _assert_english_only(_sub_langs(calls[0]))


def test_english_request_excludes_auto_translated_tail():
    """The old "en.*" also matched YouTube's machine-translated tracks -- en-ja,
    en-es, en-en-US-<hash> -- so a popular video meant 11 subtitle requests to
    use 1. The burst is what earns a 429, and a 429 mid-fetch is what used to
    cost the whole capture."""
    langs = download.SUB_LANGS_ENGLISH.split(",")
    assert len(langs) <= 4, f"too many tracks requested up front: {langs}"
    assert all(l in {"en", "en-US", "en-GB", "en-orig"} for l in langs), langs
    assert "*" not in download.SUB_LANGS_ENGLISH


def test_translated_fallback_is_still_available():
    """A video with no real English track should still get a transcript."""
    assert download.SUB_LANGS_TRANSLATED == "en.*"


def test_fetch_captions_retries_once_for_a_translated_track(monkeypatch, tmp_path):
    """No English found -> exactly one retry with the wider list, never a loop."""
    calls = _capture_argv(monkeypatch)
    download.fetch_captions(URL, tmp_path / "download")
    requested = [_sub_langs(c) for c in calls]
    assert requested == [download.SUB_LANGS_ENGLISH, download.SUB_LANGS_TRANSLATED], requested
