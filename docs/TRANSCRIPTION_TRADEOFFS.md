# Laqta — Transcription Architecture & Hardware Tradeoffs

This document details the speech-to-text architecture, CPU/RAM profiles, model storage layout, and design tradeoffs for local transcription in Laqta (implementing PRD §5 FR-03, §8, §10, and §11 Gate B).

---

## 1. Local-First Design & Reference Hardware

Laqta targets personal developer workstations and modest creator laptops with **8 GB RAM and modern multi-core x86_64 CPUs** (Intel Core i5/i7 8th gen+, AMD Ryzen 3000+, or Apple Silicon via Rosetta/native).

To prevent out-of-memory (OOM) operating system terminations and UI freezes:
1. **Lazy Model Loading**: Speech models are **never loaded at module import time** or server startup. Weights are loaded into RAM only when an active transcription job executes.
2. **Strict Serialization**: The persistent job queue executes heavy processing with **one worker at a time** (`MAX_WORKERS=1` by default). Audio extraction and speech transcription run sequentially.
3. **CPU-First Defaults**: Whisper runs on CPU using `int8` quantization via CTranslate2, delivering 2x–3x faster execution and halving memory consumption compared to float32.

---

## 2. Model Size & Hardware Profiles

| Model Size | Weights on Disk | Peak RAM Usage (int8) | Relative Speed (CPU) | Recommended Hardware Target | Recommended Use Case |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`tiny`** | ~75 MB | ~1.0 GB | ~6× real-time | Low-spec / CI / Fast draft | Fast exploratory pass, quick testing |
| **`base`** *(Default)* | ~145 MB | ~1.5 GB | ~4× real-time | **8 GB RAM reference system** | **General podcast/dialogue drafting** |
| **`small`** | ~490 MB | ~2.5 GB | ~2× real-time | 8 GB–16 GB RAM | Balanced accuracy for Arabic & technical terms |
| **`medium`** | ~1.5 GB | ~5.0 GB | ~0.8× real-time | 16 GB+ RAM | High accuracy multi-speaker & dialect content |
| **`large-v3`** | ~3.1 GB | ~8.0 GB | ~0.3× real-time | 16 GB–32 GB RAM (or CUDA GPU) | Maximum quality; risks OOM on 8 GB systems |

> [!IMPORTANT]
> On machines with 8 GB total system RAM, selecting `medium` or `large-v3` on CPU while a desktop browser and other applications are running risks system swap thrashing or OOM termination. `base` or `small` with `int8` is the recommended sweet spot.

---

## 3. Storage Layout & Model Downloads

All Whisper model weights are stored inside the configurable Laqta data directory:

```
~/.local/share/qatta/          # Linux default (or $QATTA_DATA_DIR)
├── models/
│   └── whisper/              # Cached faster-whisper CTranslate2 weights
│       ├── models--Systran--faster-whisper-tiny/
│       ├── models--Systran--faster-whisper-base/
│       └── models--Systran--faster-whisper-small/
├── projects/
│   └── <project_id>/
│       ├── media/            # Original user media (never deleted)
│       └── temp/
│           └── <job_id>/     # Intermediate 16 kHz mono WAV (cleaned after run)
└── qatta.db                  # SQLite database (stores projects, media, jobs, transcripts)
```

### Pre-downloading Models for Offline / Air-gapped Environments
If the host workstation has no continuous internet access, models can be pre-downloaded using Python:

```bash
python -c "from faster_whisper import WhisperModel; WhisperModel('base', download_root='~/.local/share/qatta/models/whisper')"
```

---

## 4. Truthful Timestamp Reporting & Subtitles

Laqta upholds strict engineering honesty regarding speech recognition accuracy:
- **`word` granularity**: When faster-whisper is executed with `word_timestamps=True`, segment cross-attention token alignment estimates word boundaries. The API truthfully marks `timing_granularity: "word"` and returns individual word tokens with start/end timestamps and confidence probabilities.
- **`segment` granularity**: If word timestamps are disabled or unavailable, the API marks `timing_granularity: "segment"`.
- **No False Claims**: Laqta does not claim millisecond-exact phoneme alignment or forced alignment until Phase 4 (WhisperX / wav2vec2 alignment).

---

## 5. Multi-Language & Arabic Support

- **Auto-Detection**: Setting `language: null` (or selecting "Auto-detect" in the UI) lets the model inspect the initial audio frames to identify the spoken language.
- **Explicit Language (`ar`, `en`, etc.)**: Supplying an explicit language code bypasses language detection latency, eliminates language-switching hallucinations, and noticeably improves Arabic speech transcription quality on `base` and `small` models.

---

## 6. Preserving Prior Transcripts

When a user re-transcribes media with a different model size, language, or parameters:
- Previous transcripts are **never overwritten or deleted**.
- Each run creates an immutable `TranscriptRecord` in SQLite with its own UUID, model metadata, language, and timestamp.
- The UI provides a "Saved Run" selector so users can review, compare, and toggle between different transcription runs at any time.

---

## 7. Two-Pass Architecture, Profiles & Transcript Cache (2026-10 update)

Since the performance work documented in `PERFORMANCE.md`, transcription is
two-pass:

1. **Pass A (full video)** runs with segment-level timestamps by default.
   Three profiles exist (`fast` default `base`, `balanced` `small`,
   `accurate` `medium` with full-video word timestamps and an explicit
   "takes longer" warning). Explicit request fields override any profile.
2. **Pass B (selected clip only)** re-derives word timestamps on a bounded
   clip (30–55 s typical, hard cap 120 s) when a render explicitly asks for
   karaoke captions and the transcript lacks word timings. Words are offset
   back to absolute source timestamps; failures fall back to segment
   captions and never discard the transcript. This is clip-scoped Whisper
   re-timing — NOT WhisperX/wav2vec2 alignment (§4 word-level claims above
   now read as: "word" = Whisper cross-attention word estimates).
3. **Content-addressed transcript cache** (`<data_dir>/cache/transcripts/`,
   schema versioned): identical audio + identical transcription settings
   reuse the stored transcript without re-running ASR; caption/layout/export
   settings changes never invalidate it. Measured: 18 ms fingerprint +
   0.2 ms lookup vs a full ASR pass.
