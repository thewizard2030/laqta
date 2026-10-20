#!/usr/bin/env python3
"""Reproducible transcription performance benchmark for Qatta (docs/PERFORMANCE.md).

Measures, for one audio sample per invocation:
- Model startup (load) time, cold within the process (process-environment
  cold start; OS page cache warm unless --cold-page-cache is used).
- Audio decode time (16 kHz mono float32, streamed chunked path).
- Pass A transcription wall time, with or without word timestamps.
- Audio duration and real-time factor (RTF = processing / audio duration).
- Peak process RSS via getrusage(RUSAGE_SELF).ru_maxrss (Linux: KiB).
- Optional Pass B clip re-timing duration for a bounded [start, start+clip]
  window inside the same transcript.

The same command produces all "before"/"after" rows in docs/PERFORMANCE.md:

    cd backend
    .venv/bin/python tools/benchmark_transcription.py \\
        --audio /tmp/qatta_bench/sample_en.wav --language en

    # before = full-video word timestamps (legacy default)
    .venv/bin/python tools/benchmark_transcription.py --audio ... --language en --word-timestamps

    # after = Pass A (profile 'fast': no full-video word timestamps)
    .venv/bin/python tools/benchmark_transcription.py --audio ... --language en

Sample generation (synths speech with espeak-ng; synthetic by design, used
for timing/RTF, not accuracy):

    bash tools/benchmark_transcription.py --make-samples
"""

from __future__ import annotations

import argparse
import json
import resource
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

BENCH_ROOT = Path(tempfile.gettempdir()) / "qatta_bench"

EN_SENTENCE = (
    "Welcome to the Qatta transcription benchmark. "
    "We measure real-time factor on modest hardware. "
    "Believe it or not, local processing can be fast enough. "
)
AR_SENTENCE = (
    "مرحبًا بكم في معيار سرعة النسخ في قطة. "
    "نقيس الوقت الحقيقي على الأجهزة المتوسطة. "
    "المعالجة المحلية سريعة بما يكفي."
)

EN_WORDS = (
    "welcome to the qatta transcription benchmark we measure real time factor "
    "on modest hardware believe it or not local processing can be fast enough "
)


def make_samples(seconds: float) -> list[Path]:
    """Generate fixed English and Arabic speech samples with espeak-ng."""
    import math

    if shutil.which("espeak-ng") is None:
        raise SystemExit("espeak-ng not found; install it or pass --audio explicitly.")
    BENCH_ROOT.mkdir(parents=True, exist_ok=True)
    out = []
    reps = max(1, math.ceil(seconds / 10.0))
    for lang, text, name in (
        ("en-us", EN_SENTENCE, "sample_en.wav"),
        ("ar", AR_SENTENCE, "sample_ar.wav"),
    ):
        path = BENCH_ROOT / name
        subprocess.run(
            [
                "espeak-ng",
                "-v",
                lang,
                "-s",
                "150",
                "-w",
                str(path),
                text * reps,
            ],
            check=True,
            capture_output=True,
        )
        out.append(path)
    return out


def duration_of(path: Path) -> float:
    """Media duration via ffprobe."""
    ffprobe = shutil.which("ffprobe")
    res = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(res.stdout.strip())


