# OpenRouter (optional hosted LLM)

Laqta can optionally use **OpenRouter** — one OpenAI-compatible gateway in
front of many hosted models — for stage `s04` candidate proposals and for the
FastAPI candidate reranker. Model ids ending in `:free` are offered at **zero
price**.

Everything here is **optional**. The deterministic local generator
(`HeuristicFallbackProvider`) and the deterministic baseline ranker work with
no network, no API key and no account. An LLM only ever *proposes*; the
pipeline still derives every millisecond from the real utterance table.

---

## 1. The three switches (all fail-closed)

| Switch | Layer | Effect when off |
| --- | --- | --- |
| `QATTA_ALLOW_CLOUD_APIS=false` | core pipeline | Stage `s04` refuses to build a cloud provider **before** any request. The heuristic generator runs instead. |
| `QATTA_LLM_HOSTED_OPT_IN=false` | FastAPI reranker | A non-loopback endpoint is refused: "transcript text would leave the device". The baseline ranker runs instead. |
| `QATTA_LLM_OPENROUTER_API_KEY` (unset) | both | The provider refuses to construct. Nothing is sent. |

The three are independent on purpose: enabling the key alone does not send
anything anywhere.

## 2. Enabling it

```bash
# .env (git-ignored) — never commit a key
QATTA_LLM_OPENROUTER_API_KEY=sk-or-v1-...
QATTA_LLM_OPENROUTER_MODEL=minimax/minimax-m3.1-flash:free
QATTA_LLM_OPENROUTER_BASE_URL=https://openrouter.ai/api/v1

# core pipeline (stage s04)
QATTA_LLM_PROVIDER=openrouter
QATTA_ALLOW_CLOUD_APIS=true

# FastAPI candidate reranker
QATTA_LLM_PROVIDER=openrouter
QATTA_LLM_RANKER_ENABLED=true
QATTA_LLM_HOSTED_OPT_IN=true
```

`QATTA_LLM_PROVIDER=openrouter` is enough to make the base URL and model
follow the OpenRouter defaults; an explicit `QATTA_LLM_BASE_URL` /
`QATTA_LLM_MODEL` always wins.

The key is a secret: it is read from the environment only, sent exclusively in
the `Authorization` header, stripped from every error message, and never
returned by any API endpoint (`/api/capabilities` reports only
`api_key_configured: true`).

## 3. Free models

Free models are ids ending in `:free`. The pool is **rotated by OpenRouter**,
so treat any list as a snapshot. A snapshot taken on 2026-10-19
(`GET https://openrouter.ai/api/v1/models`, no key needed):

```
minimax/minimax-m3.1-flash:free
nvidia/nemotron-3-super-120b-a12b:free
nvidia/nemotron-3.5-super-vl:free
xingchen-agi/xing4.0-29b-a4b:free
google/gemma-4-31b-it:free
google/gemma-4-26b-a4b-it:free
liquid/lfm-2.5-2.6b:free
dots-studio/dots-3-note-preview:free
```

Query the live catalogue at any time:

```bash
curl -s https://openrouter.ai/api/v1/models | python3 -c "
import sys, json
for m in json.load(sys.stdin)['data']:
    p = m.get('pricing') or {}
    if p.get('prompt') == '0' and p.get('completion') == '0':
        print(m['id'], m.get('context_length'))
"
```

The same list is available programmatically through
`qatta.stages.s04_candidates.llm.list_free_models()` (public endpoint, no
key, no transcript data) and is mirrored in the backend capabilities response
(`llm.free_models`).

## 4. What actually happens on a free model

- **Free models share a rate-limited upstream pool.** HTTP 429 is an
  *expected* outcome, not a bug. The provider turns it into a clear message
  ("rate-limited … the deterministic local generator remains available") and
  the stage degrades to the local heuristic generator.
- **Not every model supports `response_format`.** The provider asks for
  strict JSON first and retries once without it when the gateway rejects the
  parameter; the parser also accepts fenced JSON.
- **Free-tier request budget.** A free key on the OpenRouter free tier is
  limited to a small number of requests per day (the key's own limits are
  visible at `GET https://openrouter.ai/api/v1/key`). Stage `s04` makes one
  request per sliding window, so a 2-hour video costs roughly
  `120 min / 15 min ≈ 8–9` requests at the default `sliding_window_sec=900`
  and `sliding_overlap_sec=120`. Widen the window if the budget is tight.
- **No timestamps, ever.** The model receives utterance lines keyed by
  `u_id` and answers with `u_id` spans only; all milliseconds are derived by
  the pipeline from the real `AtomicUtterance` rows (rule 3).

## 5. Privacy disclosure (FR-11 / PRD §9)

With a hosted adapter, **portions of the transcript text leave this device**
and are processed by OpenRouter (and by the model provider behind it). Laqta
surfaces this in the UI:

- the dashboard engine strip shows `OpenRouter · <model>` and states that the
  provider is hosted;
- the settings tab shows the provider, the model, whether a key is configured
  and the full disclosure text;
- `GET /api/capabilities` returns `llm.provider`, `llm.hosted_opt_in` and
  `llm.disclosure`.

Media files, rendered clips and project data are never uploaded by this
integration — only transcript text used for candidate proposals is sent.

## 6. Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `Cloud LLM provider 'openrouter' requires explicit opt-in` | `QATTA_ALLOW_CLOUD_APIS=false` (core) | Set it to `true` — or keep it off and rely on the local generator. |
| `openrouter provider selected but QATTA_LLM_OPENROUTER_API_KEY is empty` | no key in the environment | Add the key to `.env` (git-ignored). |
| `LLM ranker skipped: endpoint is remote …` | `QATTA_LLM_HOSTED_OPT_IN=false` (backend) | Set it to `true` to accept the disclosure. |
| `OpenRouter rate-limited this request (HTTP 429)` | the free pool is busy | Retry later or switch `QATTA_LLM_OPENROUTER_MODEL` to another `:free` model. |
| `OpenRouter rejected the API key (HTTP 401)` | wrong/expired key | Rotate the key in the OpenRouter dashboard. |
| Model answers with prose instead of JSON | the model ignores the JSON instruction | The provider retries without `response_format`; if it still fails, the stage falls back to the local generator. |

## 7. Key hygiene

- The key belongs in `.env` (git-ignored) or the process environment only.
- Never paste a key into a source file, a commit, an issue or a screenshot.
- Rotate the key in the OpenRouter dashboard if it was ever shared outside
  the machine that should hold it.
