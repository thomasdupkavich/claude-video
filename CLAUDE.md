# claude-video — Thomas's fork

Fork of `bradautomates/claude-video` (the `/watch` skill). This is the LIVE copy:
`~/.claude/skills/watch` is a symlink into `skills/watch/`, so editing a file
here changes `/watch` immediately. No install step, no cache copy, no sync.

## Remotes
- `origin` → `thomasdupkavich/claude-video` (the fork — push here)
- `upstream` → `bradautomates/claude-video` (Brad's, **fetch only**; push URL is
  deliberately broken so nothing can go back to him by accident)

Taking Brad's work: `git fetch upstream`, look at what changed, and cherry-pick
only what's actually an improvement over what's here. Do not blanket-merge —
this fork has diverged on purpose.

## What diverges from upstream
- `skills/watch/scripts/local_whisper.py` — local whisper.cpp backend, tried
  ahead of Groq/OpenAI. No key, no bill, audio never leaves the machine.
- `whisper.py` — Groq model reads `GROQ_WHISPER_MODEL`, defaults to
  `whisper-large-v3-turbo` ($0.04/hr vs $0.111/hr).
- `frames.py` — `-vsync` → `-fps_mode`. ffmpeg 9 removed `-vsync`, which broke
  every frame mode and 21 of 71 tests upstream. Still broken on Brad's main.
- `watch.py` — every report opens with `Result: complete | partial | failed`,
  names which stream is missing and why, and exits 1 when nothing was captured.
- `failures.py` — 17 classified download failures in plain English, each with
  retry advice, a fix command where one exists, and whether the video still
  exists at all. An unrecognized error says so instead of guessing, and the raw
  yt-dlp text is always kept underneath.

## Config
`~/.config/watch/.env` (0600): whisper.cpp binary + model paths, `GROQ_API_KEY`,
`GROQ_WHISPER_MODEL`, `WATCH_DETAIL=balanced`, `SETUP_COMPLETE=true`.

## Before committing
`python3 -m pytest -q` — 92 passed is the bar. Anything less is a regression.

Removing the plugin also removed its SessionStart status line. That hook was
silent once configured, so nothing of value was lost.
