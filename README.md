# /watch

**Give Claude the ability to watch any video.**

Paste a URL or a local path, ask a question, and Claude downloads the video,
pulls a timestamped transcript, extracts the frames where the picture actually
changes, and looks at every one of them. By the time it answers, it has *seen*
the video and *heard* the audio.

```
/watch https://youtu.be/dQw4w9WgXcQ what happens at the 30 second mark?
```

Transcription runs **on your own machine** by default. No key, no per-minute
bill, and the audio never leaves the Mac.

---

## What it does, in order

1. **Asks the site about the video** — length, title, captions — before
   downloading anything. Too long, and it stops here and says so.
2. **Downloads only what it needs.** The source resolution follows the frame
   size you asked for, and H.264 is preferred over AV1 because it decodes
   several times faster.
3. **Finds the cuts on a throwaway 240p copy**, then decodes only those moments
   out of the real file. Locating a shot change needs no detail; rendering it
   does.
4. **Gets the transcript** — native captions if they exist, otherwise local
   `whisper.cpp`, otherwise a cloud fallback if you configured one.
5. **Writes a record to disk** so a long capture survives a client timeout.
6. **Hands Claude the frames and the transcript.**

Steps 3 and 4 run at the same time.

## Detail modes

| Mode | Frames | Engine |
|------|--------|--------|
| `transcript` | none | skips the download entirely when captions exist |
| `efficient` | up to 50 | keyframes only, near-instant |
| `balanced` *(default)* | up to 100 | scene-aware, duplicates dropped |
| `token-burner` | uncapped | every scene change, whole video |

Set the default with `WATCH_DETAIL` in `~/.config/watch/.env`.

## Options

- `--detail transcript|efficient|balanced|token-burner`
- `--start T` / `--end T` — focus on a section, at a denser frame rate
- `--timestamps T1,T2,…` — pin a frame at exact moments
- `--resolution W` — frame width (default 512; 1024 to read on-screen text,
  which automatically pulls a larger source)
- `--max-frames N`, `--fps F`, `--max-duration S`
- `--no-dedup` — keep near-identical frames
- `--no-whisper` — skip transcription entirely
- `--whisper groq|openai` — force a cloud backend
- `--out-dir DIR`

## Every report says what it got

```
- **Result:** partial — no transcript
> **No transcript.** Local whisper.cpp failed: model file not found.
> Nothing below reflects what was said.
```

`complete`, `partial`, or `failed`. A run that captured nothing exits non-zero,
so it can never be mistaken for an empty video. A download that fails is
classified into one of 17 plain-English causes — age gate, members-only,
region, deleted, stale yt-dlp — each with whether a retry can help and the
command that would fix it. An unrecognised error says it is a guess and prints
the original.

## Setup

```bash
python3 skills/watch/scripts/setup.py
```

Installs `ffmpeg` and `yt-dlp`, and scaffolds `~/.config/watch/.env` at `0600`.

For local transcription:

```bash
brew install whisper-cpp
# then in ~/.config/watch/.env, absolute paths:
WHISPER_CPP_BIN=/opt/homebrew/bin/whisper-cli
WHISPER_CPP_MODEL=/path/to/ggml-large-v3-turbo.bin
```

A large-turbo model is ~1.5 GB and runs at roughly 16x realtime on Apple
Silicon. Nothing runs in the background — it launches per video and exits.

## Tests

```bash
python3 -m pytest -q      # 95 passed
```

## Credits

Built on `yt-dlp`, `ffmpeg`, `whisper.cpp`, and Claude's multimodal `Read`.

Forked from [bradautomates/claude-video](https://github.com/bradautomates/claude-video)
by Bradley Bonanno, and diverged substantially since — local transcription,
two-pass scene extraction, result reporting, failure classification, resource
guards, and an ffmpeg 9 fix. MIT licensed; see `LICENSE`.
