# Validation

## Overview
Client-side boundary validation for candidate clip start/end editing, ensuring cut spans remain within source media bounds and between 30 and 55 seconds.

## Interface
- boundaries.ts: validateBoundaryEdit - Validates proposed start/end edits against duration constraints
- boundaries.ts: BoundaryBounds, BoundaryValidationResult - Type contracts for validation results
- boundaries.ts: DEFAULT_MIN_DURATION_MS, DEFAULT_MAX_DURATION_MS - Default 30s and 55s boundaries

## Invariants
- Rejects null, NaN, negative start times, end times exceeding media duration, end times less than start time, and durations outside configured min/max range

## Side Effects
- None

## Verification
- Run: `npm --prefix frontend test`
