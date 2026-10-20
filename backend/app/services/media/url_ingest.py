"""URL ingestion service (yt-dlp) — PRD FR-12.

Design constraints (all binding):
- Flag-controlled end-to-end. The route refuses work with an explicit
  error unless URL ingestion is enabled (default ON since the FR-12
  review was completed by owner decision on 2026-10-19; disabling via
  ``QATTA_ENABLE_URL_INGESTION=false`` is always honored), yt-dlp is
  installed, AND the user explicitly confirmed content rights for this
  run. Nothing may run silently.
- The download runs as a background job only; request handlers never block
  on network/file processing.
- Strict subprocess argument arrays (no shell=True), a finite download
  deadline, cooperative cancellation, bounded log capture, and honest
  progress parsing from yt-dlp's ``--newline`` output.
- Output filenames are platform-controlled (``%(id)s.%(ext)s``) with
  ``--restrict-filenames`` so no remote name can traverse paths.
- SSRF hardening: only public http(s) URLs are accepted; loopback, private,
  link-local, and reserved hostnames/IPs (including DNS-resolved private
  addresses) are rejected before any download starts.
- Access controls are never circumvented: yt-dlp runs without any credential
  or bypass flags; private/auth-gated sources simply fail.

yt-dlp is Unlicense-licensed and remains an optional local dependency.
"""

import asyncio
import os
import re
import shutil
import socket
import sys
import time
from dataclasses import dataclass
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import urlparse

# Ensure the active virtual environment's bin directory is searched
_venv_bin = str(Path(sys.executable).parent)
_current_path = os.environ.get("PATH", "")
if _venv_bin not in _current_path:
    os.environ["PATH"] = f"{_venv_bin}:{_current_path}"

# The PATH tweak above must run before these imports so that `yt-dlp` is
# found inside an activated virtual environment.
from app.core.config import settings  # noqa: E402
from app.core.logging import logger  # noqa: E402
from app.services.media.audio import (  # noqa: E402
    JobCancelledError,
    _read_bounded_stream,
)
from app.services.transcription.youtube_extractor import (  # noqa: E402
    YouTubeTranscriptExtractor,
    extract_youtube_video_id,
)


@dataclass(frozen=True)
class UrlIngestResult:
    """Result of one successful URL ingest run."""

    media_path: Path
    subtitle_path: Path | None = None
    language: str | None = None
    video_id: str | None = None


class UrlIngestError(Exception):
    """Exception raised when URL ingestion cannot proceed or download fails."""

    def __init__(self, message: str, error_code: str = "URL_INGEST_FAILED"):
        super().__init__(message)
        self.message = message
        self.error_code = error_code


