# Contributing to Laqta

Thanks for taking the time to contribute. Laqta is a local-first studio: your
media never has to leave your machine, and the project is built on a small set
of rules that keep it that way.

- **Bug reports and feature requests:** [GitHub Issues](https://github.com/thewizard2030/laqta/issues)
- **Security issues:** report privately — see [SECURITY.md](SECURITY.md), *not* an issue
- **Questions:** [Discussions](https://github.com/thewizard2030/laqta/discussions)

---

## 1. The rules that matter

These are not style preferences — they are the properties that make Laqta
trustworthy. A change that breaks one of them will not be merged.

1. **Local first.** Nothing may upload media, audio, transcripts or renders
   without an explicit, per-use opt-in. The default path must work with no
   account and no API key.
2. **No silent behaviour.** The UI and the CLI must report what actually
   happened. Never present a stub, a mock or an estimate as a real result.
3. **Untrusted input.** Transcripts, captions, metadata and file names are
   attacker-controlled data. Never interpolate them into a shell command, a
   path, a SQL statement or a template.
4. **Subprocess discipline.** Argument arrays, `shell=False`, a deadline, a
   cancellation path and bounded log output — every time.
5. **No fake claims.** Do not advertise word-level alignment, RTL correctness,
   speaker detection or "virality prediction" unless it is implemented *and*
   tested.
6. **Licence safety.** Dependencies must be MIT / Apache-2.0 / BSD / ISC /
   Unlicense. AGPL-3.0 is forbidden (`ultralytics`/YOLOv8 included).
   Document the licence of anything new in `THIRD_PARTY_NOTICES.md`.
7. **Work off the request.** Do not implement future phases, and do not
   rewrite code you were not asked to touch.

## 2. Set up

```bash
git clone https://github.com/thewizard2030/laqta.git
cd laqta
./scripts/setup.sh          # backend + local ASR + frontend
```

Verify the machine:

```bash
backend/.venv/bin/laqta doctor
```

Run the studio:

```bash
./scripts/dev.sh            # API on :8000, studio on :5173
```

## 3. Make your change

```bash
git checkout -b feature/my-change
# …edit, then:
cd backend && .venv/bin/pytest            # backend tests
pytest ../tests                            # core pipeline tests
cd ../frontend && npm run check            # typecheck + lint + format + tests
```

`npm run check` runs everything the CI runs for the frontend:

| Command | What it does |
|---------|--------------|
| `npm run typecheck` | `tsc --noEmit` |
| `npm run lint` | ESLint (errors fail; warnings are reported) |
| `npm run lint:strict` | ESLint with zero warnings allowed |
| `npm run format:check` | Prettier check (`npm run format` to fix) |
| `npm run test` | Vitest |

For Python, the equivalent gates are:

```bash
ruff check qatta backend/app backend/tests tests scripts
ruff format --check qatta backend/app backend/tests tests scripts
python scripts/check_version.py
```

### Style

- **Python** — `ruff format` is the formatter; `ruff check` is the linter.
  100-column lines, type hints on public functions, docstrings that explain
  *why*.
- **TypeScript/React** — Prettier is the formatter, ESLint the linter. Functional
  components, typed props, no `any` (use `unknown` and narrow it).
- **Tests** — every behaviour change needs a test. Use the real code paths;
  mock at the network boundary, not the logic boundary.
- **Comments** — explain the reason, not the mechanics. The code says what it
  does; the comment says why it does it that way.

## 4. Before you open a pull request

- [ ] `npm run check` passes in `frontend/`
- [ ] `pytest` (backend) and `pytest tests` (core) pass
- [ ] `ruff check` and `ruff format --check` are clean
- [ ] New dependencies are licence-compatible and documented in
      `THIRD_PARTY_NOTICES.md`
- [ ] Behaviour changes are reflected in the docs (`README.md`, `docs/`)
- [ ] The pull request describes *why*, not just *what*

## 5. Commit and pull request style

- One logical change per pull request.
- Conventional-ish prefixes: `feat:`, `fix:`, `docs:`, `refactor:`,
  `test:`, `chore:`, `perf:`, `build:`, `ci:`.
- Write the commit subject in the imperative mood: *"add caption safe-area
  guide"*, not *"added caption safe-area guide"*.
- Reference issues with `Fixes #123`.

## 6. Adding a dependency

1. Check the licence (MIT / Apache-2.0 / BSD / ISC / Unlicense only).
2. Prefer a standard-library solution.
3. If the dependency is heavy, make it **lazy and optional** — import it inside
   the function that needs it and degrade with a clear error when it is
   missing.
4. Add it to the right profile in `backend/requirements*.txt` and to the
   matching extra in `pyproject.toml`.
5. Regenerate the lock: `python scripts/generate_lock.py`.
6. Document it in `THIRD_PARTY_NOTICES.md`.

## 7. Reporting a security issue

Do **not** open a public issue. See [SECURITY.md](SECURITY.md) for the private
reporting channel and the response times.

## 8. Code of conduct

Participation is governed by [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## 9. Licence

Contributions are licensed under the [MIT License](LICENSE). By contributing
you agree that your work is distributed under those terms.
