# Laqta — Product Requirements Document (PRD)

**Status:** Draft v1.0 — implementation-ready scope  
**Product:** Laqta  
**Positioning:** Local-first, open-source long-video-to-Shorts studio, with Arabic-first UX and explainable clip selection.  
**Primary environment:** Fedora Linux, CPU-first, 8 GB RAM.  
**Default promise:** Help creators find, review, and render strong short-form clips. Laqta does not promise virality or claim to predict views reliably.

---

## 1. Product vision

Laqta turns a long video into a ranked set of short, self-contained clip candidates. It combines transcript structure, speech timing, audio characteristics, scene/face cues, and optional LLM analysis. The user can inspect why a clip was proposed, adjust its boundaries, choose a vertical layout and subtitle style, and render an MP4 locally.

The product should be useful without a paid API key. LLM providers and advanced computer-vision models are optional adapters, not hard dependencies.

### Product principles

1. **Local-first:** Local media stays on the user's device by default. No account or cloud upload is required.
2. **Arabic-first, not Arabic-only:** Handle Arabic RTL captions and Arabic/English mixed speech deliberately; support English too.
3. **Explainable recommendations:** Show evidence and confidence limitations rather than a mysterious “95% viral” score.
4. **Human-in-the-loop:** No auto-publishing in the MVP; users review and approve cuts.
5. **Progressive complexity:** Ship a reliable CPU-friendly pipeline before speaker diarization, active-speaker models, or GPU-heavy workflows.
6. **Reproducible outputs:** Persist processing settings, source time ranges, model/provider identity, and render configuration.
7. **Rights-aware ingestion:** Local file import is the first supported source. URL downloading is a later opt-in adapter for content the user owns or is authorized to download.

## 2. Target users and initial use cases

### Primary users
- Podcasters and interview creators.
- Arabic-speaking YouTubers in Egypt and the Gulf.
- Educators and tutorial creators.
- Small creator teams that want to repurpose long-form material without a mandatory subscription.

### MVP use cases
- Import a local MP4/MOV/MKV/WebM file.
- Generate a transcript and timestamps.
- Suggest 5–10 promising clips with reasons and editable boundaries.
- Render a vertical 9:16 preview with burned-in subtitles.
- Export MP4 and SRT/ASS captions locally.

### Explicit non-goals for MVP
- Guaranteed virality, reach, or views.
- Automatic upload/publishing/scheduling to YouTube or other platforms.
- Cloud accounts, collaboration, billing, subscriptions, or telemetry by default.
- Fully automatic active-speaker detection across complex multi-camera podcasts.
- Voice cloning/dubbing.
- Full nonlinear video editor replacement.
- Mandatory URL downloading or mandatory commercial AI APIs.

## 3. Product differentiation

Existing open-source projects already cover a large part of the basic feature set: transcription, LLM clip selection, subtitles, vertical cropping, and face tracking. Laqta should not compete merely by checking the same feature boxes.

Differentiation priorities:
1. Arabic caption correctness: RTL layout, punctuation, mixed Arabic/English segments, font fallback, and real-device render tests.
2. Explainable clip selection: each candidate cites the transcript spans and measurable signals behind the recommendation.
3. Honest scoring: a Clip Potential Score (CPS) measures heuristic/editorial quality, not a calibrated probability of virality.
4. Modest hardware: one-at-a-time processing, lazy-loaded models, cancellation, resume-safe jobs, and visible memory-conscious settings.
5. Evaluation-first development: a curated test set and human editor ratings are used before claims of quality improvements.
6. Provider adapters: rule-based fallback always works; Ollama/OpenAI-compatible local endpoints and hosted LLM providers are optional.

## 4. User journey

1. User launches Laqta locally and sees recent projects.
2. User creates a project and imports a local video.
3. Laqta probes the media with FFprobe and shows duration, dimensions, audio presence, file size, and compatibility warnings.
4. User chooses a transcription model size and language (auto/Arabic/English).
5. Laqta extracts mono 16 kHz audio to a temporary working directory and transcribes it.
6. The transcript is saved with segment and, when available, word-level timestamps. If word timestamps are unavailable, Laqta records that limitation and falls back gracefully.
7. Candidate generation creates transcript-aligned windows from sentences, topic boundaries, silences, and target duration settings.
8. Optional LLM selection ranks candidate IDs and produces structured reasons. It is not allowed to invent timestamps or create unsupported claims.
9. Laqta validates every selected range and computes feature scores and penalties.
10. User reviews candidates, previews source time ranges, edits start/end points and title/hook text.
11. User selects a layout (center crop, face-guided crop if available, blurred background; split-screen is later/experimental), caption style, and output resolution.
12. Laqta renders with FFmpeg, presents the output path and a preview, and keeps logs for troubleshooting.

