# Test fixtures

Static inputs used by the test suites. They are committed on purpose — a test
that depends on a file only present on one machine is not a test.

| File | What it is | Used for |
|------|------------|----------|
| `sample_captions.ar.vtt` | A WebVTT caption track in Arabic (public broadcast captions) with `align`/`position` cue settings. | Exercises the real VTT parser, the Arabic BiDi handling and the caption timing path. |

The VTT file is a caption track only — it contains no video and no personal
data. If a test needs a media file, it generates one locally (see
`backend/tests/test_candidate_review_api.py` for the pattern) instead of
committing a binary.
