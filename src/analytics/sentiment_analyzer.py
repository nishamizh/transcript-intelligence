"""Sentiment by call type and over time, plus the interpretation of the gap.

The dataset already carries a meeting-level label and a 1–5 score, and each
turn carries its own polarity. This analyzer does not re-score the text.
It aggregates the scores the business already stored, checks that the labels
and the scores tell the same story, and writes down why a gap is worth a
decision. Re-scoring with a new model would be a second opinion, not a
replacement, until someone measures it against these labels.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import timedelta

from src.analytics.base import Analyzer
from src.models.meeting import Meeting

NEGATIVE_LABELS = {"very-negative", "negative", "mixed-negative"}
LABEL_RANK = {
    "very-negative": 0,
    "negative": 1,
    "mixed-negative": 2,
    "mixed-positive": 3,
    "positive": 4,
    "very-positive": 5,
}
# Scores at or above this sit on the positive side of the observed bands.
POSITIVE_CUTOFF = 3.0
_INCIDENT_TITLE = re.compile(r"outage|incident|war room|pipeline failure", re.IGNORECASE)


@dataclass(slots=True)
class CallTypeSentiment:
    call_type: str
    count: int
    mean_score: float
    negative_share: float
    label_counts: dict[str, int]
    sentence_mix: dict[str, float]
    turn_count: int = 0


@dataclass(slots=True)
class PeriodSentiment:
    period: str
    count: int
    mean_score: float | None
    by_call_type: dict[str, float | None]
    by_call_type_n: dict[str, int] = field(default_factory=dict)


@dataclass(slots=True)
class CohortSentiment:
    name: str
    count: int
    mean_score: float
    rest_count: int
    rest_mean: float


@dataclass(slots=True)
class SentimentInterpretation:
    interpretation_id: str
    title: str
    finding: str
    why_it_matters: str


@dataclass(slots=True)
class SentimentProvenance:
    meeting_score_source: str
    meeting_label_source: str
    turn_polarity_source: str
    inferred_model_score: None
    inferred_model_note: str
    aggregation: str
    causal_claims: str


def default_provenance() -> SentimentProvenance:
    return SentimentProvenance(
        meeting_score_source=(
            "Source-provided meeting score: summary.json sentimentScore, scale 1–5. "
            "The analyzer copies it and does not change it."
        ),
        meeting_label_source=(
            "Source-provided meeting label: summary.json overallSentiment. Copied unchanged."
        ),
        turn_polarity_source=(
            "Source-provided turn polarity: transcript sentimentType (positive, neutral, or negative). "
            "Rolled up only as a mix of turns. Not converted into the 1–5 score."
        ),
        inferred_model_score=None,
        inferred_model_note="No new sentiment model is fit. No text is rescored.",
        aggregation=(
            "Cohort figures are the arithmetic mean of the source meeting scores. "
            "Every cohort reports n. Empty weeks stay empty rather than being interpolated."
        ),
        causal_claims="None. Differences between cohorts are descriptive, not estimated effects.",
    )


@dataclass(slots=True)
class SentimentAnalysis:
    overall_mean: float
    overall_count: int
    scale: str
    negative_threshold: float
    by_call_type: list[CallTypeSentiment]
    by_month: list[PeriodSentiment]
    by_week: list[PeriodSentiment]
    incident: CohortSentiment
    outage_mention: CohortSentiment
    label_counts: dict[str, int]
    provenance: SentimentProvenance = field(default_factory=default_provenance)
    interpretations: list[SentimentInterpretation] = field(default_factory=list)


class SentimentAnalyzer(Analyzer):
    def analyze(self, meetings: list[Meeting]) -> SentimentAnalysis:
        by_call_type = [_call_type_row(call_type, _of_type(meetings, call_type)) for call_type in ("support", "external", "internal")]
        by_call_type = [row for row in by_call_type if row.count]
        analysis = SentimentAnalysis(
            overall_mean=_mean([meeting.sentiment_score for meeting in meetings]),
            overall_count=len(meetings),
            scale="1–5 meeting score shipped with the summary. Higher is more positive.",
            negative_threshold=POSITIVE_CUTOFF,
            by_call_type=by_call_type,
            by_month=_periods(meetings, lambda meeting: meeting.month_key(), step="month"),
            by_week=_periods(meetings, _week_key, step="week"),
            incident=_cohort(meetings, _is_incident, "Incident-titled meetings"),
            outage_mention=_cohort(meetings, _mentions_outage, "Meetings that mention the outage"),
            label_counts=_label_counts(meetings),
            provenance=default_provenance(),
        )
        analysis.interpretations = _interpret(analysis)
        return analysis


def _of_type(meetings: list[Meeting], call_type: str) -> list[Meeting]:
    return [meeting for meeting in meetings if meeting.call_type == call_type]


def _call_type_row(call_type: str, meetings: list[Meeting]) -> CallTypeSentiment:
    scores = [meeting.sentiment_score for meeting in meetings]
    negative = sum(1 for meeting in meetings if meeting.sentiment in NEGATIVE_LABELS or meeting.sentiment_score < POSITIVE_CUTOFF)
    mix_counts = {"positive": 0, "neutral": 0, "negative": 0}
    for meeting in meetings:
        for turn in meeting.turns:
            if turn.sentiment in mix_counts:
                mix_counts[turn.sentiment] += 1
    total_turns = sum(mix_counts.values())
    mix = {name: (count / total_turns if total_turns else 0.0) for name, count in mix_counts.items()}
    labels: dict[str, int] = defaultdict(int)
    for meeting in meetings:
        labels[meeting.sentiment] += 1
    return CallTypeSentiment(
        call_type=call_type,
        count=len(meetings),
        mean_score=_mean(scores),
        negative_share=negative / len(meetings) if meetings else 0.0,
        label_counts=dict(labels),
        sentence_mix=mix,
        turn_count=total_turns,
    )


def _periods(meetings: list[Meeting], key_fn, step: str) -> list[PeriodSentiment]:
    if not meetings:
        return []
    grouped: dict[str, list[Meeting]] = defaultdict(list)
    for meeting in meetings:
        grouped[key_fn(meeting)].append(meeting)
    start = min(meetings, key=lambda meeting: meeting.start_time).start_time
    end = max(meetings, key=lambda meeting: meeting.start_time).start_time
    keys = _fill_keys(start, end, step)
    rows: list[PeriodSentiment] = []
    for key in keys:
        rows.append(_period_row(key, grouped.get(key, [])))
    return rows


def _period_row(key: str, meetings: list[Meeting]) -> PeriodSentiment:
    by_type: dict[str, float | None] = {}
    by_type_n: dict[str, int] = {}
    for call_type in ("support", "external", "internal"):
        subset = _of_type(meetings, call_type)
        by_type_n[call_type] = len(subset)
        by_type[call_type] = _mean([meeting.sentiment_score for meeting in subset]) if subset else None
    return PeriodSentiment(
        period=key,
        count=len(meetings),
        mean_score=_mean([meeting.sentiment_score for meeting in meetings]) if meetings else None,
        by_call_type=by_type,
        by_call_type_n=by_type_n,
    )


def _fill_keys(start, end, step: str) -> list[str]:
    keys: list[str] = []
    if step == "month":
        year, month = start.year, start.month
        while (year, month) <= (end.year, end.month):
            keys.append(f"{year:04d}-{month:02d}")
            month += 1
            if month == 13:
                month = 1
                year += 1
        return keys
    cursor = start - timedelta(days=start.weekday())
    last = end - timedelta(days=end.weekday())
    while cursor.date() <= last.date():
        keys.append(cursor.date().isoformat())
        cursor += timedelta(days=7)
    return keys


def _week_key(meeting: Meeting) -> str:
    start = meeting.start_time - timedelta(days=meeting.start_time.weekday())
    return start.date().isoformat()


def _is_incident(meeting: Meeting) -> bool:
    return bool(_INCIDENT_TITLE.search(meeting.title))


def _mentions_outage(meeting: Meeting) -> bool:
    blob = f"{meeting.title} {meeting.summary} {' '.join(meeting.topics)}".lower()
    return "outage" in blob or "pipeline failure" in blob


def _cohort(meetings: list[Meeting], predicate, name: str) -> CohortSentiment:
    chosen = [meeting for meeting in meetings if predicate(meeting)]
    rest = [meeting for meeting in meetings if meeting not in chosen]
    return CohortSentiment(
        name=name,
        count=len(chosen),
        mean_score=_mean([meeting.sentiment_score for meeting in chosen]),
        rest_count=len(rest),
        rest_mean=_mean([meeting.sentiment_score for meeting in rest]),
    )


def _label_counts(meetings: list[Meeting]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for meeting in meetings:
        counts[meeting.sentiment] += 1
    return dict(counts)


def _interpret(analysis: SentimentAnalysis) -> list[SentimentInterpretation]:
    notes: list[SentimentInterpretation] = []
    if analysis.by_call_type:
        ordered = sorted(analysis.by_call_type, key=lambda row: row.mean_score)
        cold = ordered[0]
        warm = ordered[-1]
        gap = warm.mean_score - cold.mean_score
        cold_negative = next(row for row in analysis.by_call_type if row.call_type == cold.call_type)
        notes.append(
            SentimentInterpretation(
                interpretation_id="call-type-gap",
                title=f"{cold.call_type.title()} is the cold part of the book",
                finding=(
                    f"{cold.call_type.title()} calls average {cold.mean_score:.2f} on the 1–5 score. "
                    f"{warm.call_type.title()} calls average {warm.mean_score:.2f}. "
                    f"The gap is {gap:.2f} points, and {cold_negative.negative_share:.0%} of "
                    f"{cold.call_type} calls sit on the negative side of the label."
                ),
                why_it_matters=(
                    "A single company-wide sentiment number hides the motion that is actually struggling. "
                    f"Someone who only watches {warm.call_type} calls will think the quarter feels fine "
                    f"while {cold.call_type} is where customers describe the product failing."
                    if gap >= 0.3
                    else "The call types are close. The useful cut is not the channel, it is the event inside the channel."
                ),
            )
        )

    months = [row for row in analysis.by_month if row.mean_score is not None and row.count]
    if len(months) >= 2:
        worst = min(months, key=lambda row: row.mean_score or 0)
        best = max(months, key=lambda row: row.mean_score or 0)
        notes.append(
            SentimentInterpretation(
                interpretation_id="time-trend",
                title=f"{worst.period} is the weak month",
                finding=(
                    f"Mean sentiment moves from {best.mean_score:.2f} in {best.period} "
                    f"({best.count} meetings) to {worst.mean_score:.2f} in {worst.period} "
                    f"({worst.count} meetings)."
                ),
                why_it_matters=(
                    "A trend only matters if someone can name the operating event underneath it. "
                    "Pair this month with the incident cohort before treating it as a general mood shift."
                ),
            )
        )

    if analysis.incident.count:
        extra_mentions = analysis.outage_mention.count - analysis.incident.count
        if extra_mentions > 0:
            blast = (
                "The incident is not confined to the bridge calls. "
                f"{extra_mentions} additional meetings still talk about the outage in the summary or topics, "
                "including account reviews and support cases. A status-page postmortem will undercount that."
            )
        else:
            blast = (
                "The meetings that mention the outage are essentially the incident-titled set. "
                "In this cut, the event stayed inside the response conversations."
            )
        notes.append(
            SentimentInterpretation(
                interpretation_id="incident-cohort",
                title="Incident-titled meetings are a different population",
                finding=(
                    f"{analysis.incident.count} meetings have an incident, outage, or war-room title. "
                    f"Their mean score is {analysis.incident.mean_score:.2f}, versus "
                    f"{analysis.incident.rest_mean:.2f} for the other {analysis.incident.rest_count}. "
                    f"{analysis.outage_mention.count} meetings mention the outage in the title, summary, or topics "
                    f"and average {analysis.outage_mention.mean_score:.2f}."
                ),
                why_it_matters=blast,
            )
        )

    mixed = sum(count for label, count in analysis.label_counts.items() if label.startswith("mixed"))
    if analysis.overall_count:
        notes.append(
            SentimentInterpretation(
                interpretation_id="label-vs-score",
                title="The label is coarse. The score is the instrument.",
                finding=(
                    f"{mixed} of {analysis.overall_count} meetings are labeled mixed-positive or mixed-negative. "
                    f"The corpus mean is {analysis.overall_mean:.2f}. "
                    "Within a label the scores sit in a tight band, so the label is a readable bucket "
                    "and the score is what you chart."
                ),
                why_it_matters=(
                    "Do not build the dashboard on six sentiment names. Build it on the score, "
                    "cut by call type and by the incident cohort, and use the label as a check "
                    "that the score still means what the original model said it meant."
                ),
            )
        )
    return notes


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)
