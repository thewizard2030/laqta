# Laqta backend

The FastAPI service behind the [Laqta](https://github.com/thewizard2030/laqta)
studio. It binds to `127.0.0.1` by default, never uploads media, and keeps
every artefact (projects, media, transcripts, renders) in the local data
directory.

This directory holds the HTTP layer only. The manifest-based pipeline lives in
the [`qatta/`](../qatta) core package at the repository root.

## Run it

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

- API root: <http://127.0.0.1:8000/>
- Health: <http://127.0.0.1:8000/api/health>
- Capabilities: <http://127.0.0.1:8000/api/capabilities>
- OpenAPI docs: <http://127.0.0.1:8000/docs>

## Tests

```bash
cd backend
pytest            # this directory only
pytest ../tests   # the core pipeline suite
```

## Configuration

Every setting is read from the environment with the `QATTA_` prefix — see
[`.env.example`](../.env.example) for the full list. The hosted providers
(OpenRouter, Groq, AssemblyAI) are **fail-closed**: they stay disabled until
their explicit opt-in flag *and* an API key are both present.

## License

MIT — see [LICENSE](../LICENSE).
