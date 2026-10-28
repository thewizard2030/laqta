<div align="center">

<img src="docs/assets/laqta-logo.png" alt="Laqta — لقطّة" width="520" />

### **The Free, Open-Source & Local-First Opus Clip Alternative**
**Turn long videos & podcasts into ranked vertical Shorts — entirely on your own machine.**

[![Language](https://img.shields.io/badge/%D8%A7%D9%84%D8%B9%D8%B1%D8%A8%D9%8A%D8%A9-README.ar.md-22d3ee.svg)](README.ar.md)
[![CI](https://github.com/thewizard2030/laqta/actions/workflows/ci.yml/badge.svg)](https://github.com/thewizard2030/laqta/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/thewizard2030/laqta?label=release&color=7c4dff)](https://github.com/thewizard2030/laqta/releases/latest)
[![Stars](https://img.shields.io/github/stars/thewizard2030/laqta?style=flat&color=7c4dff)](https://github.com/thewizard2030/laqta/stargazers)
[![License: MIT](https://img.shields.io/badge/License-MIT-7c4dff.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20macOS%20%7C%20Windows-lightgrey.svg)]()
[![Local first](https://img.shields.io/badge/100%25%20local-no%20cloud%20required-10b981.svg)](docs/POLICY.md)
[![Arabic RTL](https://img.shields.io/badge/Arabic%20RTL-Native%20BiDi-22d3ee.svg)](README.ar.md)

[English](README.md) • [العربية (Arabic)](README.ar.md)

</div>

---

Laqta (**لقطّة** — *"a take / a cut"*) imports long-form videos or podcasts, transcribes them locally with Faster-Whisper, ranks the most engaging clip candidates with an **explainable score**, and renders vertical 1080×1920 MP4s with right-to-left-aware captions.

**No account. No upload. No telemetry.** Media and audio processing stay strictly inside your machine (`127.0.0.1`). Zero mandatory paid API keys or cloud lock-in.

![Laqta Pipeline Workflow](docs/assets/workflow-demo.svg)

---

## ⚖️ Why Laqta vs. Commercial Tools

| Feature | **Laqta (Open Source)** | **Opus Clip / Submagic / Klap** | Generic OSS Tools |
| :--- | :--- | :--- | :--- |
| **Cost** | **100% Free (MIT License)** | \$19 – \$49 / month | Free |
| **Privacy & Security** | **100% Local** (Media never leaves PC) | Cloud uploaded & stored | Varies |
| **Arabic & RTL Support** | **Native RTL** + Arablish Whisper prompt | Frequently broken / reversed letters | Poor or unsupported |
| **Clip Scoring** | **Explainable** (Signal-by-signal rationale) | Black-box "viral %" | Arbitrary time cuts |
| **Hardware Fit** | Optimized for **8 GB RAM CPU** | Cloud servers only | Heavy GPU required |
| **Telemetry / Tracking** | **Zero** (Binds strictly to `127.0.0.1`) | User & footage tracked | Varies |
| **Extensibility** | CLI, local API, & manifest pipeline | Closed web app | Mostly CLI only |

---

## ✨ Key Features

| | |
|---|---|
| 🧠 **Explainable ranking** | Every clip carries a Clip Potential Score (0–100) **and the per-signal rationale that produced it** (speech rate, pitch dynamics, topic boundaries). No black-box fake virality scores — the ranking is [measured and benchmarked](docs/EVALUATION.md). |
| 🌍 **Arabic-First UX** | Native Right-to-Left (RTL) caption layout, FSI/PDI isolate markers, mirrored lines, and an Arabic-aware Whisper prompt that keeps English technical terms in Latin script without breaking layout. |
| 🔒 **Local-first guarantee** | Media, audio, transcripts, and rendered clips stay in your data directory. The local API binds to `127.0.0.1`; there is no telemetry. |
| 🪶 **Runs on modest hardware** | CPU-first and tuned for an 8 GB machine: a fast full pass for the transcript, then word-level re-timing only for the clips you actually render. |
| 🚪 **No subscription lock-in** | Works with zero API keys. Hosted providers (OpenRouter, Groq, AssemblyAI) are optional, opt-in **and** fail-closed. |
| 💻 **Complete Studio UI** | Modern React + Vite workbench with interactive waveform, drag-and-drop import, timeline scrubbing, and title-safe vertical framing. |

---

## 📸 The Studio Workbench

![The Laqta studio workbench](docs/assets/laqta-studio.png)

*Every screenshot in this repository was taken from a real, local run on a synthetic demo video — no third-party content.*

---

## 🚀 Quick Start

### Option 1: One-Line Docker Run (Recommended)

Run Laqta instantly without manually installing Python, Node, or FFmpeg:

```bash
git clone https://github.com/thewizard2030/laqta.git
cd laqta
docker compose up
```

Open your browser at **<http://localhost:8000>**.

---

### Option 2: Native Local Installation

#### Prerequisites
| Dependency | Version |
|---|---|
| **Python** | 3.11 or 3.12 |
| **Node.js** | 22.12 or newer |
| **FFmpeg** | with **libass** (for burned-in subtitles) |
| **Memory / RAM** | 8 GB works; a GPU is optional |

#### Setup & Launch

```bash
# 1. Clone repository
git clone https://github.com/thewizard2030/laqta.git
cd laqta

# 2. Setup backend & frontend
./scripts/setup.sh

# 3. Launch studio in release mode
laqta studio --production
```

The studio will build and serve from <http://127.0.0.1:8000>.

For active development with hot reload, use `./scripts/dev.sh` (API on `:8000` and Vite on `:5173`).

---

### Platform Notes

<details>
<summary><b>macOS (Homebrew)</b></summary>

```bash
brew install ffmpeg          # includes libass
./scripts/setup.sh
```

</details>

<details>
<summary><b>Windows (PowerShell)</b></summary>

```powershell
winget install Gyan.FFmpeg
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```

</details>

<details>
<summary><b>Linux (Ubuntu / Debian / Fedora)</b></summary>

```bash
# Ubuntu / Debian
sudo apt update && sudo apt install -y ffmpeg libass-dev python3 python3-venv nodejs npm

# Fedora / RHEL
sudo dnf install -y ffmpeg libass python3 python3-devel nodejs npm
```

</details>

---

## 🩺 Check Your Machine (`laqta doctor`)

Laqta includes a built-in doctor command to verify installed dependencies:

```bash
laqta doctor
```

```text
✓   Python          3.11.x           >= 3.11 required
✓   FFmpeg          8.x              /usr/bin/ffmpeg (libass supported)
✓   FFprobe         8.x              /usr/bin/ffprobe
✓   Local ASR       faster-whisper   Speech recognition on this CPU
✓   Data directory  writable         ~/.local/share/qatta
```

> **First run model download:** The local speech model is downloaded once into your cache (~145 MB for `fast`, ~460 MB for `balanced`, ~1.5 GB for `accurate`). After that, everything runs 100% offline.

---

## 🌍 The Arabic & RTL Superpower

Most existing subtitle and short-form video editors break when handling Arabic:
- Letters get reversed or disconnected.
- Punctuation and brackets appear at the opposite side of the line.
- Mixed Arablish sentences (e.g. *"الـ AI بيشتغل على الـ CPU"*) cause words to jump positions.

Laqta solves this natively:
1. **FSI / PDI isolates & RLM markers** ensure correct directional boundaries between Arabic and Latin scripts.
2. **Specialized Arablish Whisper prompting** ensures technical terms (e.g. *Machine Learning*, *API*, *Docker*) remain in Latin script while the Arabic stays correctly shaped.
3. **Noto Sans Arabic** ensures high-contrast, modern subtitles rendered cleanly via `libass`.

---

## 📊 Measured Ranking Evaluation

```bash
python scripts/evaluate_ranking.py
```

```text
item              sel  hits    prec     rec      F1     cov     bad
-------------------------------------------------------------------
synthetic_01        6     3    1.00    1.00    1.00    0.95    0.00
synthetic_02        6     2    0.83    1.00    0.91    0.96    0.22
-------------------------------------------------------------------
TOTAL                          0.92    1.00    0.96    0.96    0.11
```

The benchmark synthesises its own narration, labels it by hand, and runs the real pipeline over it — so labeled spans are exact and scores are reproducible. Read the full methodology in [docs/EVALUATION.md](docs/EVALUATION.md).

---

## 🏗️ Architecture

```text
qatta/                     # Manifest-based core pipeline (Pydantic v2)
  core/schema.py           # Atomic per-project state (qatta_manifest.json)
  core/pipeline.py         # Stage orchestration, resume, wall-clock timings
  stages/                  # s01_ingest → s02_transcript → s03_multimodal →
                           # s04_candidates → s05/s05b → s06_reframe_subs → s07_render
backend/                   # Local FastAPI service (binds strictly to 127.0.0.1)
  app/api/routes/          # /api/health, /api/capabilities, /api/projects, …
  app/services/            # Media probing, faster-whisper ASR, captions, render
frontend/                  # React 18 + TypeScript + Vite + Tailwind CSS
  src/features/dashboard/  # Home screen & capabilities probe
  src/components/studio/   # Workbench: clips list, timeline, inspector, player
docs/                      # Architecture, evaluation, brand system, PRD
tests/                     # Test suite (159 core + 274 backend + 106 frontend)
```

| Reference Document | What it covers |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | How stages fit together, the manifest lifecycle, pipeline internals |
| [docs/EVALUATION.md](docs/EVALUATION.md) | Measured ranking benchmarks: precision, recall, F1, coverage |
| [docs/POLICY.md](docs/POLICY.md) | What leaves your machine, URL ingestion rights, model licenses |
| [docs/BRANDING.md](docs/BRANDING.md) | Name, colors, one-accent rule, typography system |
| [docs/PERFORMANCE.md](docs/PERFORMANCE.md) | Two-pass transcription profiles and memory benchmarks |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Development setup, code guidelines, PR requirements |

---

## 📈 Star History

[![Star History Chart](https://api.star-history.com/svg?repos=thewizard2030/laqta&type=Date)](https://star-history.com/#thewizard2030/laqta&Date)

---

## 🤝 Contributing & Community

We welcome contributions from developers, designers, and video creators!

- Join the conversation on **[GitHub Discussions](https://github.com/thewizard2030/laqta/discussions)**.
- Report bugs or request features via **[GitHub Issues](https://github.com/thewizard2030/laqta/issues)**.
- Read our **[CONTRIBUTING.md](CONTRIBUTING.md)** and **[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)**.
- Security vulnerabilities should be reported privately according to **[SECURITY.md](SECURITY.md)**.

---

## 📄 License

[MIT](LICENSE) — © 2026 Mohamed Aboelela and Laqta contributors.

Third-party licenses are listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Laqta ships **no** proprietary weights; models are fetched on first use into your local Hugging Face cache.
