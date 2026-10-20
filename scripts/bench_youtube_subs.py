#!/usr/bin/env python3
"""Operational benchmark for the YouTube captions-first pipeline.

This is a MEASUREMENT tool, not a test. It runs the real pipeline against
a real YouTube video the caller has rights to use:

    python scripts/bench_youtube_subs.py \
        "https://www.youtube.com/watch?v=<ID>" --rights-confirmed

Every step's MEASURED wall time is printed from
``manifest.stage_timings_ms``. This script never asserts a target like
"<30 s for a 2-hour video" — it only reports what the host machine
actually measured, so any performance claim can cite real data.

Requirements / gates (all enforced):
- yt-dlp must be installed locally (no download of the full media).
- ``--rights-confirmed`` is mandatory: run ONLY on videos you own or
  have permission to process (PRD FR-12).
- Pass 2 (word timing) is local faster-whisper; the first run downloads
  model weights at its own cost and is NOT included in the caption-fetch
  claim.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from qatta.core.config import QattaSettings  # noqa: E402
from qatta.core.schema import QattaManifest  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="Public YouTube video URL")
    parser.add_argument(
        "--rights-confirmed",
        action="store_true",
        help="Confirm you own the video or have permission to process it.",
    )
    parser.add_argument(
        "--transcription-backend",
        default="youtube_subs_first",
        choices=["youtube_subs_first", "local_turbo"],
        help="Compare the captions-first flow against full local Whisper.",
    )
    parser.add_argument(
        "--render",
        action="store_true",
        help="Also render the winning shorts from their section files.",
    )
    args = parser.parse_args()

    if not args.rights_confirmed:
        parser.error(
            "refusing to run without --rights-confirmed (PRD FR-12): run "
            "ONLY on videos you own or have permission to use."
        )
    if shutil.which("yt-dlp") is None:
        try:
            import yt_dlp  # noqa: F401
        except ImportError:
            print("yt-dlp is not installed — nothing was fetched.", file=sys.stderr)
            return 1

    settings = QattaSettings(
        transcription_backend=args.transcription_backend,
        _env_file=None,
    )
    project_id = f"bench_{int(time.time())}"
    work_dir = settings.data_dir / "projects" / project_id
    work_dir.mkdir(parents=True, exist_ok=True)

    placeholder = QattaManifest(
        project_id=project_id,
        source_path=args.url,
        duration_sec=1.0,
    )
    manifest_path = work_dir / "qatta_manifest.json"
    manifest_path.write_text(placeholder.model_dump_json(), encoding="utf-8")

    from qatta.core.pipeline import PipelineOrchestrator
    from qatta.stages.s01_ingest import ingestor
    from qatta.stages.s02_transcript import fast_pass, fine_pass
    from qatta.stages.s03_multimodal import analyzer
    from qatta.stages.s04_candidates import generator
    from qatta.stages.s05_ranking import scorer
    from qatta.stages.s05b_section_fetch import section_fetch
    from qatta.stages.s06_render import renderer

    orch = PipelineOrchestrator(project_id=project_id, work_dir=work_dir, settings=settings)
    ingestor.register(orch)
    fast_pass.register(orch)
    fine_pass.register(orch)
    analyzer.register(orch)
    generator.register(orch)
    scorer.register(orch)
    section_fetch.register(orch)
    if args.render:
        renderer.register(orch)

    stages = [
        "s01_ingest",
        "s02_transcript",
        "s03_multimodal",
        "s04_candidates",
        "s05_ranking",
        "s05b_section_fetch",
        "s02b_fine_alignment",
    ] + (["s06_render"] if args.render else [])
    failed_at = None
    for name in stages:
        try:
            orch.run_stage(name)
        except Exception as e:  # surface the honest stage failure
            failed_at = name
            print(f"stage {name} FAILED: {e}", file=sys.stderr)
            break
    manifest = orch.manifest

    print(
        json.dumps(
            {
                "project_id": project_id,
                "profile": f"{args.transcription_backend}",
                "source_url": args.url,
                "duration_sec": manifest.duration_sec,
                "utterances": len(manifest.atomic_utterances),
                "candidates": len(manifest.candidates),
                "sections_fetched": sum(1 for c in manifest.candidates if c.section_media_path),
                "work_dir": str(work_dir),
                "failed_at_stage": failed_at,
                "stage_timings_ms": manifest.stage_timings_ms,
                "total_pipeline_ms": sum(manifest.stage_timings_ms.values()),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    print(
        "\nNOTE: measurements above are specific to this machine and this "
        "run. Any performance number you report must come from this file — "
        "never from the '<30 s' style estimates."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