## 5. Functional requirements

### FR-01 — Project and media management
- Create, rename, and delete projects.
- Import local video via browser file picker or drag-and-drop.
- Support MP4, MOV, MKV, and WebM where installed FFmpeg supports decoding.
- Validate file size, extension, media signature/probe result, duration, and available disk space.
- Store media in a controlled Laqta data directory; do not trust client-supplied filesystem paths.
- Preserve original source media unless the user explicitly deletes it.

### FR-02 — Media probing and audio extraction
- Use `ffprobe` to determine codecs, duration, frame rate, resolution, and audio streams.
- Extract temporary mono 16 kHz audio for transcription using FFmpeg.
- Run subprocesses with argument arrays, no `shell=True`, timeouts, cancellation, bounded logs, and clear failure messages.
- Detect missing FFmpeg/libass and provide installation guidance without crashing.

### FR-03 — Transcription
- Provide a pluggable `TranscriptionProvider` interface.
- Initial implementation: faster-whisper on CPU with configurable model size and int8 compute where supported.
- Default to a conservative model setting suitable for an 8 GB machine; model choice is user-configurable.
- Support Arabic, English, and auto language detection as supported by the selected model.
- Persist text, segment timestamps, confidence/metadata when available, and word timestamps when available.
- Allow re-transcription with a different model/language setting without destroying prior results.
- Word-level alignment may be offered through an optional WhisperX adapter after dependency and Arabic alignment tests. Do not claim millisecond-level accuracy universally.

### FR-04 — Candidate generation
- Build candidate windows from transcript boundaries, pauses, sentence boundaries, and configurable target duration (default 30–55 seconds; user can change it).
- Candidate boundaries must reference existing transcript tokens/segments wherever possible.
- Avoid starting/ending mid-word; use short contextual padding when needed.
- Reject or penalize candidates with incomplete syntax, unresolved pronouns/context, excessive silence, or too little semantic content.
- Avoid excessive overlap and near-duplicate candidates by default.
- Store candidates before ranking so the process can be reproduced and debugged.

### FR-05 — Clip ranking and explanations
- Introduce a `ClipScorer` interface with deterministic baseline features and optional model/provider features.
- Initial Clip Potential Score (CPS), 0–100, is a heuristic/editorial score, not a probability of virality.
- Initial configurable weights:
  - self-contained idea / context independence: 25%
  - opening hook / curiosity: 20%
  - story or answer completion: 20%
  - usefulness, novelty, emotion, or surprise: 10%
  - speech clarity and audio dynamics: 10%
  - visual composition: 5%
  - boundary/timing quality: 10%
- Penalties: cut-off words, unfinished clauses, long dead air, low intelligibility, redundant content, unsupported context, or sensitive/high-risk content that should be manually reviewed.
- Weights are configuration, not scientific claims; evaluate them with human ratings before tuning.
- Missing modalities must be marked `unavailable`, not treated as positive evidence or silently represented as zero.
- Every LLM response is validated against a strict Pydantic schema; retries are bounded.
- LLM receives candidate IDs and transcript excerpts and returns candidate IDs, rationale, hook suggestion, and evidence spans—not arbitrary timestamps.
- Keep transcript text as untrusted data; never execute instructions contained in source transcripts.

### FR-06 — Audio features
- Later MVP-compatible enhancement: compute RMS/volume envelope, silence proportion, and optional pitch/tempo proxies.
- Loudness alone must not increase the score automatically; excitement varies by genre and culture.
- Audio features must include normalization rules and explanatory labels.
- Laugh/cheer detection is optional and must be treated as uncertain unless validated.

