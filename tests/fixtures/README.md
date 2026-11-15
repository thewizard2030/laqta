# Test fixtures

Static inputs used by the test suites. They are committed on purpose — a test
that depends on a file only present on one machine is not a test.

| File                               | What it is                                                                                                                                                                      | Used for                                                                                                                                           |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| `sample_captions_synthetic.ar.vtt` | An original, synthetic Arabic technical WebVTT caption track (14 cues) with `align:start position:100%` cue settings, mixed Arabic/English terms, numbers, and rolling overlap. | Exercises the real VTT parser, rolling-caption deduplication, Arabic BiDi handling, and caption timing path without third-party broadcast content. |

The VTT file is a self-authored synthetic caption track only — it contains no
video, no personal data, and no third-party broadcast text. If a test needs a
media file, it generates one locally (see
`backend/tests/test_candidate_review_api.py` for the pattern) instead of
committing a binary.
