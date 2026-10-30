"""Redact contact details before text is copied into a public report."""

from __future__ import annotations

import re

_EMAIL = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
_PHONE = re.compile(r"(?<!\d)(?:\+?1[-.\s]?)?(?:\(\d{3}\)|\d{3})[-.\s]\d{3}[-.\s]\d{4}\b")
_WHITESPACE = re.compile(r"\s+")


def redact_public_text(text: str, limit: int = 240, focus: str = "") -> str:
    """Collapse whitespace, hide emails and phone numbers, and cap the length.

    When the sentence is longer than the cap, the window prefers `focus` so the
    excerpt still contains the word that justified it. Nothing is paraphrased.
    """

    cleaned = _EMAIL.sub("[redacted-email]", text or "")
    cleaned = _PHONE.sub("[redacted-phone]", cleaned)
    cleaned = _WHITESPACE.sub(" ", cleaned).strip()
    if limit <= 0 or len(cleaned) <= limit:
        return cleaned
    start = 0
    found = cleaned.lower().find(focus.lower()) if focus else -1
    if found >= 0:
        start = max(0, found - (limit // 3))
    end = min(len(cleaned), start + limit)
    start = max(0, end - limit)
    if start > 0:
        space = cleaned.find(" ", start)
        if space != -1 and (found < 0 or space < found):
            start = space + 1
    if end < len(cleaned):
        space = cleaned.rfind(" ", start, end)
        if space > start:
            end = space
    snippet = cleaned[start:end].strip()
    if start > 0:
        snippet = "…" + snippet
    if end < len(cleaned):
        snippet = snippet + "…"
    return snippet
