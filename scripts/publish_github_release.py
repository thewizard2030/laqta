#!/usr/bin/env python3
"""Validate and publish a Laqta GitHub Release from an immutable release tag.

Uses Python's standard library exclusively to verify semantic version tags,
manifest consistency, changelog notes, source archive contents + SHA-256
digest, and to create the GitHub Release and upload the source tarball
idempotently over HTTPS without leaking credentials or following untrusted
redirects.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tarfile
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import check_version  # noqa: E402
import release_notes  # noqa: E402

DEFAULT_REPO = "thewizard2030/laqta"
GITHUB_API_BASE = "https://api.github.com"
GITHUB_API_VERSION = "2022-11-28"
MAX_DOWNLOAD_REDIRECTS = 5
REDIRECT_STATUS_CODES = frozenset({301, 302, 303, 307, 308})
SHA256_DIGEST_RE = re.compile(r"^sha256:([0-9a-fA-F]{64})$")
SEMVER_TAG_RE = re.compile(r"^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
REPO_SLUG_RE = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")

TRUSTED_API_HOSTS = frozenset({"api.github.com", "uploads.github.com"})
TRUSTED_DOWNLOAD_HOSTS = frozenset(
    {
        "api.github.com",
        "github.com",
        "objects.githubusercontent.com",
        "release-assets.githubusercontent.com",
        "github-releases.githubusercontent.com",
    }
)

PLACEHOLDER_TOKENS = frozenset(
    {
        "placeholder",
        "changeme",
        "your_token",
        "your-token",
        "your-token-here",
        "replace_me",
        "replace-me",
        "dummy",
        "none",
        "null",
        "xxx",
        "<github_token>",
        "<token>",
    }
)

REQUIRED_ARCHIVE_FILES = (
    "LICENSE",
    "README.md",
    "README.ar.md",
    "CHANGELOG.md",
    "qatta/__init__.py",
    "tests/fixtures/sample_captions_synthetic.ar.vtt",
)

FORBIDDEN_EXACT_PATHS = frozenset(
    {
        "tests/fixtures/sample_captions.ar.vtt",
    }
)

FORBIDDEN_DIR_PARTS = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
    }
)

FORBIDDEN_EXTENSIONS = (
    ".db",
    ".sqlite",
    ".sqlite3",
    ".pem",
    ".key",
    ".onnx",
    ".pt",
    ".pth",
    ".safetensors",
)


class ReleasePublishError(RuntimeError):
    """Raised when release preflight validation or GitHub API publishing fails."""


@dataclass(frozen=True)
class PublishResult:
    """Structured outcome returned by :func:`publish_github_release`."""

    tag: str
    repo: str
    release_url: str
    asset_name: str
    asset_size: int
    asset_sha256: str
    action: str  # "uploaded" | "already_exists"
    release_created: bool


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Disable urllib automatic redirect following so hops are checked explicitly."""

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None


_NO_REDIRECT_OPENER = urllib.request.build_opener(_NoRedirectHandler())
HttpOpener = Callable[..., Any]


def _default_no_redirect_open(request: urllib.request.Request, timeout: float = 30.0) -> Any:
    return _NO_REDIRECT_OPENER.open(request, timeout=timeout)


def redact_secret(text: str, token: str | None) -> str:
    """Scrub ``token`` and Bearer authorization fragments from output or errors."""
    cleaned = text
    if token:
        stripped = token.strip()
        if stripped:
            cleaned = cleaned.replace(stripped, "[REDACTED]")
    cleaned = re.sub(
        r"(Authorization:\s*Bearer\s+)\S+",
        r"\1[REDACTED]",
        cleaned,
        flags=re.IGNORECASE,
    )
    return cleaned


def validate_tag(tag: str) -> str:
    """Ensure ``tag`` is a strict ``vMAJOR.MINOR.PATCH`` release tag."""
    candidate = tag.strip()
    if not SEMVER_TAG_RE.match(candidate):
        raise ReleasePublishError(
            f"Invalid release tag {tag!r}: expected strict semantic version tag vMAJOR.MINOR.PATCH."
        )
    return candidate


