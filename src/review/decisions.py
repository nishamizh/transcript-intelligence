"""Reviewer decisions live beside the report and never replace it."""

from __future__ import annotations

import json
from pathlib import Path

DECISIONS = {"accept", "edit", "reject", ""}


def load_decisions(path: Path) -> dict:
    if not path.exists():
        return {"version": 1, "items": []}
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.setdefault("version", 1)
    payload.setdefault("items", [])
    return payload


def ensure_decision_template(path: Path, item_ids: list[str]) -> bool:
    """Add blank rows for new queue ids. Never change a decision that is already stored.

    Returns True when the file was written.
    """

    existing = load_decisions(path) if path.exists() else {"version": 1, "items": []}
    by_id = {item["item_id"]: item for item in existing.get("items", []) if item.get("item_id")}
    changed = not path.exists()
    for item_id in item_ids:
        if item_id in by_id:
            continue
        by_id[item_id] = {
            "item_id": item_id,
            "decision": "",
            "corrected_theme": "",
            "reason": "",
        }
        changed = True
    if not changed:
        return False
    ordered: list[dict] = []
    seen: set[str] = set()
    for item_id in item_ids:
        ordered.append(by_id[item_id])
        seen.add(item_id)
    for item_id, item in by_id.items():
        if item_id not in seen:
            ordered.append(item)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"version": 1, "items": ordered}, indent=2) + "\n",
        encoding="utf-8",
    )
    return True
