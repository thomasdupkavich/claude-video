#!/usr/bin/env python3
"""Turn a download failure into a plain-English verdict with a fix.

A raw yt-dlp traceback tells you the symptom. This tells you the cause, whether
retrying can ever work, and the exact command that would fix it.

Three things this does that a plain pattern table does not:

1. **Separates "we could not get it" from "it is not there."** A private video
   and a stale extractor produce similar noise, and answering from the title
   because the tool said "error" is the failure mode worth designing against.
2. **Diagnoses the most common real cause.** Most sudden breakage on a site that
   worked last week is an outdated yt-dlp, not a restriction. When the failure
   is extractor-shaped, this checks how old the installed yt-dlp is and says so,
   with the upgrade command, instead of blaming the video.
3. **Never hides the original error.** The verdict comes first, the raw text
   stays underneath, and an unrecognized failure says plainly that it is
   unrecognized rather than being forced into the nearest category.
"""
from __future__ import annotations

import datetime as _dt
import re
import shutil
import subprocess
from dataclasses import dataclass, field


# How old an installed yt-dlp has to be before it becomes a prime suspect for an
# extractor failure. Sites change their delivery every few weeks.
STALE_AFTER_DAYS = 30


@dataclass
class Failure:
    kind: str                     # stable machine-readable slug
    headline: str                 # one line, plain English, no jargon
    detail: str                   # what it means for the caller
    retry: str                    # "never" | "later" | "after-fix" | "unknown"
    fix: str = ""                 # literal command to run, when one exists
    exists: bool | None = None    # does the video exist? None = cannot tell
    recognized: bool = True
    raw: str = ""
    notes: list[str] = field(default_factory=list)

    def render(self) -> str:
        """Markdown block for the watch report."""
        lines = [f"> **Download failed — {self.headline}**", ">"]
        lines.append(f"> {self.detail}")
        retry_text = {
            "never": "Retrying will not help.",
            "later": "This may work later; nothing to change.",
            "after-fix": "Retry after the fix below.",
            "unknown": "Whether a retry helps is unknown.",
        }[self.retry]
        lines += [">", f"> _{retry_text}_"]
        if self.fix:
            lines += [">", f"> Fix: `{self.fix}`"]
        for note in self.notes:
            lines += [">", f"> {note}"]
        if self.exists is False:
            lines += [">", "> The video is gone, not blocked. There is nothing to capture."]
        if not self.recognized:
            lines += [
                ">",
                "> This error did not match any known cause, so the reading above is a guess. "
                "The original message is below — trust it over this verdict.",
            ]
        if self.raw:
            lines += [">", "> ```", *(f"> {ln}" for ln in self.raw.strip().splitlines()[-6:]), "> ```"]
        return "\n".join(lines)


