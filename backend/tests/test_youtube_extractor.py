"""Unit tests for native YouTube transcript extraction and text cleaning.

Tests:
- URL regex parser for all standard, mobile, shorts, and embed URLs
- Noise tag and inline markup removal
- Rolling auto-caption deduplication
- WebVTT generation
- Innertube player response parsing (json3 and XML timedtext)
- Language selection priorities (Arabic -> English -> Default)
- Offline mocked end-to-end extraction and VTT file writing
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.transcription.transcript_cleaner import (
    CleanCue,
    clean_cue_text,
    cues_to_api_segments,
    cues_to_vtt,
    dedup_rolling_text_cues,
    format_ms_to_vtt_timestamp,
)
from app.services.transcription.youtube_extractor import (
    YouTubeTranscriptExtractor,
    extract_youtube_video_id,
)


class TestYouTubeUrlParser:
    def test_extract_video_id_standard(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert extract_youtube_video_id(url) == "dQw4w9WgXcQ"

    def test_extract_video_id_with_extra_params(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s&feature=shared"
        assert extract_youtube_video_id(url) == "dQw4w9WgXcQ"

    def test_extract_video_id_shortlink(self):
        url = "https://youtu.be/dQw4w9WgXcQ?t=1"
        assert extract_youtube_video_id(url) == "dQw4w9WgXcQ"

    def test_extract_video_id_shorts(self):
        url = "https://www.youtube.com/shorts/dQw4w9WgXcQ"
        assert extract_youtube_video_id(url) == "dQw4w9WgXcQ"

    def test_extract_video_id_embed(self):
        url = "https://www.youtube.com/embed/dQw4w9WgXcQ"
        assert extract_youtube_video_id(url) == "dQw4w9WgXcQ"

    def test_extract_video_id_invalid(self):
        assert extract_youtube_video_id("https://vimeo.com/12345678") is None
        assert extract_youtube_video_id("") is None
        assert extract_youtube_video_id("not-a-url") is None


class TestTranscriptCleaner:
    def test_clean_cue_text_noise_and_markup(self):
        raw = "<c>Hello</c> <00:00:01.000>[Music] world &amp; everyone! [موسيقى]"
        cleaned = clean_cue_text(raw)
        assert cleaned == "Hello world & everyone!"

    def test_clean_cue_text_applause_and_laughter(self):
        raw = "[Applause] (Laughter) [تصفيق] شكراً جزيلاً"
        cleaned = clean_cue_text(raw)
        assert cleaned == "شكراً جزيلاً"

    def test_format_vtt_timestamp(self):
        assert format_ms_to_vtt_timestamp(0) == "00:00:00.000"
        assert format_ms_to_vtt_timestamp(1500) == "00:00:01.500"
        assert format_ms_to_vtt_timestamp(3661234) == "01:01:01.234"

    def test_dedup_rolling_text_cues(self):
        # Auto-captions rolling sequence
        cues = [
            CleanCue(start_ms=1000, end_ms=3000, text="hello world"),
            CleanCue(start_ms=2500, end_ms=4500, text="hello world this is a test"),
            CleanCue(start_ms=4000, end_ms=6000, text="this is a test of deduplication"),
        ]
        deduped = dedup_rolling_text_cues(cues)
        assert len(deduped) == 3
        assert deduped[0].text == "hello world"
        assert deduped[1].text == "this is a test"
        assert deduped[2].text == "of deduplication"

    def test_cues_to_vtt(self):
        cues = [
            CleanCue(start_ms=1000, end_ms=3000, text="مرحبا بكم"),
            CleanCue(start_ms=3000, end_ms=5000, text="في هذا الفيديو"),
        ]
        vtt = cues_to_vtt(cues)
        assert "WEBVTT" in vtt
        assert "00:00:01.000 --> 00:00:03.000" in vtt
        assert "مرحبا بكم" in vtt
        assert "00:00:03.000 --> 00:00:05.000" in vtt
        assert "في هذا الفيديو" in vtt

    def test_cues_to_api_segments(self):
        cues = [
            CleanCue(start_ms=1000, end_ms=3000, text="Hello"),
        ]
        segs = cues_to_api_segments(cues)
        assert len(segs) == 1
        assert segs[0]["id"] == "u_0001"
        assert segs[0]["start"] == 1.0
        assert segs[0]["end"] == 3.0
        assert segs[0]["text"] == "Hello"


class TestYouTubeExtractorParsing:
    def test_parse_json3_timedtext(self):
        data = {
            "events": [
                {
                    "tStartMs": 1000,
                    "dDurationMs": 2500,
                    "segs": [{"utf8": "First "}, {"utf8": "sentence."}],
                },
                {
                    "tStartMs": 3500,
                    "dDurationMs": 2000,
                    "segs": [{"utf8": "Second sentence."}],
                },
            ]
        }
        cues = YouTubeTranscriptExtractor._parse_json3_timedtext(data)
        assert len(cues) == 2
        assert cues[0].text == "First sentence."
        assert cues[0].start_ms == 1000
        assert cues[0].end_ms == 3500
        assert cues[1].text == "Second sentence."
        assert cues[1].start_ms == 3500
        assert cues[1].end_ms == 5500

    def test_parse_xml_timedtext(self):
        xml_content = """<?xml version="1.0" encoding="utf-8" ?>
        <transcript>
            <text start="1.5" dur="2.0">Hello &amp; welcome</text>
            <text start="3.5" dur="1.8">to Laqta</text>
        </transcript>
        """
        cues = YouTubeTranscriptExtractor._parse_xml_timedtext(xml_content)
        assert len(cues) == 2
        assert cues[0].text == "Hello & welcome"
        assert cues[0].start_ms == 1500
        assert cues[0].end_ms == 3500
        assert cues[1].text == "to Laqta"

    def test_parse_vtt_timedtext(self):
        vtt_content = """WEBVTT
