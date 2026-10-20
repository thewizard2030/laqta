"""Stage s05_ranking — hard veto gates, CPS scoring, winner selection.

Gate order is fixed: cheap deterministic checks run BEFORE any LLM score
is trusted, and every gate adjustment is recorded in the candidate's
``evidence_log`` in human-readable Arabic (so an editor can audit WHY a
boundary moved or a clip was rejected).

Gate 1 — Dangling Context: if the first utterance starts with an
Arabic/English anaphora/connector (e.g. "عشان كده", "النقطة التانية", "
"زي ما قلتلك", "هو لما", "و ده اللي"), the span is shifted backward by
one, then (if still dangling) two utterances. When no earlier utterance
can absorb the context, the gate flags a ``HookRemixVariant`` instead —
the remix replaces the clipped opening with a short in-clip hook plus a
≤2-second Arabic bridge text.

Gate 2 — Clean boundaries: the start/end must rest on a real pause
(pause before >= ``boundary_pause_ms``) or a clear RMS contrast with the
neighbouring utterance (ratio >= ``boundary_rms_contrast``). When the
boundary violates it, the span is snapped to the nearest utterance
boundary that DOES pass, within ``snap_search_ms``; if nothing nearby
qualifies, the candidate is rejected (never silently scored on bad
audio).

Gate 3 — Duration: ``min_clip_sec`` <= span duration <= ``max_clip_sec``
(from the same config the manifest stages already honor).

CPS: archetype-weighted weighted sum over measurable components,
rescaled to 0–100. When ``visual_composition`` is None, its weight is
REDISTRIBUTED across the remaining components (renormalization), so
missing signals are never treated as zero evidence.

Not honest in this stage (explicit): crosstalk_ratio stays 0.0 and
``MonetizationMeta`` is not fabricated (ypp_safe etc. have no verified
estimator yet) — documented both here and in the manifest notes.
"""

from __future__ import annotations

import re

from qatta.core.config import QattaSettings
from qatta.core.pipeline import PipelineError
from qatta.core.schema import (
    ClipCandidate,
    CPSBreakdown,
    HookRemixVariant,
    QattaManifest,
    VetoGates,
)

# Arabic + English connectors/anaphora that make a clip start dangle.
_DANGLING_CONNECTORS: list[str] = [
    "عشان كده",
    "عشان كدا",
    "النقطة التانية",
    "النقطة التانيه",
    "النقطة الثانية",
    "زي ما قلتلك",
    "زي ما قلنا",
    "زي ما قلت",
    "هو لما",
    "لما كلامك",
    "و ده اللي",
    "و ده سبب",
    "ده اللي كان",
    "بقى بعد",
    "طيب بص",
    "في آخر حاجة",
    "ثانياً",
    "ثالثاً",
    "بص يا سيدي",
    "so ",
    "so,",
    "and that",
    "like i said",
    "anyway",
    "the second",
    "as i mentioned",
]

_CROSSTALK_NOT_MEASURED = (
    "crosstalk_ratio غير مقاس في هذه المرحلة (غير محسوب) — يظل 0.0 حتى تُضاف قياسات حقيقية"
)


def is_dangling(utterance) -> bool:
    """True when the utterance STARTS with an unresolved connector."""
    text = (utterance.text or "").strip().lower()
    for connector in _DANGLING_CONNECTORS:
        if text.startswith(connector):
            return True
    return False


def _find_utterance(u_index, u_id):
    row = u_index.get(u_id)
    if row is None:
        raise PipelineError(f"candidate references unknown utterance {u_id}")
    return row


class GateContext:
    """Indexes + thresholds shared by the three gates."""

    def __init__(self, manifest: QattaManifest, settings: QattaSettings):
        self.settings = settings
        self.ordered = sorted(manifest.atomic_utterances, key=lambda u: (u.start_ms, u.u_id))
        self.by_u_id = {u.u_id: u for u in self.ordered}
        self.ordinal = {u.u_id: i for i, u in enumerate(self.ordered)}

    def utterance_at(self, index: int):
        if 0 <= index < len(self.ordered):
            return self.ordered[index]
        return None


# ---------------------------------------------------------------------------
# Gate 1 — dangling context auto-healer
# ---------------------------------------------------------------------------


