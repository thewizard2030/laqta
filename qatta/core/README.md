# Pipeline Substrate (core)

## Overview
Core pipeline substrate providing strict Pydantic v2 data models, pipeline configuration settings, and atomic manifest persistence orchestration.

## Interface
- schema.py: QattaManifest, AtomicUtterance, WordToken, ClipCandidate, VetoGates, CPSBreakdown, HookRemixVariant, MonetizationMeta
- config.py: QattaSettings
- pipeline.py: PipelineOrchestrator, PipelineError

## Invariants
- Single atomic source of truth: All pipeline state lives in qatta_manifest.json, serialized via Pydantic v2 and saved atomically with tempfile + os.replace
- Rule 3: No LLM timestamps; atomic utterances identified by U_0001 pattern bounded by acoustic pauses
- Timing consistency: All timed spans stored as integer milliseconds; duration_sec must match (end_ms - start_ms) / 1000 within 51 ms tolerance
- Stage timing measurement: Real elapsed wall time in milliseconds is recorded in stage_timings_ms (no estimates)
- Fail-closed cloud gates: Orchestrator refuses to run gated stages if cloud backends are not explicitly permitted

## Side Effects
- Reads and writes qatta_manifest.json atomically on local disk
- Spawns ffprobe subprocess to inspect source media duration

## Verification
- Run: `pytest tests/`
