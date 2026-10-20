"""Two-pass transcription performance profiles (docs/PERFORMANCE.md).

Pass A (full-video analysis) runs with segment-level timestamps and no
word-level alignment. This is the single biggest CPU win on the reference
8 GB machine: Whisper word timing requires cross-attention alignment over
every predicted token for the whole video, roughly doubling decode time,
while captions only ever need one selected clip's words (Pass B re-derives
those per clip; see app/services/transcription/alignment.py).

Profiles:
- fast      (default): base, int8, beam 1, no full-video word alignment.
- balanced: small, int8, beam 1, no full-video word alignment. Better Arabic
  quality, roughly 2x slower than ``fast`` — still safe on 8 GB.
- accurate: configurable higher-accuracy model with word timestamps on the
  full video; carries an explicit "takes longer" warning surfaced to users.

Every value is independently configurable via settings/env (QATTA_*) and an
explicit request field always wins over the profile default.
"""

from dataclasses import dataclass, field

from app.core.config import Settings

PROFILE_KEYWORDS_WARNING = (
    "The 'accurate' profile transcribes the full video with word-level "
    "alignment enabled; on CPU this typically takes several times longer "
    "than the other profiles."
)


@dataclass(frozen=True)
class TranscriptionProfile:
    """Resolved configuration for one transcription pass."""

    name: str
    model_size: str
    compute_type: str
    beam_size: int
    word_timestamps: bool
    vad_filter: bool
    description: str
    accuracy_warning: str | None = None

    def to_dict(self) -> dict:
        """Serializable form persisted in job config for auditability."""
        return {
            "profile": self.name,
            "model_size": self.model_size,
            "compute_type": self.compute_type,
            "beam_size": self.beam_size,
            "word_timestamps": self.word_timestamps,
            "vad_filter": self.vad_filter,
            "description": self.description,
            "accuracy_warning": self.accuracy_warning,
        }


def _profiles(settings: Settings) -> dict[str, TranscriptionProfile]:
    """Build profile table from live settings (env/test override friendly)."""
    return {
        "fast": TranscriptionProfile(
            name="fast",
            model_size=settings.FAST_WHISPER_MODEL,
            compute_type=settings.DEFAULT_WHISPER_COMPUTE_TYPE,
            beam_size=1,
            word_timestamps=False,
            vad_filter=settings.WHISPER_VAD_FILTER,
            description=(
                "Draft transcription: base int8 CPU model, beam size 1, "
                "VAD filtering, segment-level timestamps (no full-video "
                "word alignment)."
            ),
        ),
        "balanced": TranscriptionProfile(
            name="balanced",
            model_size=settings.BALANCED_WHISPER_MODEL,
            compute_type=settings.DEFAULT_WHISPER_COMPUTE_TYPE,
            beam_size=1,
            word_timestamps=False,
            vad_filter=settings.WHISPER_VAD_FILTER,
            description=(
                "Higher quality draft on CPU: small int8 model with segment "
                "timestamps; word timing is re-derived per selected clip "
                "only."
            ),
        ),
        "accurate": TranscriptionProfile(
            name="accurate",
            model_size=settings.ACCURATE_WHISPER_MODEL,
            compute_type=settings.DEFAULT_WHISPER_COMPUTE_TYPE,
            beam_size=1,
            word_timestamps=True,
            vad_filter=settings.WHISPER_VAD_FILTER,
            description=(
                "Highest accuracy pass with word-level alignment over the "
                "full video. Significantly slower on CPU; intended for "
                "final-quality transcripts."
            ),
            accuracy_warning=PROFILE_KEYWORDS_WARNING,
        ),
    }


def get_profile_names(settings: Settings | None = None) -> list[str]:
    return list(_profiles(settings or Settings()).keys())


@dataclass(frozen=True)
class ResolvedTranscription:
    """The effective transcription configuration plus any surfaced warnings."""

    config: TranscriptionProfile
    overrides_applied: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        data = self.config.to_dict()
        if self.overrides_applied:
            data["explicit_overrides"] = dict(self.overrides_applied)
        return data


def resolve_transcription_profile(
    profile_name: str | None = None,
    *,
    model_size: str | None = None,
    beam_size: int | None = None,
    word_timestamps: bool | None = None,
    vad_filter: bool | None = None,
    compute_type: str | None = None,
    settings: Settings | None = None,
) -> ResolvedTranscription:
    """Resolve the effective configuration for a transcription job.

    Resolution order for each knob: explicit argument > profile default
    (from settings-aware table). Passing ``None`` for every argument yields
    exactly the configured profile defaults.

    Args:
        profile_name: One of 'fast' | 'balanced' | 'accurate'. ``None`` uses
            ``settings.DEFAULT_WHISPER_PROFILE``.
        model_size: Explicit Whisper model size ('tiny', 'base', 'small',
            'medium', 'large-v3').
        beam_size: Explicit beam search width (>= 1).
        word_timestamps: Force word timing on/off for the full-video pass.
        vad_filter: Force Silero VAD on/off.
        compute_type: Force CTranslate2 compute type (e.g. 'int8', 'float32').
        settings: Settings override (tests).

    Raises:
        ValueError: Unknown profile name.
    """
    settings = settings or Settings()
    table = _profiles(settings)
    name = (profile_name or settings.DEFAULT_WHISPER_PROFILE).strip().lower()
    if name not in table:
        valid = ", ".join(sorted(table))
        raise ValueError(f"Unknown transcription profile '{profile_name}'. Valid: {valid}.")
    profile = table[name]
    cli: dict[str, object] = {}
    if model_size is not None:
        cli["model_size"] = str(model_size)
    if beam_size is not None:
        cli["beam_size"] = int(beam_size)
    if word_timestamps is not None:
        cli["word_timestamps"] = bool(word_timestamps)
    if vad_filter is not None:
        cli["vad_filter"] = bool(vad_filter)
    if compute_type is not None:
        cli["compute_type"] = str(compute_type)
    if not cli:
        return ResolvedTranscription(config=profile)

    resolved = TranscriptionProfile(
        name=profile.name,
        model_size=cli.get("model_size", profile.model_size),
        compute_type=cli.get("compute_type", profile.compute_type),
        beam_size=cli.get("beam_size", profile.beam_size),
        word_timestamps=cli.get("word_timestamps", profile.word_timestamps),
        vad_filter=cli.get("vad_filter", profile.vad_filter),
        description=profile.description,
        accuracy_warning=profile.accuracy_warning,
    )
    return ResolvedTranscription(config=resolved, overrides_applied=cli)
