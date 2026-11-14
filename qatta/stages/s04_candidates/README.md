# S04 Candidates

## Overview
Candidate short clip proposal generation across overlapping sliding windows using LLM providers (Ollama, Gemini, OpenRouter, OpenAI-compatible) with deterministic heuristic fallback.

## Interface
- SlidingWindowChunker(window_sec: int = 900, overlap_sec: int = 120)
- generate_heuristic_candidates(utterances: list[AtomicUtterance], settings: QattaSettings, window_index: int = 0) -> list[ClipCandidate]
- run_candidates_stage(manifest: QattaManifest, settings: QattaSettings | None = None) -> QattaManifest
- select_provider(settings: QattaSettings, client: httpx.Client | None = None) -> LLMProvider
- validate_proposal(raw: dict, valid_u_ids: set[str]) -> dict | None
- OllamaProvider(LLMProvider)
- GeminiProvider(LLMProvider)
- OpenAICompatibleProvider(LLMProvider)
- OpenRouterProvider(LLMProvider)
- register(orchestrator: PipelineOrchestrator) -> None

## Invariants
- Rule 3: LLMs never output timestamps; models reference only u_id identifiers, and all millisecond boundaries are strictly derived from AtomicUtterance timestamps
- Cloud LLM providers (Gemini, OpenRouter, OpenAI compatible) are fail-closed, requiring QATTA_ALLOW_CLOUD_APIS=true and valid API keys
- If the LLM is unreachable, times out, or produces invalid output, execution falls back deterministically to generate_heuristic_candidates (recorded in evidence log)
- Proposed candidates are initialized with pending veto gates (passed_all=False, rejection_reason='pending_s05_ranking')

## Side Effects
- Issues HTTP POST requests to Ollama (127.0.0.1:11434) or external cloud LLM APIs via httpx
- Mutates QattaManifest.candidates with proposed ClipCandidate instances

## Verification
- Run: `pytest tests/`
