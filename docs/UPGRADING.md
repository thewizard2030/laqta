# Upgrading Laqta

What changed between the releases, and what you have to do.

---

## 0.1.1 → 0.1.2

**No action required.** The API, the data directory and the project format
are unchanged — your existing projects keep working.

New in this release:

- **Release mode.** The API can serve the studio itself:
  `laqta studio --production` builds the frontend and serves the whole
  application from <http://127.0.0.1:8000>.
- An **error boundary** in the studio: a render error no longer blanks the
  app.
- `laqta doctor --json` for scripts and CI.
- `scripts/setup.ps1` — a first-class Windows install.
- `/api/health` now reports the **job worker** state (`degraded` when the
  worker is not running).

> If your tooling reads `/api/health`, the response gained a `worker` field.
> The `status` value is now `degraded` when the worker is stopped — it used
> to say `healthy` unconditionally.

---

## 0.1.0 → 0.1.1

### ⚠️ URL import is now disabled by default

`QATTA_ENABLE_URL_INGESTION` shipped as `True` and is now `False`: the
feature is **fail-closed** and needs an explicit opt-in, like every other path
that reaches the network.

If you use the YouTube import, add this to your `.env`:

```bash
QATTA_ENABLE_URL_INGESTION=true
```

Without it the import button stays visible and refuses with the reason —
nothing is downloaded. The per-import rights confirmation is mandatory
either way.

### The hosted paths are unchanged

`QATTA_ALLOW_CLOUD_APIS` and `QATTA_LLM_HOSTED_OPT_IN` still default to
`False`. If you had opted in, nothing changes — and the studio keeps
disclosing that transcript text leaves the machine.

### Toolchain

| | Before | Now |
|---|---|---|
| Node | 20+ | **22.12+** (the Vitest 5 requirement) |
| Python | 3.11+ | 3.11+ (unchanged) |
| Tailwind | 3 | 4 (the theme now lives in `src/index.css` — `@theme`) |

The upgrade is mechanical: `npm ci` in `frontend/` and `pip install -r
backend/requirements-dev.txt` in `backend/`.

### The API health response

`GET /api/health` gained a `worker` field and can now report `degraded`.
See the note above.

### The core test suite no longer writes to your data directory

`pytest tests` used to create real projects in `~/.local/share/qatta`
(you may find leftovers named "API Manifest Test" — they are safe to
delete). The suite is hermetic now.

---

## 0.0.x → 0.1.0

The first public release. See [CHANGELOG.md](../CHANGELOG.md).
