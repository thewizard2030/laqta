#!/usr/bin/env python3
"""Assert that every manifest in the repository declares the same version.

The single source of truth is ``qatta/__init__.py`` (``__version__``). The
backend imports it, the frontend mirrors it in ``package.json`` and the two
Python manifests repeat it. This script is the guard that keeps them in sync
and is executed by CI.

Usage::

    python scripts/check_version.py          # verify (exit 1 on mismatch)
    python scripts/check_version.py --show   # print the table, always exit 0
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_module(path: Path, module_name: str):
    """Import a module from an explicit file path without touching sys.path."""
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise SystemExit(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _toml_version(path: Path) -> str:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    version = data.get("project", {}).get("version")
    if not version:
        raise SystemExit(f"Could not find [project].version in {path}")
    return str(version)


def _npm_version(path: Path) -> str:
    data = json.loads(path.read_text(encoding="utf-8"))
    version = data.get("version")
    if not version:
        raise SystemExit(f"Could not find version in {path}")
    return str(version)


def _backend_declared_version() -> str:
    """The backend re-exports the core version — read the literal it imports.

    The backend module is imported for real (it only touches ``sys.path`` and
    the core package), so the check proves the *runtime* value, not a string.
    """
    backend_init = REPO_ROOT / "backend" / "app" / "__init__.py"
    source = backend_init.read_text(encoding="utf-8")
    if not re.search(r"from\s+qatta\s+import\s+__version__", source):
        raise SystemExit(f"{backend_init} must import __version__ from the qatta core package")
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    module = _load_module(backend_init, "laqta_backend_app_version_probe")
    return str(module.__version__)


def collect() -> list[tuple[str, str]]:
    """Return ``(label, version)`` for every version declaration."""
    core = _load_module(REPO_ROOT / "qatta" / "__init__.py", "laqta_core_version_probe")
    return [
        ("qatta/__init__.py (source of truth)", str(core.__version__)),
        ("backend/app/__init__.py", _backend_declared_version()),
        ("pyproject.toml", _toml_version(REPO_ROOT / "pyproject.toml")),
        ("backend/pyproject.toml", _toml_version(REPO_ROOT / "backend" / "pyproject.toml")),
        ("frontend/package.json", _npm_version(REPO_ROOT / "frontend" / "package.json")),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--show",
        action="store_true",
        help="print the versions without failing on a mismatch",
    )
    args = parser.parse_args()

    entries = collect()
    source = entries[0][1]

    width = max(len(label) for label, _ in entries)
    print(f"{'manifest'.ljust(width)}  version")
    for label, version in entries:
        marker = " " if version == source else "!" if not args.show else " "
        print(f"{label.ljust(width)}  {version}{marker}")

    mismatched = [(label, version) for label, version in entries if version != source]
    if mismatched:
        print(
            "\nVersion mismatch. The source of truth is "
            f"`qatta/__init__.py` ({source}). Update: "
            + ", ".join(label for label, _ in mismatched),
            file=sys.stderr,
        )
        if not args.show:
            return 1
    else:
        print(f"\nAll manifests agree on {source}.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