### FR-07 — Video analysis and reframing
- Initial rendering modes: center crop; blurred background with source frame fit; manual horizontal focal point.
- Optional lightweight face detection/tracking adapter, disabled by default if dependencies are missing or too costly.
- Smooth crop coordinates using temporal filtering and reset tracking at scene cuts.
- Never switch crop position on every small face movement; use hysteresis/cooldown.
- Active-speaker detection and automatic split-screen are post-MVP or experimental adapters.
- Do not ship Ultralytics YOLO in the core dependency set without a deliberate license decision; model and dependency licenses must be documented.

### FR-08 — Captions
- Generate SRT and ASS.
- Support editable word/line timing and adjustable max characters/line, safe margins, font, size, stroke, and color.
- Support RTL and mixed Arabic/Latin text. Test punctuation, numerals, hashtags, and embedded English names.
- Optional active-word highlight/ASS karaoke effect only when timing quality permits; provide a clean non-karaoke fallback.
- Do not rely on a single font being present; detect missing fonts and suggest local fonts.
- Preview rendering before final export.

### FR-09 — Rendering/export
- Use FFmpeg as the primary renderer; no MoviePy dependency in the core path.
- Export 1080×1920 MP4 (H.264 video + AAC audio) as a preset, with lower-resolution/quality options for CPU-constrained devices.
- Render one job at a time by default on 8 GB RAM.
- Save rendered outputs separately from sources, with stable filenames and no overwriting without confirmation.
- Support cancel/retry; failed renders must not be marked complete.
- Store the exact ffmpeg command/config for debugging without exposing secrets.

### FR-10 — Job queue and progress
- Long-running jobs must not block HTTP request handlers.
- Persist job state in SQLite: queued, running, succeeded, failed, cancelled.
- Expose progress stage, percentage when measurable, elapsed time, and readable errors.
- On restart, mark interrupted jobs as recoverable or failed with a resume/retry action; do not claim automatic resume unless implemented.
- Use one worker by default and configurable limits.

### FR-11 — Optional provider adapters
- Rule-based/local baseline operates without any external key.
- Optional OpenAI-compatible endpoint adapter for local servers such as Ollama/LM Studio.
- Optional hosted provider adapter may be added later; keys are stored locally and never logged.
- Provider requests disclose when transcript text leaves the device and require explicit user opt-in.
- Provide request timeouts, token limits, retries with backoff, and a deterministic fallback.

### FR-12 — URL ingestion
- The platform-policy/rights review was completed by owner decision on
  2026-10-19; yt-dlp is enabled and ON by default. An operator can still
  disable it explicitly (`QATTA_ENABLE_URL_INGESTION=false`); when
  disabled, every path refuses with a clear error (fail-closed).
- Every import must surface a user confirmation that they own the content
  or have permission to download/use it (backend refuses without it).
- YouTube captions-first mode (`youtube_subs_first`): Pass 1 reads the
  platform caption track via a `skip_download` yt-dlp call (no local
  Whisper on the long media, no full-video download). Utterances come
  from real cue timestamps with rolling-caption dedup; the LLM selects
  candidates by `u_id` only; stage s05b downloads ONLY the ranking-winning
  sections (`download_ranges`, keyframe-aligned) and Pass 2 re-times words
  locally on those sections, offset-corrected to the source timeline.
  Real per-stage wall time is persisted in `manifest.stage_timings_ms`;
  performance numbers must cite that measurement.
- Never assume `--write-info-json` includes YouTube “Most Replayed” heatmap data.
- Heatmap/replay data is optional and used only if it is actually returned and validated.
- Do not bypass DRM, paywalls, authentication, or access controls.

### FR-13 — Feedback and learning (post-MVP)
- Allow export/import of a simple CSV for manual tracking of published clips and performance metrics.
- Do not automate YouTube analytics connection in MVP.
- Store source candidate IDs with resulting rendered clips so later performance data can be associated with the exact clip.
- Avoid training claims until a sufficiently large, permissioned dataset and evaluation protocol exist.

### FR-14 — Accessibility and UX
- Clear keyboard focus and labels.
- Progress indication and cancellation for long tasks.
- Dark theme is acceptable, but captions and controls must meet readable contrast.
- Arabic layout may be RTL; transcript editor must support both RTL and LTR.
- Show “AI suggestion — review before publishing” where recommendations may be wrong.

## 6. Technical architecture

