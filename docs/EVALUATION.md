# Clip-selection evaluation

What the ranking actually does, measured.

Laqta's central claim is that it ranks clips **explainably** and *well*. The
first half is easy to check by reading the code; the second half needs
numbers. This document is those numbers, the method that produced them, and
the limits.

Reproduce it:

```bash
python scripts/evaluate_ranking.py            # run the benchmark
python scripts/evaluate_ranking.py --check    # fail on a regression
python scripts/evaluate_ranking.py --json     # the raw report
```

---

## 1. The method

**Dataset** — [`clip_selection_v1.json`](../benchmarks/clip_selection_v1.json):
two items, each a narration script split into sentences that a human labelled
`highlight`, `context` or `filler`.

**Media** — the narration is synthesised with espeak-ng and rendered to a
video, so **the labelled spans are exact**: every sentence's start and end are
known to the millisecond. Nothing third-party is committed, and the whole set
is reproducible from source.

**Pipeline** — the benchmark drives the *studio's own path*: import →
transcription job → candidate generation → ranking, over HTTP. What is
measured is what a user gets, not a private code path.

**Metrics** — the vocabulary the highlight-detection literature uses
(SoccerNet-style, and the same five metrics Rhapsody reports for podcast
highlights):

| Metric | Meaning |
|--------|---------|
| **precision** | of the selected clips, how many contain at least one labelled highlight |
| **recall** | of the labelled highlights, how many are covered by a selected clip |
| **F1** | the harmonic mean of the two |
| **coverage** | how much of the timeline the selection occupies (the union of the selected clips) |
| **bad coverage** | of the selected time, how much lies outside every labelled highlight |

A clip *hits* a label when it covers at least **50 %** of that label. The
test is relative to the label, not to the clip: a 40-second clip containing a
6-second highlight hits it, even though the intersection-over-union of the
two spans is small.

---

## 2. The results

Measured on the reference machine (see `docs/PERFORMANCE.md`), with the
`base` profile and the deterministic local ranker:

| Item | Selected | Labels hit | Precision | Recall | F1 | Coverage | Bad coverage |
|------|---------:|-----------:|----------:|-------:|---:|---------:|-------------:|
| `synthetic_01` | 6 | 3 | 1.00 | 1.00 | 1.00 | 0.95 | 0.00 |
| `synthetic_02` | 6 | 2 | 0.83 | 1.00 | 0.91 | 0.96 | 0.22 |
| **TOTAL** | 12 | 5 | **0.92** | **1.00** | **0.96** | 0.96 | 0.11 |

**What this says**

- **The ranking finds the highlights.** Recall is 1.00: every labelled
  highlight in the set is covered by a selected clip. On a set where a human
  marked five moments worth clipping, the ranker proposed clips covering all
  five.
- **It over-selects.** Coverage is 0.96 — the selection takes almost the
  entire timeline, and 11 % of the selected time is not a highlight at all.
  The current ranker is *generous*: it rarely misses a good moment, but it
  does not yet trim the boring parts. That is the clearest improvement
  direction the benchmark points at.
- **The metrics are not a marketing claim.** Two items with five labels is a
  *small* set. It is a regression gate, not a benchmark that decides whether
  the product is good.

---

## 3. Why this matters, in context

Rhapsody ([arXiv:2505.19429](https://arxiv.org/html/2505.19429v2)) reports the
same task — podcast highlight detection — on 13 000 episodes with labels
derived from YouTube's replay graph, and finds that *"even state-of-the-art
LLMs, such as GPT-4o, struggle with this task, performing on par with simple
heuristics"*.

That is exactly Laqta's bet: a deterministic, local, explainable ranker is not
a compromise — it is competitive. The benchmark exists so that the claim can
be **checked** rather than believed, and so that a change to the scoring
signals cannot silently make it worse.

---

## 4. Limits — read this before quoting the numbers

1. **The dataset is synthetic and tiny.** Two items, five labelled
   highlights, one narrator, one language. It was built this way so that the
   labels are exact and the whole set is reproducible from source with no
   third-party media. It is *not* a public research dataset.
2. **The labels are sentence-level.** A human marked "this sentence is worth
   clipping", not exact clip boundaries. A human who would cut a clip at a
   different point is a different label set.
3. **The narration is synthetic.** Real speech has music, room tone,
   interruptions and multiple speakers. The ranking sees none of that here.
4. **The transcript is machine-generated.** The script is known, so a
   transcription error rate could be measured too — but the ranking is
   measured on the transcript the pipeline actually produced, which is the
   point.
5. **The numbers move with the ASR model.** A different `faster-whisper`
   version can change the transcript and therefore the candidates. The CI
   gate therefore allows a small tolerance instead of demanding an exact
   match.

---

## 5. The gate

`benchmarks/baseline.json` holds the recorded numbers. CI runs the benchmark
weekly and on demand, and fails when a metric drops by more than the
tolerance (0.1 for precision/recall/F1, 0.05 for bad coverage). Raising the
baseline is a deliberate act: `--write-baseline` records the current numbers.

To make the ranking better, change the signals in
`qatta/stages/s05_ranking/scorer.py`, re-run the benchmark, and let the
numbers say whether it helped.