def peak_rss_mib() -> float:
    """Peak resident set size of THIS process in MiB (Linux ru_maxrss = KiB)."""
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", type=Path)
    parser.add_argument("--language", choices=["en", "ar", None], default=None)
    parser.add_argument("--model", default="base")
    parser.add_argument("--compute", default="int8")
    parser.add_argument("--beam", type=int, default=1)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument(
        "--word-timestamps",
        action="store_true",
        help="Pass A WITH full-video word timestamps (legacy 'before' mode).",
    )
    parser.add_argument(
        "--clip-alignment",
        action="store_true",
        help="Also measure Pass B: bounded clip re-timing at 10 s offset.",
    )
    parser.add_argument("--clip-offset-sec", type=float, default=10.0)
    parser.add_argument("--clip-length-sec", type=float, default=30.0)
    parser.add_argument("--clip-beam", type=int, default=5)
    parser.add_argument(
        "--provider",
        choices=["faster-whisper", "groq", "assemblyai", "huggingface", "whisper.cpp", "fake"],
        default="faster-whisper",
        help="Transcription engine / provider to benchmark.",
    )
    parser.add_argument(
        "--device",
        choices=["auto", "cpu", "cuda"],
        default="auto",
        help="Target hardware device for local engines.",
    )
    parser.add_argument("--make-samples", action="store_true")
    parser.add_argument("--seconds", type=float, default=20.0)
    args = parser.parse_args()

    if args.make_samples:
        paths = make_samples(args.seconds)
        for p in paths:
            print(f"generated {p} ({duration_of(p):.2f}s)")
        return 0

    if args.audio is None:
        parser.error("--audio is required unless --make-samples")

    audio_path = args.audio.resolve()
    if not audio_path.is_file():
        parser.error(f"audio not found: {audio_path}")

    total_duration = duration_of(audio_path)
    report: dict = {
        "audio": str(audio_path),
        "provider": args.provider,
        "language_arg": args.language,
        "model": args.model,
        "compute_type": args.compute,
        "beam_size": args.beam,
        "cpu_threads": args.threads,
        "word_timestamps_pass_a": args.word_timestamps,
        "audio_duration_sec": round(total_duration, 3),
    }

    if args.provider != "faster-whisper":
        import asyncio

        from app.services.transcription.manager import transcription_manager

        t0 = time.perf_counter()
        res = asyncio.run(
            transcription_manager.transcribe(
                audio_path=audio_path,
                provider_name=args.provider,
                language=args.language,
                model_size=args.model,
                word_timestamps=args.word_timestamps,
                use_cache=False,
            )
        )
        elapsed = time.perf_counter() - t0
        report["elapsed_sec"] = round(elapsed, 3)
        report["rtf"] = round(elapsed / total_duration, 3) if total_duration else None
        report["segments_count"] = len(res.segments)
        report["text_length"] = len(res.text)
        report["device"] = res.device
        report["compute_type"] = res.compute_type
        report["fallback_reason"] = res.fallback_reason
        report["peak_rss_overall_mib"] = round(peak_rss_mib(), 1)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("faster-whisper is not installed in this environment.", file=sys.stderr)
        return 2

    # 1. Model startup (cold within this process), using Qatta's offline
    # weight cache so measurements reflect the app's configuration.
    from app.core.config import settings as app_settings
    from app.services.transcription.faster_whisper_provider import (
        _decode_audio_to_float32,
        find_local_whisper_snapshot,
    )

    target_device = "cpu"
    fallback_reason = None
    if args.device in ("cuda", "auto"):
        try:
            import ctranslate2

            if ctranslate2.get_cuda_device_count() > 0:
                target_device = "cuda"
            else:
                if args.device == "cuda":
                    fallback_reason = "No CUDA devices detected; CPU fallback active"
        except Exception as e:
            if args.device == "cuda":
                fallback_reason = f"CUDA query error: {e}"

    report["target_device"] = target_device
    report["fallback_reason"] = fallback_reason

    t0 = time.perf_counter()
    local_snap = find_local_whisper_snapshot(args.model, [app_settings.get_whisper_models_dir()])
    model_target = local_snap if local_snap else args.model
    model_kwargs: dict = {
        "model_size_or_path": model_target,
        "device": target_device,
        "compute_type": args.compute if target_device == "cpu" else "float16",
        "cpu_threads": args.threads,
        "num_workers": 1,
    }

    if not local_snap:
        model_kwargs["download_root"] = str(app_settings.get_whisper_models_dir())
    model = WhisperModel(**model_kwargs)
    report["model_load_sec"] = round(time.perf_counter() - t0, 3)
    report["peak_rss_after_model_mib"] = round(peak_rss_mib(), 1)

    # 2. Audio decode (streaming chunked WAV path)
    t0 = time.perf_counter()
    audio = _decode_audio_to_float32(audio_path)
    report["audio_decode_sec"] = round(time.perf_counter() - t0, 3)
    report["audio_samples"] = len(audio)

    # 3. Pass A transcription
    t0 = time.perf_counter()
    segments, info = model.transcribe(
        audio,
        language=args.language,
        beam_size=args.beam,
        word_timestamps=args.word_timestamps,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500),
    )
    n_segments = 0
    n_words = 0
    last_end = 0.0
    text_parts = []
    for seg in segments:
        n_segments += 1
        last_end = seg.end
        text_parts.append(seg.text.strip())
        if args.word_timestamps and seg.words:
            n_words += len(seg.words)
    pass_a_sec = time.perf_counter() - t0
    report["pass_a_sec"] = round(pass_a_sec, 3)
    report["pass_a_segments"] = n_segments
    report["pass_a_words"] = n_words
    report["transcribed_duration_sec"] = round(last_end, 3)
    report["rtf_pass_a"] = round(pass_a_sec / total_duration, 3) if total_duration else None
    report["pass_a_text_chars"] = sum(len(t) for t in text_parts)
    report["peak_rss_after_pass_a_mib"] = round(peak_rss_mib(), 1)

    # 4. Optional Pass B: bounded clip re-timing with offset conversion
    if args.clip_alignment:
        from app.services.transcription.alignment import convert_words_to_absolute

        offset = max(args.clip_offset_sec, 0.0)
        clip_len = min(args.clip_length_sec, max(1.0, total_duration - offset))
        start_sample = int(offset * 16000)
        end_sample = start_sample + int(clip_len * 16000)
        clip_audio = audio[start_sample:end_sample]
        if len(clip_audio) < 1000:
            report["pass_b"] = {"skipped": "clip window exceeds audio length"}
        else:
            t0 = time.perf_counter()
            clip_segments, _ = model.transcribe(
                clip_audio,
                language=args.language,
                beam_size=args.clip_beam,
                word_timestamps=True,
            )
            raw_words = []
            for seg in clip_segments:
                for w in seg.words or []:
                    raw_words.append((w.word.strip(), w.start, w.end, None))
            absolute = convert_words_to_absolute(raw_words, clip_start_sec=offset)
            pass_b_sec = time.perf_counter() - t0
            report["pass_b"] = {
                "clip_offset_sec": offset,
                "clip_length_sec": round(clip_len, 3),
                "duration_sec": round(pass_b_sec, 3),
                "rtf_pass_b": round(pass_b_sec / clip_len, 3) if clip_len else None,
                "words_absolutized": len(absolute),
                "first_word_absolute_start": (round(absolute[0].start, 3) if absolute else None),
                "last_word_absolute_end": (round(absolute[-1].end, 3) if absolute else None),
            }
            report["peak_rss_after_pass_b_mib"] = round(peak_rss_mib(), 1)

    report["total_sec_excl_model_load"] = round(report["audio_decode_sec"] + pass_a_sec, 3)
    report["peak_rss_overall_mib"] = round(peak_rss_mib(), 1)

    print(json.dumps(report, indent=2, ensure_ascii=False))

    # Cache cycle note: cache lookup cost is a file SHA-256 + settings hash,
    # measured separately in docs (see tests/test_transcription_cache.py and
    # PERFORMANCE.md). It is linear in file size and independent of the model.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
