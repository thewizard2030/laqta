import { MediaAsset } from "./media";

export interface Project {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
  media_count: number;
  media_assets: MediaAsset[];
}

export interface CreateProjectPayload {
  name: string;
}

export interface UpdateProjectPayload {
  name: string;
}