def validate_repo_slug(repo: str) -> str:
    """Validate GitHub repository slug ``owner/name``."""
    candidate = repo.strip()
    if not REPO_SLUG_RE.match(candidate):
        raise ReleasePublishError(
            f"Invalid GitHub repository slug {repo!r}: expected 'owner/repo'."
        )
    return candidate


def ensure_https_url(url: str) -> str:
    """Reject non-HTTPS endpoints before issuing any HTTP request."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ReleasePublishError(f"Refusing non-HTTPS URL for GitHub request: {url!r}")
    return url


def _hostname_of(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    return (parsed.hostname or "").lower()


def compute_archive_sha256(archive_path: Path) -> str:
    """Compute lowercase hexadecimal SHA-256 digest of ``archive_path``."""
    hasher = hashlib.sha256()
    with archive_path.open("rb") as handle:
        while chunk := handle.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def parse_sha256_digest(raw_digest: Any) -> str | None:
    """Parse GitHub's ``sha256:<hex>`` asset digest field or fail closed if invalid."""
    if raw_digest is None:
        return None
    if isinstance(raw_digest, str):
        candidate = raw_digest.strip()
        if not candidate:
            return None
        match = SHA256_DIGEST_RE.fullmatch(candidate)
        if match:
            return match.group(1).lower()
    raise ReleasePublishError(
        f"Unsupported or malformed GitHub release asset digest {raw_digest!r}; failing closed."
    )


def require_github_token(env: dict[str, str] | None = None) -> str:
    """Read and validate ``GITHUB_TOKEN`` without exposing its value."""
    source = os.environ if env is None else env
    token = source.get("GITHUB_TOKEN", "").strip()
    lowered = token.lower()
    if not token or lowered in PLACEHOLDER_TOKENS or "placeholder" in lowered:
        raise ReleasePublishError(
            "GITHUB_TOKEN is missing or set to a placeholder. Configure a fine-grained GitHub "
            "token in CircleCI Context 'laqta-release-publishing' scoped to thewizard2030/laqta "
            "with Contents: Read and write (and Workflows: Read and write when workflows change)."
        )
    return token


def verify_version_alignment(tag: str) -> str:
    """Confirm all manifests agree and match ``tag`` (`vMAJOR.MINOR.PATCH`)."""
    valid_tag = validate_tag(tag)
    entries = check_version.collect()
    source_version = entries[0][1]
    mismatched = [(label, version) for label, version in entries if version != source_version]
    if mismatched:
        details = ", ".join(f"{label}={version}" for label, version in mismatched)
        raise ReleasePublishError(
            f"Manifest version mismatch against qatta/__init__.py ({source_version}): {details}."
        )
    expected_tag = f"v{source_version}"
    if valid_tag != expected_tag:
        raise ReleasePublishError(
            f"Tag {valid_tag} does not match manifest version {source_version} "
            f"(expected {expected_tag})."
        )
    return source_version


def resolve_release_notes(
    tag: str,
    *,
    notes_file: Path | None = None,
    changelog_path: Path = REPO_ROOT / "CHANGELOG.md",
) -> str:
    """Extract and validate non-empty release notes for ``tag``."""
    valid_tag = validate_tag(tag)
    if not changelog_path.is_file():
        raise ReleasePublishError(f"Changelog file not found: {changelog_path}")

    changelog_text = changelog_path.read_text(encoding="utf-8")
    extracted = release_notes.build_notes(valid_tag, changelog_text)
    if extracted is None or not extracted.strip():
        raise ReleasePublishError(
            f"CHANGELOG.md has no non-empty release notes section for {valid_tag}."
        )

    if notes_file is not None:
        if not notes_file.is_file():
            raise ReleasePublishError(f"Release notes file not found: {notes_file}")
        file_text = notes_file.read_text(encoding="utf-8").strip()
        if not file_text:
            raise ReleasePublishError(f"Release notes file is empty: {notes_file}")
        return file_text

    return extracted


