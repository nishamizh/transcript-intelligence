"""Shared vocabulary for human review. Predictions are not labels."""

from __future__ import annotations

from src.analytics.topic_analyzer import THEMES

TAXONOMY_VERSION = "governed-themes-v1"
MODEL_VERSION = "lexical-nmf-8-seed-7"
SAMPLE_SEED = 7
SAMPLE_TARGET = 30
MIN_LABELED_TO_GENERALIZE = 30

THEME_IDS: tuple[str, ...] = tuple(theme.theme_id for theme in THEMES)
THEME_NAMES: dict[str, str] = {theme.theme_id: theme.name for theme in THEMES}
CALL_TYPE_ORDER: tuple[str, ...] = ("support", "external", "internal")

# A transcript is human-reviewed only after one of these is saved.
TOPIC_DECISIONS = frozenset({"approve", "correct", "ambiguous"})
# Older files used this set. They remain readable. They are not written by the new form.
LEGACY_TOPIC_DECISIONS = frozenset({"accept", "edit", "reject"})
INSIGHT_DECISIONS = frozenset({"accept", "reject", "needs_revision", "needs_more_evidence"})

TOPIC_REVIEWED = TOPIC_DECISIONS | LEGACY_TOPIC_DECISIONS
RESOLVED_INSIGHT_DECISIONS = frozenset({"accept", "reject"})


class DecisionSchemaError(ValueError):
    """A review row cannot be stored because a required field is missing or invalid."""


def require_reviewer(reviewer_id: str) -> str:
    cleaned = (reviewer_id or "").strip()
    if not cleaned:
        raise DecisionSchemaError("A reviewer id is required before a decision can be saved.")
    return cleaned


def require_topic_decision(decision: str, human_topic: str, predicted_topic: str) -> tuple[str, str]:
    choice = (decision or "").strip()
    if choice not in TOPIC_DECISIONS:
        raise DecisionSchemaError(
            "Choose approve, correct, or ambiguous. A blank decision is not a human review."
        )
    predicted = (predicted_topic or "").strip()
    if predicted not in THEME_IDS:
        raise DecisionSchemaError(f"Predicted topic {predicted!r} is not in the eight-theme taxonomy.")
    corrected = (human_topic or "").strip()
    if choice == "approve":
        return choice, predicted
    if choice == "ambiguous":
        return choice, ""
    if corrected not in THEME_IDS:
        raise DecisionSchemaError("A correction must name one of the eight governed themes.")
    return choice, corrected


def require_insight_decision(decision: str) -> str:
    choice = (decision or "").strip()
    if choice not in INSIGHT_DECISIONS:
        raise DecisionSchemaError(
            "Choose accept, reject, needs revision, or needs more evidence. Insights are not auto-approved."
        )
    return choice


def optional_rating(value: int | None, label: str) -> int | None:
    if value is None or value == "":
        return None
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise DecisionSchemaError(f"{label} must be a whole number from 1 to 5, or left blank.") from exc
    if number < 1 or number > 5:
        raise DecisionSchemaError(f"{label} must be from 1 to 5, or left blank.")
    return number
