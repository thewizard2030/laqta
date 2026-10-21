import React, { useState } from "react";
import { Film } from "lucide-react";
import { generateMediaFileUrl } from "../../lib/api/mediaUrl";

interface ProjectPosterProps {
  /** Media asset id. When missing, the honest placeholder is rendered. */
  mediaId?: string | null;
  /** Timestamp (in seconds) of the frame the browser should display. */
  frameAtSeconds?: number;
  /** Accessible description of the frame, e.g. the source file name. */
  label: string;
  /** Extra classes for the outer frame element. */
  className?: string;
}

/**
 * Real poster frame for a project.
 *
 * The frame is streamed by the local backend
 * (`GET /api/media/{mediaId}/file`, byte-range capable) and the browser is
 * asked to display the picture at `frameAtSeconds` through a media fragment.
 * Nothing is fabricated: when the media is missing or cannot be decoded the
 * component falls back to a neutral placeholder instead of a fake screenshot.
 */
export const ProjectPoster: React.FC<ProjectPosterProps> = ({
  mediaId,
  frameAtSeconds = 1,
  label,
  className = "",
}) => {
  const [hasFailed, setHasFailed] = useState(false);
  const mediaUrl = mediaId ? generateMediaFileUrl(mediaId) : null;
  const showFrame = Boolean(mediaUrl) && !hasFailed;

  return (
    <div
      className={`relative overflow-hidden bg-obsidian-950 ${className}`}
      role="img"
      aria-label={label}
      data-testid="project-poster"
    >
      {showFrame ? (
        <video
          src={`${mediaUrl}#t=${frameAtSeconds}`}
          preload="metadata"
          muted
          playsInline
          onError={() => setHasFailed(true)}
          className="absolute inset-0 h-full w-full object-cover"
          aria-hidden="true"
        />
      ) : (
        <div
          className="absolute inset-0 flex items-center justify-center bg-linear-to-br from-laqta-950/60 via-obsidian-900 to-slate-900"
          data-testid="project-poster-placeholder"
        >
          <Film className="h-6 w-6 text-slate-600" aria-hidden="true" />
        </div>
      )}
    </div>
  );
};

export default ProjectPoster;
