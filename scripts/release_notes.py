#!/usr/bin/env python3
"""Extract the release notes for a tag from CHANGELOG.md.

The GitHub release workflow publishes these notes. A tag that has no section
in the changelog is an error — an empty release body is worse than a failed
release, because it looks intentional.

    python scripts/release_notes.py v0.1.0
    python scripts/release_notes.py v0.1.0 --check   # only verify
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CHANGELOG = REPO_ROOT / "CHANGELOG.md"
REPO_URL = "https://github.com/thewizard2030/laqta"


def section_for(tag: str, changelog: str) -> str | None:
    """Return the body of the changelog section for ``tag`` (or None).

    The heading is matched exactly — ``## [0.1.0]`` and ``## [v0.1.0]`` are
    both accepted — and the section ends at the next version heading.
    """
    wanted = tag[1:] if tag.startswith("v") else tag
    lines = changelog.splitlines()

    start = None
    for index, line in enumerate(lines):
        if line.startswith("## [") and line[4:].split("]")[0] in (wanted, tag):
            start = index + 1
            break
    if start is None:
        return None

    body: list[str] = []
    for line in lines[start:]:
        if line.startswith("## ["):
            break
        body.append(line)

    return "\n".join(body).strip()


def build_notes(tag: str, changelog: str) -> str | None:
    body = section_for(tag, changelog)
    if body is None:
        return None
    return (
        f"## Laqta {tag}\n\n"
        f"{body}\n\n"
        "---\n\n"
        f"Full changelog: [CHANGELOG.md]({REPO_URL}/blob/main/CHANGELOG.md)\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag", help="the release tag, e.g. v0.1.0")
    parser.add_argument(
        "--check",
        action="store_true",
        help="only verify that a section exists",
    )
    args = parser.parse_args()

    if not CHANGELOG.is_file():
        print(f"::error::{CHANGELOG} is missing.", file=sys.stderr)
        return 1

    changelog = CHANGELOG.read_text(encoding="utf-8")
    notes = build_notes(args.tag, changelog)

    if notes is None:
        print(
            f"::error::No CHANGELOG.md section found for {args.tag}. Add one before releasing.",
            file=sys.stderr,
        )
        return 1

    if args.check:
        print(f"CHANGELOG.md has a section for {args.tag}.")
        return 0

    print(notes, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
