@AGENTS.md

## Fork-specific instructions

- This is the live `/watch` source. `~/.claude/skills/watch` points to `skills/watch/`; changes here take effect immediately.
- Preserve the intentional fork behavior. Before changing watch, download, frame extraction, media, Whisper, or failure handling, read `docs/fork-divergences.md`.
- Fetch from `upstream` and push only to `origin`. Review upstream changes and cherry-pick individual improvements; never blanket-merge upstream.
- Runtime configuration is `~/.config/watch/.env` (0600).
- Before committing, run `python3 -m pytest -q`. Do not commit with test failures.
