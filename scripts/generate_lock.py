#!/usr/bin/env python3
"""Generate (or verify) the pinned dependency lock for a Laqta profile.

The committed lock is resolved for the **minimum supported Python** (3.11) so
that a single file installs on every supported interpreter (3.11 / 3.12).
Resolution is done by `uv pip compile` (fast, cross-version, hash-capable)
when it is available; otherwise the script falls back to resolving the
closure against the interpreter it runs in, which pins that environment only.

    python scripts/generate_lock.py                     # write the lock
    python scripts/generate_lock.py --check             # verify it is current
    python scripts/generate_lock.py --profile all       # lock the "all" profile
    python scripts/generate_lock.py --no-hashes         # skip hashes

Install the lock with:

    pip install --require-hashes -r backend/requirements-lock.txt
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from importlib import metadata
from pathlib import Path

try:
    from packaging.requirements import Requirement
except ImportError:  # pragma: no cover - packaging ships with pip
    print(
        "This script needs the 'packaging' library (shipped with pip/setuptools).",
        file=sys.stderr,
    )
    raise SystemExit(2) from None

REPO_ROOT = Path(__file__).resolve().parent.parent
MIN_PYTHON = "3.11"

PROFILES = {
    "default": ("backend/requirements-asr.txt", "backend/requirements-lock.txt"),
    "api": ("backend/requirements.txt", None),
    "all": ("backend/requirements-all.txt", None),
}

_INCLUDE_RE = re.compile(r"^\s*-r\s+(?P<path>\S+)\s*$")
_COMMENT_RE = re.compile(r"^\s*#")


def parse_requirement_names(path: Path) -> list[str]:
    """Collect the distribution names required by a requirements file."""
    names: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or _COMMENT_RE.match(raw):
            continue
        include = _INCLUDE_RE.match(line)
        if include:
            names.extend(parse_requirement_names(path.parent / include.group("path")))
            continue
        if line.startswith("-"):  # other pip options (--index-url, ...)
            continue
        try:
            requirement = Requirement(line)
        except Exception:  # noqa: BLE001 - a malformed line must not break the run
            print(f"  ! skipping unparsable line: {line}", file=sys.stderr)
            continue
        names.append(requirement.name)
    return names


def resolve_with_uv(requirements: Path, python_version: str, hashes: bool) -> str | None:
    """Resolve with `uv pip compile`; return None when uv is unavailable."""
    if shutil.which("uv") is None:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "lock.txt"
        command = [
            "uv",
            "pip",
            "compile",
            "--quiet",
            "--python-version",
            python_version,
            "--no-emit-index-url",
            "--no-emit-find-links",
        ]
        if hashes:
            command.append("--generate-hashes")
        command += [str(requirements), "--output-file", str(out)]
        result = subprocess.run(command, capture_output=True, text=True, cwd=REPO_ROOT)
        if result.returncode != 0:
            print(result.stderr.strip(), file=sys.stderr)
            return None
        return out.read_text(encoding="utf-8")


def resolve_locally(requirements: Path) -> tuple[str | None, list[str]]:
    """Resolve the closure against the current interpreter (no network)."""
    names = parse_requirement_names(requirements)
    resolved: dict[str, str] = {}
    queue = list(names)
    missing: list[str] = []

    while queue:
        name = queue.pop()
        key = name.lower().replace("_", "-")
        if key in resolved:
            continue
        try:
            distribution = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            missing.append(name)
            continue
        resolved[key] = distribution.version
        for requirement_text in distribution.requires or []:
            try:
                requirement = Requirement(requirement_text)
            except Exception:  # noqa: BLE001 - ignore malformed metadata
                continue
            if requirement.marker is not None and not requirement.marker.evaluate():
                continue
            queue.append(requirement.name)

    if missing:
        return None, missing

    lines = [
        f"# Resolved against the local interpreter (Python {sys.version.split()[0]}).",
        "# Regenerate with `uv` for a portable, cross-version lock.",
        "",
    ]
    lines.extend(f"{name}=={version}" for name, version in sorted(resolved.items()))
    lines.append("")
    return "\n".join(lines), []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        choices=sorted(PROFILES),
        default="default",
        help="which requirements profile to lock (default: default)",
    )
    parser.add_argument(
        "--python-version",
        default=MIN_PYTHON,
        help=f"python version to resolve for (default: {MIN_PYTHON})",
    )
    parser.add_argument(
        "--no-hashes",
        action="store_true",
        help="omit hashes (smaller lock, weaker supply-chain guarantee)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the lock file is up to date instead of writing it",
    )
    args = parser.parse_args()

    requirements_rel, output_rel = PROFILES[args.profile]
    if output_rel is None:
        print(
            f"The '{args.profile}' profile is not locked — only the default "
            "profile ships a lock file.",
            file=sys.stderr,
        )
        return 2

    requirements = REPO_ROOT / requirements_rel
    output = REPO_ROOT / output_rel

    print(f"Resolving {requirements_rel} for Python {args.python_version} …")
    content = resolve_with_uv(requirements, args.python_version, not args.no_hashes)

    if content is None:
        print("uv is not available — resolving against the local interpreter.")
        content, missing = resolve_locally(requirements)
        if content is None:
            print("These packages are not installed locally:", file=sys.stderr)
            for name in sorted(set(missing)):
                print(f"  - {name}", file=sys.stderr)
            return 1

    header = (
        "# Laqta backend — pinned dependency lock.\n"
        "#\n"
        f"# Generated by scripts/generate_lock.py from {requirements_rel}\n"
        f"# resolved for Python {args.python_version}.\n"
        "# Regenerate after changing a profile:\n"
        "#\n"
        "#     python scripts/generate_lock.py\n"
        "#\n"
    )
    body = content.split("\n", 1)[1] if content.startswith("#") else content
    # Drop the resolver's own command echo (it contains a temporary path).
    body = "\n".join(
        line for line in body.splitlines() if not line.startswith("#    uv pip compile")
    )
    final = header + body.lstrip("\n")

    if args.check:
        current = output.read_text(encoding="utf-8") if output.exists() else ""
        if current.strip() == final.strip():
            print(f"{output_rel} is up to date.")
            return 0
        print(
            f"{output_rel} is OUT OF DATE — run scripts/generate_lock.py",
            file=sys.stderr,
        )
        return 1

    output.write_text(final, encoding="utf-8")
    packages = len([line for line in final.splitlines() if line and not line.startswith("#")])
    print(f"Wrote {output_rel} ({packages} pinned lines).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