def verify_git_tag_tree(tag: str, repo_root: Path = REPO_ROOT) -> None:
    """Verify ``tag`` resolves to ``HEAD`` and contains only the clean fixture tree."""
    valid_tag = validate_tag(tag)

    tag_commit = subprocess.run(
        ["git", "rev-parse", "--verify", f"refs/tags/{valid_tag}^{{commit}}"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if tag_commit.returncode != 0:
        raise ReleasePublishError(
            f"Release tag {valid_tag} does not exist or resolve to a commit: "
            f"{tag_commit.stderr.strip()}"
        )

    head_commit = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if head_commit.returncode != 0:
        raise ReleasePublishError(f"Could not resolve HEAD commit: {head_commit.stderr.strip()}")

    if tag_commit.stdout.strip() != head_commit.stdout.strip():
        raise ReleasePublishError(
            f"Tag {valid_tag} ({tag_commit.stdout.strip()[:12]}) does not resolve to "
            f"checked-out HEAD ({head_commit.stdout.strip()[:12]})."
        )

    ls_tree = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", valid_tag],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if ls_tree.returncode != 0:
        raise ReleasePublishError(f"Unable to inspect tagged tree {valid_tag}: {ls_tree.stderr}")

    tree_files = set(ls_tree.stdout.splitlines())
    synthetic = "tests/fixtures/sample_captions_synthetic.ar.vtt"
    deprecated = "tests/fixtures/sample_captions.ar.vtt"
    if synthetic not in tree_files:
        raise ReleasePublishError(
            f"Tagged tree {valid_tag} is missing required fixture {synthetic}."
        )
    if deprecated in tree_files:
        raise ReleasePublishError(
            f"Tagged tree {valid_tag} still contains deprecated fixture {deprecated}."
        )


def _is_forbidden_archive_path(rel_path: str) -> str | None:
    """Return a reason string if ``rel_path`` must never appear in a source tarball."""
    normalized = rel_path.removeprefix("./").lstrip("/")
    if not normalized:
        return None
    if normalized in FORBIDDEN_EXACT_PATHS:
        return f"deprecated broadcast caption fixture present ({normalized})"

    parts = [part for part in normalized.split("/") if part]
    for part in parts[:-1]:
        if part in FORBIDDEN_DIR_PARTS:
            return f"forbidden build/VCS directory entry ({normalized})"

    if normalized.startswith("frontend/dist/") or normalized.startswith("dist/"):
        return f"build artifact directory included ({normalized})"

    basename = parts[-1] if parts else normalized
    if basename == ".env" or (basename.startswith(".env.") and basename != ".env.example"):
        return f"environment secret file included ({normalized})"

    if basename in {"settings.json", "model.bin"}:
        return f"private state or model weight included ({normalized})"

    if any(normalized.lower().endswith(ext) for ext in FORBIDDEN_EXTENSIONS):
        return f"forbidden key, database, or model weight included ({normalized})"

    return None


def validate_source_archive(archive_path: Path, tag: str) -> int:
    """Validate that ``archive_path`` is a clean source-only tarball for ``tag``."""
    valid_tag = validate_tag(tag)
    if not archive_path.is_file():
        raise ReleasePublishError(f"Source archive not found: {archive_path}")

    size = archive_path.stat().st_size
    if size <= 0:
        raise ReleasePublishError(f"Source archive is empty: {archive_path}")

    expected_prefix = f"laqta-{valid_tag}/"
    relative_files: set[str] = set()

    try:
        with tarfile.open(archive_path, "r:gz") as tf:
            for member in tf.getmembers():
                name = member.name
                if name == "pax_global_header":
                    continue
                if not name.startswith(expected_prefix) and name != expected_prefix.rstrip("/"):
                    raise ReleasePublishError(
                        f"Archive member {name!r} does not use expected prefix {expected_prefix!r}."
                    )
                rel = name[len(expected_prefix) :]
                if not rel:
                    continue
                reason = _is_forbidden_archive_path(rel)
                if reason is not None:
                    raise ReleasePublishError(f"Archive failed security/hygiene check: {reason}")
                if member.isfile() or member.issym():
                    relative_files.add(rel)
    except tarfile.TarError as exc:
        raise ReleasePublishError(f"Invalid gzip tar archive {archive_path}: {exc}") from exc

    missing = [path for path in REQUIRED_ARCHIVE_FILES if path not in relative_files]
    if missing:
        raise ReleasePublishError(
            "Source archive is missing required release files: " + ", ".join(missing)
        )

    return size


def _read_http_body(response: Any) -> bytes:
    raw = response.read()
    return raw if isinstance(raw, bytes) else str(raw).encode("utf-8")


def _extract_error_body(exc: urllib.error.HTTPError) -> tuple[str, dict[str, Any] | None]:
    raw_body = ""
    try:
        raw_bytes = exc.read()
        raw_body = raw_bytes.decode("utf-8", errors="replace").strip() if raw_bytes else ""
    except Exception:
        raw_body = ""
    parsed_json: dict[str, Any] | None = None
    if raw_body:
        try:
            loaded = json.loads(raw_body)
            if isinstance(loaded, dict):
                parsed_json = loaded
        except json.JSONDecodeError:
            parsed_json = None
    return raw_body, parsed_json


def _is_already_exists_422(code: int, parsed: dict[str, Any] | None, raw_body: str) -> bool:
    if code != 422:
        return False
    if parsed:
        errors = parsed.get("errors")
        if isinstance(errors, list):
            for entry in errors:
                if isinstance(entry, dict) and entry.get("code") == "already_exists":
                    return True
        message = str(parsed.get("message", "")).lower()
        if "already exists" in message or "already_exists" in message:
            return True
    return "already exists" in raw_body.lower() or "already_exists" in raw_body.lower()


def _format_http_error(
    code: int,
    reason: Any,
    headers: Any,
    raw_body: str,
    parsed: dict[str, Any] | None,
    *,
    action: str,
    token: str,
) -> str:
    hdrs = headers or {}
    remaining = str(hdrs.get("X-RateLimit-Remaining", "")).strip()
    reset = str(hdrs.get("X-RateLimit-Reset", "")).strip()
    retry_after = str(hdrs.get("Retry-After", "")).strip()

    detail = str(parsed["message"]) if parsed and parsed.get("message") else raw_body

    if code == 401:
        msg = (
            f"GitHub API authorization failed (HTTP 401) while {action}: {detail or reason}. "
            "Verify GITHUB_TOKEN in CircleCI Context 'laqta-release-publishing'."
        )
    elif code == 429 or (code == 403 and (remaining == "0" or "rate limit" in detail.lower())):
        extra = f" retry_after={retry_after}" if retry_after else ""
        reset_info = f" reset={reset}" if reset else ""
        msg = (
            f"GitHub API rate limit exceeded (HTTP {code}) while {action}: "
            f"{detail or reason}.{extra}{reset_info}"
        )
    elif code == 403:
        msg = (
            f"GitHub API permission denied (HTTP 403) while {action}: {detail or reason}. "
            "Ensure GITHUB_TOKEN has Contents: Read and write permissions."
        )
    else:
        msg = f"GitHub API request failed (HTTP {code}) while {action}: {detail or reason}."

    return redact_secret(msg, token)


class _AlreadyExistsConflictError(Exception):
    """Internal signal for concurrent 422 already_exists responses."""


def _github_request(
    *,
    method: str,
    url: str,
    token: str,
    tag: str,
    body: bytes | None = None,
    content_type: str | None = None,
    accept: str = "application/vnd.github+json",
    opener: HttpOpener = _default_no_redirect_open,
    timeout: float = 30.0,
) -> tuple[int, dict[str, Any]]:
    ensure_https_url(url)
    host = _hostname_of(url)
    if host not in TRUSTED_API_HOSTS:
        raise ReleasePublishError(
            f"Refusing to send authenticated GitHub API request to untrusted host {host!r}."
        )

    headers: dict[str, str] = {
        "Accept": accept,
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
        "User-Agent": f"laqta-release-publisher/{tag}",
    }
    if content_type is not None:
        headers["Content-Type"] = content_type
    if body is not None:
        headers["Content-Length"] = str(len(body))

    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with opener(request, timeout=timeout) as response:
            status = int(getattr(response, "status", 200))
            if status in REDIRECT_STATUS_CODES:
                raise ReleasePublishError(
                    f"Refusing unexpected redirect (HTTP {status}) on API call {method} {url}."
                )
            payload_bytes = _read_http_body(response)
            data = json.loads(payload_bytes.decode("utf-8")) if payload_bytes else {}
            if not isinstance(data, dict):
                raise ReleasePublishError(
                    f"Unexpected non-object GitHub API JSON response from {url}"
                )
            return status, data
    except urllib.error.HTTPError as exc:
        if exc.code in REDIRECT_STATUS_CODES:
            raise ReleasePublishError(
                f"Refusing unexpected redirect (HTTP {exc.code}) on API call {method} {url}."
            ) from exc
        if exc.code == 404 and method == "GET":
            return 404, {}
        raw_body, parsed = _extract_error_body(exc)
        if method == "POST" and _is_already_exists_422(exc.code, parsed, raw_body):
            raise _AlreadyExistsConflictError from exc
        raise ReleasePublishError(
            _format_http_error(
                exc.code,
                exc.reason,
                exc.headers,
                raw_body,
                parsed,
                action=f"{method} {url}",
                token=token,
            )
        ) from exc
    except urllib.error.URLError as exc:
        raise ReleasePublishError(
            redact_secret(f"Network error contacting GitHub API ({url}): {exc.reason}", token)
        ) from exc


def _resolve_redirect_target(current_url: str, location: str) -> str:
    candidate = urllib.parse.urljoin(current_url, location.strip())
    ensure_https_url(candidate)
    host = _hostname_of(candidate)
    if host not in TRUSTED_DOWNLOAD_HOSTS:
        raise ReleasePublishError(
            f"Refusing redirect to untrusted download destination {host!r} ({candidate})."
        )
    return candidate


def _hash_stream_from_url(
    *,
    download_url: str,
    token: str,
    tag: str,
    expected_size: int,
    opener: HttpOpener = _default_no_redirect_open,
    timeout: float = 30.0,
) -> tuple[int, str]:
    """Download an existing release asset safely over HTTPS and return `(size, sha256)`."""
    ensure_https_url(download_url)
    initial_host = _hostname_of(download_url)
    if initial_host not in TRUSTED_DOWNLOAD_HOSTS:
        raise ReleasePublishError(
            f"Refusing to download verification asset from untrusted host {initial_host!r}."
        )

    current_url = download_url
    send_auth = initial_host in TRUSTED_API_HOSTS

    for _hop in range(MAX_DOWNLOAD_REDIRECTS + 1):
        headers: dict[str, str] = {
            "Accept": "application/octet-stream",
            "User-Agent": f"laqta-release-publisher/{tag}",
        }
        if send_auth and _hostname_of(current_url) in TRUSTED_API_HOSTS:
            headers["Authorization"] = f"Bearer {token}"

        request = urllib.request.Request(current_url, headers=headers, method="GET")
        try:
            with opener(request, timeout=timeout) as response:
                status = int(getattr(response, "status", 200))
                if status in REDIRECT_STATUS_CODES:
                    resp_headers = getattr(response, "headers", None) or {}
                    location = str(resp_headers.get("Location", "")).strip()
                    if not location:
                        raise ReleasePublishError(
                            f"Redirect response (HTTP {status}) from {current_url} "
                            "omitted Location."
                        )
                    current_url = _resolve_redirect_target(current_url, location)
                    # Never forward Authorization headers to any redirect destination.
                    send_auth = False
                    continue

                hasher = hashlib.sha256()
                total_bytes = 0
                while True:
                    chunk = response.read(65536)
                    if not chunk:
                        break
                    chunk_bytes = chunk if isinstance(chunk, bytes) else str(chunk).encode("utf-8")
                    total_bytes += len(chunk_bytes)
                    if total_bytes > expected_size:
                        raise ReleasePublishError(
                            f"Downloaded asset exceeded expected size ({expected_size} bytes); "
                            "aborting content verification."
                        )
                    hasher.update(chunk_bytes)
                return total_bytes, hasher.hexdigest()
        except urllib.error.HTTPError as exc:
            if exc.code in REDIRECT_STATUS_CODES:
                hdrs = exc.headers or {}
                location = str(hdrs.get("Location", "")).strip()
                if not location:
                    raise ReleasePublishError(
                        f"Redirect response (HTTP {exc.code}) from {current_url} omitted Location."
                    ) from exc
                current_url = _resolve_redirect_target(current_url, location)
                send_auth = False
                continue
            raw_body, parsed = _extract_error_body(exc)
            raise ReleasePublishError(
                _format_http_error(
                    exc.code,
                    exc.reason,
                    exc.headers,
                    raw_body,
                    parsed,
                    action=f"GET {current_url}",
                    token=token,
                )
            ) from exc
        except urllib.error.URLError as exc:
            raise ReleasePublishError(
                redact_secret(
                    f"Network error downloading asset for verification ({current_url}): "
                    f"{exc.reason}",
                    token,
                )
            ) from exc

    raise ReleasePublishError(
        f"Exceeded maximum redirects ({MAX_DOWNLOAD_REDIRECTS}) while verifying asset digest."
    )


def _select_verification_download_url(asset: dict[str, Any]) -> str | None:
    for field in ("url", "browser_download_url"):
        raw = str(asset.get(field, "")).strip()
        if raw:
            ensure_https_url(raw)
            return raw
    return None


def _verify_existing_asset(
    *,
    asset: dict[str, Any],
    asset_name: str,
    expected_size: int,
    expected_sha256: str,
    token: str,
    tag: str,
    opener: HttpOpener,
) -> None:
    """Verify an existing release asset matches exact byte size AND SHA-256 content."""
    remote_size = asset.get("size")
    if remote_size != expected_size:
        raise ReleasePublishError(
            f"Existing release asset {asset_name!r} has conflicting size {remote_size} bytes "
            f"(expected {expected_size} bytes); refusing to overwrite or delete it."
        )

    remote_sha256 = parse_sha256_digest(asset.get("digest"))
    if remote_sha256 is not None:
        if remote_sha256 != expected_sha256:
            raise ReleasePublishError(
                f"Existing release asset {asset_name!r} has identical size ({expected_size} bytes) "
                f"but SHA-256 digest mismatch (remote sha256:{remote_sha256}, "
                f"local sha256:{expected_sha256}); refusing to overwrite or delete it."
            )
        return

    # Fail closed if digest metadata is unavailable and no HTTPS verification URL exists.
    download_url = _select_verification_download_url(asset)
    if download_url is None:
        raise ReleasePublishError(
            f"Existing release asset {asset_name!r} has matching size ({expected_size} bytes) "
            "but no SHA-256 digest or verifiable HTTPS download URL; failing closed."
        )

    downloaded_size, downloaded_sha256 = _hash_stream_from_url(
        download_url=download_url,
        token=token,
        tag=tag,
        expected_size=expected_size,
        opener=opener,
    )
    if downloaded_size != expected_size or downloaded_sha256 != expected_sha256:
        raise ReleasePublishError(
            f"Existing release asset {asset_name!r} failed download-and-hash verification "
            f"(remote size={downloaded_size}, sha256:{downloaded_sha256}; "
            f"expected size={expected_size}, sha256:{expected_sha256}); "
            "refusing to overwrite or delete it."
        )


def _resolve_upload_url(release: dict[str, Any], repo: str, asset_name: str) -> str:
    raw_upload = str(release.get("upload_url", "")).strip()
    if raw_upload:
        base_upload = re.sub(r"\{[^{}]*\}", "", raw_upload)
    else:
        release_id = release.get("id")
        if not release_id:
            raise ReleasePublishError("GitHub Release response is missing both upload_url and id.")
        base_upload = f"https://uploads.github.com/repos/{repo}/releases/{release_id}/assets"
    encoded_name = urllib.parse.quote(asset_name, safe="")
    separator = "&" if "?" in base_upload else "?"
    upload_url = ensure_https_url(f"{base_upload}{separator}name={encoded_name}")
    host = _hostname_of(upload_url)
    if host not in TRUSTED_API_HOSTS:
        raise ReleasePublishError(f"Refusing untrusted release asset upload host {host!r}.")
    return upload_url


def _fetch_release_by_tag(
    *,
    tag_lookup_url: str,
    valid_tag: str,
    token: str,
    opener: HttpOpener,
) -> tuple[int, dict[str, Any]]:
    status, release = _github_request(
        method="GET",
        url=tag_lookup_url,
        token=token,
        tag=valid_tag,
        opener=opener,
    )
    if status != 404:
        returned_tag = str(release.get("tag_name", "")).strip()
        if returned_tag != valid_tag:
            raise ReleasePublishError(
                f"GitHub Release tag mismatch: expected {valid_tag!r}, "
                f"API returned {returned_tag!r}."
            )
    return status, release


def _find_matching_asset(release: dict[str, Any], asset_name: str) -> dict[str, Any] | None:
    existing_assets = release.get("assets") or []
    if not isinstance(existing_assets, list):
        raise ReleasePublishError("GitHub Release response returned malformed assets list.")
    for asset in existing_assets:
        if isinstance(asset, dict) and asset.get("name") == asset_name:
            return asset
    return None


def publish_github_release(
    *,
    tag: str,
    repo: str,
    archive_path: Path,
    notes: str,
    token: str,
    opener: HttpOpener = _default_no_redirect_open,
) -> PublishResult:
    """Create or resume a GitHub Release for ``tag`` with SHA-256 verification."""
    valid_tag = validate_tag(tag)
    valid_repo = validate_repo_slug(repo)
    expected_size = validate_source_archive(archive_path, valid_tag)
    expected_sha256 = compute_archive_sha256(archive_path)
    if not notes.strip():
        raise ReleasePublishError(f"Release notes for {valid_tag} cannot be empty.")

    encoded_tag = urllib.parse.quote(valid_tag, safe="")
    tag_lookup_url = ensure_https_url(
        f"{GITHUB_API_BASE}/repos/{valid_repo}/releases/tags/{encoded_tag}"
    )
    status, release = _fetch_release_by_tag(
        tag_lookup_url=tag_lookup_url,
        valid_tag=valid_tag,
        token=token,
        opener=opener,
    )

    release_created = False
    if status == 404:
        create_url = ensure_https_url(f"{GITHUB_API_BASE}/repos/{valid_repo}/releases")
        payload = json.dumps(
            {
                "tag_name": valid_tag,
                "name": f"Laqta {valid_tag}",
                "body": notes,
                "draft": False,
                "prerelease": False,
            }
        ).encode("utf-8")
        try:
            _, release = _github_request(
                method="POST",
                url=create_url,
                token=token,
                tag=valid_tag,
                body=payload,
                content_type="application/json; charset=utf-8",
                opener=opener,
            )
            release_created = True
        except _AlreadyExistsConflictError as exc:
            retry_status, release = _fetch_release_by_tag(
                tag_lookup_url=tag_lookup_url,
                valid_tag=valid_tag,
                token=token,
                opener=opener,
            )
            if retry_status == 404:
                raise ReleasePublishError(
                    f"GitHub reported release conflict for {valid_tag}, "
                    "but tag lookup returned 404."
                ) from exc

    returned_tag = str(release.get("tag_name", "")).strip()
    if returned_tag != valid_tag:
        raise ReleasePublishError(
            f"GitHub Release tag mismatch: expected {valid_tag!r}, API returned {returned_tag!r}."
        )

    asset_name = archive_path.name
    release_url = str(release.get("html_url") or release.get("url") or "")
    existing_asset = _find_matching_asset(release, asset_name)
    if existing_asset is not None:
        _verify_existing_asset(
            asset=existing_asset,
            asset_name=asset_name,
            expected_size=expected_size,
            expected_sha256=expected_sha256,
            token=token,
            tag=valid_tag,
            opener=opener,
        )
        return PublishResult(
            tag=valid_tag,
            repo=valid_repo,
            release_url=release_url,
            asset_name=asset_name,
            asset_size=expected_size,
            asset_sha256=expected_sha256,
            action="already_exists",
            release_created=release_created,
        )

    upload_url = _resolve_upload_url(release, valid_repo, asset_name)
    archive_bytes = archive_path.read_bytes()
    try:
        _, uploaded_asset = _github_request(
            method="POST",
            url=upload_url,
            token=token,
            tag=valid_tag,
            body=archive_bytes,
            content_type="application/gzip",
            opener=opener,
        )
    except _AlreadyExistsConflictError as exc:
        retry_status, refreshed_release = _fetch_release_by_tag(
            tag_lookup_url=tag_lookup_url,
            valid_tag=valid_tag,
            token=token,
            opener=opener,
        )
        if retry_status == 404:
            raise ReleasePublishError(
                f"Asset upload conflict reported for {asset_name!r}, "
                f"but release {valid_tag} was 404."
            ) from exc
        concurrent_asset = _find_matching_asset(refreshed_release, asset_name)
        if concurrent_asset is None:
            raise ReleasePublishError(
                f"Asset upload returned already_exists for {asset_name!r}, "
                "but the asset was absent on subsequent release lookup."
            ) from exc
        _verify_existing_asset(
            asset=concurrent_asset,
            asset_name=asset_name,
            expected_size=expected_size,
            expected_sha256=expected_sha256,
            token=token,
            tag=valid_tag,
            opener=opener,
        )
        return PublishResult(
            tag=valid_tag,
            repo=valid_repo,
            release_url=str(refreshed_release.get("html_url") or release_url),
            asset_name=asset_name,
            asset_size=expected_size,
            asset_sha256=expected_sha256,
            action="already_exists",
            release_created=release_created,
        )

    uploaded_name = uploaded_asset.get("name")
    uploaded_size = uploaded_asset.get("size")
    if uploaded_name != asset_name or uploaded_size != expected_size:
        raise ReleasePublishError(
            "Uploaded asset verification failed: "
            f"expected ({asset_name!r}, {expected_size} bytes), "
            f"got ({uploaded_name!r}, {uploaded_size} bytes)."
        )
    uploaded_sha256 = parse_sha256_digest(uploaded_asset.get("digest"))
    if uploaded_sha256 is not None and uploaded_sha256 != expected_sha256:
        raise ReleasePublishError(
            "Uploaded asset SHA-256 verification failed: "
            f"expected sha256:{expected_sha256}, API returned sha256:{uploaded_sha256}."
        )

    return PublishResult(
        tag=valid_tag,
        repo=valid_repo,
        release_url=release_url,
        asset_name=asset_name,
        asset_size=expected_size,
        asset_sha256=expected_sha256,
        action="uploaded",
        release_created=release_created,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tag",
        default=os.environ.get("CIRCLE_TAG", ""),
        help="Semantic release tag (defaults to $CIRCLE_TAG), e.g. v0.2.5",
    )
    parser.add_argument(
        "--repo",
        default=DEFAULT_REPO,
        help=f"GitHub repository slug owner/repo (default: {DEFAULT_REPO})",
    )
    parser.add_argument(
        "--archive",
        type=Path,
        required=True,
        help="Path to the generated dist/laqta-vX.Y.Z.tar.gz archive",
    )
    parser.add_argument(
        "--notes-file",
        type=Path,
        default=None,
        help="Optional pre-generated release notes markdown file",
    )
    parser.add_argument(
        "--changelog",
        type=Path,
        default=REPO_ROOT / "CHANGELOG.md",
        help="Path to CHANGELOG.md (default: repo root CHANGELOG.md)",
    )
    parser.add_argument(
        "--verify-git-tag",
        action="store_true",
        help="Verify git tag resolves to HEAD and contains the synthetic fixture only",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Run all preflight and archive checks without calling the GitHub API",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    token: str | None = os.environ.get("GITHUB_TOKEN")
    try:
        tag = validate_tag(args.tag)
        verify_version_alignment(tag)
        notes = resolve_release_notes(
            tag,
            notes_file=args.notes_file,
            changelog_path=args.changelog,
        )
        if args.verify_git_tag:
            verify_git_tag_tree(tag)
        archive_size = validate_source_archive(args.archive, tag)
        archive_sha256 = compute_archive_sha256(args.archive)

        if args.validate_only:
            print(
                f"Validated release {tag} for {args.repo}: "
                f"archive={args.archive.name} ({archive_size} bytes, sha256:{archive_sha256})."
            )
            return 0

        token = require_github_token()
        result = publish_github_release(
            tag=tag,
            repo=args.repo,
            archive_path=args.archive,
            notes=notes,
            token=token,
        )
    except ReleasePublishError as exc:
        print(f"ERROR: {redact_secret(str(exc), token)}", file=sys.stderr)
        return 1

    if result.action == "already_exists":
        print(
            f"Release {result.tag} on {result.repo} already has verified asset "
            f"{result.asset_name} ({result.asset_size} bytes, sha256:{result.asset_sha256}); "
            "no duplicate upload performed."
        )
    else:
        verb = "Created release and uploaded" if result.release_created else "Uploaded"
        print(
            f"{verb} verified asset {result.asset_name} ({result.asset_size} bytes, "
            f"sha256:{result.asset_sha256}) for {result.tag} on {result.repo}."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