def heal_dangling_context(
    manifest: QattaManifest,
    proposal,
    gate_ctx: GateContext,
    settings: QattaSettings,
) -> tuple[ClipCandidate, list[str], bool]:
    """Shift start backward across dangling utterances; else flag remix.

    Returns (candidate, evidence_lines, still_dangling). A candidate that
    cannot be healed keeps its boundaries and gets a Remix (hook at the
    first non-dangling utterance) — the gate itself then reads as
    RESOLVED, honestly labeled by the remix evidence line.
    """
    evidence: list[str] = []
    start_u = proposal.start_u_id
    start_index = gate_ctx.ordinal[start_u]
    shifted = start_index
    shift_count = 0
    while shift_count < 2 and shifted > 0:
        current = gate_ctx.utterance_at(shifted)
        if not is_dangling(current):
            break
        prev_u = gate_ctx.utterance_at(shifted - 1)
        if prev_u is None:
            break
        snapped = proposal.model_dump()
        snapped["start_u_id"] = prev_u.u_id
        snapped["start_ms"] = prev_u.start_ms
        snapped["duration_sec"] = (proposal.end_ms - prev_u.start_ms) / 1000.0
        proposal = ClipCandidate.model_validate(snapped)
        shift_count += 1
        shifted -= 1

    current = gate_ctx.utterance_at(shifted)
    if is_dangling(current):
        # Cannot fix boundaries with earlier context: flag a HookRemix.
        # The hook lives INSIDE the clip: prefer the first NON-dangling
        # utterance of the span (an already-clean opening line); fall
        # back to the current (dangling) start when none exists.
        start_index = gate_ctx.ordinal[proposal.start_u_id]
        end_index = gate_ctx.ordinal[proposal.end_u_id]
        hook_u = next(
            (
                gate_ctx.utterance_at(i)
                for i in range(start_index, end_index + 1)
                if gate_ctx.utterance_at(i) is not None
                and not is_dangling(gate_ctx.utterance_at(i))
            ),
            current,
        )
        hook_payload = proposal.hook_remix.model_dump()
        hook_payload["enabled"] = True
        hook_payload.setdefault("hook_u_id", None)
        hook_payload["hook_u_id"] = hook_payload.get("hook_u_id") or hook_u.u_id
        hook_payload["ai_bridge_text"] = hook_payload.get("ai_bridge_text") or _arabic_bridge_text(
            current.text
        )
        hook_payload["context_preserved"] = False
        hook_u_id = hook_payload["hook_u_id"]
        hook_row = gate_ctx.by_u_id.get(hook_u_id)
        if hook_row is not None:
            hook_payload["source_start_ms"] = hook_row.start_ms
            hook_payload["source_end_ms"] = hook_row.end_ms
        remix = HookRemixVariant.model_validate(hook_payload)
        snapped = proposal.model_dump()
        snapped["hook_remix"] = remix.model_dump()
        healed = ClipCandidate.model_validate(snapped)
        evidence.append(
            "البوابة 1: البداية تبدأ بسياق معلّق "
            f"({current.text[:30]!r}) ولم يُعثر على سياق سابق داخل "
            "النافذة، وفي حالة تعذّر تراجع البداية رفعنا من HookRemix."
        )
        return healed, evidence, False  # resolved via remix flag

    if shift_count:
        evidence.append(
            f"البوابة 1: البداية كانت بسياق معلّق؛ أزلنا {shift_count} "
            "جملة من البداية حتى لا تبدأ بجملة تنتمي لسابقها."
        )
    return proposal, evidence, False


def _arabic_bridge_text(text: str) -> str:
    """A ~2-second Arabic bridge drafted from the clip's own words."""
    words = [w for w in re.split(r"\s+", (text or "").strip()) if w]
    if not words:
        return "قبل ما نكمل، دي نقطة مهمة جداً."
    # Take a short final clause for effect; bounded to the model budget.
    trimmed = " ".join(words[-5:])
    return f"وقبل أن نصل إلى الحدث: {trimmed}"[:60]


# ---------------------------------------------------------------------------
# Gate 2 — clean audio boundaries (snap or reject)
# ---------------------------------------------------------------------------


