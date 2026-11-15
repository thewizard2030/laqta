"""Isolated unit tests for scripts/publish_github_release.py (mocked HTTP only)."""

from __future__ import annotations

import hashlib
import io
import json
import subprocess
import sys
import tarfile
import urllib.error
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import publish_github_release as pub  # noqa: E402


class _FakeHTTPResponse:
    def __init__(
        self,
        status: int,
        body: dict[str, Any] | bytes,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status = status
        self.headers = headers or {}
        if isinstance(body, bytes):
            self._payload = body
        else:
            self._payload = json.dumps(body).encode("utf-8")
        self._pos = 0

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            chunk = self._payload[self._pos :]
            self._pos = len(self._payload)
            return chunk
        chunk = self._payload[self._pos : self._pos + size]
        self._pos += len(chunk)
        return chunk

    def __enter__(self) -> _FakeHTTPResponse:
        return self

    def __exit__(self, *args: object) -> bool:
        return False


def _make_source_tarball(
    path: Path,
    tag: str = "v0.2.5",
    *,
    include_files: dict[str, bytes] | None = None,
    omit: set[str] | None = None,
) -> tuple[int, str]:
    files: dict[str, bytes] = {
        "LICENSE": b"MIT License\n",
        "README.md": b"# Laqta\n",
        "README.ar.md": b"# Laqta AR\n",
        "CHANGELOG.md": b"## [0.2.5] - 2026-11-15\n\n- Notes\n",
        "qatta/__init__.py": b'__version__ = "0.2.5"\n',
        "tests/fixtures/sample_captions_synthetic.ar.vtt": b"WEBVTT\n",
        ".env.example": b"QATTA_ALLOW_CLOUD_APIS=false\n",
    }
    if omit:
        for rel in omit:
            files.pop(rel, None)
    if include_files:
        files.update(include_files)

    prefix = f"laqta-{tag}"
    with tarfile.open(path, "w:gz") as tf:
        for rel, content in files.items():
            info = tarfile.TarInfo(name=f"{prefix}/{rel}")
            info.size = len(content)
            tf.addfile(info, io.BytesIO(content))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return path.stat().st_size, digest


def _http_error(
    url: str,
    code: int,
    message: str,
    *,
    headers: dict[str, str] | None = None,
    errors: list[dict[str, Any]] | None = None,
) -> urllib.error.HTTPError:
    body: dict[str, Any] = {"message": message}
    if errors is not None:
        body["errors"] = errors
    payload = json.dumps(body).encode("utf-8")
    return urllib.error.HTTPError(
        url=url,
        code=code,
        msg=message,
        hdrs=headers or {},  # type: ignore[arg-type]
        fp=io.BytesIO(payload),
    )


def test_missing_and_placeholder_github_token() -> None:
    with pytest.raises(pub.ReleasePublishError, match="GITHUB_TOKEN"):
        pub.require_github_token({})
    with pytest.raises(pub.ReleasePublishError, match="GITHUB_TOKEN"):
        pub.require_github_token({"GITHUB_TOKEN": "   "})
    with pytest.raises(pub.ReleasePublishError, match="GITHUB_TOKEN"):
        pub.require_github_token({"GITHUB_TOKEN": "placeholder"})


@pytest.mark.parametrize("bad_tag", ["", "0.2.5", "v0.2", "v0.2.5-rc1", "v01.2.5"])
def test_invalid_tag_rejected(bad_tag: str) -> None:
    with pytest.raises(pub.ReleasePublishError, match="Invalid release tag"):
        pub.validate_tag(bad_tag)


def test_version_mismatch_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        pub.check_version,
        "collect",
        lambda: [
            ("qatta/__init__.py (source of truth)", "0.2.5"),
            ("pyproject.toml", "0.2.5"),
        ],
    )
    with pytest.raises(pub.ReleasePublishError, match="does not match manifest version"):
        pub.verify_version_alignment("v0.2.6")

    monkeypatch.setattr(
        pub.check_version,
        "collect",
        lambda: [
            ("qatta/__init__.py (source of truth)", "0.2.5"),
            ("pyproject.toml", "0.2.0"),
        ],
    )
    with pytest.raises(pub.ReleasePublishError, match="Manifest version mismatch"):
        pub.verify_version_alignment("v0.2.5")


