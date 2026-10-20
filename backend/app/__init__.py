import sys
from pathlib import Path

# Ensure project root is in sys.path so 'qatta' can be imported when running from backend directory
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Single source of truth for the version: the `qatta` core package.
# `scripts/check_version.py` asserts that every other manifest agrees.
from qatta import __version__  # noqa: E402

__all__ = ["__version__"]
