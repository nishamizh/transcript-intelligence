"""Score a reviewer file. Empty reviews stay unavailable. Nothing here is invented."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.analytics.topic_analyzer import THEMES
from src.review.decisions import DECISIONS, load_decisions

THEME_IDS = {theme.theme_id for theme in THEMES} | {"unclassified"}


def evaluate(report: dict, queue: dict, decisions: dict) -> dict:
    meetings = {meeting["meeting_id"] for meeting in report.get("meetings", [])}
    queue_items = {item["item_id"]: item for item in queue.get("items", [])}
    decision_rows = [row for row in decisions.get("items", []) if row.get("decision")]

    theme_pairs = _theme_pairs(queue_items, decision_rows)
    insight_rows = _insight_rows(queue_items, decision_rows)
    citation = _citation_completeness(report, meetings)

    if not theme_pairs:
        theme_block = {
            "status": "unavailable",
            "usable_labels": 0,
            "per_theme": [],
            "micro_precision": None,
            "micro_recall": None,
            "micro_f1": None,
            "macro_f1": None,
            "confusion": [],
            "note": "No meeting item has a usable accept or corrected theme. Accuracy is not estimated.",
        }
    else:
        theme_block = _theme_metrics(theme_pairs)
        theme_block["status"] = "measured"
        theme_block["usable_labels"] = len(theme_pairs)

    reviewed_insights = [row for row in insight_rows if row["decision"] in {"accept", "edit", "reject"}]
    if not reviewed_insights:
        acceptance = {
            "status": "unavailable",
            "reviewed": 0,
            "accepted": 0,
            "rate": None,
            "note": "No stakeholder insight has been accepted, edited, or rejected.",
        }
    else:
        accepted = sum(1 for row in reviewed_insights if row["decision"] == "accept")
        acceptance = {
            "status": "measured",
            "reviewed": len(reviewed_insights),
            "accepted": accepted,
            "rate": round(accepted / len(reviewed_insights), 4),
            "note": "Acceptance counts only decision=accept. Edit and reject are reviewed and not accepted.",
        }

    return {
        "theme_classification": theme_block,
        "insight_acceptance": acceptance,
        "citation_completeness": citation,
        "decisions_present": len(decision_rows),
        "ignored_blank_decisions": sum(1 for row in decisions.get("items", []) if not row.get("decision")),
    }


def _theme_pairs(queue_items: dict, decision_rows: list[dict]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for row in decision_rows:
        item = queue_items.get(row.get("item_id"))
        if not item or item.get("item_type") != "meeting_classification":
            continue
        decision = row.get("decision")
        if decision not in DECISIONS or decision == "":
            continue
        predicted = item.get("predicted_theme") or ""
        if decision == "accept":
            gold = predicted
        else:
            gold = (row.get("corrected_theme") or "").strip()
            if decision == "reject" and not gold:
                continue
            if decision == "edit" and gold not in THEME_IDS:
                continue
            if gold not in THEME_IDS:
                continue
        if predicted not in THEME_IDS or gold not in THEME_IDS:
            continue
        pairs.append((gold, predicted))
    return pairs


def _insight_rows(queue_items: dict, decision_rows: list[dict]) -> list[dict]:
    rows = []
    for row in decision_rows:
        item = queue_items.get(row.get("item_id"))
        if item and item.get("item_type") == "stakeholder_insight":
            rows.append(row)
    return rows


def _theme_metrics(pairs: list[tuple[str, str]]) -> dict:
    labels = sorted({gold for gold, _ in pairs} | {predicted for _, predicted in pairs})
    confusion: dict[tuple[str, str], int] = {}
    for gold, predicted in pairs:
        confusion[(gold, predicted)] = confusion.get((gold, predicted), 0) + 1

    per_theme = []
    f1_values: list[float] = []
    micro_tp = micro_fp = micro_fn = 0
    for label in labels:
        tp = sum(1 for gold, predicted in pairs if gold == label and predicted == label)
        fp = sum(1 for gold, predicted in pairs if gold != label and predicted == label)
        fn = sum(1 for gold, predicted in pairs if gold == label and predicted != label)
        precision = tp / (tp + fp) if tp + fp else None
        recall = tp / (tp + fn) if tp + fn else None
        f1 = None
        if precision is not None and recall is not None and precision + recall > 0:
            f1 = 2 * precision * recall / (precision + recall)
            f1_values.append(f1)
        micro_tp += tp
        micro_fp += fp
        micro_fn += fn
        per_theme.append(
            {
                "theme": label,
                "support": tp + fn,
                "precision": _round(precision),
                "recall": _round(recall),
                "f1": _round(f1),
            }
        )

    micro_precision = micro_tp / (micro_tp + micro_fp) if micro_tp + micro_fp else None
    micro_recall = micro_tp / (micro_tp + micro_fn) if micro_tp + micro_fn else None
    micro_f1 = None
    if micro_precision is not None and micro_recall is not None and micro_precision + micro_recall > 0:
        micro_f1 = 2 * micro_precision * micro_recall / (micro_precision + micro_recall)
    macro_f1 = sum(f1_values) / len(f1_values) if f1_values else None
    return {
        "per_theme": per_theme,
        "micro_precision": _round(micro_precision),
        "micro_recall": _round(micro_recall),
        "micro_f1": _round(micro_f1),
        "macro_f1": _round(macro_f1),
        "confusion": [
            {"gold": gold, "predicted": predicted, "count": count}
            for (gold, predicted), count in sorted(confusion.items())
        ],
        "note": (
            "Gold is the predicted theme on accept, and corrected_theme on edit or on reject when a "
            "corrected theme is present. Reject with no corrected theme is excluded from F1. "
            "Macro F1 averages only themes whose precision and recall are both defined."
        ),
    }


def _citation_completeness(report: dict, meetings: set[str]) -> dict:
    insights = report.get("insights") or []
    if not insights:
        return {
            "status": "unavailable",
            "rate": None,
            "complete": 0,
            "total": 0,
            "note": "The report has no insights to check.",
        }
    complete = 0
    for insight in insights:
        evidence = insight.get("evidence") or []
        if evidence and all(
            item.get("meeting_id") in meetings and str(item.get("quote") or "").strip()
            for item in evidence
        ):
            complete += 1
    return {
        "status": "measured",
        "rate": round(complete / len(insights), 4),
        "complete": complete,
        "total": len(insights),
        "note": (
            "Share of insights whose cited meeting ids exist in this report and whose quotes are non-empty. "
            "This is a structural check, not reviewer agreement and not accuracy."
        ),
    }


def _round(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 4)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate reviewer decisions against the pipeline report. Does not modify source meetings."
    )
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--queue", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)
    report = json.loads(args.report.read_text(encoding="utf-8"))
    queue_path = args.queue or args.report.parent / "review_queue.json"
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    decisions = load_decisions(args.decisions)
    result = evaluate(report, queue, decisions)
    text = json.dumps(result, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    theme_status = result["theme_classification"]["status"]
    acceptance_status = result["insight_acceptance"]["status"]
    print(
        f"Theme metrics: {theme_status}. Insight acceptance: {acceptance_status}. "
        f"Citation completeness: {result['citation_completeness']['status']}."
    )


if __name__ == "__main__":
    main()
