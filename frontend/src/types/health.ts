export interface HealthResponse {
  status: string;
  app: string;
  version: string;
  /** Background job worker: "running" | "stopped". A stopped worker means
   *  queued jobs would never run, so the studio shows a degraded state. */
  worker: string;
  timestamp: string;
}
