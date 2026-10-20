# Support

## Where to ask

| Your question | Where |
|---------------|-------|
| "How do I …?" (usage, setup, configuration) | [GitHub Discussions](https://github.com/thewizard2030/laqta/discussions) |
| "This is broken" (a reproducible bug) | [GitHub Issues](https://github.com/thewizard2030/laqta/issues) — use the **Bug report** template |
| "I would like …" (a feature) | [GitHub Issues](https://github.com/thewizard2030/laqta/issues) — use the **Feature request** template |
| "Is this safe?" (a security problem) | **Do not open an issue** — see [SECURITY.md](SECURITY.md) |
| "How do I contribute?" | [CONTRIBUTING.md](CONTRIBUTING.md) |
| "Why is it called Laqta?" | [docs/BRANDING.md](docs/BRANDING.md) |

## Before you open an issue

Most reports can be answered with one command:

```bash
backend/.venv/bin/laqta doctor
```

It prints exactly what is installed and what is missing — FFmpeg, FFprobe,
the local speech model, yt-dlp, the data directory, the disk and whether a
hosted ranker is configured. Please include its output in any bug report.

## Common questions

**The first transcription is slow.**
The speech model is downloaded on first use (145 MB for `base`, ~1.5 GB for
`medium`) and then cached. After that, everything runs offline.

**"No local ASR installed".**
Install the recommended profile:
`pip install -r backend/requirements-asr.txt`. The app still runs without it —
the studio reports the missing capability instead of pretending it works.

**"FFmpeg was not found on this machine".**
Install FFmpeg with libass (`sudo dnf install ffmpeg libass` on Fedora,
`brew install ffmpeg` on macOS, `choco install ffmpeg` on Windows). Rendering
and thumbnail extraction need it; importing does not.

**The studio says a hosted ranker is enabled.**
Somebody set `QATTA_ALLOW_CLOUD_APIS=true` and
`QATTA_LLM_HOSTED_OPT_IN=true` and configured a key. In that mode the
transcript of the window being scored is sent to that provider. Unset the
key to return to fully local behaviour — the deterministic ranker takes over.

**Can I use it on a machine without a GPU?**
Yes. Laqta is CPU-first and targets an 8 GB RAM reference machine. Use the
`fast` profile and a smaller model on modest hardware.

**Does it upload my video?**
No. Media is copied into your local data directory and processed there. The
only exception is a hosted provider you explicitly configured and consented to
— see [docs/POLICY.md](docs/POLICY.md).

## Language

The project is Arabic-first. Issues and discussions in Arabic and English are
both welcome; Arabic issues get Arabic replies.
