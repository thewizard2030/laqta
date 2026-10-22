# Benchmarks

The measured behaviour of Laqta's ranking, and the data behind it.

| Path | What it is |
|------|------------|
| `clip_selection_v1.json` | The labelled dataset: narration scripts with every sentence marked `highlight`, `context` or `filler` |
| `baseline.json` | The recorded metrics. CI fails when the current run drops below them |

Run it:

```bash
python scripts/evaluate_ranking.py            # run and print the table
python scripts/evaluate_ranking.py --check    # fail on a regression
python scripts/evaluate_ranking.py --json     # the raw report
python scripts/evaluate_ranking.py --write-baseline   # record new numbers
```

The method, the results and the limits are in
[`docs/EVALUATION.md`](../docs/EVALUATION.md).

## Why the media is synthesised

Each sentence is spoken separately (espeak-ng), so its exact time span is
known to the millisecond, and the sentences are joined with a pause. The
labelled spans are therefore *exact* rather than approximate, the whole set
is reproducible from source, and **no third-party media is committed** — which
keeps the benchmark licence-clean and the repository small.

The cost is stated plainly in the evaluation: the narration is synthetic, so it
has none of the messiness of real speech. It is a regression gate, not a
claim about the state of the art.

## Requirements

- `ffmpeg` and `ffprobe` (with libass)
- `espeak-ng` — a **development-only** tool. The application never uses it; it
  only synthesises the benchmark narration.
- The local speech model (`base` by default) — downloaded once.
