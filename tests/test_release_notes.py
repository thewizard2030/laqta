"""The release notes must be extractable for the tag that is being published.

An empty release body looks intentional, so the extraction is verified here
instead of only in the workflow.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from release_notes import build_notes, section_for  # noqa: E402

CHANGELOG = REPO_ROOT / "CHANGELOG.md"

SAMPLE = """# Changelog

## [Unreleased]

Nothing yet.

## [0.1.0] — 2026-10-20

The first public release.

- A bullet
- Another bullet

## [0.0.9] — 2026-01-01

An older release.
"""


def test_extracts_the_section_for_a_tag() -> None:
    body = section_for("v0.1.0", SAMPLE)

    assert body is not None
    assert "The first public release." in body
    assert "- A bullet" in body
    # The next version must not leak into the section.
    assert "An older release." not in body
    assert "Nothing yet." not in body


def test_accepts_a_tag_without_the_v_prefix() -> None:
    assert section_for("0.1.0", SAMPLE) == section_for("v0.1.0", SAMPLE)


def test_unknown_tag_has_no_section() -> None:
    assert section_for("v9.9.9", SAMPLE) is None
    assert build_notes("v9.9.9", SAMPLE) is None


def test_real_changelog_has_a_section_for_the_current_version() -> None:
    from qatta import __version__

    changelog = CHANGELOG.read_text(encoding="utf-8")
    notes = build_notes(f"v{__version__}", changelog)

    assert notes is not None, f"CHANGELOG.md has no section for v{__version__}"
    assert len(notes) > 200, "the release notes look empty"
    assert notes.startswith(f"## Laqta v{__version__}")


def test_the_script_writes_the_notes() -> None:
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "release_notes.py"), "v0.1.0"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "## Laqta v0.1.0" in result.stdout
    assert "Full changelog" in result.stdout


def test_the_script_fails_for_an_unknown_tag() -> None:
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "release_notes.py"), "v9.9.9"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )

    assert result.returncode == 1
    assert "No CHANGELOG.md section" in result.stderr
