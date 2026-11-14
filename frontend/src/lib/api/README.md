# Api

## Overview
Type-safe HTTP and XHR client for the Laqta backend running on 127.0.0.1:8000, providing typed methods for all REST API endpoints, error abstraction with ApiClientError, upload progress tracking, and media stream URL generation.

## Interface
- client.ts: ApiClient - Typed API client class encapsulating all REST endpoints
- client.ts: api - Singleton instance of ApiClient
- client.ts: ApiClientError - Standardized error class with HTTP status code and server detail messages
- client.ts: ApiClientOptions, RequestOptions - Request configuration interfaces
- mediaUrl.ts: generateMediaFileUrl - Helper generating streaming URL for project media assets
- mediaUrl.ts: generateCandidateThumbnailUrl - Helper generating URL for extracted candidate frame thumbnails

## Invariants
- Connects to local host backend (127.0.0.1) by default
- XHR uploads enforce a 5-minute timeout for large video files and dispatch numeric percentage progress updates
- Standard JSON requests set AbortController timeouts (default 30 seconds)

## Side Effects
- Performs network fetch and XMLHttpRequest calls to /api/* endpoints

## Verification
- Run: `npm --prefix frontend test`
