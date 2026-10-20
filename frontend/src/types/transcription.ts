/**
 * Types for speech recognition / transcription subsystem.
 */

export interface WordTiming {
  word: string;
  start: number;
  end: number;
  probability?: number | null;
}

export interface TranscriptSegment {
  id: string;
  start: number;
  end: number;
  text: string;
  words?: WordTiming[] | null;
  avg_logprob?: number | null;
  no_speech_prob?: number | null;
}

export interface TranscriptResponse {
  id: string;
  media_id: string;
  language: string;
  provider: string;
  model: string;
  status: string;
  text: string;
  segments: TranscriptSegment[];
  word_timestamps_available: boolean;
  timing_granularity: "word" | "segment";
  created_at: string;
}

export interface TranscriptionRequest {
  model_size?: string;
  language?: string;
  word_timestamps?: boolean;
  profile?: string;
  provider?: string;
  beam_size?: number;
  max_duration_sec?: number;
}
