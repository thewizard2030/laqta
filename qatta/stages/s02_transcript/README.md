# S02 Transcript

## Overview
Two-pass speech transcription architecture: fast coarse speech run discovery (Pass 1) and localized word-level alignment on winning clips (Pass 2), with Arablish code-switching support and YouTube captions-first ingestion.

## Interface
- run_fast_pass_stage(manifest: QattaManifest, settings: QattaSettings | None = None) -> QattaManifest
- run_fine_pass_stage(manifest: QattaManifest, settings: QattaSettings | None = None) -> QattaManifest
- align_candidate_words(candidate: ClipCandidate, pcm: np.ndarray, sr: int, transcriber: TranscriptionAdapter, settings: QattaSettings) -> None
- build_atomic_utterances(segments: list[TranscriptSegment], pcm: np.ndarray, sr: int, pause_split_ms: int) -> list[AtomicUtterance]
- detect_speech_runs(pcm: np.ndarray, sr: int, pause_split_ms: int) -> list[tuple[int, int]]
- load_pcm_16k(path: str | Path) -> tuple[np.ndarray, int]
- select_transcriber(settings: QattaSettings) -> TranscriptionAdapter
- LocalTurboBatchedTranscriber(TranscriptionAdapter)
- GroqWhisperTranscriber(TranscriptionAdapter)
- parse_vtt(content: str) -> list[VttCue]
- dedup_rolling_captions(cues: list[VttCue]) -> list[TranscriptSegment]
- fetch_info_and_subs(url: str, work_dir: Path, languages: list[str], timeout: float) -> tuple[dict, Path]
- register(orchestrator: PipelineOrchestrator) -> None

## Invariants
- Pass 1 transcribes full audio without word timestamps (word_timestamps=False, beam_size=1); word-level timing occurs exclusively in Pass 2 on ranked winning clips
- Utterances are segmented by real acoustic pauses (pause_split_ms default 350 ms); LLMs only receive and return u_id identifiers, never raw timestamps
- Initial prompt preserves Arablish technical terms in Latin script (e.g., AI, API, SaaS)
- Cloud Groq API backend is fail-closed and requires explicit opt-in (QATTA_ALLOW_CLOUD_APIS=true) and groq_api_key
- Auto-generated YouTube captions have rolling repeated lines stripped deterministically via dedup_rolling_captions

## Side Effects
- Loads faster-whisper CTranslate2 model into CPU/GPU memory
- Performs external HTTP requests to Groq API if groq_api backend is configured and permitted
- Invokes yt-dlp to download VTT subtitle files for YouTube sources
- Mutates QattaManifest.atomic_utterances, word tokens, and candidate snapped boundaries (start_ms, end_ms, duration_sec)

## Verification
- Run: `pytest tests/`