def test_missing_changelog_notes_fails(tmp_path: Path) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("## [0.2.0] — 2026-11-14\n\nOld release.\n", encoding="utf-8")

    with pytest.raises(pub.ReleasePublishError, match="CHANGELOG.md has no non-empty"):
        pub.resolve_release_notes("v0.2.5", changelog_path=changelog)

    changelog.write_text(
        "## [0.2.5] — 2026-11-15\n\n- Solid release.\n",
        encoding="utf-8",
    )
    empty_notes = tmp_path / "notes.md"
    empty_notes.write_text("   \n", encoding="utf-8")
    with pytest.raises(pub.ReleasePublishError, match="Release notes file is empty"):
        pub.resolve_release_notes("v0.2.5", notes_file=empty_notes, changelog_path=changelog)


def test_archive_validation_and_exclusions(tmp_path: Path) -> None:
    good = tmp_path / "laqta-v0.2.5.tar.gz"
    size, _ = _make_source_tarball(good)
    assert pub.validate_source_archive(good, "v0.2.5") == size

    old_fixture = tmp_path / "old-fixture.tar.gz"
    _make_source_tarball(
        old_fixture,
        include_files={"tests/fixtures/sample_captions.ar.vtt": b"WEBVTT\n"},
    )
    with pytest.raises(pub.ReleasePublishError, match="deprecated broadcast caption fixture"):
        pub.validate_source_archive(old_fixture, "v0.2.5")

    missing_synthetic = tmp_path / "missing-synthetic.tar.gz"
    _make_source_tarball(
        missing_synthetic,
        omit={"tests/fixtures/sample_captions_synthetic.ar.vtt"},
    )
    with pytest.raises(pub.ReleasePublishError, match="missing required release files"):
        pub.validate_source_archive(missing_synthetic, "v0.2.5")

    for forbidden_rel in (
        ".env",
        "backend/.env.local",
        "backend/qatta.db",
        "settings.json",
        "weights/model.bin",
        "frontend/dist/index.html",
        "node_modules/pkg/index.js",
    ):
        bad = tmp_path / f"bad-{forbidden_rel.replace('/', '_')}.tar.gz"
        _make_source_tarball(bad, include_files={forbidden_rel: b"bad"})
        with pytest.raises(pub.ReleasePublishError, match="security/hygiene"):
            pub.validate_source_archive(bad, "v0.2.5")


def test_publish_first_upload_and_digest_verification(tmp_path: Path) -> None:
    archive = tmp_path / "laqta-v0.2.5.tar.gz"
    size, sha256 = _make_source_tarball(archive)
    calls: list[tuple[str, str, str]] = []

    def fake_opener(request: Any, timeout: float = 30.0) -> _FakeHTTPResponse:
        url = request.full_url
        method = request.get_method()
        calls.append((method, url, request.headers.get("Authorization", "")))
        if method == "GET" and url.endswith("/releases/tags/v0.2.5"):
            raise _http_error(url, 404, "Not Found")
        if method == "POST" and url.endswith("/repos/thewizard2030/laqta/releases"):
            payload = json.loads(request.data.decode("utf-8"))
            assert payload["tag_name"] == "v0.2.5"
            assert payload["name"] == "Laqta v0.2.5"
            return _FakeHTTPResponse(
                201,
                {
                    "id": 99,
                    "tag_name": "v0.2.5",
                    "html_url": "https://github.com/thewizard2030/laqta/releases/tag/v0.2.5",
                    "upload_url": "https://uploads.github.com/repos/thewizard2030/laqta/releases/99/assets{?name,label}",
                    "assets": [],
                },
            )
        if (
            method == "POST"
            and url
            == "https://uploads.github.com/repos/thewizard2030/laqta/releases/99/assets?name=laqta-v0.2.5.tar.gz"
        ):
            assert len(request.data) == size
            return _FakeHTTPResponse(
                201,
                {
                    "name": "laqta-v0.2.5.tar.gz",
                    "size": size,
                    "digest": f"sha256:{sha256}",
                },
            )
        raise AssertionError(f"Unexpected call: {method} {url}")

    result = pub.publish_github_release(
        tag="v0.2.5",
        repo="thewizard2030/laqta",
        archive_path=archive,
        notes="## Laqta v0.2.5\n\n- Release notes.",
        token="secret-unit-token",
        opener=fake_opener,
    )

    assert result.release_created is True
    assert result.action == "uploaded"
    assert result.asset_name == "laqta-v0.2.5.tar.gz"
    assert result.asset_size == size
    assert result.asset_sha256 == sha256
    assert len(calls) == 3
    assert all(url.startswith("https://") for _, url, _ in calls)
    assert all(auth == "Bearer secret-unit-token" for _, _, auth in calls)


