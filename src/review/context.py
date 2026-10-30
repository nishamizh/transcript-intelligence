"""Source context for a reviewer. Loaded from the meeting folder, then redacted."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from src.analytics.text_safety import redact_public_text

_SOURCE_FILES = ("meeting-info.json", "summary.json", "transcript.json")


def source_document_hash(data_dir: Path, meeting_id: str) -> str:
    folder = Path(data_dir) / meeting_id
    digest = hashlib.sha256()
    found = False
    for name in _SOURCE_FILES:
        path = folder / name
        if not path.exists():
            continue
        found = True
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
    if not found:
        return ""
    return digest.hexdigest()


def load_meeting_context(data_dir: Path, meeting_id: str, turn_limit: int = 40) -> dict:
    folder = Path(data_dir) / meeting_id
    transcript_path = folder / "transcript.json"
    summary_path = folder / "summary.json"
    turns: list[dict] = []
    summary = ""
    if summary_path.exists():
        summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
        summary = redact_public_text(str(summary_payload.get("summary") or ""), limit=600)
    if transcript_path.exists():
        payload = json.loads(transcript_path.read_text(encoding="utf-8"))
        rows = payload.get("data") if isinstance(payload, dict) else payload
        for row in rows or []:
            sentence = str(row.get("sentence") or "").strip()
            if not sentence:
                continue
            turns.append(
                {
                    "speaker": row.get("speaker_name") or "",
                    "time_seconds": row.get("time"),
                    "sentence": redact_public_text(sentence, limit=400),
                    "sentiment": row.get("sentimentType") or "",
                }
            )
    shown = turns[:turn_limit]
    return {
        "meeting_id": meeting_id,
        "available": transcript_path.exists(),
        "turn_count": len(turns),
        "shown": len(shown),
        "turns": shown,
        "summary": summary,
        "source_document_hash": source_document_hash(data_dir, meeting_id),
        "note": (
            "These are source transcript turns, redacted for email addresses and phone numbers. "
            "The short excerpt on the card is only a starting point."
        ),
    }


def normalize_passage(text: str) -> str:
    cleaned = text.replace("…", " ").replace("...", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = re.sub(r"^[A-Z][A-Za-z .'-]{0,40}:\s+", "", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip().lower()


def passage_in(haystack: str, quote: str) -> bool:
    needle = normalize_passage(quote)
    if len(needle) < 12:
        return False
    folded = re.sub(r"\s+", " ", haystack).lower()
    return needle in folded
