"""Durable reviewer decisions.

Rows are keyed by item_id. Saving again keeps the previous row in `audit`
and does not create a second active decision. Reports never call this module
to fill in a label.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from src.review.decisions import atomic_write_json, load_decisions
from src.review.schema import (
    MODEL_VERSION,
    TAXONOMY_VERSION,
    DecisionSchemaError,
    optional_rating,
    require_insight_decision,
    require_reviewer,
    require_topic_decision,
)


class DecisionStore:
    def __init__(self, path: Path):
        self.path = Path(path)

    def load(self) -> dict:
        payload = load_decisions(self.path)
        payload["items"] = _collapse_items(payload.get("items", []))
        return payload

    def save_topic_review(
        self,
        *,
        item_id: str,
        predicted_topic: str,
        decision: str,
        human_topic: str,
        reviewer_id: str,
        notes: str = "",
        model_version: str = MODEL_VERSION,
        taxonomy_version: str = TAXONOMY_VERSION,
    ) -> dict:
        choice, gold = require_topic_decision(decision, human_topic, predicted_topic)
        reviewer = require_reviewer(reviewer_id)
        if not str(item_id or "").startswith("meeting:"):
            raise DecisionSchemaError("A topic review must use a meeting item id.")
        return self._save(
            item_id=item_id,
            updates={
                "item_id": item_id,
                "decision": choice,
                "predicted_topic": predicted_topic,
                "human_topic": gold,
                "corrected_theme": gold if choice == "correct" else "",
                "reviewer_id": reviewer,
                "notes": (notes or "").strip(),
                "reason": (notes or "").strip(),
                "model_version": model_version,
                "taxonomy_version": taxonomy_version,
                "corrected_recommendation": "",
                "evidence_quality": None,
                "business_usefulness": None,
            },
        )

    def save_insight_review(
        self,
        *,
        item_id: str,
        decision: str,
        reviewer_id: str,
        notes: str = "",
        corrected_recommendation: str = "",
        evidence_quality: int | None = None,
        business_usefulness: int | None = None,
        model_version: str = MODEL_VERSION,
        taxonomy_version: str = TAXONOMY_VERSION,
    ) -> dict:
        choice = require_insight_decision(decision)
        reviewer = require_reviewer(reviewer_id)
        if not str(item_id or "").startswith("insight:"):
            raise DecisionSchemaError("An insight review must use an insight item id.")
        quality = optional_rating(evidence_quality, "Evidence quality")
        usefulness = optional_rating(business_usefulness, "Business usefulness")
        recommendation = "" if choice == "accept" else (corrected_recommendation or "").strip()
        return self._save(
            item_id=item_id,
            updates={
                "item_id": item_id,
                "decision": choice,
                "predicted_topic": "",
                "human_topic": "",
                "corrected_theme": "",
                "reviewer_id": reviewer,
                "notes": (notes or "").strip(),
                "reason": (notes or "").strip(),
                "model_version": model_version,
                "taxonomy_version": taxonomy_version,
                "corrected_recommendation": recommendation,
                "evidence_quality": quality,
                "business_usefulness": usefulness,
            },
        )

    def _save(self, *, item_id: str, updates: dict) -> dict:
        payload = load_decisions(self.path)
        items = _collapse_items(payload.get("items", []))
        now = datetime.now(timezone.utc).isoformat()
        current = next((item for item in items if item.get("item_id") == item_id), None)
        if current is not None and _same_review(current, updates):
            return current
        audit = list(current.get("audit") or []) if current else []
        if current and _has_review(current):
            audit.append(_snapshot(current, now))
        review_id = f"{item_id}:r{len(audit) + 1}"
        stored = {
            "item_id": item_id,
            "review_id": review_id,
            "decision": updates["decision"],
            "predicted_topic": updates.get("predicted_topic") or "",
            "human_topic": updates.get("human_topic") or "",
            "corrected_theme": updates.get("corrected_theme") or "",
            "reviewer_id": updates["reviewer_id"],
            "reviewer_timestamp": now,
            "notes": updates.get("notes") or "",
            "reason": updates.get("reason") or "",
            "model_version": updates.get("model_version") or MODEL_VERSION,
            "taxonomy_version": updates.get("taxonomy_version") or TAXONOMY_VERSION,
            "corrected_recommendation": updates.get("corrected_recommendation") or "",
            "evidence_quality": updates.get("evidence_quality"),
            "business_usefulness": updates.get("business_usefulness"),
            "audit": audit,
        }
        replaced = False
        rewritten: list[dict] = []
        for item in items:
            if item.get("item_id") == item_id:
                if not replaced:
                    rewritten.append(stored)
                    replaced = True
                continue
            rewritten.append(item)
        if not replaced:
            rewritten.append(stored)
        atomic_write_json(self.path, {"version": 2, "items": rewritten})
        return stored


def _collapse_items(items: list[dict]) -> list[dict]:
    """One active row per item id. A filled decision beats a later blank row."""

    ordered: list[str] = []
    by_id: dict[str, dict] = {}
    for item in items:
        item_id = item.get("item_id")
        if not item_id:
            continue
        previous = by_id.get(item_id)
        if previous is None:
            ordered.append(item_id)
            by_id[item_id] = item
            continue
        if previous.get("decision") and not item.get("decision"):
            continue
        by_id[item_id] = item
    return [by_id[item_id] for item_id in ordered]


def _has_review(item: dict) -> bool:
    return bool((item.get("decision") or "").strip())


def _same_review(current: dict, updates: dict) -> bool:
    if not _has_review(current):
        return False
    keys = (
        "decision",
        "human_topic",
        "corrected_theme",
        "reviewer_id",
        "notes",
        "corrected_recommendation",
        "evidence_quality",
        "business_usefulness",
    )
    return all(current.get(key) == updates.get(key) for key in keys)


def _snapshot(item: dict, replaced_at: str) -> dict:
    return {
        "review_id": item.get("review_id") or "",
        "decision": item.get("decision") or "",
        "predicted_topic": item.get("predicted_topic") or "",
        "human_topic": item.get("human_topic") or "",
        "corrected_theme": item.get("corrected_theme") or "",
        "reviewer_id": item.get("reviewer_id") or "",
        "reviewer_timestamp": item.get("reviewer_timestamp") or "",
        "notes": item.get("notes") or item.get("reason") or "",
        "corrected_recommendation": item.get("corrected_recommendation") or "",
        "evidence_quality": item.get("evidence_quality"),
        "business_usefulness": item.get("business_usefulness"),
        "replaced_at": replaced_at,
    }
