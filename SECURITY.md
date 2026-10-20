# Security Policy

Laqta is a **local-first** application. Your media is meant to stay on your
machine. This document explains what that means in practice, how to report a
problem, and what the maintainers will and will not do.

---

## Reporting a vulnerability

**Please do not open a public issue for a security problem.**

Report it privately through GitHub Security Advisories:

> <https://github.com/thewizard2030/laqta/security/advisories/new>

If that route is unavailable, open a regular issue that says only *"security
report — please contact me privately"* and nothing else. The maintainer will
reply with a private channel.

Please include:

- the Laqta version (`laqta --version`) and the commit you tested,
- your operating system, Python and Node versions,
- what an attacker can achieve, and the steps to reproduce it,
- whether any user data is involved.

### What to expect

| Stage | Target |
|-------|--------|
| Acknowledgement | 3 days |
| Triage (valid / not valid) | 7 days |
| Fix or mitigation for confirmed issues | 30 days, sooner if the risk is high |
| Public disclosure | After a fix is released, coordinated with the reporter |

We are happy to credit you in the advisory and the changelog. Please give us a
reasonable window before disclosing publicly.

### What is in scope

- Anything that causes the application to send user data off the machine
  without the explicit, documented opt-in.
- Path traversal or command injection through media, transcripts, captions,
  file names or URLs.
- The local API being reachable from outside the machine when the user
  believes it is not.
- A bypass of the URL-ingestion gate or of the per-import rights confirmation.
- Secrets, keys or tokens being written to logs, manifests, exports or the
  SQLite database.
- Unsafe deserialisation of manifests, job payloads or candidate data.

### What is out of scope

- Running Laqta with `--host 0.0.0.0` on an untrusted network. The API has no
  authentication by design; binding it to a public interface exposes it.
- The optional **hosted** providers (OpenRouter, Groq, AssemblyAI). These send
  transcript text to a third party **by design and with a visible
  disclosure**. Report a bug if the disclosure is missing or wrong — not the
  existence of the feature.
- yt-dlp or YouTube's own behaviour when importing a URL.
- Vulnerabilities in the model weights or in upstream libraries without a
  Laqta-specific mitigation.
- Denial of service by feeding the application a deliberately hostile
  multi-gigabyte file on your own machine.

---

## Threat model

### Trust boundaries

```
┌───────────────────────────────────────────────────────────────┐
│ Your machine                                                  │
│                                                               │
│  ┌──────────────┐    ┌────────────────────────────────────┐  │
│  │ Browser      │◀──▶│ FastAPI (127.0.0.1:8000)            │  │
│  │ (the studio) │    │  • project store (SQLite)           │  │
│  └──────────────┘    │  • job queue (single worker)        │  │
│                       │  • media files (copied, never moved) │  │
│                       └──────────────┬─────────────────────┘  │
│                                      │ subprocess argv, no shell│
│                               ┌──────▼───────┐                 │
│                               │ ffmpeg /     │                 │
│                               │ ffprobe      │                 │
│                               └──────────────┘                 │
└───────────────────────────────────────────────────────────────┘
             ▲
             │  only with an explicit opt-in + a key
┌────────────┴─────────────┐
│ Hosted provider          │   ← transcript text of the scored window
│ (OpenRouter/Groq/…)      │      leaves the device, disclosed in the UI
└──────────────────────────┘
```

### What Laqta guarantees

1. **Local by default.** The server binds to `127.0.0.1` and the CORS
   allow-list is explicit — never `*`. Media, audio, transcripts and renders
   are written to your local data directory and are never uploaded.
2. **No telemetry.** Laqta has no analytics, no crash reporting and no
   phone-home. The only outbound request it can ever make is to a hosted
   provider *you* configured and consented to.
3. **The hosted path is fail-closed.** A hosted provider needs **both** an
   opt-in flag and an API key. Without both, the deterministic local ranker is
   used. The UI states plainly when transcript text will leave the device.
4. **Untrusted data stays data.** Transcripts and metadata are treated as
   attacker-controlled input. They are never interpolated into shell
   commands; subprocesses always receive argument arrays with `shell=False`,
   a deadline and bounded output.
5. **Secrets stay secret.** API keys are read from the environment only. They
   are never logged, never returned by an API endpoint and never written to
   the manifest, the database or an export.
6. **Media processing is off the request path.** Long jobs run in a single
   worker with persisted state, so a crash or a restart never leaves a
   half-written project.

### What Laqta does **not** guarantee

- The API has **no authentication**. It is a single-user desktop tool. Do not
  expose it to a network you do not control.
- Laqta cannot police what a hosted provider does with the text it receives.
  Read the disclosure before enabling it.
- The local data directory is **not encrypted at rest**. Anyone with access
  to your user account can read your media and transcripts.
- A model weight downloaded from the Hugging Face Hub is trusted as-is.
  Laqta does not vendor or verify its contents.

### Hardening notes

- If you need the API on another device, put it behind a tunnel or an
  authenticating reverse proxy. Do not change the bind address alone.
- Keep the data directory on an encrypted volume if the machine may be lost.
- Review `~/.local/share/qatta` before sharing a machine or a bug report.
- Rotate any hosted-provider key that may have been exposed, and unset
  `QATTA_LLM_OPENROUTER_API_KEY` to return to fully local behaviour.

---

## Supported versions

| Version | Supported | Notes |
|---------|-----------|-------|
| 0.1.x | ✅ | The current release line |
| < 0.1 | ❌ | Pre-release snapshots; upgrade to 0.1.x |

Only the latest release line receives security fixes. Fixes are published as a
new patch release, never as a silent change to an existing tag.

## Dependency advisories

The runtime dependency tree is audited on every CI run and weekly by
`audits.yml`:

```bash
uvx pip-audit --requirement backend/requirements-asr.txt
cd frontend && npm audit --omit=dev
```

Known advisories in the *development* tooling (not shipped to users) are
tracked in [docs/RELEASING.md](docs/RELEASING.md).

## Reporting a security issue about a dependency

Please report it to the upstream project first, then open an issue here
mentioning the dependency and the upstream advisory so the Laqta maintainers
can decide whether a mitigation or a version bump is needed.
