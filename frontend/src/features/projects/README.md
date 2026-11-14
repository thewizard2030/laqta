# Projects

## Overview
Project workspace management, project creation modals, project listing with grid and table views, batch deletion, project renaming, video file uploading with binary header verification, and interactive project detail workbench.

## Interface
- CreateProjectModal.tsx: CreateProjectModal - Modal dialog for initializing new video editing projects
- ProjectDetailView.tsx: ProjectDetailView - Active project workbench coordinating media loading and transcription
- ProjectList.tsx: ProjectList - Grid/table listing of user projects with search and sorting
- MediaUploader.tsx: MediaUploader - Drag-and-drop file uploader with extension validation and progress bar
- YouTubeImportModal.tsx: YouTubeImportModal - Modal for importing media from YouTube with rights confirmation

## Invariants
- Media uploader validates file extensions (.mp4, .mov, .mkv, .webm) before initiating XHR uploads
- Project deletion and batch deletion require explicit confirmation via ConfirmDialog
- URL ingestion requires explicit rights confirmation checkbox before submit button is enabled

## Side Effects
- Makes CRUD API calls to /api/projects
- Uploads media with progress reporting to /api/projects/{projectId}/media
- Polls project job status at 1.5s intervals when active background jobs exist

## Verification
- Run: `npm --prefix frontend test`
