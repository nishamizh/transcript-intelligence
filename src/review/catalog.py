"""Display records for the reviewer. Built from the report, never from invented text."""

from __future__ import annotations

from src.analytics.text_safety import redact_public_text
from src.review.schema import THEME_IDS, THEME_NAMES


def topic_cards(report: dict, sample: dict, decisions: dict, role: str) -> list[dict]:
    meetings = {row["meeting_id"]: row for row in report.get("meetings", [])}
    queue = {row["item_id"]: row for row in (report.get("review_queue") or {}).get("items", [])}
    saved = {row.get("item_id"): row for row in decisions.get("items", []) if row.get("item_id")}
    block = sample.get(role) or {}
    cards = []
    for item in block.get("items") or []:
        meeting = meetings.get(item.get("meeting_id")) or {}
        queued = queue.get(item.get("item_id")) or {}
        decision = saved.get(item.get("item_id")) or {}
        predicted = meeting.get("primary_theme") or item.get("predicted_topic") or ""
        labels = meeting.get("topics") or queued.get("original_labels") or []
        excerpt = queued.get("evidence_excerpt") or meeting.get("excerpt") or meeting.get("summary") or ""
        cards.append(
            {
                "item_id": item.get("item_id"),
                "transcript_id": item.get("meeting_id"),
                "title": meeting.get("title") or queued.get("title") or item.get("meeting_id"),
                "call_type": meeting.get("call_type") or item.get("call_type") or "",
                "original_topics": list(labels),
                "predicted_topic": predicted,
                "predicted_topic_name": THEME_NAMES.get(predicted, predicted),
                "other_topics": [
                    {"id": theme_id, "name": THEME_NAMES[theme_id]}
                    for theme_id in THEME_IDS
                    if theme_id != predicted
                ],
                "excerpt": redact_public_text(str(excerpt), limit=400),
                "rationale": _rationale(meeting, queued, predicted),
                "indicators": _indicators(meeting, queued),
                "selection_probability": item.get("selection_probability"),
                "sample_weight": item.get("sample_weight"),
                "reasons": item.get("reasons") or queued.get("reasons") or [],
                "also_in_representative": bool(item.get("also_in_representative")),
                "also_in_challenging": bool(item.get("also_in_challenging")),
                "decision": decision.get("decision") or "",
                "review_status": decision.get("review_status") or ("pending" if not decision.get("decision") else decision.get("decision")),
                "conflict": bool(decision.get("conflict")),
                "adjudicated": bool(decision.get("adjudicated")),
                "submissions": list(decision.get("submissions") or []),
                "model_version": decision.get("model_version") or "lexical-nmf-8-seed-7",
                "taxonomy_version": decision.get("taxonomy_version") or "governed-themes-v1",
                "human_topic": decision.get("human_topic") or decision.get("corrected_theme") or "",
                "notes": decision.get("notes") or decision.get("reason") or "",
                "reviewer_id": decision.get("reviewer_id") or "",
                "reviewer_timestamp": decision.get("reviewer_timestamp") or "",
                "review_id": decision.get("review_id") or "",
            }
        )
    return cards


def insight_cards(report: dict, decisions: dict) -> list[dict]:
    saved = {row.get("item_id"): row for row in decisions.get("items", []) if row.get("item_id")}
    cards = []
    for insight in report.get("insights") or []:
        item_id = f"insight:{insight.get('insight_id')}"
        decision = saved.get(item_id) or {}
        evidence = []
        for item in insight.get("evidence") or []:
            evidence.append(
                {
                    "meeting_id": item.get("meeting_id") or "",
                    "title": item.get("title") or "",
                    "quote": redact_public_text(str(item.get("quote") or ""), limit=320),
                }
            )
        cards.append(
            {
                "item_id": item_id,
                "insight_id": insight.get("insight_id") or "",
                "title": insight.get("title") or "",
                "description": insight.get("finding") or "",
                "why_it_matters": insight.get("why_it_matters") or "",
                "stakeholder": insight.get("stakeholder") or "",
                "stakeholder_label": {
                    "support": "Support",
                    "sales": "Sales",
                    "product": "Product",
                    "engineering": "Engineering",
                }.get(insight.get("stakeholder") or "", insight.get("stakeholder") or ""),
                "source_meeting_ids": [item.get("meeting_id") for item in insight.get("evidence") or [] if item.get("meeting_id")],
                "evidence": evidence,
                "recommendation": insight.get("recommendation") or "",
                "evidence_indicator": _evidence_indicator(insight),
                "decision": decision.get("decision") or "",
                "notes": decision.get("notes") or decision.get("reason") or "",
                "corrected_recommendation": decision.get("corrected_recommendation") or "",
                "evidence_quality": decision.get("evidence_quality"),
                "business_usefulness": decision.get("business_usefulness"),
                "reviewer_id": decision.get("reviewer_id") or "",
                "reviewer_timestamp": decision.get("reviewer_timestamp") or "",
                "review_id": decision.get("review_id") or "",
            }
        )
    return cards


