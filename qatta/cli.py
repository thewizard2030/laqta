"""Laqta command line interface.

``laqta`` is the entry point for working with the studio from a terminal:

    laqta --version      print the version
    laqta doctor         check this machine for everything Laqta needs
    laqta serve          run the local API server
    laqta studio         run the API and the studio frontend together
    laqta models         show the locally cached speech models

The CLI never contacts the network and never uploads anything: it only
inspects the local machine and starts a server that binds to 127.0.0.1.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from qatta import __version__

app = typer.Typer(
    name="laqta",
    help="Laqta — local-first long-video to vertical Shorts studio.",
    add_completion=False,
    no_args_is_help=True,
)
console = Console()

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"

OK = "[green]✓[/green]"
WARN = "[yellow]![/yellow]"
FAIL = "[red]✗[/red]"


BACKEND_MISSING_HINT = (
    "The API server ships with the Laqta source checkout, not with the "
    "published package. Clone the repository (git clone "
    "https://github.com/thewizard2030/laqta.git) and run the command from "
    "there, or start the API directly with `uvicorn app.main:app` from the "
    "backend/ directory."
)


def _backend_on_path() -> bool:
    """Make the backend package importable (it lives beside the core)."""
    if not BACKEND_DIR.is_dir():
        return False
    path = str(BACKEND_DIR)
    if path not in sys.path:
        sys.path.insert(0, path)
    return True


def _backend_importable() -> bool:
    """Whether the API package can actually be imported."""
    if not _backend_on_path():
        return False
    try:
        import app.main  # noqa: F401
    except Exception:  # noqa: BLE001 - any import error means "not usable"
        return False
    return True


def _which(name: str) -> str | None:
    return shutil.which(name)


def _binary_version(path: str, args: list[str] | None = None) -> str:
    try:
        result = subprocess.run(
            [path, *(args or ["-version"])],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown version"
    output = (result.stdout or result.stderr or "").strip()
    first_line = output.splitlines()[0] if output else ""
    for token in ("ffmpeg version ", "ffprobe version ", "version "):
        if first_line.startswith(token):
            return first_line[len(token) :].split(" ")[0]
    return first_line or "unknown version"


def _probe_http(url: str, timeout: float = 1.5) -> str | None:
    """Return the response body of a local URL, or None when unreachable.

    Uses the standard library only: the CLI must work without the backend's
    dependencies installed.
    """
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
            return response.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError, ValueError):
        return None


def _human_bytes(size: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} TB"


@app.callback(invoke_without_command=True)
def main_callback(
    version: bool = typer.Option(False, "--version", "-V", help="Show the Laqta version and exit."),
) -> None:
    """Laqta — local-first long-video to vertical Shorts studio."""
    if version:
        console.print(f"Laqta {__version__}")
        raise typer.Exit()


@app.command()
def version() -> None:
    """Print the Laqta version."""
    console.print(f"Laqta {__version__}")


@app.command()
def doctor(
    json_output: bool = typer.Option(
        False, "--json", help="Print the report as JSON (for scripts and CI)."
    ),
) -> None:
    """Check this machine for everything Laqta needs.

    Reports exactly what is installed and what is missing — the same honest
    detection the studio UI shows. Exits non-zero only when a *required*
    component is missing.
    """
    if json_output:
        _doctor_json()
        return

    console.print("\n[bold]Laqta doctor[/bold] — local environment check\n")

    required_failures: list[str] = []
    table = Table(box=None, pad_edge=False, show_header=False)
    table.add_column("", width=2)
    table.add_column("component", style="bold", no_wrap=True)
    table.add_column("status")
    table.add_column("detail", overflow="fold")

    # --- Python -----------------------------------------------------------
    py_version = ".".join(str(part) for part in sys.version_info[:3])
    # The package requires Python 3.11, but the CLI can be run straight from a
    # source checkout with an older interpreter — so the check stays.
    if sys.version_info < (3, 11):  # noqa: UP036
        table.add_row(FAIL, "Python", py_version, "3.11 or newer is required")
        required_failures.append("Python >= 3.11")
    else:
        table.add_row(OK, "Python", py_version, ">= 3.11 required")

    # --- Media binaries ---------------------------------------------------
    ffmpeg = _which("ffmpeg")
    if ffmpeg:
        table.add_row(OK, "FFmpeg", _binary_version(ffmpeg), ffmpeg)
    else:
        table.add_row(FAIL, "FFmpeg", "not found in PATH", "Required for rendering")
        required_failures.append("FFmpeg")

    ffprobe = _which("ffprobe")
    if ffprobe:
        table.add_row(OK, "FFprobe", _binary_version(ffprobe), ffprobe)
    else:
        table.add_row(FAIL, "FFprobe", "not found in PATH", "Required to inspect media")
        required_failures.append("FFprobe")

    # --- Backend capability report (single source of truth) ---------------
    capabilities = None
    if _backend_on_path():
        try:
            from app.services.media.probe import detect_capabilities

            capabilities = detect_capabilities()
        except Exception as exc:  # noqa: BLE001 - never fail the doctor on import
            table.add_row(
                WARN,
                "Backend",
                "not importable",
                f"{type(exc).__name__}: {exc}",
            )

    if capabilities is not None:
        asr = capabilities.asr
        if asr.faster_whisper:
            detail = "faster-whisper"
            if asr.whisperx:
                detail += " + whisperX alignment"
            table.add_row(OK, "Local ASR", detail, "Speech recognition on this CPU")
        else:
            table.add_row(
                WARN,
                "Local ASR",
                "not installed",
                "pip install -r backend/requirements-asr.txt",
            )

        ingestion = capabilities.url_ingestion
        if ingestion.feature_flag and ingestion.yt_dlp.available:
            table.add_row(
                OK,
                "URL import",
                "yt-dlp available",
                "Enabled by the operator (rights confirmation required)",
            )
        elif ingestion.feature_flag:
            table.add_row(WARN, "URL import", "yt-dlp missing", ingestion.notice or "")
        else:
            table.add_row(
                WARN,
                "URL import",
                "disabled by operator",
                ingestion.notice or "QATTA_ENABLE_URL_INGESTION=false",
            )

        storage = capabilities.storage
        if storage.writable:
            table.add_row(OK, "Data directory", "writable", storage.data_dir)
        else:
            table.add_row(FAIL, "Data directory", "read-only", storage.data_dir)
            required_failures.append("writable data directory")

        llm = capabilities.llm
        if llm.provider == "openrouter" and llm.api_key_configured and llm.hosted_opt_in:
            table.add_row(
                WARN,
                "Hosted ranker",
                "enabled",
                "Transcript text leaves this device when scoring",
            )
        else:
            table.add_row(
                OK,
                "Hosted ranker",
                "disabled",
                "Local heuristic scoring is used — nothing is uploaded",
            )

    # --- yt-dlp (standalone, works without the backend) --------------------
    if capabilities is None:
        ytdlp = _which("yt-dlp")
        if ytdlp:
            table.add_row(OK, "yt-dlp", _binary_version(ytdlp, ["--version"]), ytdlp)
        else:
            table.add_row(WARN, "yt-dlp", "not installed", "Needed for URL import")

    # --- Disk -------------------------------------------------------------
    try:
        usage = shutil.disk_usage(str(REPO_ROOT))
        free = _human_bytes(usage.free)
        if usage.free > 2 * 1024**3:
            table.add_row(OK, "Disk space", free, "available on the data volume")
        else:
            table.add_row(WARN, "Disk space", free, "Less than 2 GB free")
    except OSError:
        table.add_row(WARN, "Disk space", "unknown", "")

    # --- The running services -------------------------------------------
    # A local machine can have everything installed and still have no server
    # running; say so explicitly instead of leaving the user guessing.
    api_port = os.environ.get("QATTA_PORT", "8000")
    health = _probe_http(f"http://127.0.0.1:{api_port}/api/health")
    if health:
        try:
            import json

            payload = json.loads(health)
            label = f"{payload.get('app', 'Laqta')} {payload.get('version', '')}".strip()
        except ValueError:
            label = "reachable"
        table.add_row(OK, "API", f"running on :{api_port}", label)
    else:
        table.add_row(
            WARN,
            "API",
            f"not running on :{api_port}",
            "Start it with `laqta serve`",
        )

    if _backend_importable():
        table.add_row(OK, "Backend", "importable", "the API server can be started here")
    else:
        table.add_row(
            WARN,
            "Backend",
            "not available here",
            "the API server ships with the source checkout",
        )

    frontend = _probe_http("http://127.0.0.1:5173/")
    if frontend is not None:
        table.add_row(OK, "Studio", "running on :5173", "open http://127.0.0.1:5173")
    else:
        table.add_row(
            WARN,
            "Studio",
            "not running on :5173",
            "Start it with `npm run dev` in frontend/",
        )

    console.print(table)

    if required_failures:
        console.print(
            "\n[bold red]Action needed:[/bold red] "
            + ", ".join(required_failures)
            + "\nSee the installation guide in the README.\n"
        )
        raise typer.Exit(code=1)

    console.print(
        "\n[bold green]Ready.[/bold green] Start the studio with "
        "`laqta studio` (API + frontend in one command).\n"
    )


def _doctor_json() -> None:
    """Print the doctor report as JSON — the same facts, machine-readable."""
    import json

    report: dict[str, object] = {
        "app": "Laqta",
        "version": __version__,
        "python": ".".join(str(part) for part in sys.version_info[:3]),
        "ok": True,
        "missing": [],
    }
    missing: list[str] = []

    def add(name: str, present: bool, detail: str, required: bool = False) -> None:
        report[name] = {"present": present, "detail": detail}
        if not present:
            if required:
                report["ok"] = False
                missing.append(name)

    ffmpeg = _which("ffmpeg")
    add(
        "ffmpeg",
        ffmpeg is not None,
        _binary_version(ffmpeg) if ffmpeg else "not found in PATH",
        required=True,
    )
    ffprobe = _which("ffprobe")
    add(
        "ffprobe",
        ffprobe is not None,
        _binary_version(ffprobe) if ffprobe else "not found in PATH",
        required=True,
    )
    ytdlp = _which("yt-dlp")
    add("yt_dlp", ytdlp is not None, "yt-dlp" if ytdlp else "not installed")

    try:
        import faster_whisper  # noqa: F401

        add("asr", True, "faster-whisper")
    except Exception:  # noqa: BLE001
        add("asr", False, "not installed")

    if _backend_importable():
        try:
            from app.services.media.probe import detect_capabilities

            capabilities = detect_capabilities()
            add("backend", True, "importable")
            add(
                "storage",
                capabilities.storage.writable,
                capabilities.storage.data_dir,
                required=True,
            )
            add(
                "url_ingestion",
                capabilities.url_ingestion.feature_flag,
                "enabled" if capabilities.url_ingestion.feature_flag else "disabled by operator",
            )
        except Exception as exc:  # noqa: BLE001
            add("backend", False, f"{type(exc).__name__}: {exc}")
    else:
        add("backend", False, "the API server ships with the source checkout")

    api_port = os.environ.get("QATTA_PORT", "8000")
    add(
        "api",
        _probe_http(f"http://127.0.0.1:{api_port}/api/health") is not None,
        f":{api_port}",
    )
    add("studio", _probe_http("http://127.0.0.1:5173/") is not None, ":5173")

    report["missing"] = missing
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["ok"]:
        raise typer.Exit(code=1)


@app.command()
def serve(
    host: str = typer.Option(
        "127.0.0.1",
        "--host",
        help="Interface to bind. Keep 127.0.0.1 unless you know what you do.",
    ),
    port: int = typer.Option(8000, "--port", help="Port to listen on."),
    reload: bool = typer.Option(False, "--reload", help="Reload on code changes."),
) -> None:
    """Run the local API server (binds to 127.0.0.1 by default)."""
    if not _backend_on_path():
        console.print("[red]The API server is not available here.[/red]")
        console.print(BACKEND_MISSING_HINT)
        raise typer.Exit(code=1)
    try:
        import uvicorn
    except ImportError:
        console.print(
            "[red]uvicorn is not installed.[/red] Run: pip install -r backend/requirements.txt"
        )
        raise typer.Exit(code=1) from None

    console.print(f"Starting Laqta {__version__} API on http://{host}:{port}")
    if host not in ("127.0.0.1", "localhost", "::1"):
        console.print(
            "[yellow]Warning:[/yellow] binding to a non-loopback address exposes "
            "an unauthenticated API to your network."
        )
    uvicorn.run("app.main:app", host=host, port=port, reload=reload)


@app.command()
def models() -> None:
    """Show the locally cached speech models.

    Laqta does not ship model weights — the local speech model is downloaded
    on first use into the Hugging Face cache.
    """
    cache = os.environ.get("HF_HOME") or (Path.home() / ".cache" / "huggingface")
    hub_cache = Path(cache) / "hub"
    console.print(f"\n[bold]Model cache[/bold]: {hub_cache}\n")

    if not hub_cache.is_dir():
        console.print(
            "No models downloaded yet. The first transcription downloads the "
            "model\n(~145 MB for the `base` profile, ~1.5 GB for `medium`).\n"
        )
        return

    table = Table(box=None, pad_edge=False, show_header=False)
    table.add_column("", width=2)
    table.add_column("model", style="bold")
    table.add_column("size")
    found = False
    for entry in sorted(hub_cache.glob("models--*")):
        found = True
        size = sum(f.stat().st_size for f in entry.rglob("*") if f.is_file())
        table.add_row(OK, entry.name.replace("models--", ""), _human_bytes(size))
    if not found:
        console.print("The cache exists but holds no models yet.\n")
        return
    console.print(table)
    console.print("")


@app.command()
def studio(
    host: str = typer.Option("127.0.0.1", "--host", help="API interface."),
    port: int = typer.Option(8000, "--port", help="API port."),
    api_only: bool = typer.Option(False, "--api-only", help="Start only the API."),
    frontend_only: bool = typer.Option(
        False, "--frontend-only", help="Start only the studio frontend."
    ),
) -> None:
    """Run the API and the studio frontend together.

    Equivalent to `scripts/dev.sh`, but from the installed command.
    """
    import signal
    import subprocess

    backend_dir = REPO_ROOT / "backend"
    frontend_dir = REPO_ROOT / "frontend"
    uvicorn_bin = backend_dir / ".venv" / "bin" / "uvicorn"
    if sys.platform.startswith("win"):  # pragma: no cover - Windows layout
        uvicorn_bin = backend_dir / ".venv" / "Scripts" / "uvicorn.exe"

    processes: list[subprocess.Popen] = []

    def start_backend() -> None:
        if not uvicorn_bin.exists():
            console.print(
                "[red]No backend environment found.[/red] Run ./scripts/setup.sh first.",
                style=None,
            )
            raise typer.Exit(code=1)
        console.print(f"[cyan]API[/cyan]      → http://{host}:{port}")
        processes.append(
            subprocess.Popen(  # noqa: S603
                [str(uvicorn_bin), "app.main:app", "--host", host, "--port", str(port)],
                cwd=str(backend_dir),
            )
        )

    def start_frontend() -> None:
        if not (frontend_dir / "node_modules").is_dir():
            console.print(
                "[red]No frontend dependencies found.[/red] Run ./scripts/setup.sh first."
            )
            raise typer.Exit(code=1)
        npm = shutil.which("npm")
        if npm is None:
            console.print("[red]npm was not found.[/red] Install Node.js 22.12+.")
            raise typer.Exit(code=1)
        console.print("[cyan]Studio[/cyan]   → http://127.0.0.1:5173")
        processes.append(
            subprocess.Popen(  # noqa: S603
                [npm, "run", "dev"],
                cwd=str(frontend_dir),
            )
        )

    if not frontend_only:
        start_backend()
    if not api_only:
        start_frontend()

    console.print("\n[bold]Laqta is running.[/bold] Press Ctrl-C to stop.\n")

    def shutdown(*_: object) -> None:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()

    signal.signal(signal.SIGINT, lambda *_: shutdown())
    try:
        while True:
            for process in processes:
                if process.poll() is not None:
                    shutdown()
                    raise typer.Exit(code=process.returncode or 0)
            time.sleep(0.5)
    except KeyboardInterrupt:  # pragma: no cover - interactive
        shutdown()


def main() -> None:
    """Console-script entry point."""
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