### Stack
- Frontend: React + TypeScript + Vite + Tailwind CSS; use a restrained component library if helpful.
- Backend: Python + FastAPI + Pydantic.
- Persistence: SQLite; SQLAlchemy or SQLModel only if it simplifies migrations and testability.
- Media: FFmpeg/FFprobe subprocesses.
- ASR: faster-whisper primary; WhisperX as optional adapter after verification.
- Scoring: deterministic Python feature layer + optional LLM provider interface.
- Tests: pytest; Vitest + React Testing Library; optional end-to-end smoke test.

### Repository layout

```text
qatta/
  frontend/
    src/
      app/
      components/
      features/projects/
      features/transcription/
      features/clips/
      features/rendering/
      lib/api/
      types/
  backend/
    app/
      api/routes/
      core/config.py
      core/logging.py
      db/
      schemas/
      services/media/
      services/transcription/
      services/candidates/
      services/scoring/
      services/captions/
      services/rendering/
      providers/llm/
      jobs/
      main.py
    tests/
  docs/
  scripts/
  .env.example
  README.md
  LICENSE
  THIRD_PARTY_NOTICES.md
```

### Recommended storage
- App data root: `~/.local/share/qatta/` on Linux, configurable.
- Projects and metadata in SQLite.
- Source media, temp audio, transcripts, caption files, outputs, and per-job logs in project-specific directories.
- Temp files should be cleaned after successful tasks according to settings; preserve user exports.

### API shape (initial contracts; adjust only with documented reason)
- `GET /api/health`
- `GET /api/capabilities` — FFmpeg, libass, model, and provider availability.
- `GET /api/projects`
- `POST /api/projects`
- `GET /api/projects/{project_id}`
- `DELETE /api/projects/{project_id}`
- `POST /api/projects/{project_id}/media` — upload local file.
- `GET /api/media/{media_id}`
- `POST /api/media/{media_id}/transcription-jobs`
- `POST /api/media/{media_id}/candidate-jobs`
- `GET /api/jobs/{job_id}`
- `POST /api/jobs/{job_id}/cancel`
- `GET /api/media/{media_id}/clips`
- `PATCH /api/clips/{clip_id}` — update start/end/title/hook fields after validation.
- `POST /api/clips/{clip_id}/render-jobs`
- `GET /api/clips/{clip_id}/artifacts`

Use polling for MVP job updates. Add SSE only if needed. Validate IDs, ownership within the local app, every request body, and media duration bounds.

## 7. Data model

Minimum tables/entities:
- `Project(id, name, created_at, updated_at)`
- `MediaAsset(id, project_id, safe_path, original_name, size_bytes, duration_ms, width, height, video_codec, audio_codec, status, created_at)`
- `Transcript(id, media_id, language, provider, model, status, segments_json, word_timestamps_available, created_at)`
- `Candidate(id, media_id, start_ms, end_ms, transcript_span_ids_json, title, hook, rationale_json, feature_scores_json, cps, status, created_at)`
- `Job(id, project_id, media_id, type, status, stage, progress, error_code, error_message, config_json, created_at, started_at, finished_at)`
- `RenderedClip(id, candidate_id, output_path, width, height, duration_ms, render_config_json, created_at)`
- `ProviderConfig(id, provider, non_secret_config_json, encrypted_secret_reference_or_local_secret_key, enabled)`

Secrets must not be placed in plain logs, returned from the API, or committed. For a single-user local application, use environment variables or local OS secret storage later; document any limitations of the first version.

## 8. Scoring protocol

### Initial baseline
- Generate stable, transcript-grounded candidates first.
- Calculate measurable features in Python when possible.
- Ask an optional LLM to rank only the candidates supplied to it.
- Validate returned IDs, durations, boundary constraints, and evidence references.
- Blend scores only when the relevant evidence exists.

### Evaluation before tuning
- Assemble 20–50 permissioned test clips first; expand later.
- Include Egyptian Arabic, Gulf Arabic, Modern Standard Arabic, English, mixed-language speech, single speaker, two speakers, and noisy audio.
- Ask at least one human editor to rank candidate usefulness/standalone completeness on a 1–5 rubric.
- Measure top-5 hit rate, boundary correction distance, transcript error on a manually verified subset, render success rate, memory usage, and processing time.
- Do not tune solely against views: views are confounded by audience size, posting time, topic, and channel history.

