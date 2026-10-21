#!/usr/bin/env python3
"""Compare the measured coverage against the recorded baseline.

A patch release must not silently reduce coverage, so CI fails when the
number drops below the baseline. The baseline is deliberately the *current*
number, not a target — raising it is a separate, explicit change.

    python scripts/check_coverage.py --backend cov.json --frontend cov-summary.json
    python scripts/check_coverage.py --show     # print the numbers only
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINE_FILE = REPO_ROOT / "config" / "coverage-baseline.json"


def read_backend(path: Path) -> float:
    data = json.loads(path.read_text(encoding="utf-8"))
    return round(float(data["totals"]["percent_covered"]), 2)


def read_frontend(path: Path) -> dict[str, float]:
    data = json.loads(path.read_text(encoding="utf-8"))
    total = data["total"]
    return {
        "lines": round(float(total["lines"]["pct"]), 2),
        "functions": round(float(total["functions"]["pct"]), 2),
        "branches": round(float(total["branches"]["pct"]), 2),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", type=Path, help="backend coverage JSON")
    parser.add_argument("--frontend", type=Path, help="frontend coverage summary JSON")
    parser.add_argument("--show", action="store_true", help="print the numbers without failing")
    args = parser.parse_args()

    baseline = json.loads(BASELINE_FILE.read_text(encoding="utf-8"))
    measured: dict[str, float] = {}

    if args.backend and args.backend.exists():
        measured["backend"] = read_backend(args.backend)
    if args.frontend and args.frontend.exists():
        measured.update(read_frontend(args.frontend))

    if not measured:
        print("No coverage report was supplied — nothing to check.")
        return 0

    print("Coverage")
    print("-" * 46)
    regressions: list[str] = []
    for key, value in measured.items():
        limit = float(baseline.get(key, 0))
        status = "ok" if value >= limit else "REGRESSION"
        print(f"  {key:12} {value:6.2f}%  (baseline {limit:.2f}%)  {status}")
        if value < limit:
            regressions.append(f"{key}: {value:.2f}% < baseline {limit:.2f}%")

    if regressions:
        print()
        for line in regressions:
            print(f"::error::Coverage regression — {line}", file=sys.stderr)
        if not args.show:
            return 1
    else:
        print("\nNo coverage regression.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