def test_retry_after_release_creation_before_asset_upload(tmp_path: Path) -> None:
    archive = tmp_path / "laqta-v0.2.5.tar.gz"
    size, sha256 = _make_source_tarball(archive)
    methods: list[str] = []

    def fake_opener(request: Any, timeout: float = 30.0) -> _FakeHTTPResponse:
        method = request.get_method()
        url = request.full_url
        methods.append(method)
        if method == "GET" and url.endswith("/releases/tags/v0.2.5"):
            return _FakeHTTPResponse(
                200,
                {
                    "id": 101,
                    "tag_name": "v0.2.5",
                    "html_url": "https://github.com/thewizard2030/laqta/releases/tag/v0.2.5",
                    "upload_url": "https://uploads.github.com/repos/thewizard2030/laqta/releases/101/assets{?name,label}",
                    "assets": [],
                },
            )
        if method == "POST" and "uploads.github.com" in url:
            return _FakeHTTPResponse(
                201,
                {"name": "laqta-v0.2.5.tar.gz", "size": size, "digest": f"sha256:{sha256}"},
            )
        raise AssertionError(f"Unexpected call: {method} {url}")

    result = pub.publish_github_release(
        tag="v0.2.5",
        repo="thewizard2030/laqta",
        archive_path=archive,
        notes="## Laqta v0.2.5\n",
        token="secret-unit-token",
        opener=fake_opener,
    )

    assert result.release_created is False
    assert result.action == "uploaded"
    assert result.asset_sha256 == sha256
    assert methods == ["GET", "POST"]


def test_retry_existing_asset_matching_digest_succeeds(tmp_path: Path) -> None:
    archive = tmp_path / "laqta-v0.2.5.tar.gz"
    size, sha256 = _make_source_tarball(archive)
    calls: list[str] = []

    def fake_opener(request: Any, timeout: float = 30.0) -> _FakeHTTPResponse:
        calls.append(request.get_method())
        return _FakeHTTPResponse(
            200,
            {
                "id": 101,
                "tag_name": "v0.2.5",
                "html_url": "https://github.com/thewizard2030/laqta/releases/tag/v0.2.5",
                "assets": [
                    {
                        "name": "laqta-v0.2.5.tar.gz",
                        "size": size,
                        "digest": f"sha256:{sha256.upper()}",
                    }
                ],
            },
        )

    result = pub.publish_github_release(
        tag="v0.2.5",
        repo="thewizard2030/laqta",
        archive_path=archive,
        notes="## Laqta v0.2.5\n",
        token="secret-unit-token",
        opener=fake_opener,
    )

    assert result.action == "already_exists"
    assert result.release_created is False
    assert result.asset_sha256 == sha256
    assert calls == ["GET"]


def test_existing_asset_same_size_different_digest_fails(tmp_path: Path) -> None:
    archive = tmp_path / "laqta-v0.2.5.tar.gz"
    size, sha256 = _make_source_tarball(archive)
    different_sha256 = ("0" if sha256[0] != "0" else "1") + sha256[1:]
    calls: list[str] = []

    def fake_opener(request: Any, timeout: float = 30.0) -> _FakeHTTPResponse:
        calls.append(request.get_method())
        return _FakeHTTPResponse(
            200,
            {
                "id": 101,
                "tag_name": "v0.2.5",
                "assets": [
                    {
                        "name": "laqta-v0.2.5.tar.gz",
                        "size": size,
                        "digest": f"sha256:{different_sha256}",
                    }
                ],
            },
        )

    with pytest.raises(pub.ReleasePublishError, match="SHA-256 digest mismatch"):
        pub.publish_github_release(
            tag="v0.2.5",
            repo="thewizard2030/laqta",
            archive_path=archive,
            notes="## Laqta v0.2.5\n",
            token="secret-unit-token",
            opener=fake_opener,
        )

    assert calls == ["GET"]


