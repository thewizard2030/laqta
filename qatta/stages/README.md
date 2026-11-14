# Pipeline Stages

## Overview
Intermediate architectural package grouping all discrete manifest-based pipeline stages (s01_ingest through s07_render_learn).

## Subdirectories & Boundaries
- [s01_ingest](./s01_ingest/README.md): Media probing and 16 kHz audio extraction
- [s02_transcript](./s02_transcript/README.md): Two-pass speech recognition and YouTube captions-first flow
- [s03_multimodal](./s03_multimodal/README.md): Acoustic energy/pitch analysis and scene cut detection
- [s04_candidates](./s04_candidates/README.md): Sliding window candidate proposals and LLM reranking
- [s05_ranking](./s05_ranking/README.md): Veto gates and archetype-weighted CPS scoring
- [s05b_section_fetch](./s05b_section_fetch/README.md): Selective download of ranked YouTube video sections
- [s06_render](./s06_render/README.md): ASS subtitle generation and vertical MP4 video rendering
- [s06_reframe_subs](./s06_reframe_subs/README.md): Permissive camera reframing and Arabic BiDi caption shaping
- [s07_render_learn](./s07_render_learn/README.md): YPP-safe rendering, hook remix, and channel performance feedback loop