Kind: captions
Language: ar

00:00:01.000 --> 00:00:03.000
مرحبا بكم

00:00:03.500 --> 00:00:05.500
في هذا الفيديو
"""
        cues = YouTubeTranscriptExtractor._parse_vtt_timedtext(vtt_content)
        assert len(cues) == 2
        assert cues[0].text == "مرحبا بكم"
        assert cues[0].start_ms == 1000
        assert cues[0].end_ms == 3000
        assert cues[1].text == "في هذا الفيديو"
        assert cues[1].start_ms == 3500
        assert cues[1].end_ms == 5500

    @pytest.mark.asyncio
    async def test_fetch_and_parse_timedtext_normalizes_fmt_param(self):
        base_url_with_srv3 = "https://www.youtube.com/api/timedtext?v=test&lang=ar&fmt=srv3"
        requested_urls = []

        mock_client = AsyncMock()

        async def fake_get(url, **kwargs):
            requested_urls.append(url)
            resp = MagicMock()
            resp.status_code = 200
            resp.content = (
                b'{"events": [{"tStartMs": 1000, "dDurationMs": 2000, "segs": [{"utf8": "Test"}]}]}'
            )
            resp.json.return_value = {
                "events": [
                    {
                        "tStartMs": 1000,
                        "dDurationMs": 2000,
                        "segs": [{"utf8": "Test"}],
                    }
                ]
            }
            return resp

        mock_client.get = fake_get

        cues = await YouTubeTranscriptExtractor._fetch_and_parse_timedtext(
            mock_client, base_url_with_srv3
        )
        assert len(cues) == 1
        assert cues[0].text == "Test"
        # Verify fmt=srv3 was stripped and replaced with fmt=json3
        assert len(requested_urls) >= 1
        assert "fmt=srv3" not in requested_urls[0]
        assert "fmt=json3" in requested_urls[0]

    def test_select_best_track_priority(self):
        tracks = [
            {"languageCode": "fr", "baseUrl": "https://tt.youtube.com/fr"},
            {"languageCode": "en-US", "baseUrl": "https://tt.youtube.com/en"},
            {"languageCode": "ar", "baseUrl": "https://tt.youtube.com/ar"},
        ]
        # Default priority: Arabic -> English -> First
        chosen, lang = YouTubeTranscriptExtractor._select_best_track(tracks, ["ar", "en"])
        assert chosen["languageCode"] == "ar"
        assert lang == "ar"

        # Explicit English preference
        chosen_en, lang_en = YouTubeTranscriptExtractor._select_best_track(tracks, ["en", "ar"])
        assert chosen_en["languageCode"] == "en-US"
        assert lang_en == "en"


@pytest.mark.asyncio
class TestYouTubeExtractorExtraction:
    async def test_extract_and_save_vtt_mocked(self, tmp_path):
        fake_player_resp = {
            "captions": {
                "playerCaptionsTracklistRenderer": {
                    "captionTracks": [
                        {
                            "baseUrl": "https://www.youtube.com/api/timedtext?v=test1234567",
                            "languageCode": "ar",
                        }
                    ]
                }
            }
        }
        fake_json3_resp = {
            "events": [
                {
                    "tStartMs": 500,
                    "dDurationMs": 2000,
                    "segs": [{"utf8": "مرحبا بالعالم"}],
                }
            ]
        }

        # Mock httpx AsyncClient
        mock_client = AsyncMock()

        async def fake_post(url, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = fake_player_resp
            return resp

        async def fake_get(url, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            resp.content = b'{"events": []}'
            resp.json.return_value = fake_json3_resp
            return resp

        mock_client.post = fake_post
        mock_client.get = fake_get

        with patch("httpx.AsyncClient", return_value=mock_client):
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None

            result = await YouTubeTranscriptExtractor.extract_and_save_vtt(
                "https://www.youtube.com/watch?v=test1234567",
                tmp_path,
                preferred_langs=["ar", "en"],
            )

            assert result is not None
            vtt_path, lang, cues = result
            assert vtt_path.is_file()
            assert vtt_path.name == "test1234567.ar.vtt"
            assert lang == "ar"
            assert len(cues) == 1
            assert "مرحبا بالعالم" in vtt_path.read_text(encoding="utf-8")