def test_existing_asset_different_size_fails(tmp_path: Path) -> None:
    archive = tmp_path / "laqta-v0.2.5.tar.gz"
    size, sha256 = _make_source_tarball(archive)

    def fake_opener(request: Any, timeout: float = 30.0) -> _FakeHTTPResponse:
        return _FakeHTTPResponse(
            200,
            {
                "id": 101,
                "tag_name": "v0.2.5",
                "assets": [
                    {
                        "name": "laqta-v0.2.5.tar.gz",
                        "size": size + 42,
                        "digest": f"sha256:{sha256}",
                    }
                ],
            },
        )

    with pytest.raises(pub.ReleasePublishError, match="conflicting size"):
        pub.publish_github_release(
            tag="v0.2.5",
            repo="thewizard2030/laqta",
            archive_path=archive,
            notes="## Laqta v0.2.5\n",
            token="secret-unit-token",
            opener=fake_opener,
        )


def test_missing_digest_fails_closed_without_download_url(tmp_path: Path) -> None:
    archive = tmp_path / "laqta-v0.2.5.tar.gz"
    size, _ = _make_source_tarball(archive)

    def fake_opener(request: Any, timeout: float = 30.0) -> _FakeHTTPResponse:
        return _FakeHTTPResponse(
            200,
            {
                "id": 101,
                "tag_name": "v0.2.5",
                "assets": [{"name": "laqta-v0.2.5.tar.gz", "size": size}],
            },
        )

    with pytest.raises(pub.ReleasePublishError, match="failing closed"):
        pub.publish_github_release(
            tag="v0.2.5",
            repo="thewizard2030/laqta",
            archive_path=archive,
            notes="## Laqta v0.2.5\n",
            token="secret-unit-token",
            opener=fake_opener,
        )


def test_missing_digest_malformed_fails_closed(tmp_path: Path) -> None:
    archive = tmp_path / "laqta-v0.2.5.tar.gz"
    size, _ = _make_source_tarball(archive)

    def fake_opener(request: Any, timeout: float = 30.0) -> _FakeHTTPResponse:
        return _FakeHTTPResponse(
            200,
            {
                "id": 101,
                "tag_name": "v0.2.5",
                "assets": [
                    {
                        "name": "laqta-v0.2.5.tar.gz",
                        "size": size,
                        "digest": "md5:d41d8cd98f00b204e9800998ecf8427e",
                    }
                ],
            },
        )

    with pytest.raises(pub.ReleasePublishError, match="Unsupported or malformed"):
        pub.publish_github_release(
            tag="v0.2.5",
            repo="thewizard2030/laqta",
            archive_path=archive,
            notes="## Laqta v0.2.5\n",
            token="secret-unit-token",
            opener=fake_opener,
        )


