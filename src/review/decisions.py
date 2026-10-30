"""Reviewer decisions live beside the report and never replace it."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

DECISIONS = {"accept", "edit", "reject", ""}


def load_decisions(path: Path) -> dict:
    if not path.exists():
        return {"version": 1, "items": []}
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.setdefault("version", 1)
    payload.setdefault("items", [])
    return payload


def atomic_write_json(path: Path, payload: dict) -> None:
    """Replace a JSON file only after the new bytes are flushed.

    A crash during the write leaves the previous file in place.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    )
    tmp_name = handle.name
    try:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
        handle.close()
        os.replace(tmp_name, path)
    except Exception:
        handle.close()
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def ensure_decision_template(path: Path, item_ids: list[str]) -> bool:
    """Add blank rows for new queue ids. Never change a decision that is already stored.

    Returns True when the file was written.
    """

    existing = load_decisions(path) if path.exists() else {"version": 1, "items": []}
    by_id: dict[str, dict] = {}
    for item in existing.get("items", []):
        item_id = item.get("item_id")
        if not item_id:
            continue
        previous = by_id.get(item_id)
        if previous is not None and previous.get("decision") and not item.get("decision"):
            continue
        by_id[item_id] = item
    unique_ids: list[str] = []
    seen_input: set[str] = set()
    for item_id in item_ids:
        if not item_id or item_id in seen_input:
            continue
        seen_input.add(item_id)
        unique_ids.append(item_id)
    changed = not path.exists()
    for item_id in unique_ids:
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
    for item_id in unique_ids:
        ordered.append(by_id[item_id])
        seen.add(item_id)
    for item_id, item in by_id.items():
        if item_id not in seen:
            ordered.append(item)
    version = existing.get("version", 1) if path.exists() else 1
    atomic_write_json(path, {"version": version, "items": ordered})
    return True