## 9. Security, privacy, copyright, and licenses

- Bind backend to `127.0.0.1` by default; warn before any external binding.
- Do not expose a permissive CORS configuration.
- Validate file content and probe media instead of trusting extensions.
- Use subprocess argument arrays, timeouts, cancellation, restricted output paths, and resource limits.
- Treat subtitles/transcripts from the video as untrusted data and guard LLM prompts against instruction injection.
- No telemetry by default. If telemetry is ever added, make it explicit and opt-in.
- Local file processing is the default. Any cloud LLM feature must disclose what text leaves the machine and require opt-in.
- Initial project license can be MIT, but only after an inventory of all copied/adapted code and dependencies. Publish `THIRD_PARTY_NOTICES.md`; audit model-weight licenses separately from library licenses.
- Do not copy code from an existing project unless its license and attribution obligations have been checked. Learning from an architecture is not the same as copying source code.
- URL ingestion must include a user rights confirmation and must not circumvent access controls.

## 10. Performance requirements (initial targets to measure, not promises)

On a reference CPU-only Fedora machine with 8 GB RAM:
- UI and API should remain responsive while jobs run.
- Only one heavy media/ASR job runs at a time by default.
- Model loading is lazy and memory use is configurable.
- Jobs expose progress and cancellation.
- A small test video should render in a deterministic integration test; long-video speed is benchmarked, not promised in advance.
- No hard maximum file size is hard-coded without documenting disk-space requirements and configurable limits.

## 11. MVP release gates

### Gate A — foundation
- Install/start instructions work on Fedora.
- Health/capabilities endpoints pass tests.
- UI can create a project and import a local video safely.

### Gate B — transcription
- Real file audio extraction and faster-whisper transcript work end-to-end.
- Missing model/download/dependency errors are actionable.
- Word-level timestamp availability is accurately reported.

### Gate C — candidates
- A video can generate candidate ranges and persisted scores.
- All ranges are valid, non-empty, within source duration, and previewable.
- LLM failure falls back to baseline ranking.

### Gate D — render
- One candidate exports as 1080×1920 MP4 on FFmpeg-capable Linux.
- Arabic SRT/ASS sample passes visual review; no claim of RTL correctness until inspected.
- Failed renders and cancelled jobs are not marked successful.

### Gate E — release quality
- Tests, formatting, dependency/license inventory, README, screenshots, sample workflow, and known limitations are documented.
- No API key or personal media is committed.

## 12. Roadmap

**P0 — Foundation:** project, upload, media probing, persistent job model, baseline UI.  
**P1 — Transcript:** faster-whisper adapter, transcript editor, segment/word timing metadata.  
**P2 — Candidates:** candidate segmentation, deterministic baseline features, optional LLM ranker, explainable scores.  
**P3 — Renderer:** clip trim, vertical presets, SRT/ASS captions, FFmpeg output, preview.  
**P4 — Better framing:** optional face detection, crop smoothing, experimental split-screen.  
**P5 — Research/evaluation:** benchmark set, editor-feedback import, score calibration experiments.  
**P6 — Optional source adapters:** yt-dlp with rights-aware UX; optional heatmap only if data is available.  
**P7 — Performance analytics:** CSV import/export for published clip metrics.

## 13. Acceptance criteria for the first usable release

A user can, without creating an account or supplying a paid API key:
1. start Laqta locally;
2. import a supported local video;
3. transcribe it with the selected local model;
4. receive at least one valid clip candidate or a clear message explaining why none passed the rules;
5. inspect and edit the candidate boundaries;
6. render a vertical MP4 with Arabic or English captions where the dependencies support it;
7. find the output and job logs locally;
8. rerun automated tests successfully.

---

## Research and dependency links

These are starting points, not blanket endorsements. Re-check repository activity, API details, and licenses at implementation time.
- OpenShorts: https://github.com/MinTALI/openshorts
- ClippyMe: https://github.com/fralapo/clippyme
- faster-whisper: https://github.com/SYSTRAN/faster-whisper
- WhisperX: https://github.com/m-bain/whisperX
- yt-dlp: https://github.com/yt-dlp/yt-dlp
- FFmpeg documentation: https://ffmpeg.org/documentation.html
- Ultralytics licensing: https://www.ultralytics.com/license