def test_missing_digest_verifies_via_safe_redirect_and_strips_auth(tmp_path: Path) -> None:
    archive = tmp_path / "laqta-v0.2.5.tar.gz"
    size, sha256 = _make_source_tarball(archive)
    archive_bytes = archive.read_bytes()
    seen_hops: list[tuple[str, str | None]] = []

    def fake_opener(request: Any, timeout: float = 30.0) -> _FakeHTTPResponse:
        url = request.full_url
        auth = request.headers.get("Authorization")
        seen_hops.append((url, auth))
        if url.endswith("/releases/tags/v0.2.5"):
            return _FakeHTTPResponse(
                200,
                {
                    "id": 101,
                    "tag_name": "v0.2.5",
                    "html_url": "https://github.com/thewizard2030/laqta/releases/tag/v0.2.5",
                    "assets": [
                        {
                            "name": "laqta-v0.2.5.tar.gz",
                            "size": size,
                            "digest": None,
                            "url": "https://api.github.com/repos/thewizard2030/laqta/releases/assets/555",
                        }
                    ],
                },
            )
        if url == "https://api.github.com/repos/thewizard2030/laqta/releases/assets/555":
            return _FakeHTTPResponse(
                302,
                b"",
                headers={"Location": "https://objects.githubusercontent.com/github-production/555"},
            )
        if url == "https://objects.githubusercontent.com/github-production/555":
            return _FakeHTTPResponse(200, archive_bytes)
        raise AssertionError(f"Unexpected URL: {url}")

    result = pub.publish_github_release(
        tag="v0.2.5",
        repo="thewizard2030/laqta",
        archive_path=archive,
        notes="## Laqta v0.2.5\n",
        token="secret-unit-token",
        opener=fake_opener,
    )

    assert result.action == "already_exists"
    assert result.asset_sha256 == sha256
    assert seen_hops == [
        (
            "https://api.github.com/repos/thewizard2030/laqta/releases/tags/v0.2.5",
            "Bearer secret-unit-token",
        ),
        (
            "https://api.github.com/repos/thewizard2030/laqta/releases/assets/555",
            "Bearer secret-unit-token",
        ),
        ("https://objects.githubusercontent.com/github-production/555", None),
    ]


def test_missing_digest_rejects_untrusted_redirect_and_content_tamper(tmp_path: Path) -> None:
    archive = tmp_path / "laqta-v0.2.5.tar.gz"
    size, _ = _make_source_tarball(archive)
    tampered_bytes = b"X" * size

    def untrusted_redirect_opener(request: Any, timeout: float = 30.0) -> _FakeHTTPResponse:
        url = request.full_url
        if url.endswith("/releases/tags/v0.2.5"):
            return _FakeHTTPResponse(
                200,
                {
                    "id": 101,
                    "tag_name": "v0.2.5",
                    "assets": [
                        {
                            "name": "laqta-v0.2.5.tar.gz",
                            "size": size,
                            "url": "https://api.github.com/repos/thewizard2030/laqta/releases/assets/555",
                        }
                    ],
                },
            )
        if url.endswith("/releases/assets/555"):
            raise urllib.error.HTTPError(
                url,
                302,
                "Found",
                {"Location": "https://untrusted.example.net/payload.tar.gz"},  # type: ignore[arg-type]
                fp=None,
            )
        raise AssertionError(f"Unexpected call after untrusted redirect: {url}")

    with pytest.raises(pub.ReleasePublishError, match="untrusted download destination"):
        pub.publish_github_release(
            tag="v0.2.5",
            repo="thewizard2030/laqta",
            archive_path=archive,
            notes="## Laqta v0.2.5\n",
            token="secret-unit-token",
            opener=untrusted_redirect_opener,
        )

    def tampered_download_opener(request: Any, timeout: float = 30.0) -> _FakeHTTPResponse:
        url = request.full_url
        if url.endswith("/releases/tags/v0.2.5"):
            return _FakeHTTPResponse(
                200,
                {
                    "id": 101,
                    "tag_name": "v0.2.5",
                    "assets": [
                        {
                            "name": "laqta-v0.2.5.tar.gz",
                            "size": size,
                            "browser_download_url": "https://github.com/thewizard2030/laqta/releases/download/v0.2.5/laqta-v0.2.5.tar.gz",
                        }
                    ],
                },
            )
        # Never attach Authorization to non-API download hosts
        assert request.headers.get("Authorization") is None
        return _FakeHTTPResponse(200, tampered_bytes)

    with pytest.raises(pub.ReleasePublishError, match="download-and-hash verification"):
        pub.publish_github_release(
            tag="v0.2.5",
            repo="thewizard2030/laqta",
            archive_path=archive,
            notes="## Laqta v0.2.5\n",
            token="secret-unit-token",
            opener=tampered_download_opener,
        )


