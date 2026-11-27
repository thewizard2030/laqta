"""Schema v2 (face-guided framing) and the manifest version guard.

v2 is additive on purpose: it adds ``crop_trajectory`` and ``framing_meta`` to
``ClipCandidate`` and bumps ``schema_version``. The risk this file guards
against is the opposite of a migration bug — a *newer* manifest being accepted
and silently stripped of the fields this build does not understand, which
would destroy framing data on a downgrade.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from qatta.core.config import QattaSettings
from qatta.core.pipeline import PipelineError, PipelineOrchestrator
from qatta.core.schema import (
    MAX_SCHEMA_VERSION,
    ClipCandidate,
    CropKeyframe,
    FramingMeta,
    QattaManifest,
    ShotFraming,
)


def _candidate(**overrides) -> dict:
    """A minimally valid candidate payload, so tests vary one field at a time."""
    payload = {
        "clip_id": "clip_001",
        "start_u_id": "U_0001",
        "end_u_id": "U_0002",
        "start_ms": 1000,
        "end_ms": 5000,
        "duration_sec": 4.0,
        "veto_gates": {
            "dangling_context": False,
            "clean_audio_boundaries": True,
            "crosstalk_ratio": 0.0,
            "passed_all": True,
        },
        "cps": {
            "total_score": 85.0,
            "archetype": "TACTICAL_INSIGHT",
            "standalone_clarity": 18.0,
            "hook_strength": 19.0,
            "story_payoff": 17.0,
            "value_originality": 16.0,
            "audio_dynamics": 15.0,
            "boundary_precision": 10.0,
        },
        "hook_remix": {"enabled": False},
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Additive compatibility: a v1 manifest must still load unchanged
# ---------------------------------------------------------------------------


def test_a_v1_manifest_still_validates_without_the_new_fields() -> None:
    """v1 is the shape on disk for every existing project; it cannot break."""
    manifest = QattaManifest.model_validate(
        {
            "schema_version": 1,
            "project_id": "legacy",
            "source_path": "/media/source.mp4",
            "duration_sec": 10.0,
            "candidates": [_candidate()],
        }
    )

    assert manifest.schema_version == 1
    candidate = manifest.candidates[0]
    # Absent in v1 -> defaults. "Not computed" must stay distinguishable from
    # "computed and chose centre", which is why framing_meta is None here.
    assert candidate.crop_trajectory == []
    assert candidate.framing_meta is None


def test_a_new_manifest_declares_the_current_version() -> None:
    manifest = QattaManifest(
        project_id="fresh",
        source_path="/media/source.mp4",
        duration_sec=10.0,
    )

    assert manifest.schema_version == MAX_SCHEMA_VERSION == 2


def test_the_written_manifest_round_trips_through_json(tmp_path: Path) -> None:
    """The trajectory must survive the atomic save/load the pipeline does."""
    manifest = QattaManifest(
        project_id="roundtrip",
        source_path="/media/source.mp4",
        duration_sec=10.0,
        candidates=[
            ClipCandidate.model_validate(
                _candidate(
                    crop_trajectory=[
                        {
                            "shot_index": 0,
                            "start_ms": 1000,
                            "end_ms": 5000,
                            "layout": "SINGLE_SPEAKER",
                            "keyframes": [
                                {"timestamp_ms": 1000, "center_x": 0.25},
                                {"timestamp_ms": 1200, "center_x": 0.5},
                            ],
                        }
                    ],
                    framing_meta={
                        "detector": "opencv_haar",
                        "enabled": True,
                        "frames_sampled": 20,
                        "frames_analysed": 19,
                        "frames_with_face": 12,
                        "elapsed_ms": 840,
                    },
                )
            )
        ],
    )

    path = tmp_path / "qatta_manifest.json"
    path.write_text(manifest.model_dump_json(), encoding="utf-8")
    reloaded = QattaManifest.model_validate(json.loads(path.read_text(encoding="utf-8")))

    shot = reloaded.candidates[0].crop_trajectory[0]
    assert shot.layout == "SINGLE_SPEAKER"
    assert [k.center_x for k in shot.keyframes] == [0.25, 0.5]
    assert reloaded.candidates[0].framing_meta.frames_with_face == 12


# ---------------------------------------------------------------------------
# ShotFraming validation: a bad trajectory must be refused, not persisted
# ---------------------------------------------------------------------------


def test_a_keyframe_outside_its_shot_is_refused() -> None:
    with pytest.raises(ValidationError, match="lies outside"):
        ShotFraming(
            shot_index=0,
            start_ms=1000,
            end_ms=2000,
            layout="SINGLE_SPEAKER",
            keyframes=[CropKeyframe(timestamp_ms=5000, center_x=0.5)],
        )


def test_unordered_keyframes_are_refused() -> None:
    with pytest.raises(ValidationError, match="not in time order"):
        ShotFraming(
            shot_index=0,
            start_ms=0,
            end_ms=2000,
            layout="SINGLE_SPEAKER",
            keyframes=[
                CropKeyframe(timestamp_ms=1500, center_x=0.5),
                CropKeyframe(timestamp_ms=500, center_x=0.5),
            ],
        )


def test_a_shot_that_ends_before_it_starts_is_refused() -> None:
    with pytest.raises(ValidationError, match="greater than start_ms"):
        ShotFraming(shot_index=0, start_ms=2000, end_ms=2000, layout="SINGLE_SPEAKER")


def test_an_out_of_range_centre_is_refused() -> None:
    with pytest.raises(ValidationError):
        CropKeyframe(timestamp_ms=0, center_x=1.5)


def test_an_unknown_layout_is_refused() -> None:
    """No split-screen or PiP is implemented, so it cannot be persisted."""
    with pytest.raises(ValidationError):
        ShotFraming(shot_index=0, start_ms=0, end_ms=1000, layout="DUAL_SPLIT_PIP")


def test_framing_meta_requires_a_real_detector_name() -> None:
    with pytest.raises(ValidationError):
        FramingMeta(
            detector="",
            enabled=True,
            frames_sampled=0,
            frames_analysed=0,
            frames_with_face=0,
            elapsed_ms=0,
        )


# ---------------------------------------------------------------------------
# The reader's upper bound: refuse a manifest from a newer build
# ---------------------------------------------------------------------------


def _orchestrator_with_manifest(tmp_path: Path, payload: dict) -> PipelineOrchestrator:
    (tmp_path / "qatta_manifest.json").write_text(json.dumps(payload), encoding="utf-8")
    return PipelineOrchestrator(project_id="guard", work_dir=tmp_path, settings=QattaSettings())


def test_a_newer_manifest_is_refused_rather_than_stripped(tmp_path: Path) -> None:
    """Accepting it would drop unknown fields on the next save."""
    with pytest.raises(PipelineError, match="newer than this Laqta build"):
        _orchestrator_with_manifest(
            tmp_path,
            {
                "schema_version": MAX_SCHEMA_VERSION + 1,
                "project_id": "guard",
                "source_path": "/media/source.mp4",
                "duration_sec": 10.0,
            },
        )


def test_the_current_version_is_accepted(tmp_path: Path) -> None:
    orchestrator = _orchestrator_with_manifest(
        tmp_path,
        {
            "schema_version": MAX_SCHEMA_VERSION,
            "project_id": "guard",
            "source_path": "/media/source.mp4",
            "duration_sec": 10.0,
        },
    )

    assert orchestrator.manifest.schema_version == MAX_SCHEMA_VERSION


def test_a_v1_manifest_is_still_readable_by_this_build(tmp_path: Path) -> None:
    orchestrator = _orchestrator_with_manifest(
        tmp_path,
        {
            "schema_version": 1,
            "project_id": "guard",
            "source_path": "/media/source.mp4",
            "duration_sec": 10.0,
        },
    )

    assert orchestrator.manifest.schema_version == 1