def _rationale(meeting: dict, queued: dict, predicted: str) -> str:
    name = THEME_NAMES.get(predicted, predicted or "unassigned")
    labels = meeting.get("topics") or queued.get("original_labels") or []
    others = [
        THEME_NAMES.get(theme_id, theme_id)
        for theme_id in (meeting.get("governed_themes") or [])
        if theme_id and theme_id != predicted
    ]
    parts = [f"The model assigned {name}."]
    if labels:
        parts.append("Supplied labels: " + "; ".join(str(label) for label in labels) + ".")
    else:
        parts.append("This meeting has no supplied topic label.")
    if others:
        parts.append("Other governed themes also matched: " + ", ".join(others) + ".")
    generated = meeting.get("generated_topic") or queued.get("generated_topic")
    if generated:
        parts.append(f"The held-out TF-IDF/NMF topic is {generated}.")
    overlap = meeting.get("lexical_topic_overlap")
    if overlap is None:
        overlap = queued.get("lexical_topic_overlap")
    status = meeting.get("lexical_overlap_status") or queued.get("overlap_status") or ""
    if overlap is not None:
        parts.append(
            f"Lexical overlap with the supplied labels is {overlap}"
            + (f" ({status})." if status else ".")
            + " That overlap is a word-sharing check, not a confidence probability."
        )
    scores = queued.get("theme_scores") or {}
    if scores:
        ranked = sorted(scores.items(), key=lambda pair: -pair[1])[:3]
        shown = ", ".join(f"{THEME_NAMES.get(theme_id, theme_id)} {score}" for theme_id, score in ranked)
        parts.append(f"Keyword theme scores: {shown}.")
        if len(ranked) >= 2:
            margin = ranked[0][1] - ranked[1][1]
            parts.append(f"Margin between the top two scores: {margin:.2f}. A margin of 1 or less is why a case can land on the review queue.")
    return " ".join(parts)


def _indicators(meeting: dict, queued: dict) -> list[str]:
    rows = []
    overlap = meeting.get("lexical_topic_overlap")
    if overlap is None:
        overlap = queued.get("lexical_topic_overlap")
    status = meeting.get("lexical_overlap_status") or queued.get("overlap_status")
    if overlap is not None:
        rows.append(f"Lexical overlap {overlap}" + (f" · {status}" if status else ""))
    themes = meeting.get("governed_themes") or []
    if themes:
        rows.append(f"{len(themes)} governed theme{'s' if len(themes) != 1 else ''} matched")
    if queued.get("reasons"):
        rows.append("Queue flags: " + ", ".join(queued["reasons"]))
    if not rows:
        rows.append("No separate confidence score is stored for this assignment.")
    return rows


def _evidence_indicator(insight: dict) -> str:
    citations = len(insight.get("evidence") or [])
    label = insight.get("metric_label") or "Published metric"
    value = insight.get("metric_value") or "—"
    return (
        f"{label}: {value}. {citations} cited excerpt{'s' if citations != 1 else ''}. "
        "There is no separate model confidence on the insight. "
        "Use the optional 1–5 ratings if you want to score evidence quality or usefulness."
    )
