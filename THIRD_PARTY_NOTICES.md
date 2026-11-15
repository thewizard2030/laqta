# Third-Party Notices

Laqta uses and integrates with several open-source libraries and tools.

## System Tools

- **FFmpeg / FFprobe**: LGPL 2.1+ / GPL 2.0+ depending on build configuration. Used via subprocess execution without linking proprietary wrappers.
- **libass**: ISC license. Used for high-quality subtitle rendering.

- **espeak-ng (dev/benchmark only)**: GPL 3.0. Used ONLY by the optional
  `tools/benchmark_transcription.py --make-samples` helper to synthesize
  timing test samples; never linked into the application runtime.

## Core Package (`qatta/`) Dependencies

Declared in the root `pyproject.toml` for the manifest-based core pipeline.
None are AGPL-3.0; `ultralytics`/YOLOv8 and any AGPL dependency remain
forbidden. Heavy analysis libraries are imported lazily by the stages that
need them:

- **pydantic-settings**: MIT License. Core pipeline configuration
  (`QATTA_`-prefixed env vars).
- **typer / rich**: MIT License (Sebastián Ramírez / Will McGugan).
  CLI output formatting (CLI entry point arrives in a later increment;
  no runtime dependency yet).
- **numpy / soundfile**: BSD 3-Clause License. Audio array handling
  (imported lazily by audio stages).
- **librosa**: ISC License. Audio analysis (imported lazily).
- **PySceneDetect (`scenedetect[opencv]`)**: BSD 2-Clause License.
  Shot-boundary detection; pulls on `opencv-python` (Intel), which is
  Apache 2.0 — no AGPL OpenCV build is declared.
- **mediapipe**: Apache 2.0 License (Google LLC). Optional face/image
  landmark analysis for later framing stages (imported lazily; no wheels
  exist for some Python versions — stages degrade with a clear
  "capability unavailable" error).
- **yt-dlp**: Unlicense. Powers URL ingestion and the YouTube
  captions-first transcription source (PRD FR-12, review completed by
  owner decision on 2026-10-19). Imports require per-import rights
  confirmation and honor the `QATTA_ENABLE_URL_INGESTION=false` opt-out;
  cloud ASR keys remain optional and fail-closed.

## Backend Libraries

- **FastAPI**: MIT License (Sebastián Ramírez).
- **Pydantic**: MIT License (Samuel Colvin and contributors).
- **Uvicorn**: BSD 3-Clause License.
- **pytest**: MIT License.
- **HTTPX**: BSD 3-Clause License.
- **faster-whisper**: MIT License (SYSTRAN / Pierre Guillou). Local CPU ASR
  via CTranslate2. Model weights downloaded at runtime are OpenAI Whisper
  model weights (MIT License) converted by SYSTRAN to CTranslate2 format.
- **CTranslate2 / CTranslate2 runtime libs**: MIT License (OpenNMT).
- **PyAV**: BSD 3-Clause License (locked `av==18.1.0` uses `BSD-3-Clause`; pre-built PyPI wheels bundle FFmpeg shared libraries under LGPL/GPL — see [docs/LICENSING_DECISIONS.md](docs/LICENSING_DECISIONS.md) §3).
- **typing-extensions**: PSF-2.0 License (Python Software Foundation License v2; transitive FastAPI/Pydantic dependency in `backend/requirements-lock.txt`).
- **certifi**: MPL-2.0 License (CA bundle packaged for HTTP clients in `backend/requirements-lock.txt`; governs `certifi` files only).
- **tqdm**: MPL-2.0 AND MIT License (`MPL-2.0` for main package files, `MIT` for legacy module files; transitive `faster-whisper`/`huggingface-hub` dependency).
- **espeak-ng (dev/benchmark only)**: GPL 3.0. Used ONLY by the optional
  `tools/benchmark_transcription.py --make-samples` helper to synthesize
  timing test samples; never linked into the application runtime.

## Frontend Libraries

- **React / React DOM 19**: MIT License (Meta Platforms, Inc.).
- **Vite 8**: MIT License (Yuxi (Evan) You and Vite contributors).
- **Tailwind CSS 4**: MIT License (Tailwind Labs, Inc.).
- **Vitest 5**: MIT License.
- **Lucide**: ISC License. The brand marks (GitHub, YouTube) were removed
  from Lucide v1; Laqta ships its own two small inline SVGs for them
  (`frontend/src/components/ui/BrandIcons.tsx`) because they identify the
  platform a link points to.
- **Lucide Icons**: ISC License.

### Build / Dev-Only Frontend Tooling (not bundled in `frontend/dist/`)

- **lightningcss**: MPL-2.0 License (`lightningcss@1.33.0` / nested `@1.32.0`, CSS bundler used strictly at Vite/Tailwind build time).
- **minimatch**: BlueOak-1.0.0 License (dev/test/lint glob utility).
- **caniuse-lite**: CC-BY-4.0 License (build-time Browserslist database).
- **@csstools/color-helpers**: MIT-0 License (build-time CSS color helper).

## Optional Hosted Services (not libraries, no code is vendored)

- **OpenRouter** (`https://openrouter.ai/api/v1`): an optional HOSTED
  LLM gateway used by the `openrouter` provider in
  `qatta/stages/s04_candidates/llm.py` and
  `backend/app/providers/llm/openrouter.py`. It is reached over HTTPS with
  the OpenAI-compatible chat-completions API; **no OpenRouter code is copied
  into this repository** and the service is not a build or runtime
  dependency. It is fail-closed: an explicit opt-in flag, a key read from
  the environment, and the transcript-leaves-device disclosure (PRD §9) are
  all required before any request is sent. Zero-price model ids (ending in
  `:free`) are offered by OpenRouter, not by Laqta; the model weights
  themselves are provided by the upstream vendors under their own terms.
  See [docs/OPENROUTER.md](docs/OPENROUTER.md).
