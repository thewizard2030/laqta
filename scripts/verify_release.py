#!/usr/bin/env python3
"""Prove that a Laqta checkout actually works, end to end.

This is the test the project never had: a **clean room** run that starts from
nothing and drives the whole pipeline with a synthetic video.

    import → transcribe → rank → render → verify the MP4

It is the check that would have caught the packaging and release-mode gaps.
Run it against a local checkout (``--source .``) or against a clone of the
published repository.

    python scripts/verify_release.py --source . --keep
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

NARRATION = """Welcome to the Laqta release verification.
This synthetic video contains real speech so the local transcription stage
has something to work with.
The candidate ranking runs entirely on this machine.
Finally the winning clip is rendered as a vertical video with captions.

The narration is repeated so the clip window, which needs at least
twenty eight seconds of material, has something to select from.
"""


def narration_text(repeats: int = 3) -> str:
    """The narration, repeated with paragraph breaks.

    The repeated paragraphs give the voice activity detector the pauses it
    needs to cut the video into candidate spans, and the total length has to
    exceed the shortest clip the ranker will propose.
    """
    return "\n\n".join([NARRATION.strip()] * repeats)


class VerificationError(RuntimeError):
    """A step of the release proof failed."""


def log(message: str) -> None:
    print(f"  {message}", flush=True)


def step(message: str) -> None:
    print(f"\n==> {message}", flush=True)


def run(command: list[str], cwd: Path | None = None, timeout: int = 1800) -> str:
    """Run a command, raising with its output when it fails."""
    result = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        raise VerificationError(
            f"command failed: {' '.join(command)}\n"
            f"--- stdout ---\n{result.stdout[-2000:]}\n"
            f"--- stderr ---\n{result.stderr[-2000:]}"
        )
    return result.stdout


def make_demo_video(path: Path) -> Path:
    """Synthesize a short video with real speech (espeak-ng) for the pipeline."""
    if shutil.which("espeak-ng") is None:
        raise VerificationError(
            "espeak-ng is required to synthesize the demo narration "
            "(it is a development-only tool: the application never uses it)."
        )
    if shutil.which("ffmpeg") is None:
        raise VerificationError("ffmpeg is required to build the demo video.")

    wav = path.with_suffix(".wav")
    run(["espeak-ng", "-v", "en-us", "-s", "150", "-w", str(wav), narration_text()])

    # Not every FFmpeg build ships libx264 (some distributions ship the
    # patent-safe libopenh264 instead) — try them in order, the same way the
    # renderer does.
    errors = []
    for encoder in ("libx264", "libopenh264", "mpeg4"):
        command = [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x0B0F19:s=1280x720:r=25",
            "-i",
            str(wav),
            "-c:v",
            encoder,
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(path),
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=600, check=False)
        if result.returncode == 0:
            log(f"demo video encoded with {encoder}")
            return path
        errors.append(f"{encoder}: {result.stderr.strip()[:200]}")
    raise VerificationError(
        "could not encode the demo video with any available encoder:\n" + "\n".join(errors)
    )


def api(method: str, url: str, payload: dict | None = None) -> dict | list:
    """Call the local API and return the decoded JSON."""
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(  # noqa: S310 - a fixed localhost URL
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


def upload(url: str, path: Path) -> dict:
    """Upload a media file (multipart, without a third-party dependency)."""
    boundary = "----laqtaverify"
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


def wait_for(check, timeout: int = 900, interval: float = 2.0, what: str = "condition") -> None:
    """Poll until ``check`` returns a truthy value."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(interval)
    raise VerificationError(f"timed out after {timeout}s waiting for {what}")


def verify_running_api(base: str) -> dict:
    step("API health and capabilities")
    health = api("GET", f"{base}/api/health")
    log(f"health: {health['status']} · {health['app']} {health['version']}")
    if health.get("worker") != "running":
        raise VerificationError(
            f"the job worker is not running (health says {health.get('worker')!r})"
        )

    capabilities = api("GET", f"{base}/api/capabilities")
    log(
        "capabilities: ffmpeg="
        f"{capabilities['ffmpeg']['available']} asr={capabilities['asr']['faster_whisper']} "
        f"storage_writable={capabilities['storage']['writable']}"
    )
    if not capabilities["ffmpeg"]["available"]:
        raise VerificationError("FFmpeg was not detected")
    if not capabilities["asr"]["faster_whisper"]:
        raise VerificationError(
            "the local speech model is not installed — the transcript stage cannot run"
        )
    return health


