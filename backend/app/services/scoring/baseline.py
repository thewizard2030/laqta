"""Deterministic baseline clip scoring (PRD §5 FR-05, §8).

Honesty contract:
- The Clip Potential Score (CPS) is a heuristic/editorial quality score on a
  0-100 scale. It is NOT a probability of views or virality. Weights are
  configuration, not scientific claims.
- Missing modalities are surfaced as ``available=False`` with an explanatory
  rationale and are excluded from weight renormalization. They are never
  silently represented as zero or treated as positive evidence.
- No LLM is involved; every component is computed deterministically from
  transcript structure and confidence metadata only.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Default weights exactly as specified in PRD §5 FR-05. Keys are stable
# identifiers persisted with the candidate so future re-scoring stays aligned.
DEFAULT_WEIGHTS: dict[str, float] = {
    "self_contained": 0.25,  # self-contained idea / context independence
    "hook": 0.20,  # opening hook / curiosity
    "completion": 0.20,  # story or answer completion
    "novelty_emotion": 0.10,  # usefulness, novelty, emotion, or surprise
    "clarity": 0.10,  # speech clarity and audio dynamics
    "visual": 0.05,  # visual composition
    "boundary": 0.10,  # boundary/timing quality
}

COMPONENT_LABELS: dict[str, str] = {
    "self_contained": "Self-contained idea / context independence",
    "hook": "Opening hook / curiosity",
    "completion": "Story or answer completion",
    "novelty_emotion": "Usefulness, novelty, emotion, or surprise",
    "clarity": "Speech clarity and audio dynamics",
    "visual": "Visual composition",
    "boundary": "Boundary/timing quality",
}

CPS_INTERPRETATION = (
    "Heuristic editorial quality score (0-100), not a probability of views "
    "or virality. Weights are configurable defaults pending human-rating evaluation."
)

VISUAL_UNAVAILABLE_RATIONALE = (
    "No video/scene/crop analysis is implemented in this phase "
    "(FR-07 adapter not present); weight excluded from renormalization."
)

NO_CLARITY_SIGNAL_RATIONALE = (
    "Transcript has no confidence metadata (word probabilities / avg_logprob); "
    "clarity cannot be estimated from audio yet (FR-06 not implemented)."
)

# Surface-level continuation/opening markers. Deducting for these is a weak
# heuristic; matched at word level, case-insensitively.
CONTINUATION_MARKERS: set[str] = {
    "so",
    "and",
    "but",
    "because",
    "then",
    "also",
    "which",
    "okay",
    "يعني",
    "كمان",
    "برضه",
    "برضو",
    "لأن",
    "لان",
    "عشان",
    "بس",
    "طبعا",
    "زي",
    "ده",
    "دي",
    "هو",
    "هي",
}
# Prefixes counted with light deduction only, since many legitimate words
# carry them (e.g. "وهو", "فجأة").
CONTINUATION_PREFIXES: tuple[tuple[str, str], ...] = (
    ("و", 10.0),  # Arabic "wa-" prefix
    ("ف", 5.0),
)

INTERROGATIVES: set[str] = {
    "who",
    "what",
    "why",
    "how",
    "when",
    "where",
    "which",
    "ليه",
    "ليش",
    "لماذا",
    "إزاي",
    "ازاي",
    "كيف",
    "ماذا",
    "متين",
    "متى",
    "وين",
    "أين",
    "هل",
}

SENTENCE_TERMINALS: str = ".!?…؟ ؗ"
FILLERS: set[str] = {"uh", "um", "hmm", "امم", "اه", "هتة", "هتت"}


@dataclass
class ComponentScore:
    """A single CPS component with availability state and explanation."""

    key: str
    score: float | None  # 0-100 when available, None when unavailable
    available: bool
    weight: float  # nominal weight from configuration
    effective_weight: float | None  # renormalized over available components
    rationale: str


@dataclass
class ScoringResult:
    """Full explainable scoring output for one candidate."""

    cps: float
    unavailable_keys: list[str]
    components: dict[str, ComponentScore]
    rationale: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ScoringConfig:
    """Deterministic scoring + generation configuration (all user-tunable)."""

    min_duration_s: float = 30.0
    max_duration_s: float = 55.0
    weights: tuple[tuple[str, float], ...] = tuple(DEFAULT_WEIGHTS.items())
    max_overlap_iou: float = 0.5
    max_text_jaccard: float = 0.8
    pause_penalty_threshold: float = 0.25  # fraction of window that is silence
    suggested_threshold: float = 60.0  # cps >= this -> status 'suggested'
    keep_threshold: float = 25.0  # cps >= this -> persisted; below -> rejected

    def __post_init__(self) -> None:
        if self.min_duration_s <= 0 or self.max_duration_s <= self.min_duration_s:
            raise ValueError(
                "max_duration_s must be strictly greater than min_duration_s "
                f"(got min={self.min_duration_s}, max={self.max_duration_s})."
            )
        unknown = {k for k, _ in self.weights} - set(DEFAULT_WEIGHTS)
        if unknown:
            raise ValueError(f"Unknown scoring weight keys: {sorted(unknown)}.")
        for key, value in self.weights:
            if value < 0.0:
                raise ValueError(f"Weight '{key}' must be non-negative (got {value}).")

    def weight_map(self) -> dict[str, float]:
        weights = dict(self.weights)
        total = sum(weights.values())
        if total <= 0:
            raise ValueError("Sum of weights must be positive.")
        if abs(total - 1.0) > 1e-9:
            # Normalize so the fully-available total is always 1.0.
            weights = {k: v / total for k, v in weights.items()}
        return weights


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _token_set(text: str) -> set[str]:
    """Lowercased whitespace tokens with punctuation stripped, for dup checks."""
    tokens: set[str] = set()
    for raw in text.lower().split():
        stripped = raw.strip(SENTENCE_TERMINALS.strip() + "،\",'«»()[]:;")
        if stripped:
            tokens.add(stripped)
    return tokens


def jaccard_text_similarity(a: str, b: str) -> float:
    """Deterministic token-level Jaccard similarity for near-duplicate detection."""
    ta, tb = _token_set(a), _token_set(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def compute_cps(components: dict[str, ComponentScore]) -> tuple[float, dict[str, float]]:
    """Weight-renormalized CPS over available components only.

    Returns (cps, effective_weights). Components that are unavailable receive
    zero effective weight and are listed by the caller as unavailable.
    """
    weights = ScoringConfig().weight_map()  # nominal shape reference
    available_total = 0.0
    scored: list[tuple[str, float, float]] = []
    for key, comp in components.items():
        nominal = comp.weight if comp.weight is not None else weights.get(key, 0.0)
        if comp.available and comp.score is not None:
            available_total += nominal
            scored.append((key, comp.score, nominal))

    effective: dict[str, float] = {}
    cps = 0.0
    for key, score, nominal in scored:
        eff = nominal / available_total if available_total > 0 else 0.0
        effective[key] = eff
        cps += eff * score
    return round(_clamp(cps), 2), effective


def _boundary_component(
    duration_ms: int,
    silence_fraction: float,
    truncated: bool,
    cuts_speech: bool,
    low_boundary_precision: bool,
    config: ScoringConfig,
) -> tuple[float, str]:
    """Boundary/timing quality: duration fit, dead air, and cut risks."""
    span = config.max_duration_s - config.min_duration_s
    target = span / 2.0 + config.min_duration_s
    duration_s = duration_ms / 1000.0
    deviation = abs(duration_s - target) / span if span > 0 else 0.0
    fit = _clamp(100.0 * (1.0 - deviation))
    speech_quality = 100.0
    notes: list[str] = []
    if silence_fraction > config.pause_penalty_threshold:
        penalty = (silence_fraction - config.pause_penalty_threshold) * 400.0
        speech_quality -= min(penalty, 60.0)
        notes.append(
            f"Silence fraction {silence_fraction:.0%} exceeds threshold "
            f"{config.pause_penalty_threshold:.0%}."
        )
    if truncated:
        speech_quality -= 50.0
        notes.append("Window clamped to media duration; ending may cut speech.")
    if cuts_speech:
        speech_quality -= 70.0
        notes.append("Boundary cuts inside a spoken word/utterance.")
    if low_boundary_precision:
        speech_quality -= 15.0
        notes.append(
            "No word-level timestamps: boundaries use segment ends "
            "(lower boundary precision, may include brief lead-in/out)."
        )
    speech_quality = _clamp(speech_quality)
    score = round(_clamp(0.4 * fit + 0.6 * speech_quality), 2)
    rationale = f"Duration {duration_s:.1f}s vs target {target:.1f}s (fit {fit:.0f}/100). " + (
        " ".join(notes) if notes else "No dead-air or cut penalties applied."
    )
    return score, rationale


def _completion_component(ends_sentence: bool, ends_mid_segment: bool) -> tuple[float, str]:
    if ends_sentence:
        return 100.0, "Text ends with terminal punctuation; story/answer reaches closure."
    if ends_mid_segment:
        penalty_score = 35.0
        return (
            penalty_score,
            "Penalty: unfinished clause — window ends inside a sentence "
            "(no terminal punctuation observed).",
        )
    score = 65.0
    return (
        score,
        "No terminal punctuation at the end (segment-level data may simply lack "
        "punctuation); may be incomplete.",
    )


def _self_contained_component(
    starts_mid_segment: bool,
    first_word: str | None,
    first_unit_word_count: int,
) -> tuple[float, str]:
    score = 70.0
    notes: list[str] = []
    if starts_mid_segment:
        score -= 30.0
        notes.append("Penalty: starts mid-sentence (fragment, weak context independence).")
    if first_word:
        first_lower = first_word.strip(SENTENCE_TERMINALS.strip() + "،٬\"'«»()").lower()
        matched = None
        if first_lower in CONTINUATION_MARKERS:
            matched = first_lower
            score -= 20.0
            notes.append(
                f"Penalty: opens with continuation marker '{matched}', "
                "suggesting unresolved prior context."
            )
        else:
            for prefix, deduction in CONTINUATION_PREFIXES:
                if first_lower.startswith(prefix) and len(first_lower) > 2:
                    score -= deduction
                    notes.append(
                        f"Light penalty: first word starts with prefix '{prefix}' "
                        "(continuation-marking prefix; may still be self-contained)."
                    )
                    break
        if first_lower in FILLERS:
            score -= 10.0
            notes.append(f"Penalty: opens with filler '{first_lower}'.")
    if first_unit_word_count <= 2 and first_unit_word_count > 0:
        score -= 10.0
        notes.append("Penalty: opening unit is very short (possible dangling fragment).")
    if not notes:
        notes.append("No determinable fragment/continuation signals; neutral baseline.")
    return round(_clamp(score), 2), " ".join(notes)


def _hook_component(first_unit_text: str, ends_sentence: bool) -> tuple[float, str]:
    score = 55.0
    notes: list[str] = []
    first_word: str | None = first_unit_text.split()[0] if first_unit_text.split() else None
    if first_word:
        first_lower = first_word.strip(SENTENCE_TERMINALS.strip() + "،٬\"'«»()").lower()
        if first_lower in INTERROGATIVES:
            score += 20.0
            notes.append(
                f"Bonus: opens with interrogative '{first_lower}' (question hooks a viewer)."
            )
    stripped = first_unit_text.strip()
    if stripped.endswith(("؟", "?")):
        score += 15.0
        notes.append("Bonus: first sentence poses a question.")
    if any(ch.isdigit() for ch in first_unit_text):
        score += 10.0
        notes.append("Bonus: contains a number (concrete/quantified openings tend to hook).")
    if ends_sentence and len(first_unit_text.split()) <= 12:
        score += 5.0
        notes.append("Bonus: short, complete opening sentence.")
    if not notes:
        notes.append("No strong hook signals at the surface level; neutral baseline.")
    return round(_clamp(score), 2), " ".join(notes)


def _novelty_emotion_component(text: str) -> tuple[float, str]:
    """Weakest measurable component: surface signals only, disclosed as such."""
    score = 55.0
    notes = [
        "Weak signal: semantic novelty/emotion requires LLM or editor input; "
        "only surface cues measured."
    ]
    tokens = [tok.strip(SENTENCE_TERMINALS.strip() + "،٬\"'").lower() for tok in text.split()]
    if any(tok in FILLERS for tok in tokens):
        score -= 10.0
        notes.append("Penalty: filler/hesitation tokens reduce punchiness.")
    if "…" in text:
        score -= 5.0
        notes.append("Penalty: ellipsis/trailing ambiguity detected.")
    if any(line.strip().endswith("!") for line in text.split("\n")):
        score += 10.0
        notes.append("Bonus: exclamation present (weak emotional-intensity cue).")
    return round(_clamp(score), 2), " ".join(notes)


def _clarity_component(
    word_probabilities: list[float] | None,
    avg_logprobs: list[float] | None,
) -> tuple[float | None, str]:
    """Clarity from ASR confidence only; audio-envelope features are not built yet."""
    if word_probabilities:
        mean_prob = sum(word_probabilities) / len(word_probabilities)
        score = _clamp((mean_prob - 0.5) / 0.5 * 100.0)
        return (
            round(score, 2),
            f"Derived from mean word confidence {mean_prob:.2f} "
            "(ASR proxy; audio loudness/dynamics not measured).",
        )
    if avg_logprobs:
        mean_lp = sum(avg_logprobs) / len(avg_logprobs)
        low, high = -1.5, -0.2
        score = _clamp((mean_lp - low) / (high - low) * 100.0)
        return (
            round(score, 2),
            f"Derived from mean segment log-probability {mean_lp:.2f} "
            "(ASR proxy; audio loudness/dynamics not measured).",
        )
    return None, NO_CLARITY_SIGNAL_RATIONALE


def score_candidate(
    duration_ms: int,
    text: str,
    silence_fraction: float,
    truncated: bool,
    cuts_speech: bool,
    starts_mid_segment: bool,
    ends_mid_segment: bool,
    ends_sentence: bool,
    first_unit_text: str,
    first_unit_word_count: int,
    word_probabilities: list[float] | None = None,
    avg_logprobs: list[float] | None = None,
    low_boundary_precision: bool = False,
    config: ScoringConfig | None = None,
) -> ScoringResult:
    """Compute the explainable CPS and component breakdown for one candidate.

    Deterministic: identical inputs always produce an identical result.
    """
    cfg = config or ScoringConfig()
    components: dict[str, ComponentScore] = {}

    boundary_score, boundary_rationale = _boundary_component(
        duration_ms,
        silence_fraction,
        truncated,
        cuts_speech,
        low_boundary_precision,
        cfg,
    )
    components["boundary"] = ComponentScore(
        key="boundary",
        score=boundary_score,
        available=True,
        weight=cfg.weight_map()["boundary"],
        effective_weight=None,
        rationale=boundary_rationale,
    )

    completion_score, completion_rationale = _completion_component(
        ends_sentence,
        ends_mid_segment,
    )
    components["completion"] = ComponentScore(
        key="completion",
        score=completion_score,
        available=True,
        weight=cfg.weight_map()["completion"],
        effective_weight=None,
        rationale=completion_rationale,
    )

    first_word = first_unit_text.split()[0] if first_unit_text.split() else None
    self_score, self_rationale = _self_contained_component(
        starts_mid_segment,
        first_word,
        first_unit_word_count,
    )
    components["self_contained"] = ComponentScore(
        key="self_contained",
        score=self_score,
        available=True,
        weight=cfg.weight_map()["self_contained"],
        effective_weight=None,
        rationale=self_rationale,
    )

    hook_score, hook_rationale = _hook_component(first_unit_text, ends_sentence)
    components["hook"] = ComponentScore(
        key="hook",
        score=hook_score,
        available=True,
        weight=cfg.weight_map()["hook"],
        effective_weight=None,
        rationale=hook_rationale,
    )

    novelty_score, novelty_rationale = _novelty_emotion_component(text)
    components["novelty_emotion"] = ComponentScore(
        key="novelty_emotion",
        score=novelty_score,
        available=True,
        weight=cfg.weight_map()["novelty_emotion"],
        effective_weight=None,
        rationale=novelty_rationale,
    )

    clarity_score, clarity_rationale = _clarity_component(word_probabilities, avg_logprobs)
    components["clarity"] = ComponentScore(
        key="clarity",
        score=clarity_score,
        available=clarity_score is not None,
        weight=cfg.weight_map()["clarity"],
        effective_weight=None,
        rationale=clarity_rationale,
    )

    components["visual"] = ComponentScore(
        key="visual",
        score=None,
        available=False,
        weight=cfg.weight_map()["visual"],
        effective_weight=None,
        rationale=VISUAL_UNAVAILABLE_RATIONALE,
    )

    cps, effective = compute_cps(components)
    for key, comp in components.items():
        comp.effective_weight = effective.get(key)
    unavailable = [k for k, c in components.items() if not c.available]

    rationale_lines = [
        "Overall rationale (deterministic, no LLM involved):",
        *(f"{COMPONENT_LABELS[k]}: {c.rationale}" for k, c in components.items()),
    ]
    return ScoringResult(
        cps=cps,
        unavailable_keys=unavailable,
        components=components,
        rationale=rationale_lines,
    )
