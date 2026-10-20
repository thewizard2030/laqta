## What this changes

<!-- One or two sentences. What is different after this pull request? -->

## Why

<!-- The problem. Link the issue with "Fixes #123". -->

## How it was verified

<!-- The exact commands you ran and what they printed. -->

```bash
# e.g.
cd backend && .venv/bin/pytest
pytest ../tests
cd ../frontend && npm run check
```

- [ ] `pytest` (backend) and `pytest tests` (core) pass
- [ ] `npm run check` passes in `frontend/`
- [ ] `ruff check` and `ruff format --check` are clean
- [ ] New dependencies are licence-compatible and listed in `THIRD_PARTY_NOTICES.md`
- [ ] The docs still describe what the code actually does
- [ ] I did **not** include personal media, transcripts, API keys or local paths

## Notes for the reviewer

<!-- Anything the reviewer should look at twice: risky areas, trade-offs,
     follow-ups you deliberately left out. -->