def verify_pipeline(base: str, workdir: Path) -> None:
    step("Import a synthetic video")
    video = make_demo_video(workdir / "laqta-verify.mp4")
    log(f"generated {video.name} ({video.stat().st_size // 1024} KB)")

    project = api("POST", f"{base}/api/projects", {"name": "Release verification"})
    project_id = project["id"]
    log(f"project: {project_id}")

    media = upload(f"{base}/api/projects/{project_id}/media", video)
    media_id = media["id"]
    log(f"media: {media_id} ({media['duration_ms']} ms, {media['width']}x{media['height']})")

    step("Transcribe locally")
    api("POST", f"{base}/api/media/{media_id}/transcription-jobs", {"profile": "fast"})

    def transcript_ready() -> str | None:
        """The transcript text, once the local ASR has finished."""
        transcripts = api("GET", f"{base}/api/media/{media_id}/transcripts")
        if not transcripts:
            return None
        text = transcripts[0].get("text") or ""
        return text or None

    transcript = wait_for(transcript_ready, what="the transcript")
    log(f"transcript: {len(transcript)} characters")

    step("Rank the candidates")
    result = api("POST", f"{base}/api/media/{media_id}/candidates", {})
    candidates = result.get("candidates", [])
    if not candidates:
        raise VerificationError("the ranker produced no candidates")
    log(f"candidates: {len(candidates)} (best CPS {max(c['cps'] for c in candidates):.1f})")

    step("Render the best clip")
    best = max(candidates, key=lambda c: c["cps"])
    api("POST", f"{base}/api/candidates/{best['id']}/render-jobs", {})

    def render_done() -> bool:
        jobs = api("GET", f"{base}/api/projects/{project_id}/jobs")
        for job in jobs:
            if job["type"] == "render" and job["status"] in ("succeeded", "failed"):
                return job
        return None

    job = wait_for(render_done, what="the render job")
    if job["status"] != "succeeded":
        raise VerificationError(f"the render failed: {job.get('error_code')}")
    log("render: succeeded")

    step("Verify the rendered file")
    render_path = workdir / "rendered.mp4"
    with urllib.request.urlopen(  # noqa: S310
        f"{base}/api/candidates/{best['id']}/render-file", timeout=120
    ) as response:
        render_path.write_bytes(response.read())
    if render_path.stat().st_size < 10_000:
        raise VerificationError("the rendered file is suspiciously small")

    probe = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0",
            str(render_path),
        ]
    )
    log(f"rendered: {render_path.stat().st_size // 1024} KB · {probe.strip()}")


def verify_checkout(source: Path, workdir: Path) -> None:
    """Clone the source into a clean directory and install it from scratch."""
    step(f"Clean clone of {source}")
    clone = workdir / "clone"
    run(["git", "clone", "--depth", "1", str(source), str(clone)])
    log(f"cloned into {clone}")

    step("Install from the clone (setup.sh)")
    run(["bash", "scripts/setup.sh", "--no-frontend"], cwd=clone, timeout=3600)
    log("backend installed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        default=".",
        help="the repository to verify (a path or a git URL). Default: .",
    )
    parser.add_argument(
        "--base",
        default="http://127.0.0.1:8123",
        help="where the API is expected (default: http://127.0.0.1:8123)",
    )
    parser.add_argument(
        "--skip-install",
        action="store_true",
        help="do not clone and install; verify the running API instead",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="keep the temporary directory for inspection",
    )
    args = parser.parse_args()

    workdir = Path(tempfile.mkdtemp(prefix="laqta-verify-"))
    server: subprocess.Popen | None = None
    try:
        if not args.skip_install:
            verify_checkout(Path(args.source).resolve(), workdir)
            clone = workdir / "clone"
            python = clone / "backend" / ".venv" / "bin" / "python"
            if not python.exists():  # pragma: no cover - Windows layout
                python = clone / "backend" / ".venv" / "Scripts" / "python.exe"
            env = {
                **dict(__import__("os").environ),
                "QATTA_DATA_DIR": str(workdir / "data"),
            }
            server = subprocess.Popen(  # noqa: S603
                [
                    str(python),
                    "-m",
                    "uvicorn",
                    "app.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8123",
                ],
                cwd=str(clone / "backend"),
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            log("started the API from the clean clone")

            def api_up() -> bool:
                try:
                    api("GET", f"{args.base}/api/health")
                    return True
                except (urllib.error.URLError, OSError):
                    return False

            wait_for(api_up, timeout=120, interval=1, what="the API to answer")

        verify_running_api(args.base)
        verify_pipeline(args.base, workdir)
    except VerificationError as exc:
        print(f"\nxx  RELEASE VERIFICATION FAILED\n{exc}", file=sys.stderr)
        return 1
    finally:
        if server is not None:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:  # pragma: no cover
                server.kill()
        if args.keep:
            print(f"\nKept the working directory: {workdir}")
        else:
            shutil.rmtree(workdir, ignore_errors=True)

    print("\nOK  The release works end to end from a clean clone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
