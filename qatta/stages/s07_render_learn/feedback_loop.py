"""Stage s07_render_learn — YouTube Shorts Performance Feedback Loop.

Reads analytics exports (CSV or JSON) of published Shorts (stayed_to_watch_pct,
avg_percentage_viewed), calculates channel-normalized Z-scores across published clips,
and updates channel_profile.json with empirical archetype weights and hook_remix
preferences.
"""

from __future__ import annotations

import csv
import json
import logging
import math
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("qatta.s07_feedback")

DEFAULT_ARCHETYPE_WEIGHTS: dict[str, float] = {
    "STORY": 0.35,
    "TACTICAL_INSIGHT": 0.40,
    "HOT_TAKE": 0.25,
}


@dataclass
class PublishedClipRecord:
    """Analytics record for a published short clip."""

    clip_id: str
    archetype: str
    hook_remix_used: bool
    stayed_to_watch_pct: float  # Scale 0.0 - 100.0
    avg_percentage_viewed: float  # Scale 0.0 - 200.0+ (can exceed 100% on loops)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChannelProfile:
    """Channel performance profile and learned preferences."""

    archetype_weights: dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_ARCHETYPE_WEIGHTS)
    )
    hook_remix_preference: float = 0.50  # Probability or threshold [0.05, 0.95]
    total_samples: int = 0
    mean_stayed_to_watch: float = 0.0
    mean_avg_percentage_viewed: float = 0.0
    last_updated: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class ChannelProfileUpdater:
    """Manages channel profile loading, analytics parsing, and Z-score weight updates."""

    def __init__(self, learning_rate: float = 0.15) -> None:
        self.learning_rate = learning_rate

    @staticmethod
    def _parse_pct(val: Any) -> float:
        """Parse percentage string or numeric value into float in [0.0, 100.0+]."""
        if isinstance(val, (int, float)):
            f_val = float(val)
            # If value is in decimal fraction range (e.g. 0.85 -> 85%, 1.25 -> 125%)
            return f_val * 100.0 if 0.0 < f_val <= 3.0 else f_val

        s = str(val).strip()
        has_percent = "%" in s
        clean_s = s.rstrip("%").strip()
        try:
            f_val = float(clean_s)
            if not has_percent and 0.0 < f_val <= 3.0:
                return f_val * 100.0
            return f_val
        except ValueError:
            return 0.0

    @staticmethod
    def _parse_bool(val: Any) -> bool:
        """Parse boolean flag from various representations."""
        if isinstance(val, bool):
            return val
        s = str(val).strip().lower()
        return s in ("true", "1", "yes", "y", "t")

    def load_analytics_csv(self, file_path: Path | str) -> list[PublishedClipRecord]:
        """Load published clip performance records from a CSV file."""
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"Analytics CSV file not found: {path}")

        records: list[PublishedClipRecord] = []
        with open(path, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Find matching keys case-insensitively
                lower_row = {k.strip().lower(): v for k, v in row.items() if k}

                clip_id = (
                    lower_row.get("clip_id")
                    or lower_row.get("id")
                    or lower_row.get("video_id")
                    or f"clip_{len(records) + 1}"
                )
                archetype = (
                    (lower_row.get("archetype") or lower_row.get("clip_archetype") or "STORY")
                    .strip()
                    .upper()
                )

                if archetype not in DEFAULT_ARCHETYPE_WEIGHTS:
                    archetype = "STORY"

                hook_remix_val = (
                    lower_row.get("hook_remix_used")
                    or lower_row.get("hook_remix")
                    or lower_row.get("is_remix")
                    or False
                )
                hook_remix_used = self._parse_bool(hook_remix_val)

                stayed_val = (
                    lower_row.get("stayed_to_watch_pct")
                    or lower_row.get("stayed_pct")
                    or lower_row.get("viewed_vs_swiped_away")
                    or 0.0
                )
                stayed_to_watch_pct = self._parse_pct(stayed_val)

                apv_val = (
                    lower_row.get("avg_percentage_viewed")
                    or lower_row.get("apv")
                    or lower_row.get("average_percentage_viewed")
                    or 0.0
                )
                avg_percentage_viewed = self._parse_pct(apv_val)

                records.append(
                    PublishedClipRecord(
                        clip_id=clip_id,
                        archetype=archetype,
                        hook_remix_used=hook_remix_used,
                        stayed_to_watch_pct=stayed_to_watch_pct,
                        avg_percentage_viewed=avg_percentage_viewed,
                    )
                )

        return records

    def load_analytics_json(self, file_path: Path | str) -> list[PublishedClipRecord]:
        """Load published clip performance records from a JSON file."""
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"Analytics JSON file not found: {path}")

        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, list):
            data = data.get("clips", [])

        records: list[PublishedClipRecord] = []
        for item in data:
            clip_id = str(item.get("clip_id") or item.get("id") or f"clip_{len(records) + 1}")
            archetype = str(item.get("archetype") or "STORY").strip().upper()
            if archetype not in DEFAULT_ARCHETYPE_WEIGHTS:
                archetype = "STORY"

            hook_remix_used = self._parse_bool(
                item.get("hook_remix_used", item.get("hook_remix", False))
            )
            stayed_to_watch_pct = self._parse_pct(
                item.get("stayed_to_watch_pct", item.get("stayed_pct", 0.0))
            )
            avg_percentage_viewed = self._parse_pct(
                item.get("avg_percentage_viewed", item.get("apv", 0.0))
            )

            records.append(
                PublishedClipRecord(
                    clip_id=clip_id,
                    archetype=archetype,
                    hook_remix_used=hook_remix_used,
                    stayed_to_watch_pct=stayed_to_watch_pct,
                    avg_percentage_viewed=avg_percentage_viewed,
                )
            )

        return records

    @staticmethod
    def compute_composite_scores(records: list[PublishedClipRecord]) -> list[float]:
        """Compute composite retention-view score per record: 0.5*stayed + 0.5*APV."""
        return [0.5 * r.stayed_to_watch_pct + 0.5 * r.avg_percentage_viewed for r in records]

    def compute_normalized_z_scores(
        self, records: list[PublishedClipRecord]
    ) -> list[tuple[PublishedClipRecord, float]]:
        """Compute channel-normalized Z-scores for each record."""
        if not records:
            return []

        scores = self.compute_composite_scores(records)
        n = len(scores)
        mean_score = sum(scores) / n

        variance = sum((s - mean_score) ** 2 for s in scores) / n
        std_dev = math.sqrt(variance)

        results: list[tuple[PublishedClipRecord, float]] = []
        for r, score in zip(records, scores, strict=True):
            if std_dev > 1e-6:
                z = (score - mean_score) / std_dev
            else:
                z = 0.0
            results.append((r, z))

        return results

    def update_profile(
        self,
        records: list[PublishedClipRecord],
        base_profile: ChannelProfile | None = None,
    ) -> ChannelProfile:
        """Update archetype weights and hook remix preferences from analytics records."""
        profile = base_profile or ChannelProfile()
        if not records:
            return profile

        z_scored = self.compute_normalized_z_scores(records)

        # 1. Compute mean Z-scores per archetype
        archetype_z_lists: dict[str, list[float]] = {arch: [] for arch in DEFAULT_ARCHETYPE_WEIGHTS}
        for record, z in z_scored:
            if record.archetype in archetype_z_lists:
                archetype_z_lists[record.archetype].append(z)

        # Current weights
        current_weights = dict(profile.archetype_weights)
        updated_weights: dict[str, float] = {}

        for arch, z_list in archetype_z_lists.items():
            current_w = current_weights.get(arch, DEFAULT_ARCHETYPE_WEIGHTS[arch])
            if z_list:
                mean_z = sum(z_list) / len(z_list)
                # Multiplicative update bounded away from zero
                updated_w = max(0.05, current_w * (1.0 + self.learning_rate * mean_z))
            else:
                updated_w = current_w
            updated_weights[arch] = updated_w

        # Renormalize archetype weights to sum to 1.0
        total_w = sum(updated_weights.values())
        if total_w > 0:
            final_weights = {k: round(v / total_w, 4) for k, v in updated_weights.items()}
        else:
            final_weights = dict(DEFAULT_ARCHETYPE_WEIGHTS)

        # 2. Compute Hook Remix preference
        remix_z: list[float] = [z for r, z in z_scored if r.hook_remix_used]
        standard_z: list[float] = [z for r, z in z_scored if not r.hook_remix_used]

        current_remix_pref = profile.hook_remix_preference
        if remix_z and standard_z:
            mean_remix_z = sum(remix_z) / len(remix_z)
            mean_standard_z = sum(standard_z) / len(standard_z)
            diff = mean_remix_z - mean_standard_z
            new_remix_pref = current_remix_pref + (self.learning_rate * 0.5 * diff)
            new_remix_pref = max(0.05, min(0.95, round(new_remix_pref, 4)))
        else:
            new_remix_pref = current_remix_pref

        # 3. Overall stats
        mean_stayed = sum(r.stayed_to_watch_pct for r in records) / len(records)
        mean_apv = sum(r.avg_percentage_viewed for r in records) / len(records)

        return ChannelProfile(
            archetype_weights=final_weights,
            hook_remix_preference=new_remix_pref,
            total_samples=profile.total_samples + len(records),
            mean_stayed_to_watch=round(mean_stayed, 2),
            mean_avg_percentage_viewed=round(mean_apv, 2),
            last_updated=datetime.now(UTC).isoformat(),
        )

    def load_profile(self, profile_path: Path | str) -> ChannelProfile:
        """Load ChannelProfile from a JSON file."""
        path = Path(profile_path)
        if not path.is_file():
            return ChannelProfile()

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return ChannelProfile(
                archetype_weights=data.get("archetype_weights", dict(DEFAULT_ARCHETYPE_WEIGHTS)),
                hook_remix_preference=float(data.get("hook_remix_preference", 0.50)),
                total_samples=int(data.get("total_samples", 0)),
                mean_stayed_to_watch=float(data.get("mean_stayed_to_watch", 0.0)),
                mean_avg_percentage_viewed=float(data.get("mean_avg_percentage_viewed", 0.0)),
                last_updated=str(data.get("last_updated", "")),
            )
        except Exception as e:
            logger.warning("Could not read channel profile at %s: %s", path, e)
            return ChannelProfile()

    def save_profile(self, profile: ChannelProfile, profile_path: Path | str) -> Path:
        """Atomically persist ChannelProfile to a JSON file."""
        path = Path(profile_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(f".tmp-{datetime.now().timestamp()}")

        content = json.dumps(asdict(profile), indent=2)
        tmp_path.write_text(content, encoding="utf-8")
        tmp_path.replace(path)
        return path
