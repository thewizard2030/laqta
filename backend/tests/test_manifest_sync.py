"""Tests for the manifest -> SQLite bridge.

The bridge is what keeps the web API and the studio UI in step with the
manifest pipeline: it projects the utterances of a manifest into transcript
rows and refreshes the media metadata. It is the seam between the two halves
of Laqta, so it gets its own tests.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.db.repository import ProjectRepository
from app.services.bridge.manifest_sync import sync_manifest_to_db
from qatta.core.schema import AtomicUtterance, QattaManifest, WordToken


def _manifest(project_id: str, utterances: list[AtomicUtterance]) -> QattaManifest:
    return QattaManifest(
        project_id=project_id,
        source_path="/tmp/source.mp4",
        duration_sec=12.0,
        video_width=1280,
        video_height=720,
        language_profile="ar-EG-mixed",
        atomic_utterances=utterances,
    )


def _utterance(u_id: str, text: str, with_words: bool = True) -> AtomicUtterance:
    words = (
        [
            WordToken(
                word=text.split()[0],
                start_ms=0,
                end_ms=500,
                confidence=0.9,
                is_latin=False,
            )
        ]
        if with_words
        else []
    )
    return AtomicUtterance(
        u_id=u_id,
        start_ms=0,
        end_ms=1000,
        text=text,
        words=words,
    )


def test_sync_without_media_is_a_no_op(tmp_path: Path) -> None:
    """A project without media must not raise — the bridge logs and returns."""
    repo = ProjectRepository(db_path=tmp_path / "qatta.db")
    project = repo.create_project("No Media")

    sync_manifest_to_db(
        _manifest(project.id, []),
        project.id,
        repo=repo,
        candidates_repo=None,
        renders_repo=None,
    )

    assert repo.list_project_media(project.id) == []


def test_sync_writes_the_transcript_and_updates_the_media_metadata(tmp_path: Path) -> None:
    repo = ProjectRepository(db_path=tmp_path / "qatta.db")
    project = repo.create_project("With Media")
    media = repo.create_media_asset(
        project_id=project.id,
        safe_path="/tmp/media/source.mp4",
        original_name="source.mp4",
        size_bytes=1024,
        duration_ms=1,
        width=640,
        height=360,
        video_codec="h264",
        audio_codec="aac",
    )

    manifest = _manifest(
        project.id,
        [
            _utterance("U_0001", "مرحبا بكم"),
            _utterance("U_0002", "هذا اختبار"),
        ],
    )

    sync_manifest_to_db(
        manifest,
        project.id,
        repo=repo,
        candidates_repo=None,
        renders_repo=None,
    )

    # The media metadata is refreshed from the manifest probe.
    refreshed = repo.list_project_media(project.id)[0]
    assert refreshed.id == media.id
    assert refreshed.duration_ms == 12_000
    assert refreshed.width == 1280
    assert refreshed.height == 720

    # The utterances became a transcript row.
    transcripts = repo.list_media_transcripts(media.id)
    assert len(transcripts) == 1
    transcript = transcripts[0]
    assert transcript.text == "مرحبا بكم هذا اختبار"
    assert transcript.provider == "qatta_pipeline"
    assert transcript.model == "local_turbo"
    assert transcript.status == "completed"
    # Word timings are present, so the granularity is "word".
    assert transcript.word_timestamps_available is True
    assert transcript.timing_granularity == "word"
    segments = json.loads(transcript.segments_json or "[]")
    assert len(segments) == 2
    assert segments[0]["text"] == "مرحبا بكم"
    assert segments[0]["words"][0]["word"] == "مرحبا"


def test_sync_updates_an_existing_transcript_instead_of_duplicating(tmp_path: Path) -> None:
    repo = ProjectRepository(db_path=tmp_path / "qatta.db")
    project = repo.create_project("Second Sync")
    media = repo.create_media_asset(
        project_id=project.id,
        safe_path="/tmp/media/source.mp4",
        original_name="source.mp4",
        size_bytes=1024,
        duration_ms=1,
        width=640,
        height=360,
        video_codec="h264",
        audio_codec="aac",
    )

    first = _manifest(project.id, [_utterance("U_0001", "الأول")])
    sync_manifest_to_db(first, project.id, repo=repo, candidates_repo=None, renders_repo=None)

    second = _manifest(
        project.id,
        [_utterance("U_0001", "الأول"), _utterance("U_0002", "الثاني")],
    )
    sync_manifest_to_db(second, project.id, repo=repo, candidates_repo=None, renders_repo=None)

    transcripts = repo.list_media_transcripts(media.id)
    assert len(transcripts) == 1, "the transcript must be updated, not duplicated"
    assert transcripts[0].text == "الأول الثاني"


def test_utterances_without_words_report_utterance_granularity(tmp_path: Path) -> None:
    repo = ProjectRepository(db_path=tmp_path / "qatta.db")
    project = repo.create_project("No Words")
    media = repo.create_media_asset(
        project_id=project.id,
        safe_path="/tmp/media/source.mp4",
        original_name="source.mp4",
        size_bytes=1024,
        duration_ms=1,
        width=640,
        height=360,
        video_codec="h264",
        audio_codec="aac",
    )

    manifest = _manifest(
        project.id,
        [_utterance("U_0001", "بدون كلمات", with_words=False)],
    )
    sync_manifest_to_db(manifest, project.id, repo=repo, candidates_repo=None, renders_repo=None)

    transcript = repo.list_media_transcripts(media.id)[0]
    assert transcript.word_timestamps_available is False
    assert transcript.timing_granularity == "utterance"
