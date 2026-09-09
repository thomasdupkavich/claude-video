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
- `media.py` — recovers the audio when yt-dlp returns an unmerged video-only
  file, and puts a timeout on every subprocess so nothing hangs forever.
- `watch.py` — refuses videos over `WATCH_MAX_SECONDS` (3h default) *before*
  downloading; writes `manifest.json` so a long capture survives a client
  timeout; extracts frames on a worker thread while transcription runs.
- `download.py` — source resolution now follows the requested frame width and
  prefers H.264. Frames are downscaled anyway, so pulling 720p AV1 to make
  512px JPEGs paid twice: bigger download, far slower decode. Measured on an
  18-minute clip: 30s -> 12s end to end, same 157 scene changes, frames
  visually identical. (videotoolbox hwaccel was tried and is 3x SLOWER on AV1.)
- `frames.py` / `watch.py` — two-pass scene extraction. A 240p proxy is
  downloaded alongside the real file and scene detection runs on that; only the
  ~100 surviving timestamps are then decoded out of the real file, in parallel.
  Measured on Big Buck Bunny (10 min, hard cuts) at 768px: 10.4s -> 4.8s, 132
  cuts found vs 130. Falls back to the single-pass engine if the proxy fails.
- `download.py` — asks for real English captions by name
  (`en,en-US,en-GB,en-orig`) instead of the wildcard `en.*`, which also matched
  YouTube's machine-translated tail and meant 11 subtitle requests to use 1.
  Measured on one video: 11 files -> 2. Falls back to the wildcard once when no
  English track exists, so a foreign-language video still gets a transcript.
- `failures.py` — 17 classified download failures in plain English, each with
  retry advice, a fix command where one exists, and whether the video still
  exists at all. An unrecognized error says so instead of guessing, and the raw
  yt-dlp text is always kept underneath.

## Config
`~/.config/watch/.env` (0600): whisper.cpp binary + model paths, `GROQ_API_KEY`,
`GROQ_WHISPER_MODEL`, `WATCH_DETAIL=balanced`, `SETUP_COMPLETE=true`.

## Before committing
`python3 -m pytest -q` — 95 passed is the bar. Anything less is a regression.

Removing the plugin also removed its SessionStart status line. That hook was
silent once configured, so nothing of value was lost.