def test_concurrent_release_and_asset_creation_conflict_handling(tmp_path: Path) -> None:
    archive = tmp_path / "laqta-v0.2.5.tar.gz"
    size, sha256 = _make_source_tarball(archive)

    # Case A: Concurrent release creation (POST /releases returns 422 already_exists)
    tag_get_calls = 0

    def concurrent_release_opener(request: Any, timeout: float = 30.0) -> _FakeHTTPResponse:
        nonlocal tag_get_calls
        method = request.get_method()
        url = request.full_url
        if method == "GET" and url.endswith("/releases/tags/v0.2.5"):
            tag_get_calls += 1
            if tag_get_calls == 1:
                raise _http_error(url, 404, "Not Found")
            return _FakeHTTPResponse(
                200,
                {
                    "id": 202,
                    "tag_name": "v0.2.5",
                    "html_url": "https://github.com/thewizard2030/laqta/releases/tag/v0.2.5",
                    "upload_url": "https://uploads.github.com/repos/thewizard2030/laqta/releases/202/assets{?name,label}",
                    "assets": [],
                },
            )
        if method == "POST" and url.endswith("/releases"):
            raise _http_error(
                url,
                422,
                "Validation Failed",
                errors=[{"resource": "Release", "code": "already_exists", "field": "tag_name"}],
            )
        if method == "POST" and "uploads.github.com" in url:
            return _FakeHTTPResponse(
                201,
                {"name": "laqta-v0.2.5.tar.gz", "size": size, "digest": f"sha256:{sha256}"},
            )
        raise AssertionError(f"Unexpected call: {method} {url}")

    res_a = pub.publish_github_release(
        tag="v0.2.5",
        repo="thewizard2030/laqta",
        archive_path=archive,
        notes="## Laqta v0.2.5\n",
        token="secret-unit-token",
        opener=concurrent_release_opener,
    )
    assert res_a.release_created is False
    assert res_a.action == "uploaded"

    # Case B: Concurrent asset upload with identical digest -> idempotent success
    upload_race_gets = 0

    def concurrent_asset_match_opener(request: Any, timeout: float = 30.0) -> _FakeHTTPResponse:
        nonlocal upload_race_gets
        method = request.get_method()
        url = request.full_url
        if method == "GET" and url.endswith("/releases/tags/v0.2.5"):
            upload_race_gets += 1
            assets = (
                []
                if upload_race_gets == 1
                else [{"name": "laqta-v0.2.5.tar.gz", "size": size, "digest": f"sha256:{sha256}"}]
            )
            return _FakeHTTPResponse(
                200,
                {
                    "id": 202,
                    "tag_name": "v0.2.5",
                    "html_url": "https://github.com/thewizard2030/laqta/releases/tag/v0.2.5",
                    "upload_url": "https://uploads.github.com/repos/thewizard2030/laqta/releases/202/assets{?name,label}",
                    "assets": assets,
                },
            )
        if method == "POST" and "uploads.github.com" in url:
            raise _http_error(
                url,
                422,
                "Validation Failed",
                errors=[{"resource": "ReleaseAsset", "code": "already_exists", "field": "name"}],
            )
        raise AssertionError(f"Unexpected call: {method} {url}")

    res_b = pub.publish_github_release(
        tag="v0.2.5",
        repo="thewizard2030/laqta",
        archive_path=archive,
        notes="## Laqta v0.2.5\n",
        token="secret-unit-token",
        opener=concurrent_asset_match_opener,
    )
    assert res_b.action == "already_exists"
    assert res_b.asset_sha256 == sha256

    # Case C: Concurrent asset upload with conflicting digest -> hard failure
    conflict_gets = 0
    bad_sha = ("0" if sha256[0] != "0" else "1") + sha256[1:]

    def concurrent_asset_conflict_opener(request: Any, timeout: float = 30.0) -> _FakeHTTPResponse:
        nonlocal conflict_gets
        method = request.get_method()
        url = request.full_url
        if method == "GET" and url.endswith("/releases/tags/v0.2.5"):
            conflict_gets += 1
            assets = (
                []
                if conflict_gets == 1
                else [{"name": "laqta-v0.2.5.tar.gz", "size": size, "digest": f"sha256:{bad_sha}"}]
            )
            return _FakeHTTPResponse(
                200,
                {
                    "id": 202,
                    "tag_name": "v0.2.5",
                    "upload_url": "https://uploads.github.com/repos/thewizard2030/laqta/releases/202/assets{?name,label}",
                    "assets": assets,
                },
            )
        raise _http_error(
            url,
            422,
            "Validation Failed",
            errors=[{"resource": "ReleaseAsset", "code": "already_exists", "field": "name"}],
        )

    with pytest.raises(pub.ReleasePublishError, match="SHA-256 digest mismatch"):
        pub.publish_github_release(
            tag="v0.2.5",
            repo="thewizard2030/laqta",
            archive_path=archive,
            notes="## Laqta v0.2.5\n",
            token="secret-unit-token",
            opener=concurrent_asset_conflict_opener,
        )


