"""Items a reviewer can accept, edit, or reject without touching source files."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from src.analytics.insight_analyzer import Insight
from src.analytics.text_safety import redact_public_text
from src.analytics.topic_analyzer import (
    _THEME_BY_ID,
    keyword_in,
    overlap_status,
    theme_scores,
)
from src.models.meeting import Meeting

# Top two theme scores within this many points are ambiguous, not a second taxonomy.
AMBIGUOUS_SCORE_MARGIN = 1.0


def build_review_queue(meetings: list[Meeting], insights: list[Insight]) -> dict:
    items: list[dict] = []
    for meeting in sorted(meetings, key=lambda item: item.meeting_id):
        reasons = _meeting_reasons(meeting)
        if not reasons:
            continue
        scores = {theme_id: round(score, 4) for theme_id, score in theme_scores(meeting).items() if score > 0}
        items.append(
            {
                "item_id": f"meeting:{meeting.meeting_id}",
                "item_type": "meeting_classification",
                "meeting_id": meeting.meeting_id,
                "title": meeting.title,
                "call_type": meeting.call_type,
                "reasons": reasons,
                "predicted_theme": meeting.primary_theme,
                "predicted_theme_name": _theme_name(meeting.primary_theme),
                "original_labels": list(meeting.topics),
                "generated_topic": meeting.generated_topic,
                "lexical_topic_overlap": round(meeting.topic_agreement, 4),
                "overlap_status": overlap_status(meeting.topic_agreement),
                "theme_scores": scores,
                "evidence_excerpt": _meeting_excerpt(meeting),
                "cited_meeting_ids": [meeting.meeting_id],
                "insight_id": "",
                "stakeholder": "",
            }
        )

    for insight in insights:
        cited = [item.meeting_id for item in insight.evidence]
        quote = insight.evidence[0].quote if insight.evidence else ""
        items.append(
            {
                "item_id": f"insight:{insight.insight_id}",
                "item_type": "stakeholder_insight",
                "meeting_id": cited[0] if cited else "",
                "title": insight.title,
                "call_type": "",
                "reasons": ["stakeholder_insight"],
                "predicted_theme": "",
                "predicted_theme_name": "",
                "original_labels": [],
                "generated_topic": "",
                "lexical_topic_overlap": None,
                "overlap_status": "",
                "theme_scores": {},
                "evidence_excerpt": redact_public_text(quote, limit=280),
                "cited_meeting_ids": cited,
                "insight_id": insight.insight_id,
                "stakeholder": insight.stakeholder,
                "finding": insight.finding,
            }
        )

    return {
        "version": 1,
        "instructions": (
            "Record decisions in review_decisions.json. "
            "Accept, edit, or reject. An edit must name corrected_theme for a meeting item. "
            "A reason is free text. This queue is regenerated from the pipeline. "
            "It does not store decisions and it does not modify source meetings."
        ),
        "ambiguous_margin": AMBIGUOUS_SCORE_MARGIN,
        "item_count": len(items),
        "items": items,
    }


def write_review_queue(queue: dict, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "review_queue.json"
    csv_path = output_dir / "review_queue.csv"
    json_path.write_text(json.dumps(queue, indent=2) + "\n", encoding="utf-8")
    fields = [
        "item_id",
        "item_type",
        "meeting_id",
        "title",
        "reasons",
        "predicted_theme",
        "lexical_topic_overlap",
        "overlap_status",
        "cited_meeting_ids",
        "evidence_excerpt",
        "insight_id",
        "stakeholder",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for item in queue["items"]:
            row = dict(item)
            row["reasons"] = "|".join(item["reasons"])
            row["cited_meeting_ids"] = "|".join(item["cited_meeting_ids"])
            writer.writerow(row)
    return json_path, csv_path


def _meeting_reasons(meeting: Meeting) -> list[str]:
    reasons: list[str] = []
    if meeting.topic_agreement <= 0 and meeting.generated_terms:
        reasons.append("no_shared_tokens")
    scores = theme_scores(meeting)
    ranked = sorted(scores.values(), reverse=True)
    if ranked and ranked[0] > 0 and ranked[0] - ranked[1] <= AMBIGUOUS_SCORE_MARGIN:
        reasons.append("ambiguous_theme")
    return reasons


def _theme_name(theme_id: str) -> str:
    theme = _THEME_BY_ID.get(theme_id)
    return theme.name if theme else theme_id


def _meeting_excerpt(meeting: Meeting) -> str:
    theme = _THEME_BY_ID.get(meeting.primary_theme)
    keywords = list(theme.keywords) if theme else []
    for turn in meeting.turns:
        sentence = turn.sentence.strip()
        matched = next((keyword for keyword in keywords if _contains(sentence, keyword)), "")
        if sentence and matched:
            return redact_public_text(sentence, focus=matched)
    return redact_public_text(meeting.summary)


def _contains(text: str, keyword: str) -> bool:
    return keyword_in(text, keyword)