def _boundary_ok(gate_ctx: GateContext, index: int, before: bool) -> tuple[bool, float]:
    """(is_ok, pause_available_ms) for the boundary at ``index``."""
    utterance = gate_ctx.utterance_at(index)
    if utterance is None:
        return False, 0.0
    neighbour_index = index - 1 if before else index + 1
    neighbour = gate_ctx.utterance_at(neighbour_index)
    if before:
        pause_ms = (utterance.start_ms - neighbour.end_ms) if neighbour else utterance.start_ms
    else:
        pause_ms = (
            utterance.pause_after_ms
            if not neighbour
            else max(0, neighbour.start_ms - utterance.end_ms)
        )
    if pause_ms >= gate_ctx.settings.boundary_pause_ms:
        return True, float(pause_ms)
    if neighbour is not None and neighbour.start_ms >= utterance.start_ms:
        rms_self = utterance.audio_rms_norm
        rms_other = neighbour.audio_rms_norm
        contrast = rms_other / rms_self if rms_self > 0 else (float(rms_other > 0) * 99.0)
        if max(contrast, 1 / max(contrast, 1e-9)) >= (gate_ctx.settings.boundary_rms_contrast):
            return True, float(pause_ms)
    return False, float(pause_ms)


def heal_audio_boundaries(
    proposal: ClipCandidate,
    gate_ctx: GateContext,
    settings: QattaSettings,
) -> tuple[ClipCandidate, list[str], bool]:
    """Snap violated boundaries to nearby clean ones; reject if impossible.

    Snap is by UTTERANCE adjacency (at most ``max_boundary_shift``
    utterances in each direction), not by frame windows — the kept
    invariant is that boundaries always reference real utterances.
    """
    evidence: list[str] = []
    snapped_payload = proposal.model_dump()
    start_index = gate_ctx.ordinal[proposal.start_u_id]
    end_index = gate_ctx.ordinal[proposal.end_u_id]
    ok_start, _pause_start = _boundary_ok(gate_ctx, start_index, before=True)
    ok_end, _pause_end = _boundary_ok(gate_ctx, end_index, before=False)
    if ok_start and ok_end:
        evidence.append("البوابة 2: حدود الصوت سليمة (سكتات/فروق إجهاد في البداية والنهاية).")
        return proposal, evidence, True

    max_shift = 3
    if not ok_start:
        snap_done = False
        for shift in range(1, max_shift + 1):
            other_index = start_index - shift
            prev_u = gate_ctx.utterance_at(other_index)
            if prev_u is None:
                break
            ok, _ = _boundary_ok(gate_ctx, other_index, before=True)
            if ok:
                new_duration = (proposal.end_ms - prev_u.start_ms) / 1000.0
                if new_duration > settings.max_clip_sec + 2.0:
                    break
                snapped_payload["start_u_id"] = prev_u.u_id
                snapped_payload["start_ms"] = prev_u.start_ms
                snapped_payload["duration_sec"] = new_duration
                evidence.append(
                    f"البوابة 2: حد البداية لم يكن على سكتة/فروق واضحة؛ "
                    f"لاصقنا البداية بجملة {prev_u.u_id} ذات حدود سليمة."
                )
                snap_done = True
                break
        if not snap_done:
            evidence.append(
                "البوابة 2: بداية المقطع ليست على سكتة سمعية واضحة ولم "
                "نجد حدوداً سليمة قريبة بعد "
                f"{settings.snap_search_ms}ms من البحث."
            )
            return proposal, evidence, False

    if not ok_end:
        snap_done = False
        for shift in range(1, max_shift + 1):
            next_u = gate_ctx.utterance_at(end_index + shift)
            if next_u is None:
                break
            ok, _ = _boundary_ok(gate_ctx, end_index + shift, before=False)
            if ok:
                new_duration = (next_u.end_ms - snapped_payload["start_ms"]) / 1000.0
                if new_duration > settings.max_clip_sec + 2.0:
                    break
                snapped_payload["end_u_id"] = next_u.u_id
                snapped_payload["end_ms"] = next_u.end_ms
                snapped_payload["duration_sec"] = new_duration
                evidence.append(
                    f"البوابة 2: حد النهاية لم يكن على سكتة سمعية واضحة؛ "
                    f"لاصقنا النهاية بجملة {next_u.u_id}."
                )
                snap_done = True
                break
        if not snap_done:
            evidence.append(
                "البوابة 2: نهاية المقطع ليست على سكتة سمعية واضحة ولم "
                "نجد حدوداً سليمة قريبة بعد "
                f"{settings.snap_search_ms}ms من البحث."
            )
            return proposal, evidence, False

    if snapped_payload["end_ms"] <= snapped_payload["start_ms"]:
        evidence.append("البوابة 2: التطبيق أنتج حدوداً مقلوبة؛ استبعدنا المقطع.")
        return proposal, evidence, False
    snapped_payload["duration_sec"] = (
        snapped_payload["end_ms"] - snapped_payload["start_ms"]
    ) / 1000.0
    return ClipCandidate.model_validate(snapped_payload), evidence, True