# Ordered narrowest-first: age-gate wording overlaps bot-check wording, and
# "unavailable" appears inside many more specific messages.
_RULES: list[tuple[str, str, dict]] = [
    (r"sign in to confirm your age|age.?restricted|inappropriate for some users",
     "age_gate",
     dict(headline="the site is age-gating this video",
          detail="It wants a signed-in adult account before it will serve the file.",
          retry="never", exists=True)),

    (r"confirm you'?re not a bot|captcha|unusual traffic",
     "bot_check",
     dict(headline="the site thinks you're a bot",
          detail="An automation challenge is in the way. Solving it would mean pretending to be a browser, which this does not do.",
          retry="later", exists=True)),

    (r"members.?only|join this channel|subscribe to watch|premium|requires payment|purchase",
     "paid_or_members",
     dict(headline="this is behind a paid or members-only wall",
          detail="An account with access is required. No account is used here.",
          retry="never", exists=True)),

    (r"private video|this video is private",
     "private",
     dict(headline="the video is private",
          detail="The owner restricted it to specific people.",
          retry="never", exists=True)),

    (r"sign in|login required|log in|authentication",
     "login_required",
     dict(headline="the site requires a login",
          detail="It will not serve the file to a signed-out request.",
          retry="never", exists=True)),

    (r"available in your country|geo.?restrict|geo.?block|not available from your location|not available in your region",
     "region_blocked",
     dict(headline="this video isn't available in your country",
          detail="The site serves it elsewhere but not from your location.",
          retry="never", exists=True,
          fix="")),

    (r"429|too many requests|rate.?limit",
     "rate_limited",
     dict(headline="you're being rate-limited",
          detail="Too many requests in a short window. The block is temporary and lifts on its own.",
          retry="later", exists=True)),

    (r"removed by the uploader|has been removed|account associated with this video has been terminated|no longer available",
     "removed",
     dict(headline="the video was deleted",
          detail="The uploader or the platform took it down.",
          retry="never", exists=False)),

    (r"video (?:is )?unavailable|content (?:is )?unavailable|does not exist|404|not found",
     "not_found",
     dict(headline="there's no video at that link",
          detail="The URL points at nothing the site will serve.",
          retry="never", exists=False)),

    (r"this live event will begin|premieres in|scheduled to start",
     "not_started",
     dict(headline="this hasn't started yet",
          detail="It's a scheduled stream or premiere.",
          retry="later", exists=True)),

    (r"is still live|live stream|currently live",
     "still_live",
     dict(headline="this is still streaming live",
          detail="There is no finished file to download until the stream ends.",
          retry="later", exists=True)),

    (r"drm|protected content|widevine",
     "drm",
     dict(headline="the video is DRM-protected",
          detail="It is encrypted at the source. Nothing here decrypts it.",
          retry="never", exists=True)),

    (r"no space left on device|disk full",
     "disk_full",
     dict(headline="your disk is full",
          detail="The download had nowhere to go.",
          retry="after-fix", exists=True,
          fix="df -h / && rm -rf ${TMPDIR}watch-*")),

    (r"larger than max.?filesize|file is larger",
     "too_big",
     dict(headline="the file is bigger than the size limit",
          detail="The download stopped before finishing on purpose.",
          retry="after-fix", exists=True)),

    (r"getaddrinfo|name or service not known|temporary failure in name resolution|connection refused|network is unreachable|timed out",
     "network",
     dict(headline="your machine couldn't reach the site",
          detail="This is a connectivity problem on your end, not a restriction on theirs.",
          retry="later", exists=None)),

    (r"unsupported url|no suitable extractor",
     "unsupported_site",
     dict(headline="yt-dlp doesn't know this site",
          detail="There is no extractor for this domain. A direct file link may still work.",
          retry="never", exists=None)),

    # Deliberately last of the recognized rules: these strings appear inside a
    # lot of unrelated noise, and an outdated extractor is the usual cause.
    (r"nsig extraction failed|signature extraction|unable to extract|failed to parse json|no video formats found|requested format is not available",
     "extractor_broken",
     dict(headline="the site changed and yt-dlp can't read it",
          detail="This is almost always an out-of-date yt-dlp rather than anything wrong with the video.",
          retry="after-fix", exists=True,
          fix="brew upgrade yt-dlp")),
]


def ytdlp_age_days() -> int | None:
    """How many days old the installed yt-dlp is, or None if it can't be told."""
    if shutil.which("yt-dlp") is None:
        return None
    try:
        out = subprocess.run(
            ["yt-dlp", "--version"], capture_output=True, text=True, timeout=10
        ).stdout.strip()
        released = _dt.date(*(int(part) for part in out.split(".")[:3]))
    except Exception:
        return None
    return (_dt.date.today() - released).days


def classify(stderr: str, returncode: int = 1) -> Failure:
    """Read a download failure and say what actually went wrong."""
    text = (stderr or "").lower()

    for pattern, kind, fields in _RULES:
        if re.search(pattern, text):
            failure = Failure(kind=kind, raw=stderr or "", **fields)
            break
    else:
        failure = Failure(
            kind="unknown",
            headline="the download failed for a reason this doesn't recognize",
            detail="No known cause matched. The site may have changed, or this may be new.",
            retry="unknown",
            exists=None,
            recognized=False,
            raw=stderr or "",
        )

    # An outdated yt-dlp is the most common real cause of sudden breakage on a
    # site that worked before, so name it whenever the failure could be that.
    if failure.kind in ("extractor_broken", "unknown", "not_found", "unsupported_site"):
        age = ytdlp_age_days()
        if age is not None and age > STALE_AFTER_DAYS:
            failure.notes.append(
                f"Your yt-dlp is {age} days old. Sites change how they serve video every "
                "few weeks, so that is the likely cause before anything about this video is."
            )
            if not failure.fix:
                failure.fix = "brew upgrade yt-dlp"
                failure.retry = "after-fix"

    return failure


if __name__ == "__main__":
    import sys

    print(classify(sys.stdin.read()).render())
