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
    TOPIC_STATUS,
    DecisionSchemaError,
    optional_rating,
    require_finding_decision,
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
        source_document_hash: str = "",
        adjudicate: bool = False,
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
                "source_document_hash": (source_document_hash or "").strip(),
                "transcript_id": item_id.split(":", 1)[1],
                "adjudicate": adjudicate,
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
        source_document_hash: str = "",
        adjudicate: bool = False,
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
                "source_document_hash": (source_document_hash or "").strip(),
                "transcript_id": "",
                "adjudicate": adjudicate,
            },
        )

    def save_finding_review(
        self,
        *,
        insight_id: str,
        decision: str,
        reviewer_id: str,
        notes: str = "",
        checked_sources: list[str] | None = None,
        model_version: str = MODEL_VERSION,
        taxonomy_version: str = TAXONOMY_VERSION,
    ) -> dict:
        choice = require_finding_decision(decision)
        reviewer = require_reviewer(reviewer_id)
        item_id = f"finding:{insight_id}"
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
                "corrected_recommendation": "",
                "evidence_quality": None,
                "business_usefulness": None,
                "source_document_hash": "",
                "transcript_id": "",
                "checked_sources": [source for source in (checked_sources or []) if source],
                "adjudicate": False,
            },
        )

    def _save(self, *, item_id: str, updates: dict) -> dict:
        payload = load_decisions(self.path)
        items = _collapse_items(payload.get("items", []))
        now = datetime.now(timezone.utc).isoformat()
        current = next((item for item in items if item.get("item_id") == item_id), None)
        if current is not None and _same_review(current, updates) and not updates.get("adjudicate"):
            return current
        submissions = _submissions(current)
        submission = {
            "review_id": f"{item_id}:s{len(submissions) + 1}",
            "decision": updates["decision"],
            "human_topic": updates.get("human_topic") or "",
            "corrected_theme": updates.get("corrected_theme") or "",
            "reviewer_id": updates["reviewer_id"],
            "reviewer_timestamp": now,
            "notes": updates.get("notes") or "",
            "source_document_hash": updates.get("source_document_hash") or "",
        }
        submissions = [row for row in submissions if row.get("reviewer_id") != updates["reviewer_id"]]
        submissions.append(submission)
        conflict = len({(row["decision"], row.get("human_topic") or "") for row in submissions}) > 1
        adjudicate = bool(updates.get("adjudicate"))
        preserve_active = (
            current is not None
            and _has_review(current)
            and conflict
            and not adjudicate
            and current.get("reviewer_id") != updates["reviewer_id"]
        )
        if preserve_active:
            stored = dict(current)
            stored["submissions"] = submissions
            stored["conflict"] = True
            stored["adjudication_required"] = True
            stored["adjudicated"] = False
            stored["review_status"] = "conflict"
            stored["checked_sources"] = updates.get("checked_sources") or current.get("checked_sources") or []
            self._write(items, item_id, stored)
            return stored
        audit = list(current.get("audit") or []) if current else []
        if current and _has_review(current):
            audit.append(_snapshot(current, now))
        review_id = f"{item_id}:r{len(audit) + 1}"
        active_conflict = conflict and not adjudicate
        stored = {
            "item_id": item_id,
            "review_id": review_id,
            "transcript_id": updates.get("transcript_id") or (current or {}).get("transcript_id") or "",
            "decision": updates["decision"],
            "review_status": "adjudicated" if adjudicate else ("conflict" if active_conflict else _review_status(updates["decision"])),
            "predicted_topic": updates.get("predicted_topic") or "",
            "human_topic": updates.get("human_topic") or "",
            "corrected_theme": updates.get("corrected_theme") or "",
            "reviewer_id": updates["reviewer_id"],
            "reviewer_timestamp": now,
            "notes": updates.get("notes") or "",
            "reason": updates.get("reason") or "",
            "reviewer_notes": updates.get("notes") or "",
            "model_version": updates.get("model_version") or MODEL_VERSION,
            "taxonomy_version": updates.get("taxonomy_version") or TAXONOMY_VERSION,
            "source_document_hash": updates.get("source_document_hash") or "",
            "corrected_recommendation": updates.get("corrected_recommendation") or "",
            "evidence_quality": updates.get("evidence_quality"),
            "business_usefulness": updates.get("business_usefulness"),
            "checked_sources": list(updates.get("checked_sources") or []),
            "submissions": submissions,
            "conflict": active_conflict,
            "adjudication_required": active_conflict,
            "adjudicated": adjudicate,
            "adjudicator_id": updates["reviewer_id"] if adjudicate else "",
            "audit": audit,
        }
        self._write(items, item_id, stored)
        return stored

    def _write(self, items: list[dict], item_id: str, stored: dict) -> None:
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


def _submissions(current: dict | None) -> list[dict]:
    if not current:
        return []
    rows = [dict(row) for row in current.get("submissions") or []]
    if rows or not _has_review(current):
        return rows
    return [
        {
            "review_id": current.get("review_id") or "",
            "decision": current.get("decision") or "",
            "human_topic": current.get("human_topic") or "",
            "corrected_theme": current.get("corrected_theme") or "",
            "reviewer_id": current.get("reviewer_id") or "",
            "reviewer_timestamp": current.get("reviewer_timestamp") or "",
            "notes": current.get("notes") or current.get("reason") or "",
            "source_document_hash": current.get("source_document_hash") or "",
        }
    ]


def _review_status(decision: str) -> str:
    return TOPIC_STATUS.get(decision, decision or "pending")


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