def test_publish_handles_auth_and_rate_limit_errors_without_secret_leakage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    archive = tmp_path / "laqta-v0.2.5.tar.gz"
    _make_source_tarball(archive)
    secret = "ghp_TopSecretLeakTestToken998877"

    def auth_fail_opener(request: Any, timeout: float = 30.0) -> Any:
        raise _http_error(
            request.full_url,
            401,
            f"Bad credentials for Authorization: Bearer {secret}",
        )

    with pytest.raises(pub.ReleasePublishError) as auth_exc:
        pub.publish_github_release(
            tag="v0.2.5",
            repo="thewizard2030/laqta",
            archive_path=archive,
            notes="## Laqta v0.2.5\n",
            token=secret,
            opener=auth_fail_opener,
        )
    assert "HTTP 401" in str(auth_exc.value)
    assert secret not in str(auth_exc.value)

    def rate_limit_opener(request: Any, timeout: float = 30.0) -> Any:
        raise _http_error(
            request.full_url,
            403,
            f"API rate limit exceeded using {secret}",
            headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1763210000"},
        )

    with pytest.raises(pub.ReleasePublishError) as rate_exc:
        pub.publish_github_release(
            tag="v0.2.5",
            repo="thewizard2030/laqta",
            archive_path=archive,
            notes="## Laqta v0.2.5\n",
            token=secret,
            opener=rate_limit_opener,
        )
    assert "rate limit exceeded" in str(rate_exc.value)
    assert secret not in str(rate_exc.value)

    monkeypatch.setenv("GITHUB_TOKEN", secret)
    monkeypatch.setattr(pub, "verify_version_alignment", lambda tag: "0.2.5")
    monkeypatch.setattr(
        pub,
        "publish_github_release",
        lambda **kwargs: (_ for _ in ()).throw(
            pub.ReleasePublishError(f"Simulated error containing {secret}")
        ),
    )

    rc = pub.main(
        [
            "--tag",
            "v0.2.5",
            "--repo",
            "thewizard2030/laqta",
            "--archive",
            str(archive),
        ]
    )
    captured = capsys.readouterr()
    assert rc == 1
    assert secret not in captured.out
    assert secret not in captured.err
    assert "[REDACTED]" in captured.err