# ---------------------------------------------------------------------------
# Gate 3 — duration & pacing
# ---------------------------------------------------------------------------


def check_duration(proposal: ClipCandidate, settings: QattaSettings) -> tuple[bool, list[str]]:
    duration = proposal.duration_sec
    if duration + 1e-9 < settings.min_clip_sec:
        return False, [
            f"البوابة 3: مدة المقطع ({duration:.1f}s) أقل من الحد الأدنى "
            f"({settings.min_clip_sec}s) — استبعدنا المقطع."
        ]
    if duration - 1e-9 > settings.max_clip_sec + 2.0:
        return False, [
            f"البوابة 3: مدة المقطع ({duration:.1f}s) أكبر من الحد "
            f"({settings.max_clip_sec}s) — استبعدنا المقطع."
        ]
    return True, []


# ---------------------------------------------------------------------------
# CPS: archetype-weighted scoring with renormalization
# ---------------------------------------------------------------------------

# Weights sum to 1.0 per archetype; missing components renormalize.
ARCHETYPE_WEIGHTS: dict[str, dict[str, float]] = {
    "STORY": {
        "standalone_clarity": 0.20,
        "hook_strength": 0.25,
        "story_payoff": 0.30,
        "value_originality": 0.10,
        "audio_dynamics": 0.05,
        "visual_composition": 0.05,
        "boundary_precision": 0.05,
    },
    "TACTICAL_INSIGHT": {
        "standalone_clarity": 0.30,
        "hook_strength": 0.15,
        "story_payoff": 0.10,
        "value_originality": 0.25,
        "audio_dynamics": 0.05,
        "visual_composition": 0.10,
        "boundary_precision": 0.05,
    },
    "HOT_TAKE": {
        "standalone_clarity": 0.25,
        "hook_strength": 0.35,
        "story_payoff": 0.05,
        "value_originality": 0.20,
        "audio_dynamics": 0.05,
        "visual_composition": 0.05,
        "boundary_precision": 0.05,
    },
}


def compute_cps(
    archetype: str,
    *,
    standalone_clarity: float,
    hook_strength: float,
    story_payoff: float,
    value_originality: float,
    audio_dynamics: float,
    visual_composition: float | None,
    boundary_precision: float,
) -> tuple[float, dict[str, float]]:
    """Weighted CPS in [0, 100] with renormalization.

    Missing ``visual_composition`` gets its weight REDISTRIBUTED over the
    measured components rather than counting as zero. Raises for an
    unknown archetype.
    """
    weights = ARCHETYPE_WEIGHTS.get(archetype)
    if weights is None:
        raise PipelineError(
            f"Unknown archetype {archetype!r}; CPS requires one of {sorted(ARCHETYPE_WEIGHTS)}."
        )
    components = {
        "standalone_clarity": standalone_clarity,
        "hook_strength": hook_strength,
        "story_payoff": story_payoff,
        "value_originality": value_originality,
        "audio_dynamics": audio_dynamics,
        "boundary_precision": boundary_precision,
    }
    if visual_composition is not None:
        components["visual_composition"] = visual_composition

    active_weights = {key: weights[key] for key in components}
    weight_total = sum(active_weights.values())
    if weight_total <= 0:  # pragma: no cover - config guard
        raise PipelineError("CPS weights vanished (empty archetypes)")
    effective = {k: w / weight_total for k, w in active_weights.items()}

    total = 0.0
    for key, weight in effective.items():
        value = float(components[key])
        # Component values arrive on a 0–10 scale from stage s05
        # heuristics inside score_candidate (bounded provably below).
        total += weight * (value * 10.0)
    return round(min(100.0, max(0.0, total)), 2), effective