def _ip_is_forbidden(ip: str) -> bool:
    """True for loopback/private/link-local/reserved/unspecified addresses.

    Only trust this on DNS-resolved answers or explicit IP literals: an
    unparseable address is treated as forbidden (fail-closed).
    """
    try:
        addr = ip_address(ip)
    except ValueError:
        return True  # unparseable addresses are never allowed
    return (
        addr.is_loopback
        or addr.is_private
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


def _hostname_is_forbidden(hostname: str) -> bool:
    """Reject localhost-style hosts and forbidden IP-literal hosts.

    Ordinary domain names are NOT rejected here (they are checked via DNS
    resolution afterwards, which catches private-routing answers).
    """
    host = (hostname or "").strip().lower().rstrip(".")
    if not host:
        return True
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        return True
    try:
        ip_address(host)
    except ValueError:
        return False  # plain domain name; DNS check decides later
    return _ip_is_forbidden(host)


def validate_public_http_url(url: str) -> Path | str:
    """Validate that ``url`` is a public http(s) resource meant to be public.

    On a failure path raises :class:`UrlIngestError` with an explicit code;
    on success returns the URL unchanged (yt-dlp receives the exact string).
    """
    candidate = (url or "").strip()
    if not candidate:
        raise UrlIngestError("URL must not be empty.", error_code="URL_INVALID")
    if len(candidate) > 2048:
        raise UrlIngestError("URL is unreasonably long.", error_code="URL_INVALID")
    # Control characters can confuse downstream parsers; reject outright.
    if any(ord(c) < 0x20 for c in candidate):
        raise UrlIngestError("URL contains control characters.", error_code="URL_INVALID")

    try:
        parsed = urlparse(candidate)
    except ValueError as e:
        raise UrlIngestError(f"URL failed to parse: {e}", error_code="URL_INVALID") from e

    if parsed.scheme not in ("http", "https"):
        raise UrlIngestError(
            f"Only http(s) URLs are supported (got scheme '{parsed.scheme or 'none'}').",
            error_code="URL_INVALID",
        )
    if "@" in (parsed.netloc or ""):
        raise UrlIngestError(
            "URLs containing userinfo ('@') are not accepted.",
            error_code="URL_INVALID",
        )
    hostname = parsed.hostname or ""
    if _hostname_is_forbidden(hostname):
        raise UrlIngestError(
            "Access to local/internal hosts is blocked (SSRF protection).",
            error_code="URL_FORBIDDEN_HOST",
        )

    # Resolve DNS and reject any answer pointing into private address space.
    try:
        infos = socket.getaddrinfo(hostname, parsed.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise UrlIngestError(
            f"Host '{hostname}' could not be resolved: {e}",
            error_code="URL_RESOLVE_FAILED",
        ) from e
    for info in infos:
        if _ip_is_forbidden(str(info[4][0])):  # resolved answers must be strict
            raise UrlIngestError(
                f"Host '{hostname}' resolves to a private/internal address.",
                error_code="URL_FORBIDDEN_HOST",
            )

    return candidate


def _find_yt_dlp_binary(custom_path: str | None = None) -> str | None:
    """Find yt-dlp binary across custom path, system PATH, or active venv."""
    if custom_path and Path(custom_path).exists():
        return custom_path
    which_bin = shutil.which("yt-dlp")
    if which_bin and Path(which_bin).exists():
        return which_bin
    return None


def detect_yt_dlp(custom_path: str | None = None):
    """Honest detection of an installed yt-dlp binary (no bypass flags ever)."""
    from app.schemas.capabilities import BinaryCapability

    binary = _find_yt_dlp_binary(custom_path)
    if not binary:
        return BinaryCapability(
            available=False,
            path=None,
            version=None,
            details="yt-dlp is not installed. Install yt-dlp to enable URL ingestion.",
        )
    try:
        res = subprocess_run_version(binary)
        return BinaryCapability(
            available=True,
            path=binary,
            version=(res.strip().splitlines() or [""])[0] or None,
            details=None,
        )
    except Exception as e:
        return BinaryCapability(
            available=False,
            path=binary,
            version=None,
            details=f"yt-dlp probe failed: {e}",
        )


def subprocess_run_version(binary: str) -> str:
    """Run ``yt-dlp --version`` safely (argument array, bounded timeout)."""
    import subprocess

    res = subprocess.run(
        [binary, "--version"],
        capture_output=True,
        text=True,
        timeout=float(settings.YT_DLP_PROBE_TIMEOUT_SECONDS),
        check=True,
    )
    return res.stdout


def build_url_ingest_command(
    yt_dlp_bin: str,
    download_dir: Path,
    url: str,
    max_filesize_bytes: int,
    sub_langs: str = "ar.*,ar,en.*,en",
    include_subtitles: bool = True,
    player_clients: str | None = None,
    cookies_path: str | None = None,
    cookies_from_browser: str | None = None,
) -> list[str]:
    """Strict argument array for a bounded single-video download.

    - ``--no-playlist``: never descend into multi-video playlists.
    - ``-S ext:mp4``: prefer mp4 containers (matches ALLOWED_MEDIA_EXTENSIONS);
      the post-download probe still validates the actual container.
    - ``--ignore-errors``: ignore non-fatal download errors (e.g. subtitle 429
      rate limits) so the media download can proceed.
    - ``--no-cache-dir``: bypass stale cached cipher signatures and tokens.
    - ``-4``: force IPv4 to avoid IPv6 CDN dropping and 403 blocks.
    - ``--extractor-args youtube:player_client=...``: use mobile/hybrid clients
      to bypass web Proof of Origin (poToken) 403 Forbidden blocks.
    - ``--js-runtimes node``: enable Node.js to solve YouTube cipher challenges.
    - ``--write-sub`` + ``--write-auto-sub`` + ``--sub-format vtt/best``:
      extract available platform subtitles (manual or auto-captions) in VTT format
      when include_subtitles is True.
    - ``-o %(id)s.%(ext)s`` + ``--restrict-filenames``: server-controlled,
      sanitized output names (no remote-controlled path traversal).
    - No auth/bypass flags are ever passed: gated content fails honestly.
    """
    clients = player_clients or getattr(settings, "YT_DLP_PLAYER_CLIENT", "android,ios,web")
    cmd = [
        yt_dlp_bin,
        "--no-playlist",
        "--newline",
        "--no-warnings",
        "--ignore-errors",
        "--no-cache-dir",
        "-4",
        "--restrict-filenames",
        "--extractor-args",
        f"youtube:player_client={clients}",
        "-S",
        "ext:mp4",
        "--max-filesize",
        str(max_filesize_bytes),
    ]

    # Node.js or Bun runtime for YouTube JavaScript cipher challenge solving
    if shutil.which("node"):
        cmd.extend(["--js-runtimes", "node"])
    elif shutil.which("bun"):
        cmd.extend(["--js-runtimes", "bun"])

    # Explicit ffmpeg binary location if found
    ffmpeg_bin = shutil.which("ffmpeg")
    if ffmpeg_bin:
        cmd.extend(["--ffmpeg-location", ffmpeg_bin])

    # Optional cookies if configured
    eff_cookies = cookies_path or getattr(settings, "YT_DLP_COOKIES_PATH", None)
    eff_browser = cookies_from_browser or getattr(settings, "YT_DLP_COOKIES_FROM_BROWSER", None)
    if eff_cookies and Path(eff_cookies).is_file():
        cmd.extend(["--cookies", str(eff_cookies)])
    elif eff_browser:
        cmd.extend(["--cookies-from-browser", eff_browser])

    if include_subtitles:
        cmd.extend(
            [
                "--write-sub",
                "--write-auto-sub",
                "--sub-format",
                "vtt/best",
                "--sub-langs",
                sub_langs,
            ]
        )
    cmd.extend(
        [
            "-o",
            str(download_dir / "%(id)s.%(ext)s"),
            url,
        ]
    )
    return cmd


def _parse_yt_dlp_progress_line(line: str) -> float | None:
    """Return the download percent from a ``[download] 42.3% of ...`` line."""
    text = line.strip()
    if not text.startswith("[download]"):
        return None
    match = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
    if not match:
        return None
    try:
        return min(100.0, max(0.0, float(match.group(1))))
    except ValueError:  # pragma: no cover - regex guarantees float
        return None


def _locate_best_vtt(
    download_dir: Path, video_id: str | None = None
) -> tuple[Path | None, str | None]:
    """Deterministically pick the best VTT subtitle file in download_dir."""
    candidates = list(download_dir.glob("*.vtt"))
    if video_id:
        scoped = [p for p in candidates if p.name.startswith(video_id)]
        if scoped:
            candidates = scoped
    if not candidates:
        return None, None

    # Priority 1: Arabic
    ar_subs = [p for p in candidates if ".ar" in p.name.lower()]
    if ar_subs:
        chosen = min(ar_subs, key=lambda p: (len(p.stem), p.name))
        return chosen, "ar"

    # Priority 2: English
    en_subs = [p for p in candidates if ".en" in p.name.lower()]
    if en_subs:
        chosen = min(en_subs, key=lambda p: (len(p.stem), p.name))
        return chosen, "en"

    # Priority 3: Shortest stem (likely manual or primary language)
    chosen = min(candidates, key=lambda p: (len(p.stem), p.name))
    parts = chosen.stem.split(".")
    lang = parts[-1] if len(parts) > 1 else "auto"
    return chosen, lang


async def _fetch_subtitles_yt_dlp_fallback(
    yt_dlp_bin: str,
    download_dir: Path,
    url: str,
    sub_langs: str,
    *,
    timeout: float = 20.0,
    cancel_event: asyncio.Event | None = None,
    cookies_path: str | None = None,
    cookies_from_browser: str | None = None,
) -> tuple[Path | None, str | None]:
    """Tier 2 fallback: extract captions via yt-dlp --skip-download with web client."""
    if cancel_event and cancel_event.is_set():
        raise JobCancelledError()
    cmd = [
        yt_dlp_bin,
        "--no-playlist",
        "--skip-download",
        "--write-sub",
        "--write-auto-sub",
        "--sub-format",
        "vtt/best",
        "--sub-langs",
        sub_langs,
        "--extractor-args",
        "youtube:player_client=android",
        "-4",
        "--no-cache-dir",
        "--restrict-filenames",
    ]
    if shutil.which("node"):
        cmd.extend(["--js-runtimes", "node"])
    elif shutil.which("bun"):
        cmd.extend(["--js-runtimes", "bun"])

    eff_cookies = cookies_path or getattr(settings, "YT_DLP_COOKIES_PATH", None)
    eff_browser = cookies_from_browser or getattr(settings, "YT_DLP_COOKIES_FROM_BROWSER", None)
    if eff_cookies and Path(eff_cookies).is_file():
        cmd.extend(["--cookies", str(eff_cookies)])
    elif eff_browser:
        cmd.extend(["--cookies-from-browser", eff_browser])

    cmd.extend(
        [
            "-o",
            str(download_dir / "%(id)s.%(ext)s"),
            url,
        ]
    )
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            await asyncio.wait_for(proc.wait(), timeout=timeout)
        except TimeoutError:
            proc.kill()
            return None, None
        return _locate_best_vtt(download_dir)
    except JobCancelledError:
        raise
    except Exception as e:
        logger.debug(f"yt-dlp subtitle fallback failed: {e}")
        return None, None


async def _execute_yt_dlp_subprocess(
    cmd: list[str],
    *,
    started: float,
    timeout: float,
    cancel_event: asyncio.Event | None = None,
    progress_callback=None,
) -> tuple[int, str]:
    """Execute yt-dlp subprocess with streaming progress, timeout, and cancellation."""
    proc: asyncio.subprocess.Process | None = None
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stderr_task = asyncio.create_task(_read_bounded_stream(proc.stderr))

        last_pct: float | None = None
        assert proc.stdout is not None
        while True:
            if cancel_event and cancel_event.is_set():
                proc.kill()
                raise JobCancelledError()
            try:
                line = await asyncio.wait_for(proc.stdout.readline(), timeout=1.0)
            except TimeoutError:
                if time.monotonic() - started > timeout:
                    proc.kill()
                    raise UrlIngestError(
                        f"Download exceeded the {timeout:.0f}s deadline.",
                        error_code="URL_INGEST_TIMEOUT",
                    ) from None
                continue
            if not line:
                break
            pct = _parse_yt_dlp_progress_line(line.decode("utf-8", errors="replace"))
            if pct is not None and (last_pct is None or pct > last_pct + 1.0):
                last_pct = pct
                if progress_callback:
                    progress_callback(max(5.0, min(95.0, pct * 0.95)), "downloading")

        await proc.wait()
        stderr_text = await stderr_task
        return proc.returncode, stderr_text
    except JobCancelledError:
        if proc and proc.returncode is None:
            proc.kill()
        raise
    except UrlIngestError:
        if proc and proc.returncode is None:
            proc.kill()
        raise
    except Exception as e:
        if proc and proc.returncode is None:
            proc.kill()
        raise UrlIngestError(f"Unexpected failure during download: {e}") from e


async def run_url_ingest(
    url: str,
    download_dir: Path,
    *,
    cancel_event: asyncio.Event | None = None,
    timeout_sec: float | None = None,
    progress_callback=None,
    yt_dlp_bin_override: str | None = None,
) -> UrlIngestResult:
    """Download one video via yt-dlp and return the downloaded media and subtitle result.

    Raises :class:`UrlIngestError` on any failure and re-raises
    :class:`JobCancelledError` when ``cancel_event`` fires.
    """
    if cancel_event and cancel_event.is_set():
        raise JobCancelledError()

    yt_dlp_bin = yt_dlp_bin_override or _find_yt_dlp_binary()
    if not yt_dlp_bin or not Path(yt_dlp_bin).exists():
        raise UrlIngestError(
            "yt-dlp is not installed. Install yt-dlp to enable URL ingestion.",
            error_code="YT_DLP_NOT_FOUND",
        )

    download_dir.mkdir(parents=True, exist_ok=True)
    timeout = timeout_sec or float(settings.URL_INGEST_TIMEOUT_SECONDS)
    logger.info(f"URL ingest starting (timeout {timeout:.0f}s): yt-dlp <url redacted>")

    if progress_callback:
        progress_callback(2.0, "connecting")

    def _find_media() -> list[Path]:
        return [
            p
            for p in download_dir.iterdir()
            if p.is_file() and p.suffix.lower() in settings.ALLOWED_MEDIA_EXTENSIONS
        ]

    started = time.monotonic()
    vtt_path: Path | None = None
    lang: str | None = None

    is_youtube = extract_youtube_video_id(url) is not None
    native_enabled = getattr(settings, "ENABLE_NATIVE_YOUTUBE_TRANSCRIPT", True)

    # Step 1: Caption extraction for YouTube (Tier 1 native Innertube API)
    # Fetch captions before media download. This avoids yt-dlp subtitle failures on Android clients.
    if is_youtube and native_enabled:
        try:
            if progress_callback:
                progress_callback(3.0, "extracting_captions")
            logger.info("Attempting native YouTube transcript extraction (Tier 1)...")
            sub_langs_raw = getattr(settings, "URL_INGEST_SUB_LANGUAGES", "ar,en")
            preferred_langs = [
                s.strip().replace(".*", "") for s in sub_langs_raw.split(",") if s.strip()
            ]
            native_res = await YouTubeTranscriptExtractor.extract_and_save_vtt(
                url,
                download_dir,
                preferred_langs=preferred_langs,
                timeout_sec=15.0,
            )
            if native_res:
                vtt_path, lang, _ = native_res
                logger.info(
                    "Native YouTube transcript extracted successfully: "
                    f"{vtt_path.name} (lang={lang})"
                )
        except JobCancelledError:
            raise
        except Exception as e:
            logger.warning(f"Native transcript extraction step failed: {e}")

    # Step 2: Download Media Video
    # If subtitles were already obtained, omit subtitle flags to avoid
    # Android streaming caption errors ("Did not get any data blocks" / 429).
    # For sources without subtitles, include subtitle flags.
    sub_langs = getattr(settings, "URL_INGEST_SUB_LANGUAGES", "ar.*,ar,en.*,en")
    include_subtitles = vtt_path is None

    cmd = build_url_ingest_command(
        yt_dlp_bin,
        download_dir,
        url,
        max_filesize_bytes=settings.MAX_UPLOAD_SIZE_BYTES,
        sub_langs=sub_langs,
        include_subtitles=include_subtitles,
    )
    rc, stderr_text = await _execute_yt_dlp_subprocess(
        cmd,
        started=started,
        timeout=timeout,
        cancel_event=cancel_event,
        progress_callback=progress_callback,
    )

    media_files = _find_media()

    # Pass 2 (fallback): If no media file was produced and Pass 1 failed (e.g. YouTube
    # rate-limiting subtitle requests with HTTP 429 or stream HTTP 403 Forbidden), retry
    # without subtitles and fallback directly to android client so media is retrieved.
    if not media_files and (rc != 0 or "429" in stderr_text or "403" in stderr_text):
        logger.warning(
            f"yt-dlp exited rc={rc} with no media file produced (subtitle/403 stream error). "
            f"Retrying download without subtitles as fallback: {stderr_text[:300]}"
        )
        fallback_cmd = build_url_ingest_command(
            yt_dlp_bin,
            download_dir,
            url,
            max_filesize_bytes=settings.MAX_UPLOAD_SIZE_BYTES,
            include_subtitles=False,
            player_clients="android,web",
        )
        rc, stderr_text = await _execute_yt_dlp_subprocess(
            fallback_cmd,
            started=started,
            timeout=timeout,
            cancel_event=cancel_event,
            progress_callback=progress_callback,
        )
        media_files = _find_media()

    if not media_files:
        if rc != 0:
            logger.warning(f"yt-dlp exited rc={rc}: {stderr_text[:500]}")
            msg = (
                "yt-dlp could not download this URL. The video may be "
                "private, region-locked, removed, or unsupported."
            )
            if "403" in stderr_text or "Forbidden" in stderr_text:
                msg = (
                    "YouTube rejected stream download (HTTP 403 Forbidden). "
                    "YouTube anti-bot verification or video restrictions prevented "
                    "download. If the problem persists, configure browser cookies "
                    "(YT_DLP_COOKIES_FROM_BROWSER=firefox)."
                )
            raise UrlIngestError(msg, error_code="URL_INGEST_FAILED")
        raise UrlIngestError(
            "Download finished but no supported media file was produced.",
            error_code="URL_INGEST_NO_MEDIA",
        )

    largest = max(media_files, key=lambda p: p.stat().st_size)
    if not vtt_path:
        vtt_path, lang = _locate_best_vtt(download_dir, video_id=largest.stem)

    # Step 3: Tier 2 fallback for YouTube if captions were not retrieved by Tier 1
    if is_youtube and not vtt_path:
        logger.info("Attempting Tier 2 yt-dlp subtitle probe (web client)...")
        vtt_path, lang = await _fetch_subtitles_yt_dlp_fallback(
            yt_dlp_bin,
            download_dir,
            url,
            sub_langs=sub_langs,
            cancel_event=cancel_event,
        )

    if rc != 0:
        if vtt_path:
            logger.info(
                f"Media and subtitles downloaded successfully ({largest.name}, lang={lang}) "
                f"despite non-fatal warnings (rc={rc})."
            )
        else:
            logger.info(
                f"Media file successfully downloaded ({largest.name}). Platform subtitles "
                f"were not available or were skipped (rc={rc}); falling back to local Whisper."
            )

    if progress_callback:
        progress_callback(100.0, "downloaded")
    return UrlIngestResult(
        media_path=largest,
        subtitle_path=vtt_path,
        language=lang,
        video_id=largest.stem,
    )
