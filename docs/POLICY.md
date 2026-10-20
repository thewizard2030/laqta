# Laqta Policy

The rules that decide what Laqta is allowed to do with your media, with a
third-party service and with content you did not create.

This document is public on purpose: it is the contract between the project
and the person using it. The engineering rules that enforce it live in
[`AGENTS.md`](../AGENTS.md) and in the code.

---

## 1. Local-first by default

Laqta is built so that the **normal** path never touches the network:

- Media files are **copied** into your local data directory
  (`~/.local/share/qatta` by default). Your original file is never modified or
  moved.
- Audio extraction, transcription, clip ranking, caption rendering and export
  all run on your machine.
- There is **no telemetry, no analytics and no crash reporting**. Laqta has
  no phone-home path.
- The API binds to `127.0.0.1` and its CORS allow-list is explicit — never a
  wildcard.

## 2. What leaves your machine, and when

| Feature | What leaves | When it is allowed |
|---------|-------------|--------------------|
| Local transcription (faster-whisper) | nothing | always available, no key |
| Local clip ranking (deterministic CPS) | nothing | always available |
| URL import (yt-dlp) | the URL you typed | only with `QATTA_ENABLE_URL_INGESTION=true` **and** a per-import rights confirmation |
| Hosted ranker (OpenRouter / Groq / OpenAI-compatible) | the transcript text of the window being scored | only with `QATTA_ALLOW_CLOUD_APIS=true` **and** `QATTA_LLM_HOSTED_OPT_IN=true` **and** a configured key |
| Hosted transcription (Groq / AssemblyAI) | the audio of the segment | only with the same two flags **and** a key |

All three hosted paths are **fail-closed**. If a flag is off, or the key is
missing, or the opt-in is not given, the local path is used and the interface
says so. The orchestrator refuses a gated stage with an explicit error rather
than silently falling back.

The studio UI shows a persistent disclosure while a hosted provider is active,
and the CLI (`laqta doctor`) reports the same state.

## 3. Rights and responsibilities for URL imports

**You are responsible for having the right to use the material you import.**

- URL ingestion is **available by default** (it needs `yt-dlp`, which is part
  of the "everything" install profile). Set `QATTA_ENABLE_URL_INGESTION=false`
  to remove it entirely — the import button then stays visible but refuses
  with the reason.
- Every import requires a **per-import rights confirmation** in the dialog.
  The confirmation is a statement by you, not a check by Laqta.
- The default sources are caption tracks and the sections that the ranker
  selects — Laqta does not need to download a full video to work with a
  YouTube source, and it does not redistribute anything.
- Respect the copyright of the material, the terms of the platform, and the
  law in your jurisdiction. Downloading is not the same as being allowed to
  publish.
- Laqta is a tool. It is not a legal opinion, and it cannot tell you whether
  a particular video may be used.

**Anti-bot circumvention is not a feature.** If a platform blocks a download,
that block is respected; the application surfaces the error instead of
working around it.

## 4. Model weights and licences

Laqta does **not** ship model weights.

| Component | Licence | Note |
|-----------|---------|------|
| faster-whisper / CTranslate2 | MIT | Runs the Whisper models |
| OpenAI Whisper model weights | MIT | Downloaded on first use into the Hugging Face cache |
| FFmpeg | LGPL 2.1+ / GPL 2.0+ | Executed as a subprocess, never linked |
| libass | ISC | Subtitle rendering |

See [`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md) for the full list.

The first run downloads the speech model once (145 MB for `base`, ~1.5 GB for
`medium`). After that the studio works offline.

## 5. Dependency licence policy

Only **MIT, Apache-2.0, BSD, ISC and Unlicense** dependencies are allowed.
**AGPL-3.0 is forbidden** — including `ultralytics` (YOLOv8). Anything new
must be licence-compatible, documented in `THIRD_PARTY_NOTICES.md` and, if it
is heavy, optional and lazily imported.

## 6. Honest reporting

Laqta must never present a stub, a mock, an estimate or a partial result as a
finished one.

- The capability probe reports what is actually installed.
- The Clip Potential Score is a **heuristic editorial quality signal**, not a
  prediction of views, retention or virality.
- Word-level alignment, RTL correctness and speaker detection are only
  claimed where they are implemented and tested.
- Progress and job states come from the persisted job record, not from an
  optimistic UI.

## 7. Privacy of the local data directory

- The data directory holds your media, transcripts, manifests, renders and a
  SQLite database. It is **not encrypted at rest**.
- Anyone with access to your user account can read it.
- It is excluded from the repository (`.gitignore`) and from the release
  archives.
- When you share a machine, a bug report or a log, check it first.

## 8. Reporting a policy problem

If Laqta behaves differently from what this document says — for example if
data leaves the machine without the stated opt-in — treat it as a security
issue and report it privately as described in [SECURITY.md](../SECURITY.md).
