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

# Every profile that ships an optional capability gets its own lock. A profile
# without a lock would mean the pinned install guarantees nothing for the code
# that depends on it.
PROFILES = {
    "default": ("backend/requirements-asr.txt", "backend/requirements-lock.txt"),
    "url": ("backend/requirements-url.txt", "backend/requirements-url-lock.txt"),
    "analysis": (
        "backend/requirements-analysis.txt",
        "backend/requirements-analysis-lock.txt",
    ),
    "api": ("backend/requirements.txt", None),
    "all": ("backend/requirements-all.txt", None),
}

# The composed profiles install several locks; naming them in the error makes
# the relationship explicit instead of looking like an omission.
COMPOSED_FROM = {
    "api": "the backend requirements plus the default lock",
    "all": "the default, url and analysis locks together",
}

_INCLUDE_RE = re.compile(r"^\s*-r\s+(?P<path>\S+)\s*$")
_COMMENT_RE = re.compile(r"^\s*#")
_PINNED_RE = re.compile(r"^([a-zA-Z0-9][a-zA-Z0-9._-]*)==([^\s\\;]+)")


def _normalise(name: str) -> str:
    """PEP 503 name normalisation (the form the lock uses)."""
    return re.sub(r"[-_.]+", "-", name).lower()


def verify_locks() -> list[str]:
    """Check that every locked profile is structurally coherent — offline.

    This is the gate CI can rely on. ``--check`` compares against a *fresh
    resolution*, so it turns red whenever upstream publishes a new version
    even though nothing in the repository changed; it is a maintainer tool,
    not a gate. What must never happen is a requirement being added to a
    profile while its lock silently keeps the old set, and that is what this
    function detects.
    """
    problems: list[str] = []

    for name, (requirements_rel, output_rel) in sorted(PROFILES.items()):
        if output_rel is None:
            continue
        requirements = REPO_ROOT / requirements_rel
        output = REPO_ROOT / output_rel
        if not output.is_file():
            problems.append(f"{output_rel}: missing — run `--profile {name}` to generate it")
            continue

        text = output.read_text(encoding="utf-8")
        if requirements_rel not in text:
            problems.append(
                f"{output_rel}: the header does not name {requirements_rel}, so it "
                "was probably generated from a different profile"
            )

        locked: dict[str, bool] = {}
        current: str | None = None
        for line in text.splitlines():
            pinned = _PINNED_RE.match(line)
            if pinned:
                current = _normalise(pinned.group(1))
                if current in locked:
                    problems.append(f"{output_rel}: {current} is pinned twice")
                locked[current] = False
            elif "--hash=" in line and current is not None:
                locked[current] = True

        for package, has_hash in sorted(locked.items()):
            if not has_hash:
                problems.append(
                    f"{output_rel}: {package} has no hash — "
                    "install with --require-hashes would not be reproducible"
                )

        for required in parse_requirement_names(requirements):
            key = _normalise(required)
            if key not in locked:
                problems.append(
                    f"{output_rel}: {key} is required by {requirements_rel} but is "
                    "not pinned — regenerate the lock"
                )

    # The composed profile must include the locked ones, or "install
    # everything" would quietly miss a capability.
    composed = (REPO_ROOT / "backend/requirements-all.txt").read_text(encoding="utf-8")
    for included in (
        "requirements-asr.txt",
        "requirements-url.txt",
        "requirements-analysis.txt",
    ):
        if included not in composed:
            problems.append(
                f"backend/requirements-all.txt: does not include {included}, so the "
                "'everything' profile is not everything"
            )

    return problems


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
        help=(
            "compare against a fresh resolution (needs the network; turns red "
            "when upstream publishes a new version — a maintainer tool, not a gate)"
        ),
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help=(
            "check every lock is structurally coherent with its profile "
            "(offline; this is the CI gate)"
        ),
    )
    args = parser.parse_args()

    if args.verify:
        problems = verify_locks()
        if problems:
            print("The dependency locks are not coherent:", file=sys.stderr)
            for problem in problems:
                print(f"  - {problem}", file=sys.stderr)
            return 1
        locked = sorted(name for name, (_, out) in PROFILES.items() if out)
        print(f"All {len(locked)} locks are coherent: {', '.join(locked)}.")
        return 0

    requirements_rel, output_rel = PROFILES[args.profile]
    if output_rel is None:
        composed = COMPOSED_FROM.get(args.profile, "")
        print(
            f"The '{args.profile}' profile is composed, not locked: install "
            f"{composed}. The locked profiles are: "
            f"{', '.join(sorted(name for name, (_, out) in PROFILES.items() if out))}.",
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
