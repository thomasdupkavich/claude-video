# Fork divergences from `bradautomates/claude-video`

This fork is deliberately not a drop-in mirror of upstream. `AGENTS.md` remains upstream-owned so
cherry-picks stay clean; the behavior below is maintained here.

## Source and remotes

- `~/.claude/skills/watch` is a symlink into `skills/watch/`. This repository is the live source;
  there is no install, cache copy, or sync step.
- `origin` is `thomasdupkavich/claude-video` and is the only push target.
- `upstream` is `bradautomates/claude-video` and is fetch-only. Its push URL is intentionally
  broken. Selectively cherry-pick improvements after comparing them with this fork.
- Ignore upstream's plugin-install row, `dev-sync.sh`, and `hooks/` SessionStart hook; this fork
  does not use them.

## Intentional runtime behavior

- `local_whisper.py` tries local whisper.cpp before Groq or OpenAI. Audio stays local when that
  route succeeds.
- Groq uses `GROQ_WHISPER_MODEL`, defaulting to `whisper-large-v3-turbo`.
- Frame extraction uses ffmpeg `-fps_mode`, not removed `-vsync`.
- Reports begin with `Result: complete | partial | failed`, identify missing streams and reasons,
  and exit nonzero when nothing was captured.
- Media recovery handles yt-dlp video-only output. Every subprocess has a timeout.
- Videos exceeding `WATCH_MAX_SECONDS` (three hours by default) are rejected before download.
  `manifest.json` lets a long capture survive a client timeout.
- Frame extraction can run while transcription runs. Download selection follows requested frame
  width and prefers H.264 to avoid needless high-resolution AV1 work.
- Scene extraction uses a low-resolution proxy for detection, then decodes only retained
  timestamps from the real file. It falls back to single-pass extraction if the proxy fails.
- Caption selection requests real English tracks first (`en`, `en-US`, `en-GB`, `en-orig`) and
  uses the `en.*` fallback only when those tracks do not exist.
- Download errors are classified in `failures.py`. Preserve raw yt-dlp output and never invent a
  diagnosis for an unrecognized failure.

## Configuration and verification

- `~/.config/watch/.env` contains the whisper.cpp binary/model paths, `GROQ_API_KEY`,
  `GROQ_WHISPER_MODEL`, `WATCH_DETAIL=balanced`, and `SETUP_COMPLETE=true`.
- Run `python3 -m pytest -q` before a commit. Any failed test is a regression to resolve.