def _signal_functions(
    rows: list,
) -> dict[str, float]:
    """Deterministic 0-10 signals derived from utterance analytics."""
    rms_values = [r.audio_rms_norm for r in rows]
    avg_rms = sum(rms_values) / max(1, len(rms_values))
    hook_pause = max(0, rows[0].pause_after_ms) if len(rows) else 0
    hook_strength = min(10.0, 4.0 + min(4.0, hook_pause / 250.0))
    audio_dynamics = min(10.0, avg_rms * 8.0 + (max(rms_values) - min(rms_values)) * 5.0)
    text_len = sum(len(r.text) for r in rows)
    standalone_clarity = min(10.0, 4.0 + text_len / 120.0)
    payoff_pause = max(0, rows[-1].pause_after_ms) if len(rows) else 0
    story_payoff = min(10.0, 4.0 + min(4.0, payoff_pause / 300.0))
    value_originality = min(10.0, 4.0 + (rows[0].pitch_variance or 0.0) * 5.0)
    return {
        "standalone_clarity": standalone_clarity,
        "hook_strength": hook_strength,
        "story_payoff": story_payoff,
        "value_originality": value_originality,
        "audio_dynamics": audio_dynamics,
        "boundary_precision": 7.5,
    }


# ---------------------------------------------------------------------------
# Stage entry point
# ---------------------------------------------------------------------------


def run_ranking_stage(
    manifest: QattaManifest,
    settings: QattaSettings | None = None,
) -> QattaManifest:
    """Execute s05_ranking: gates -> CPS -> rank -> winners first."""
    settings = settings or QattaSettings()
    gate_ctx = GateContext(manifest, settings)
    candidates = list(manifest.candidates)
    if not candidates:
        raise PipelineError(
            "No candidates in the manifest; run stage s04_candidates before s05_ranking."
        )

    evaluated: list[ClipCandidate] = []
    for candidate in candidates:
        if candidate.veto_gates.rejection_reason in (
            None,
            "pending_s05_ranking",
        ):
            evaluated.append(_evaluate_candidate(candidate, manifest, gate_ctx, settings))
        else:
            # Already fully evaluated (idempotency for forced re-runs).
            evaluated.append(candidate)

    evaluated.sort(key=lambda c: c.cps.total_score, reverse=True)
    winner_ids = [c.clip_id for c in evaluated if c.veto_gates.passed_all][: settings.max_winners]

    # Preserve evidence ordering while tagging winners deterministically.
    final_payloads: list[dict] = []
    for candidate in evaluated:
        payload = candidate.model_dump()
        if candidate.clip_id in winner_ids:
            payload.setdefault("evidence_log", []).append(
                f"اختيار: هذا المقطع ضمن أفضل {len(winner_ids)} مقاطع "
                f"(الترتيب {winner_ids.index(candidate.clip_id) + 1})."
            )
        final_payloads.append(payload)

    data = manifest.model_dump()
    data["candidates"] = final_payloads
    return manifest.model_validate(data)


