# Bridge

## Overview
Bridge service projecting QattaManifest pipeline state into SQLite database records for backward compatibility with REST routes and frontend UI.

## Interface
- app.services.bridge.manifest_sync:sync_manifest_to_db(manifest: QattaManifest, project_id: str, repo: ProjectRepository | None = None, candidates_repo: CandidateRepository | None = None, renders_repo: RenderRepository | None = None) -> None

## Invariants
- Full backward compatibility: ensures atomic utterances, candidates, and renders in QattaManifest project cleanly to media_assets, transcripts, candidates, and rendered_clips tables [manifest_sync.py:sync_manifest_to_db]
- Preserves database integrity: updates existing transcript and candidate records when IDs match or inserts new ones without data corruption [manifest_sync.py:sync_manifest_to_db]

## Side Effects
- Executes SQL UPDATE and INSERT statements on SQLite database [manifest_sync.py:sync_manifest_to_db]

## Verification
- Run: `pytest backend/tests`
