# Captions

## Overview
Logical-order subtitle generation producing editable SRT and stylized ASS caption files with native Arabic BiDi controls and karaoke timing safety.

## Interface
- app.services.captions.service:generate_candidate_captions(captions_dir: Path, candidate_id: str, start_ms: int, end_ms: int, segments: list[TranscriptSegment], style: CaptionStyleSettings, formats: tuple[str, ...] = ('srt', 'ass')) -> GeneratedCaptions
- app.services.captions.service:overlapping_segments(segments: list[TranscriptSegment], start_ms: int, end_ms: int) -> list[TranscriptSegment]
- app.services.captions.service:arabic_font_warning(arabic_text_used: bool) -> str | None
- app.services.captions.service:GeneratedCaptions
- app.services.captions.generator:CaptionGenerationError
- app.services.captions.generator:build_cues(segments: list[TranscriptSegment], clip_start_ms: int, clip_end_ms: int, style: CaptionStyleSettings) -> CaptionBuildResult
- app.services.captions.generator:write_caption_files(output_dir: Path, candidate_id: str, result: CaptionBuildResult, style: CaptionStyleSettings, formats: tuple[str, ...] = ('srt', 'ass'), enable_karaoke: bool = False) -> dict[str, str]

## Invariants
- Text remains in logical order: text is never manually reversed or reshaped; BiDi shaping is delegated to HarfBuzz/FriBiDi in libass [generator.py]
- Arabic BiDi layout: ASS cues with Arabic text include '{\fe-1}' autodetect encoding and U+200F RIGHT-TO-LEFT MARK (RLM) on visual lines [generator.py]
- Karaoke gating: karaoke word-level highlighting requires reliable word timestamps (high confidence and no overlap) AND explicit style.karaoke opt-in [service.py:generate_candidate_captions, generator.py:build_cues]
- Rolling caption resolution: cue windows resolve overlapping speech via min(cue.end, next_cue.start) [generator.py]
- Untrusted transcript sanitation: braces '{}' and HTML formatting tags in transcripts are neutralized to prevent ASS style injection [generator.py]

## Side Effects
- Writes .srt and .ass caption files to the candidate's disk storage directory [generator.py:write_caption_files]
- Executes system fc-list binary via subprocess.run (3.0s timeout) to detect Arabic font availability [service.py:arabic_font_warning]

## Verification
- Run: `pytest backend/tests`