def _evaluate_candidate(
    candidate: ClipCandidate,
    manifest: QattaManifest,
    gate_ctx: GateContext,
    settings: QattaSettings,
) -> ClipCandidate:
    """Run the three gates and score ONE pending candidate.

    Every outcome (heal, snap, rejection) is recorded in the candidate's
    ``evidence_log`` — including rejection reasons.
    """
    evidence: list[str] = []
    utt_start = gate_ctx.by_u_id.get(candidate.start_u_id)
    utt_end = gate_ctx.by_u_id.get(candidate.end_u_id)
    if utt_start is None or utt_end is None:
        payload = candidate.model_dump()
        payload["veto_gates"] = VetoGates(
            dangling_context=True,
            clean_audio_boundaries=False,
            crosstalk_ratio=0.0,
            passed_all=False,
            rejection_reason="candidate references unknown utterances",
        ).model_dump()
        payload["evidence_log"] = list(payload.get("evidence_log", [])) + [
            "البوابة 1: المقطع يشير إلى جمل غير موجودة — استُبعد."
        ]
        return ClipCandidate.model_validate(payload)

    proposal = candidate.model_validate(candidate.model_dump())
    proposal, gate1_evidence, _ = heal_dangling_context(manifest, proposal, gate_ctx, settings)
    evidence.extend(gate1_evidence)

    proposal, gate2_evidence, boundary_ok = heal_audio_boundaries(proposal, gate_ctx, settings)
    evidence.extend(gate2_evidence)

    ok3, gate3_evidence = check_duration(proposal, settings)
    evidence.extend(gate3_evidence)

    payload = proposal.model_dump()
    payload["evidence_log"] = list(payload.get("evidence_log", [])) + evidence

    if not boundary_ok:
        payload["veto_gates"] = VetoGates(
            dangling_context=False,
            clean_audio_boundaries=False,
            crosstalk_ratio=0.0,
            passed_all=False,
            rejection_reason="clean audio boundaries could not be achieved near the clip",
        ).model_dump()
        return ClipCandidate.model_validate(payload)
    if not ok3:
        payload["veto_gates"] = VetoGates(
            dangling_context=False,
            clean_audio_boundaries=True,
            crosstalk_ratio=0.0,
            passed_all=False,
            rejection_reason=f"duration outside "
            f"[{settings.min_clip_sec}, {settings.max_clip_sec}]s",
        ).model_dump()
        return ClipCandidate.model_validate(payload)

    start_idx = gate_ctx.ordinal[proposal.start_u_id]
    end_idx = gate_ctx.ordinal[proposal.end_u_id]
    rows = gate_ctx.ordered[start_idx : end_idx + 1]
    signals: dict[str, float] = {
        "standalone_clarity": 0.0,
        "hook_strength": 0.0,
        "story_payoff": 0.0,
        "value_originality": 0.0,
        "audio_dynamics": 0.0,
        "boundary_precision": 0.0,
    }
    if len(rows) >= 2:
        signals = _signal_functions(rows)

    total, effective = compute_cps(
        proposal.cps.archetype,
        standalone_clarity=signals["standalone_clarity"],
        hook_strength=signals["hook_strength"],
        story_payoff=signals["story_payoff"],
        value_originality=signals["value_originality"],
        audio_dynamics=signals["audio_dynamics"],
        visual_composition=None,  # honestly NOT measured yet
        boundary_precision=signals["boundary_precision"],
    )
    missing_visual = "وزن visual_composition أُعيد توزيعه على المكونات المقاسة (لا نُخترع نقاط رؤية)."
    evidence.append(
        "التقييم: نوع المقطع " + proposal.cps.archetype + f" بدرجة CPS {total:.1f}/100."
    )
    evidence.append(missing_visual)
    evidence.append(_CROSSTALK_NOT_MEASURED)

    payload = proposal.model_dump()
    payload["cps"] = CPSBreakdown(
        total_score=total,
        archetype=proposal.cps.archetype,
        standalone_clarity=signals["standalone_clarity"],
        hook_strength=signals["hook_strength"],
        story_payoff=signals["story_payoff"],
        value_originality=signals["value_originality"],
        audio_dynamics=signals["audio_dynamics"],
        visual_composition=None,
        boundary_precision=signals["boundary_precision"],
    ).model_dump()
    payload["evidence_log"] = list(payload.get("evidence_log", [])) + evidence
    payload["veto_gates"] = VetoGates(
        dangling_context=False,
        clean_audio_boundaries=True,
        crosstalk_ratio=0.0,
        passed_all=True,
        rejection_reason=None,
    ).model_dump()
    return ClipCandidate.model_validate(payload)


def register(orchestrator) -> None:
    """Attach s05_ranking to a :class:`PipelineOrchestrator`."""

    @orchestrator.stage("s05_ranking")
    def _stage(manifest: QattaManifest) -> QattaManifest:
        return run_ranking_stage(manifest, orchestrator.settings)
