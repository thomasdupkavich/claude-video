"""Download-failure classification: does it name the right cause, and does it
admit when it doesn't know?

Real yt-dlp wording, taken from actual error output rather than invented, so a
site changing its phrasing shows up here first.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills" / "watch" / "scripts"))

import pytest

from failures import classify


# (stderr as yt-dlp really writes it, expected kind)
CASES = [
    ("ERROR: [youtube] id: Sign in to confirm your age. This video may be "
     "inappropriate for some users.", "age_gate"),
    ("ERROR: [youtube] id: Sign in to confirm you're not a bot. Use "
     "--cookies-from-browser or --cookies", "bot_check"),
    ("ERROR: [youtube] id: Join this channel to get access to members-only content",
     "paid_or_members"),
    ("ERROR: [youtube] id: Private video. Sign in if you've been granted access",
     "private"),
    ("ERROR: [twitter] id: The uploader has not made this video available in "
     "your country", "region_blocked"),
    ("ERROR: unable to download video data: HTTP Error 429: Too Many Requests",
     "rate_limited"),
    ("ERROR: [youtube] id: Video unavailable. This video has been removed by "
     "the uploader", "removed"),
    ("ERROR: [youtube] id: This video is unavailable", "not_found"),
    ("ERROR: [youtube] id: This live event will begin in 3 hours", "not_started"),
    ("ERROR: [generic] id: The content is protected by DRM", "drm"),
    ("ERROR: unable to write data: [Errno 28] No space left on device", "disk_full"),
    ("ERROR: File is larger than max-filesize (600000000 bytes > 500000000 bytes)",
     "too_big"),
    ("ERROR: unable to download webpage: <urlopen error [Errno 8] nodename nor "
     "servname provided, or not known> getaddrinfo failed", "network"),
    ("ERROR: Unsupported URL: https://example.com/some/page", "unsupported_site"),
    ("WARNING: [youtube] id: nsig extraction failed: Some formats may be missing",
     "extractor_broken"),
]


@pytest.mark.parametrize("stderr,expected", CASES)
def test_classifies_real_ytdlp_wording(stderr, expected):
    assert classify(stderr).kind == expected


def test_unknown_error_admits_it_is_a_guess():
    """The important property: it must not force a novel error into a category."""
    failure = classify("ERROR: something entirely new and unseen")
    assert failure.kind == "unknown"
    assert failure.recognized is False
    assert "guess" in failure.render()


def test_raw_error_is_always_preserved():
    """A verdict never replaces the original message."""
    raw = "ERROR: [youtube] id: This video is unavailable"
    assert raw in classify(raw).render()


def test_deleted_is_distinguished_from_blocked():
    """'Gone' and 'we could not reach it' must not be conflated -- answering from
    the title is only ever tempting when this distinction is lost."""
    assert classify("ERROR: This video has been removed by the uploader").exists is False
    assert classify("ERROR: Sign in to confirm your age").exists is True
    assert classify("ERROR: getaddrinfo failed").exists is None


def test_a_fix_command_is_offered_where_one_exists():
    assert classify("WARNING: nsig extraction failed").fix == "brew upgrade yt-dlp"


def test_retry_advice_is_always_one_of_the_known_values():
    for stderr, _ in CASES:
        assert classify(stderr).retry in {"never", "later", "after-fix", "unknown"}


def test_render_is_quoted_markdown_throughout():
    """The block is embedded in a report, so every line must stay inside the
    blockquote -- a bare line would break the surrounding document."""
    rendered = classify("ERROR: [youtube] id: Private video").render()
    assert all(line.startswith(">") for line in rendered.splitlines())
