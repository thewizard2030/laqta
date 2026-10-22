#!/usr/bin/env python3
"""Measure how well the deterministic ranking finds the good clips.

This is the benchmark the project's roadmap promised: a small, reproducible
evaluation of the ranking signals, with the metrics the highlight-detection
literature uses (precision, recall, F1, coverage, bad coverage).

    python scripts/evaluate_ranking.py                       # run + report
    python scripts/evaluate_ranking.py --check               # fail on a regression
    python scripts/evaluate_ranking.py --dataset benchmarks/clip_selection_v1.json

The dataset is a narration script split into labelled sentences. The media is
synthesised from that script, so the labelled spans are exact and nothing
third-party is committed. The pipeline that runs is the real one:
s01_ingest -> s02_transcript -> s04_candidates -> s05_ranking.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import wave
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATASET = REPO_ROOT / "benchmarks" / "clip_selection_v1.json"
DEFAULT_BASELINE = REPO_ROOT / "benchmarks" / "baseline.json"

# A selected clip counts as a hit when it covers at least this fraction of
# a labelled highlight.
HIT_COVERAGE = 0.5


@dataclass
class Sentence:
    text: str
    label: str
    start_sec: float = 0.0
    end_sec: float = 0.0


@dataclass
class Item:
    id: str
    title: str
    language: str
    sentences: list[Sentence] = field(default_factory=list)

    @property
    def duration_sec(self) -> float:
        return max((s.end_sec for s in self.sentences), default=0.0)

    @property
    def highlight_spans(self) -> list[tuple[float, float]]:
        return [(s.start_sec, s.end_sec) for s in self.sentences if s.label == "highlight"]


def _load_dataset(path: Path) -> list[Item]:
    data = json.loads(path.read_text(encoding="utf-8"))
    items: list[Item] = []
    for raw in data.get("items", []):
        item = Item(
            id=raw["id"],
            title=raw.get("title", raw["id"]),
            language=raw.get("language", "en"),
        )
        for sentence in raw["sentences"]:
            item.sentences.append(Sentence(text=sentence["text"], label=sentence["label"]))
        items.append(item)
    return items


def _api(method: str, url: str, payload: dict | None = None) -> dict | list:
    """Call the local API and return the decoded JSON."""
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(  # noqa: S310 - a fixed localhost URL
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=300) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


def _upload(url: str, path: Path) -> dict:
    """Upload a media file (multipart, without a third-party dependency)."""
    boundary = "----laqtabenchmark"
    body = (
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
            "Content-Type: video/mp4\r\n\r\n"
        ).encode()
        + path.read_bytes()
        + f"\r\n--{boundary}--\r\n".encode()
    )
    request = urllib.request.Request(  # noqa: S310
        url,
        data=body,
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(request, timeout=300) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


def _wait(check, timeout: int = 900, interval: float = 2.0, what: str = "condition") -> None:
    """Poll until ``check`` returns a truthy value."""
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(interval)
    raise SystemExit(f"timed out after {timeout}s waiting for {what}")


def _synthesise(item: Item, workdir: Path) -> tuple[Path, list[Sentence]]:
    """Synthesise the narration and record every sentence's exact span.

    Each sentence is synthesised on its own, so the boundaries are exact —
    the labels can be compared to real milliseconds.
    """
    if shutil.which("espeak-ng") is None:
        raise SystemExit(
            "espeak-ng is required to synthesise the benchmark narration "
            "(a development-only tool: the application never uses it)."
        )

    parts_dir = workdir / item.id
    parts_dir.mkdir(parents=True, exist_ok=True)

    cursor = 0.0
    sentences: list[Sentence] = []
    parts: list[Path] = []
    for index, sentence in enumerate(item.sentences):
        part = parts_dir / f"part_{index:03d}.wav"
        subprocess.run(
            [
                "espeak-ng",
                "-v",
                item.language,
                "-s",
                "150",
                "-w",
                str(part),
                sentence.text,
            ],
            check=True,
            capture_output=True,
        )
        with wave.open(str(part), "rb") as handle:
            frames = handle.getnframes()
            rate = handle.getframerate()
        duration = frames / float(rate)
        sentence.start_sec = cursor
        sentence.end_sec = cursor + duration
        # The next sentence starts after the pause, so the label spans stay
        # exact.
        cursor += duration
        if index < len(item.sentences) - 1:
            cursor += SENTENCE_PAUSE_SEC
        sentences.append(sentence)
        parts.append(part)

    narration = parts_dir / "narration.wav"
    _concatenate(parts, narration)

    video = parts_dir / "media.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x0B0F19:s=1280x720:r=25",
            "-i",
            str(narration),
            "-c:v",
            _video_encoder(),
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(video),
        ],
        check=True,
        capture_output=True,
    )
    return video, sentences


def _video_encoder() -> str:
    """The first H.264 encoder this FFmpeg build actually has."""
    listing = subprocess.run(
        ["ffmpeg", "-hide_banner", "-encoders"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    for encoder in ("libx264", "libopenh264", "mpeg4"):
        if encoder in listing:
            return encoder
    raise SystemExit("no usable video encoder was found in this FFmpeg build")


# The pause between two synthesised sentences. Without it the voice activity
# detector sees one continuous utterance and the pipeline has no boundaries to
# work with — the pause is what makes the benchmark realistic.
SENTENCE_PAUSE_SEC = 2.1


def _concatenate(parts: list[Path], target: Path) -> None:
    """Join the WAV parts into one file, with a pause between sentences."""
    import numpy as np

    with wave.open(str(parts[0]), "rb") as first:
        params = first.getparams()

    frames: list = []
    for index, part in enumerate(parts):
        with wave.open(str(part), "rb") as handle:
            data = np.frombuffer(handle.readframes(handle.getnframes()), dtype="<i2")
        frames.append(data)
        if index < len(parts) - 1:
            gap = np.zeros(int(params.framerate * SENTENCE_PAUSE_SEC), dtype="<i2")
            frames.append(gap)

    with wave.open(str(target), "wb") as out:
        out.setparams(params)
        out.writeframes(np.concatenate(frames).tobytes())


def _run_pipeline(base: str, media: Path, language: str = "en") -> list[dict]:
    """Run the studio's own path and return the ranked candidates.

    The benchmark deliberately drives the **studio's** path (import ->
    transcription job -> candidate generation + ranking over HTTP), not the
    core pipeline directly: what is measured must be what a user gets.
    """
    project = _api("POST", f"{base}/api/projects", {"name": "benchmark"})
    media_record = _upload(f"{base}/api/projects/{project['id']}/media", media)

    _api(
        "POST",
        f"{base}/api/media/{media_record['id']}/transcription-jobs",
        {"profile": "fast", "language": language},
    )

    def transcribed() -> bool:
        transcripts = _api("GET", f"{base}/api/media/{media_record['id']}/transcripts")
        return bool(transcripts) and bool(transcripts[0].get("text"))

    _wait(transcribed, what="the transcript")

    _api("POST", f"{base}/api/media/{media_record['id']}/candidates", {})
    candidates = _api("GET", f"{base}/api/media/{media_record['id']}/candidates")

    return [
        {
            "clip_id": candidate["id"],
            "start_sec": candidate["start_ms"] / 1000.0,
            "end_sec": candidate["end_ms"] / 1000.0,
            "cps": _cps_total(candidate.get("cps")),
            "passed": candidate.get("veto_gates", {}).get("passed_all", True),
            "evidence": list(candidate.get("rationale") or []),
        }
        for candidate in candidates
    ]


def _cps_total(cps: object) -> float:
    """The total score, whether the API returns a number or a breakdown."""
    if isinstance(cps, (int, float)):
        return float(cps)
    if isinstance(cps, dict):
        return float(cps.get("total_score", 0.0))
    return 0.0


def _covered_fraction(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    """How much of span B lies inside span A (0..1)."""
    label_length = max(0.0, b_end - b_start)
    if label_length <= 0:
        return 0.0
    intersection = max(0.0, min(a_end, b_end) - max(a_start, b_start))
    return intersection / label_length


def _union_length(spans: list[tuple[float, float]]) -> float:
    """The total length covered by a set of (possibly overlapping) spans."""
    if not spans:
        return 0.0
    ordered = sorted(spans)
    total = 0.0
    current_start, current_end = ordered[0]
    for start, end in ordered[1:]:
        if start <= current_end:
            current_end = max(current_end, end)
        else:
            total += current_end - current_start
            current_start, current_end = start, end
    return total + (current_end - current_start)


def _score_item(item: Item, candidates: list[dict]) -> dict:
    """Precision / recall / F1 / coverage / bad coverage for one item.

    A selected clip *hits* a labelled highlight when it covers at least
    ``HIT_COVERAGE`` of that label. The test is relative to the **label**,
    not to the clip: a 40-second clip that contains a 6-second highlight
    hits it, even though the intersection-over-union of the two spans is
    small. This is the convention the highlight-detection literature uses.

    Precision counts *clips*: a clip that covers three highlights is one
    good clip, not three. Coverage uses the **union** of the selected
    intervals, because the clips overlap by design.
    """
    selected = [c for c in candidates if c["passed"]]
    highlights = item.highlight_spans

    good_clips = 0
    covered_labels: set[int] = set()
    selected_spans: list[tuple[float, float]] = []
    bad_spans: list[tuple[float, float]] = []

    for candidate in selected:
        selected_spans.append((candidate["start_sec"], candidate["end_sec"]))
        hit = False
        for index, (start, end) in enumerate(highlights):
            covered = _covered_fraction(candidate["start_sec"], candidate["end_sec"], start, end)
            if covered >= HIT_COVERAGE:
                covered_labels.add(index)
                hit = True
        if hit:
            good_clips += 1
        else:
            # The part of this clip that lies outside every label is the
            # "bad" part of the selection.
            for sentence in item.sentences:
                if sentence.label == "highlight":
                    continue
                start = max(candidate["start_sec"], sentence.start_sec)
                end = min(candidate["end_sec"], sentence.end_sec)
                if end > start:
                    bad_spans.append((start, end))

    precision = good_clips / len(selected) if selected else 0.0
    recall = len(covered_labels) / len(highlights) if highlights else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    media_seconds = item.duration_sec or 1.0
    selected_seconds = _union_length(selected_spans)
    coverage = min(1.0, selected_seconds / media_seconds)
    bad_seconds = _union_length(bad_spans)
    bad_coverage = min(1.0, bad_seconds / selected_seconds) if selected_seconds else 0.0

    return {
        "id": item.id,
        "selected": len(selected),
        "candidates": len(candidates),
        "highlights": len(highlights),
        "hits": len(covered_labels),
        "good_clips": good_clips,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "coverage": round(coverage, 4),
        "bad_coverage": round(bad_coverage, 4),
        "duration_sec": round(item.duration_sec, 2),
        "top_clip_cps": max((c["cps"] for c in candidates), default=0.0),
    }


def evaluate(dataset: Path, base: str = "http://127.0.0.1:8124") -> dict:
    """Run the whole benchmark and return the aggregated report."""
    items = _load_dataset(dataset)
    with tempfile.TemporaryDirectory(prefix="laqta-benchmark-") as tmp:
        workdir = Path(tmp)
        reports: list[dict] = []
        for item in items:
            media, sentences = _synthesise(item, workdir)
            item.sentences = sentences
            candidates = _run_pipeline(base, media, item.language)
            reports.append(_score_item(item, candidates))

    total_selected = sum(report["selected"] for report in reports)
    total_good = sum(report["good_clips"] for report in reports)
    total_highlights = sum(report["highlights"] for report in reports)
    precision = total_good / total_selected if total_selected else 0.0
    recall = (
        sum(report["hits"] for report in reports) / total_highlights if total_highlights else 0.0
    )
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    coverage = sum(r["coverage"] for r in reports) / len(reports) if reports else 0.0
    bad_coverage = sum(r["bad_coverage"] for r in reports) / len(reports) if reports else 0.0

    return {
        "dataset": dataset.name,
        "items": reports,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "coverage": round(coverage, 4),
        "bad_coverage": round(bad_coverage, 4),
    }


# The tolerance absorbs the small differences a different ASR build or a
# rounding change can cause. The gate catches a *regression*, not a wobble.
TOLERANCE = 0.1
BAD_COVERAGE_TOLERANCE = 0.05


def _compare(report: dict, baseline: dict) -> list[str]:
    """The metrics that must not get worse."""
    problems: list[str] = []
    for metric in ("precision", "recall", "f1"):
        current = float(report.get(metric, 0.0))
        recorded = float(baseline.get(metric, 0.0))
        if current < recorded - TOLERANCE:
            problems.append(
                f"{metric} regressed: {current:.4f} < baseline {recorded:.4f} "
                f"(tolerance {TOLERANCE})"
            )
    # Bad coverage must not grow.
    current_bad = float(report.get("bad_coverage", 0.0))
    recorded_bad = float(baseline.get("bad_coverage", 0.0))
    if current_bad > recorded_bad + BAD_COVERAGE_TOLERANCE:
        problems.append(
            f"bad_coverage regressed: {current_bad:.4f} > baseline {recorded_bad:.4f} "
            f"(tolerance {BAD_COVERAGE_TOLERANCE})"
        )
    return problems


def _start_api(port: int, data_dir: Path) -> subprocess.Popen:
    """Start the backend on a private port with a throwaway data directory."""
    backend_dir = REPO_ROOT / "backend"
    python = backend_dir / ".venv" / "bin" / "python"
    if not python.exists():  # pragma: no cover - Windows layout
        python = backend_dir / ".venv" / "Scripts" / "python.exe"
    if not python.exists():
        raise SystemExit("No backend environment found. Run ./scripts/setup.sh first.")
    env = {
        **dict(os.environ),
        "QATTA_DATA_DIR": str(data_dir),
        "QATTA_PORT": str(port),
    }
    process = subprocess.Popen(  # noqa: S603
        [
            str(python),
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=str(backend_dir),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    def up() -> bool:
        try:
            _api("GET", f"http://127.0.0.1:{port}/api/health")
            return True
        except Exception:  # noqa: BLE001 - the server is not up yet
            return False

    _wait(up, timeout=120, interval=1, what="the API to answer")
    return process


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument(
        "--base",
        default="http://127.0.0.1:8124",
        help="the API to benchmark against (default: http://127.0.0.1:8124)",
    )
    parser.add_argument(
        "--no-start-api",
        action="store_true",
        help="use an already running API instead of starting one",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when a metric regresses against the recorded baseline",
    )
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="record the current numbers as the baseline",
    )
    parser.add_argument("--json", action="store_true", help="print the raw report")
    args = parser.parse_args()

    print("Laqta clip-selection benchmark")
    print("=" * 60)

    server = None
    data_dir = Path(tempfile.mkdtemp(prefix="laqta-benchmark-data-"))
    try:
        if not args.no_start_api:
            server = _start_api(int(args.base.rsplit(":", 1)[1]), data_dir)
        report = evaluate(args.dataset, args.base)
    finally:
        if server is not None:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:  # pragma: no cover
                server.kill()
        shutil.rmtree(data_dir, ignore_errors=True)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        header = (
            f"{'item':<16}{'sel':>5}{'hits':>6}{'prec':>8}{'rec':>8}{'F1':>8}{'cov':>8}{'bad':>8}"
        )
        print(header)
        print("-" * len(header))
        for item in report["items"]:
            print(
                f"{item['id']:<16}{item['selected']:>5}{item['hits']:>6}"
                f"{item['precision']:>8.2f}{item['recall']:>8.2f}{item['f1']:>8.2f}"
                f"{item['coverage']:>8.2f}{item['bad_coverage']:>8.2f}"
            )
        print("-" * len(header))
        print(
            f"{'TOTAL':<16}{'':>5}{'':>6}{report['precision']:>8.2f}"
            f"{report['recall']:>8.2f}{report['f1']:>8.2f}"
            f"{report['coverage']:>8.2f}{report['bad_coverage']:>8.2f}"
        )
        print(
            "\nprecision = hits / selected · recall = labels covered / labels\n"
            "coverage = selected seconds / media seconds · bad coverage = "
            "selected seconds outside a label"
        )

    if args.write_baseline:
        args.baseline.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"\nBaseline written to {args.baseline}")
        return 0

    if args.check and args.baseline.is_file():
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
        problems = _compare(report, baseline)
        if problems:
            print("\nxx  The ranking regressed:", file=sys.stderr)
            for problem in problems:
                print(f"   - {problem}", file=sys.stderr)
            return 1
        print("\nNo regression against the recorded baseline.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
