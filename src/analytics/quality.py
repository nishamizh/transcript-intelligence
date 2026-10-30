"""A quality score for the briefing itself, not another chart of the calls.

Coverage, consistency, actionability, and confidence are computed from the
meetings and the insights that cite them. They are a proxy a reviewer can
argue with. The replacement is a human accept/edit/reject loop, with an
LLM-as-judge pass once those labels exist.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.analytics.sentiment_analyzer import LABEL_RANK, SentimentAnalysis
from src.analytics.topic_analyzer import TopicAnalysis
from src.models.meeting import Meeting

_NEXT = (
    "The next evolution is a human-in-the-loop review on the zero-overlap topics "
    "and on every insight. A reviewer accepts, edits, or rejects the finding against "
    "the cited transcript. Those labels become the evaluation set. An LLM-as-judge "
    "can then score faithfulness and actionability on new runs, with the human labels "
    "as the thing it has to agree with. This score is the stand-in until that loop exists."
)


@dataclass(slots=True)
class InsightQualityScore:
    coverage: float
    consistency: float
    actionability: float
    confidence: float
    composite: float
    notes: list[str] = field(default_factory=list)
    next_evolution: str = _NEXT

    @classmethod
    def evaluate(
        cls,
        meetings: list[Meeting],
        insights: list,
        sentiment: SentimentAnalysis,
        topics: TopicAnalysis,
    ) -> InsightQualityScore:
        coverage, coverage_notes = _coverage(meetings, insights, topics)
        consistency, consistency_notes = _consistency(meetings, sentiment)
        actionability, action_notes = _actionability(insights)
        confidence, confidence_notes = _confidence(meetings, insights, consistency)
        parts = [coverage, consistency, actionability, confidence]
        composite = sum(parts) / len(parts) if parts else 0.0
        return cls(
            coverage=_round(coverage),
            consistency=_round(consistency),
            actionability=_round(actionability),
            confidence=_round(confidence),
            composite=_round(composite),
            notes=[*coverage_notes, *consistency_notes, *action_notes, *confidence_notes],
        )


def _coverage(meetings: list[Meeting], insights: list, topics: TopicAnalysis) -> tuple[float, list[str]]:
    total = len(meetings) or 1
    classified = sum(1 for meeting in meetings if meeting.primary_theme not in ("", "unclassified"))
    theme_rate = classified / total
    stakeholders = {insight.stakeholder for insight in insights}
    expected = {"support", "product", "engineering", "sales"}
    stake_rate = len(stakeholders & expected) / len(expected)
    cited = {
        item.meeting_id
        for insight in insights
        for item in insight.evidence
    }
    # Citing about a third of a 100-meeting corpus is a briefing. Citing all of it is a dump.
    evidence_rate = min(1.0, len(cited) / max(1.0, 0.35 * total))
    score = 0.45 * theme_rate + 0.25 * stake_rate + 0.30 * evidence_rate
    notes = [
        (
            f"Coverage {score:.0%}: {classified}/{len(meetings)} meetings land in a governed theme "
            f"({theme_rate:.0%}), {len(stakeholders & expected)}/4 stakeholders have a finding, "
            f"and {len(cited)} meetings are cited as evidence."
        )
    ]
    if topics.unclassified_count:
        noun = "meeting" if topics.unclassified_count == 1 else "meetings"
        notes.append(
            f"{topics.unclassified_count} {noun} stayed unclassified rather than being forced into a theme."
        )
    return score, notes


def _consistency(meetings: list[Meeting], sentiment: SentimentAnalysis) -> tuple[float, list[str]]:
    """Labels two ranks apart must not invert the score. Adjacent labels may touch."""

    bands: dict[str, list[float]] = {}
    for meeting in meetings:
        bands.setdefault(meeting.sentiment, []).append(meeting.sentiment_score)
    ranked = sorted(
        ((LABEL_RANK[label], label, scores) for label, scores in bands.items() if label in LABEL_RANK),
        key=lambda item: item[0],
    )
    checks = 0
    passes = 0
    for index, (rank, label, scores) in enumerate(ranked):
        for later_rank, later_label, later_scores in ranked[index + 1 :]:
            if later_rank < rank + 2:
                continue
            checks += 1
            if max(scores) <= min(later_scores):
                passes += 1
            else:
                del label, later_label
    ordinal = passes / checks if checks else 1.0

    recomputed = []
    for row in sentiment.by_call_type:
        subset = [meeting.sentiment_score for meeting in meetings if meeting.call_type == row.call_type]
        if not subset:
            continue
        actual = sum(subset) / len(subset)
        recomputed.append(abs(actual - row.mean_score) < 0.02)
    self_check = sum(recomputed) / len(recomputed) if recomputed else 1.0
    score = 0.7 * ordinal + 0.3 * self_check
    notes = [
        (
            f"Consistency {score:.0%}: {passes}/{checks or 0} non-adjacent sentiment labels keep their score order, "
            f"and the published call-type means match a fresh average ({self_check:.0%})."
        )
    ]
    return score, notes


def _actionability(insights: list) -> tuple[float, list[str]]:
    if not insights:
        return 0.0, ["Actionability 0%: the pipeline produced no insights."]
    ready = 0
    for insight in insights:
        has_number = any(character.isdigit() for character in insight.finding)
        if insight.recommendation and insight.why_it_matters and insight.evidence and has_number:
            ready += 1
    score = ready / len(insights)
    notes = [
        (
            f"Actionability {score:.0%}: {ready}/{len(insights)} insights include a number, "
            "a reason to care, a recommendation, and at least one cited meeting."
        )
    ]
    return score, notes


def _confidence(meetings: list[Meeting], insights: list, consistency: float) -> tuple[float, list[str]]:
    sample = min(1.0, len(meetings) / 60)
    counts = {}
    for meeting in meetings:
        counts[meeting.call_type] = counts.get(meeting.call_type, 0) + 1
    present = [count for count in counts.values() if count]
    cell = 1.0 if present and min(present) >= 15 else (min(present) / 15 if present else 0.0)
    evidence_sizes = [len(insight.evidence) for insight in insights] or [0]
    depth = min(1.0, (sum(evidence_sizes) / len(evidence_sizes)) / 3)
    score = (sample + cell + depth + consistency) / 4
    notes = [
        (
            f"Confidence {score:.0%}: sample factor {sample:.0%} at {len(meetings)} meetings, "
            f"smallest call-type cell {min(present) if present else 0}, "
            f"mean evidence items {sum(evidence_sizes) / len(evidence_sizes):.1f}."
        ),
        (
            "The composite scores the briefing's structure: themes assigned, labels consistent "
            "with scores, insights written so a person can act. It does not measure whether a "
            "reviewer would accept the conclusion. That is the human loop described below."
        ),
    ]
    return score, notes


def _round(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 4)
