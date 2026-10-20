export interface MediaAsset {
  id: string;
  project_id: string;
  original_name: string;
  size_bytes: number;
  duration_ms: number;
  width: number;
  height: number;
  video_codec: string;
  audio_codec: string;
  status: string;
  created_at: string;
}