def test_rejects_non_https_and_mismatched_api_responses(tmp_path: Path) -> None:
    with pytest.raises(pub.ReleasePublishError, match="non-HTTPS"):
        pub.ensure_https_url("http://api.github.com/repos/thewizard2030/laqta/releases")

    archive = tmp_path / "laqta-v0.2.5.tar.gz"
    size, sha256 = _make_source_tarball(archive)
    wrong_sha = ("0" if sha256[0] != "0" else "1") + sha256[1:]

    def wrong_tag_opener(request: Any, timeout: float = 30.0) -> _FakeHTTPResponse:
        return _FakeHTTPResponse(200, {"id": 101, "tag_name": "v0.2.0", "assets": []})

    with pytest.raises(pub.ReleasePublishError, match="tag mismatch"):
        pub.publish_github_release(
            tag="v0.2.5",
            repo="thewizard2030/laqta",
            archive_path=archive,
            notes="## Laqta v0.2.5\n",
            token="secret-unit-token",
            opener=wrong_tag_opener,
        )

    def wrong_uploaded_size_opener(request: Any, timeout: float = 30.0) -> _FakeHTTPResponse:
        if request.get_method() == "GET":
            return _FakeHTTPResponse(
                200,
                {
                    "id": 101,
                    "tag_name": "v0.2.5",
                    "upload_url": "https://uploads.github.com/repos/thewizard2030/laqta/releases/101/assets{?name,label}",
                    "assets": [],
                },
            )
        return _FakeHTTPResponse(201, {"name": "laqta-v0.2.5.tar.gz", "size": size - 1})

    with pytest.raises(pub.ReleasePublishError, match="Uploaded asset verification failed"):
        pub.publish_github_release(
            tag="v0.2.5",
            repo="thewizard2030/laqta",
            archive_path=archive,
            notes="## Laqta v0.2.5\n",
            token="secret-unit-token",
            opener=wrong_uploaded_size_opener,
        )

    def wrong_uploaded_digest_opener(request: Any, timeout: float = 30.0) -> _FakeHTTPResponse:
        if request.get_method() == "GET":
            return _FakeHTTPResponse(
                200,
                {
                    "id": 101,
                    "tag_name": "v0.2.5",
                    "upload_url": "https://uploads.github.com/repos/thewizard2030/laqta/releases/101/assets{?name,label}",
                    "assets": [],
                },
            )
        return _FakeHTTPResponse(
            201,
            {"name": "laqta-v0.2.5.tar.gz", "size": size, "digest": f"sha256:{wrong_sha}"},
        )

    with pytest.raises(pub.ReleasePublishError, match="Uploaded asset SHA-256 verification failed"):
        pub.publish_github_release(
            tag="v0.2.5",
            repo="thewizard2030/laqta",
            archive_path=archive,
            notes="## Laqta v0.2.5\n",
            token="secret-unit-token",
            opener=wrong_uploaded_digest_opener,
        )


def test_verify_git_tag_tree_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    def make_runner(responses: dict[tuple[str, ...], tuple[int, str, str]]):
        def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            key = tuple(cmd[:3])
            rc, out, err = responses.get(key, (0, "", ""))
            return subprocess.CompletedProcess(cmd, rc, out, err)

        return fake_run

    base_files = (
        "LICENSE\nREADME.md\nCHANGELOG.md\ntests/fixtures/sample_captions_synthetic.ar.vtt\n"
    )

    monkeypatch.setattr(
        pub.subprocess,
        "run",
        make_runner(
            {
                ("git", "rev-parse", "--verify"): (0, "abc123\n", ""),
                ("git", "ls-tree", "-r"): (0, base_files, ""),
            }
        ),
    )
    pub.verify_git_tag_tree("v0.2.5")

    monkeypatch.setattr(
        pub.subprocess,
        "run",
        make_runner(
            {
                ("git", "rev-parse", "--verify"): (0, "abc123\n", ""),
                ("git", "ls-tree", "-r"): (
                    0,
                    base_files + "tests/fixtures/sample_captions.ar.vtt\n",
                    "",
                ),
            }
        ),
    )
    with pytest.raises(pub.ReleasePublishError, match="deprecated fixture"):
        pub.verify_git_tag_tree("v0.2.5")

    monkeypatch.setattr(
        pub.subprocess,
        "run",
        make_runner(
            {
                ("git", "rev-parse", "--verify"): (0, "abc123\n", ""),
                ("git", "ls-tree", "-r"): (0, "LICENSE\nREADME.md\n", ""),
            }
        ),
    )
    with pytest.raises(pub.ReleasePublishError, match="missing required fixture"):
        pub.verify_git_tag_tree("v0.2.5")

    seq = iter(
        [
            subprocess.CompletedProcess(["git"], 0, "tag111\n", ""),
            subprocess.CompletedProcess(["git"], 0, "head222\n", ""),
        ]
    )
    monkeypatch.setattr(pub.subprocess, "run", lambda *args, **kwargs: next(seq))
    with pytest.raises(pub.ReleasePublishError, match="does not resolve to checked-out HEAD"):
        pub.verify_git_tag_tree("v0.2.5")
