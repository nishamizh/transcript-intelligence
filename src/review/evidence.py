"""Locate cited quotations in source files.

Finding a quote is a string check. It is not a judgment that the quote supports
the claim, and it is not a human review.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.review.context import normalize_passage, passage_in
from src.review.decisions import atomic_write_json

CALCULATION_VERSION = "evidence-locator-v1"
_QUALIFIERS = ("however", "although", "but ", "still ", "despite", "except", "not going to", "won't", "cannot")


def build_evidence_verification(data_dir: Path, report: dict, decisions: dict | None = None) -> dict:
    saved = {
        row.get("item_id"): row
        for row in (decisions or {}).get("items", [])
        if row.get("item_id")
    }
    findings = []
    quote_missing = 0
    quote_found = 0
    human_reviewed = 0
    human_insufficient = 0
    for insight in report.get("insights") or []:
        insight_id = insight.get("insight_id") or ""
        citations = []
        for index, item in enumerate(insight.get("evidence") or []):
            located = _locate(Path(data_dir), item.get("meeting_id") or "", item.get("quote") or "")
            if located["quote_status"] == "found":
                quote_found += 1
            else:
                quote_missing += 1
            located["passages_to_check"] = _qualifying_passages(
                Path(data_dir),
                item.get("meeting_id") or "",
                item.get("quote") or "",
            )
            located["citation_index"] = index
            citations.append(located)
        human = saved.get(f"finding:{insight_id}") or {}
        human_decision = human.get("decision") or ""
        if human_decision in {"supported", "partially_supported", "unsupported", "insufficient_evidence"}:
            human_reviewed += 1
        if human_decision == "insufficient_evidence":
            human_insufficient += 1
        findings.append(
            {
                "insight_id": insight_id,
                "title": insight.get("title") or "",
                "stakeholder": insight.get("stakeholder") or "",
                "claim": insight.get("finding") or "",
                "recommended_action": insight.get("recommendation") or "",
                "claim_kind": _claim_kind(insight_id),
                "known_limitations": _limitations(insight_id),
                "citations": citations,
                "automated_quote_status": "quotes_located" if citations and all(row["quote_status"] == "found" for row in citations) else "quote_missing",
                "human_support_status": human_decision or "pending",
                "human_reviewer_id": human.get("reviewer_id") or "",
                "human_timestamp": human.get("reviewer_timestamp") or "",
                "human_notes": human.get("notes") or human.get("reason") or "",
                "checked_sources": human.get("checked_sources") or [],
                "support_is_human": bool(human_decision),
            }
        )
    finding_count = len(findings)
    complete = finding_count > 0 and human_reviewed == finding_count
    return {
        "version": 1,
        "calculation_version": CALCULATION_VERSION,
        "label_source": "source_text_match_plus_optional_human_judgment",
        "llm_as_judge": False,
        "human_review_status": "complete" if complete else "not_yet_available",
        "finding_count": finding_count,
        "quotes_found": quote_found,
        "quotes_missing": quote_missing,
        "human_reviewed": human_reviewed,
        "human_insufficient_evidence": human_insufficient,
        "automated_quote_check": "mismatch" if quote_missing else "located",
        "note": (
            "quotes_found means the cited string occurs in the meeting's transcript, summary, or source key moment "
            "after whitespace and ellipsis are folded. It does not mean a person agreed the passage supports the claim. "
            "passages_to_check are nearby sentences with a contrast word. They are a reading aid, not contradictions. "
            "human_support_status stays pending until a reviewer saves supported, partially supported, unsupported, "
            "or insufficient evidence."
        ),
        "findings": findings,
    }


def write_evidence_verification(payload: dict, output_dir: Path) -> Path:
    path = output_dir / "evidence_verification.json"
    atomic_write_json(path, payload)
    return path


def _locate(data_dir: Path, meeting_id: str, quote: str) -> dict:
    folder = data_dir / meeting_id
    if not meeting_id or not folder.exists():
        return {
            "meeting_id": meeting_id,
            "quote": quote,
            "quote_status": "meeting_missing",
            "location": "",
            "source_file": "",
        }
    summary = _read_json(folder / "summary.json")
    transcript = _read_json(folder / "transcript.json")
    summary_text = str(summary.get("summary") or "")
    moment_text = " ".join(
        str(moment.get("text") or moment.get("summary") or "")
        for moment in (summary.get("keyMoments") or summary.get("key_moments") or [])
        if isinstance(moment, dict)
    )
    sentences = []
    rows = transcript.get("data") if isinstance(transcript, dict) else []
    for row in rows or []:
        if isinstance(row, dict) and row.get("sentence"):
            sentences.append(str(row["sentence"]))
    transcript_text = " ".join(sentences)
    needle = normalize_passage(quote)
    if needle and passage_in(transcript_text, quote):
        location = "transcript"
        source = "transcript.json"
        status = "found"
    elif needle and passage_in(summary_text, quote):
        location = "summary"
        source = "summary.json"
        status = "found"
    elif needle and passage_in(moment_text, quote):
        location = "key_moment"
        source = "summary.json"
        status = "found"
    else:
        location = ""
        source = ""
        status = "missing"
    return {
        "meeting_id": meeting_id,
        "quote": quote,
        "quote_status": status,
        "location": location,
        "source_file": source,
    }


def _qualifying_passages(data_dir: Path, meeting_id: str, quote: str) -> list[dict]:
    folder = data_dir / meeting_id
    transcript = _read_json(folder / "transcript.json") if folder.exists() else {}
    rows = transcript.get("data") if isinstance(transcript, dict) else []
    needle = normalize_passage(quote)
    found = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        sentence = str(row.get("sentence") or "").strip()
        folded = sentence.lower()
        if not sentence or (needle and needle[:40] in normalize_passage(sentence)):
            continue
        if any(token in folded for token in _QUALIFIERS):
            found.append(
                {
                    "speaker": row.get("speaker_name") or "",
                    "time_seconds": row.get("time"),
                    "sentence": sentence,
                    "screen": "contrast_word",
                    "note": "A sentence in the same transcript contains a contrast word. It is not a verdict.",
                }
            )
        if len(found) >= 3:
            break
    return found


def _claim_kind(insight_id: str) -> str:
    if insight_id in {"support-sentiment", "product-modules"}:
        return "descriptive_comparison"
    if insight_id in {"engineering-causes", "sales-at-risk"}:
        return "interpretive_rank"
    return "observed_count"


def _limitations(insight_id: str) -> str:
    notes = {
        "support-sentiment": "A difference of source sentiment means. Not an estimate of what caused the gap.",
        "product-modules": "Module cohorts are keyword assignments on the meeting text. A meeting can mention more than one product.",
        "engineering-causes": "Keyword buckets over recorded technical moments. Not a new root-cause analysis.",
        "engineering-incident": "Counted from the meeting title, not from a confirmed incident record.",
        "sales-at-risk": "Accounts are grouped by account name, or by the only external domain when the name is blank. The rank is not a churn probability.",
        "sales-competitors": "Counts use a configured competitor list. A name that is not on the list is not counted.",
        "support-recurring": "Share of support calls whose primary governed theme is reliability. The theme is a keyword map.",
        "support-unresolved": "Churn-signal moments with no positive-pivot moment. Both flags come from the source keyMoments list.",
        "product-gaps": "Count of source key moments tagged as a feature gap.",
    }
    return notes.get(insight_id, "See the finding text for what was counted.")


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}
