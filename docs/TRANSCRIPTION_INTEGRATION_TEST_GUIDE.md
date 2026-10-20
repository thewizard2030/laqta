# Laqta Transcription Provider Integration & Testing Guide

This guide describes how to configure, verify, benchmark, and run real integration tests across all local and cloud transcription engines supported by Laqta.

---

## 1. Architecture Overview

Laqta provides an asynchronous, multi-engine transcription architecture with truthful capability reporting:

| Provider | Type | Speed / Throughput | Diarization | Privacy & Data Boundary |
| :--- | :--- | :--- | :--- | :--- |
| `faster-whisper` | Local (CPU / CUDA) | Moderate to Fast | No | **100% Local**. Audio never leaves machine. |
| `whisper.cpp` | Local (C/C++ GGML) | Fast (Low RAM) | No | **100% Local**. Audio never leaves machine. |
| `groq` | Cloud (Groq API) | Ultra-Fast (~10-20x) | No | Audio uploaded via HTTPS to Groq Inc. |
| `assemblyai` | Cloud (AssemblyAI) | Fast | **Yes** (Multi-Speaker) | Audio uploaded via HTTPS to AssemblyAI Inc. |
| `huggingface` | Cloud (HF Serverless) | Moderate | No | Audio uploaded via HTTPS to Hugging Face. |
| `fake` | Simulated | Instant | No | Deterministic fixtures for unit testing. |

---

## 2. Privacy & Fail-Closed Gating

Laqta enforces strict privacy rules (PRD §5 FR-03, FR-12):
1. **Cloud APIs are disabled by default**:
   Any attempt to invoke a cloud provider (`groq`, `assemblyai`, `huggingface`) without setting:
   ```bash
   export QATTA_ALLOW_CLOUD_APIS=true
   ```
   will immediately fail closed with error code `CLOUD_APIS_DISABLED`.
2. **API Keys are never logged in plain text**:
   All log statements sanitize secret keys (e.g. `gsk_***` or `hf_***`).
3. **No transcript text logging**:
   Transcripts are treated as sensitive user data and are not logged by default.

---

## 3. Configuring Real Providers

### A. Local NVIDIA CUDA Acceleration
To enable CUDA acceleration on machines with an NVIDIA GPU:
1. Ensure NVIDIA drivers and CUDA toolkit are installed.
2. Verify CTranslate2 detects the GPU:
   ```bash
   python3 -c "import ctranslate2; print('CUDA devices:', ctranslate2.get_cuda_device_count())"
   ```
3. Set environment variable:
   ```bash
   export QATTA_WHISPER_DEVICE=cuda
   export QATTA_WHISPER_COMPUTE_TYPE=float16
   ```
*Note:* If `QATTA_WHISPER_DEVICE=cuda` is requested on a host without compatible GPU drivers, Laqta truthfully falls back to CPU INT8 and records `fallback_reason` in the capabilities and transcript metadata.

### B. Local whisper.cpp
1. Install or compile `whisper-cli`:
   ```bash
   # Example: build whisper.cpp
   git clone https://github.com/ggerganov/whisper.cpp
   cd whisper.cpp && make
   ```
2. Download a GGML model (e.g. `ggml-base.bin`):
   ```bash
   bash ./models/download-ggml-model.sh base
   ```
3. Configure Laqta paths:
   ```bash
   export QATTA_WHISPER_CPP_PATH=/path/to/whisper.cpp/main
   export QATTA_WHISPER_CPP_MODEL_PATH=/path/to/whisper.cpp/models/ggml-base.bin
   ```

### C. Groq Whisper Cloud API
1. Obtain an API key from [Groq Console](https://console.groq.com/keys).
2. Set configuration:
   ```bash
   export QATTA_ALLOW_CLOUD_APIS=true
   export GROQ_API_KEY=gsk_your_groq_api_key_here
   export QATTA_GROQ_MODEL=whisper-large-v3-turbo
   ```

### D. AssemblyAI (with Speaker Diarization)
1. Obtain an API key from [AssemblyAI Dashboard](https://www.assemblyai.com/).
2. Set configuration:
   ```bash
   export QATTA_ALLOW_CLOUD_APIS=true
   export ASSEMBLYAI_API_KEY=your_assemblyai_api_key_here
   ```

### E. Hugging Face Inference API
1. Obtain a User Access Token from [Hugging Face Settings](https://huggingface.co/settings/tokens).
2. Set configuration:
   ```bash
   export QATTA_ALLOW_CLOUD_APIS=true
   export HF_TOKEN=hf_your_hf_token_here
   export QATTA_HF_WHISPER_MODEL=openai/whisper-large-v3-turbo
   ```

---

## 4. Inspecting Capabilities & Provider Status

### Via REST API:
Start backend server:
```bash
cd backend && .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```
Query provider capability disclosures:
```bash
curl -s http://127.0.0.1:8000/api/transcription/providers | jq .
```
Expected output shows each provider, whether API keys are configured, CUDA detection, device name, and privacy disclosures.

---

## 5. Running the Transcription Benchmark Tool

Generate benchmark audio samples and benchmark across providers:

```bash
cd backend

# 1. Generate 30s test samples
.venv/bin/python tools/benchmark_transcription.py --make-samples --seconds 30

# 2. Benchmark local faster-whisper on CPU INT8
.venv/bin/python tools/benchmark_transcription.py \
    --audio /tmp/qatta_bench/sample_en.wav \
    --provider faster-whisper \
    --device cpu \
    --model base

# 3. Benchmark local faster-whisper with CUDA (or automatic fallback)
.venv/bin/python tools/benchmark_transcription.py \
    --audio /tmp/qatta_bench/sample_en.wav \
    --provider faster-whisper \
    --device cuda \
    --model base

# 4. Benchmark Groq Whisper API (when keys configured)
.venv/bin/python tools/benchmark_transcription.py \
    --audio /tmp/qatta_bench/sample_en.wav \
    --provider groq \
    --model whisper-large-v3-turbo

# 5. Benchmark AssemblyAI with speaker diarization
.venv/bin/python tools/benchmark_transcription.py \
    --audio /tmp/qatta_bench/sample_en.wav \
    --provider assemblyai
```

---

## 6. Automated Unit & Mocked Tests

Run the test suite verifying all providers, chunk boundaries, deduplication, fail-closed privacy gating, and CUDA fallback without needing live external API keys:

```bash
cd backend
.venv/bin/pytest tests/test_transcription_manager.py -v
```
