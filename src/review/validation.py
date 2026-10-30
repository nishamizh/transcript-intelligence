"""Human-validated metrics.

Numbers are computed only from adjudicated reviewer decisions.
An empty file stays NOT YET AVAILABLE. Nothing in this module writes a decision.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sklearn.metrics import accuracy_score, confusion_matrix, precision_recall_fscore_support

from src.review.decisions import load_decisions
from src.review.sample import build_review_sample
from src.review.schema import (
    MIN_LABELED_TO_GENERALIZE,
    MODEL_VERSION,
    TAXONOMY_VERSION,
    THEME_IDS,
    THEME_NAMES,
    TOPIC_EXCLUDED_FROM_ACCURACY,
    TOPIC_REVIEWED,
)

STAKEHOLDER_LABELS = {
    "support": "Support",
    "sales": "Sales",
    "product": "Product",
    "engineering": "Engineering",
}


def build_human_validation_report(
    report: dict,
    sample: dict,
    decisions: dict,
    evidence: dict | None = None,
    claims: dict | None = None,
) -> dict:
    meetings = {row["meeting_id"]: row for row in report.get("meetings", []) if row.get("meeting_id")}
    active = _active_decisions(decisions.get("items", []))
    by_item = {row["item_id"]: row for row in active}
    representative = _topic_block(
        sample.get("representative", {}).get("items", []),
        by_item,
        meetings,
        weighted=True,
    )
    challenging = _topic_block(
        sample.get("challenging", {}).get("items", []),
        by_item,
        meetings,
        weighted=False,
    )
    insights = _insight_block(report.get("insights") or [], by_item)
    topic_ready = representative["status"] == "measured"
    insight_ready = insights["acceptance_rate"]["value"] is not None
    findings = evidence or _empty_evidence()
    claim_audit = claims or _empty_claims()
    findings_ready = findings.get("human_review_status") == "complete"
    return {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "taxonomy_version": sample.get("taxonomy_version") or TAXONOMY_VERSION,
        "model_version": _model_version(report),
        "label_source": "human_review_decisions",
        "llm_as_judge": False,
        "synthetic_labels": False,
        "single_label": True,
        "data_gap": {
            "resolved": bool(topic_ready and insight_ready and findings_ready),
            "topic_classification": "RESOLVED" if topic_ready else "NOT YET AVAILABLE",
            "insight_acceptance": "NOT YET AVAILABLE" if insights["acceptance_rate"]["value"] is None else "MEASURED",
            "finding_support": "NOT YET AVAILABLE" if not findings_ready else "REVIEWED",
            "reason": (
                "Theme accuracy, insight acceptance, and finding support stay unavailable until real reviewers "
                "save adjudicated decisions. A quote that is present in a transcript is not a support judgment. "
                "A claims-audit match is a reproducibility check, not human validation. "
                "This file does not contain invented labels, and an LLM was not used as a judge."
            ),
        },
        "leakage": {
            "corrections_used_for_training": False,
            "sample_seen_by_unsupervised_model": True,
            "note": (
                "Reviewer corrections are read only when metrics are scored. They are not written back into "
                "the keyword taxonomy or the TF-IDF/NMF fit. The lexical model was fit on every transcript, "
                "including those later drawn for review. It is a diagnostic. The governed category is the "
                "keyword assignment, and the review sample is stratified on that predicted category plus call type, "
                "not on a gold label."
            ),
        },
        "sampling": {
            "seed": sample.get("seed"),
            "target": sample.get("target"),
            "method": sample.get("method"),
            "population_meetings": sample.get("population_meetings"),
            "representative_count": sample.get("representative", {}).get("count", 0),
            "challenging_count": sample.get("challenging", {}).get("count", 0),
            "overlap_count": sample.get("overlap_count", 0),
            "allocation": sample.get("representative", {}).get("allocation", []),
            "strata": sample.get("representative", {}).get("strata", []),
            "coverage": sample.get("representative", {}).get("coverage", {}),
            "challenging_bias": sample.get("challenging", {}).get("bias", ""),
            "pooling": sample.get("pooling", ""),
        },
        "topic_classification": {
            "representative": representative,
            "challenging": challenging,
            "pooling_note": sample.get("pooling")
            or "Representative and challenging accuracies are not combined.",
        },
        "business_insights": insights,
        "findings_verification": findings,
        "claims_audit": claim_audit,
        "readiness": _readiness(representative, insights, findings, claim_audit),
        "ignored_duplicate_rows": _duplicate_count(decisions.get("items", [])),
    }


def write_human_validation_report(payload: dict, output_dir: Path) -> tuple[Path, Path]:
    from src.review.decisions import atomic_write_json

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "human_validation_report.json"
    csv_path = output_dir / "human_validation_report.csv"
    atomic_write_json(json_path, payload)
    _write_csv(payload, csv_path)
    return json_path, csv_path


def _topic_block(items: list[dict], by_item: dict[str, dict], meetings: dict[str, dict], *, weighted: bool) -> dict:
    assigned = len(items)
    reviewed_rows = []
    ambiguous = 0
    insufficient_evidence = 0
    conflicts = 0
    eligible = []
    for item in items:
        decision = by_item.get(item["item_id"])
        if not decision or (decision.get("decision") or "") not in TOPIC_REVIEWED:
            continue
        reviewed_rows.append(decision)
        choice = decision.get("decision")
        if decision.get("conflict") and not decision.get("adjudicated"):
            conflicts += 1
            continue
        if choice == "ambiguous":
            ambiguous += 1
            continue
        if choice == "insufficient_evidence":
            insufficient_evidence += 1
            continue
        if choice in TOPIC_EXCLUDED_FROM_ACCURACY:
            continue
        predicted = _predicted(item, meetings)
        gold = _gold(decision, predicted)
        if gold is None or predicted not in THEME_IDS:
            continue
        weight = item.get("sample_weight")
        eligible.append(
            {
                "gold": gold,
                "predicted": predicted,
                "weight": float(weight) if weight else 1.0,
            }
        )
    unresolved = assigned - len(reviewed_rows)
    metrics = _classification_metrics(eligible, weighted=weighted and bool(eligible))
    status, generalizes, warning = _topic_status(assigned, len(eligible))
    disagreement = None
    if eligible:
        disagreement = sum(1 for row in eligible if row["gold"] != row["predicted"]) / len(eligible)
    return {
        "status": status,
        "headline": "NOT YET AVAILABLE" if status != "measured" else "MEASURED",
        "generalizes": generalizes,
        "warning": warning,
        "assigned": assigned,
        "reviewed": len(reviewed_rows),
        "eligible": len(eligible),
        "ambiguous": ambiguous,
        "insufficient_evidence": insufficient_evidence,
        "unadjudicated_conflicts": conflicts,
        "unresolved": unresolved,
        "completion": _rate(len(reviewed_rows), assigned, kind="count"),
        "ambiguous_proportion": _rate(ambiguous, assigned, kind="count"),
        "insufficient_evidence_proportion": _rate(insufficient_evidence, assigned, kind="count"),
        "unresolved_proportion": _rate(unresolved, assigned, kind="count"),
        "reviewer_disagreement_rate": _reviewer_disagreement(reviewed_rows),
        "accuracy_interval": _wilson_interval(
            sum(1 for row in eligible if row["gold"] == row["predicted"]),
            len(eligible),
        ),
        "disagreement_rate": _rate(
            sum(1 for row in eligible if row["gold"] != row["predicted"]),
            len(eligible),
            kind="metric",
        )
        if eligible
        else _empty_metric(),
        "accuracy": metrics["accuracy"],
        "macro_precision": metrics["macro_precision"],
        "macro_recall": metrics["macro_recall"],
        "macro_f1": metrics["macro_f1"],
        "weighted_precision": metrics["weighted_precision"],
        "weighted_recall": metrics["weighted_recall"],
        "weighted_f1": metrics["weighted_f1"],
        "population_estimates": metrics["population_estimates"],
        "per_category": metrics["per_category"],
        "confusion_matrix": metrics["confusion_matrix"],
        "disagreement_value": round(disagreement, 6) if disagreement is not None else None,
        "note": (
            "Eligible rows are confirmed predictions, or corrections that name one of the eight themes, "
            "plus older accept and edit rows that name a theme, after any conflict has been adjudicated. "
            "Ambiguous, insufficient evidence, pending, and unadjudicated conflicts stay out of precision, recall, F1, and accuracy. "
            "They remain in the review-coverage counts. "
            "The confusion matrix counts labeled rows. It is not weighted. "
            "Strata were drawn on the predicted theme, not on a gold label. "
            "Population estimates weight each representative row by the inverse of its selection probability. "
            "The accuracy interval is a Wilson 95% interval on the labeled rows and is not a design-based variance. "
            "Macro averages skip themes with no labeled support, and skip an undefined precision rather than treating it as zero. "
            "Reviewer corrections are not used to refit the topic model."
        ),
    }


def _classification_metrics(eligible: list[dict], *, weighted: bool) -> dict:
    empty_categories = [
        {
            "theme": theme_id,
            "name": THEME_NAMES[theme_id],
            "precision": None,
            "recall": None,
            "f1": None,
            "support": 0,
        }
        for theme_id in THEME_IDS
    ]
    empty_matrix = {
        "labels": list(THEME_IDS),
        "label_names": [THEME_NAMES[theme_id] for theme_id in THEME_IDS],
        "counts": [[0 for _ in THEME_IDS] for _ in THEME_IDS],
        "rows": "human_topic",
        "columns": "predicted_topic",
    }
    if not eligible:
        return {
            "accuracy": _empty_metric(),
            "macro_precision": _empty_metric(),
            "macro_recall": _empty_metric(),
            "macro_f1": _empty_metric(),
            "weighted_precision": _empty_metric(),
            "weighted_recall": _empty_metric(),
            "weighted_f1": _empty_metric(),
            "population_estimates": None,
            "per_category": empty_categories,
            "confusion_matrix": empty_matrix,
        }
    y_true = [row["gold"] for row in eligible]
    y_pred = [row["predicted"] for row in eligible]
    sample = _score_vectors(y_true, y_pred, sample_weight=None)
    population = None
    if weighted:
        weights = np.asarray([row["weight"] for row in eligible], dtype=float)
        population = _score_vectors(y_true, y_pred, sample_weight=weights)
        population = {
            "accuracy": population["accuracy"],
            "macro_precision": population["macro_precision"],
            "macro_recall": population["macro_recall"],
            "macro_f1": population["macro_f1"],
            "weighted_precision": population["weighted_precision"],
            "weighted_recall": population["weighted_recall"],
            "weighted_f1": population["weighted_f1"],
            "note": (
                "Weighted by 1 / selection probability so a rare stratum is not drowned by a common one. "
                "This is an estimate for the stratified sample only. It is not the challenging-case result."
            ),
        }
    return {
        "accuracy": sample["accuracy"],
        "macro_precision": sample["macro_precision"],
        "macro_recall": sample["macro_recall"],
        "macro_f1": sample["macro_f1"],
        "weighted_precision": sample["weighted_precision"],
        "weighted_recall": sample["weighted_recall"],
        "weighted_f1": sample["weighted_f1"],
        "population_estimates": population,
        "per_category": sample["per_category"],
        "confusion_matrix": sample["confusion_matrix"],
    }


def _score_vectors(y_true: list[str], y_pred: list[str], sample_weight) -> dict:
    labels = list(THEME_IDS)
    precision, recall, f1, support = precision_recall_fscore_support(
        y_true,
        y_pred,
        labels=labels,
        average=None,
        sample_weight=sample_weight,
        zero_division=np.nan,
    )
    present = [index for index, count in enumerate(support) if count > 0]
    accuracy = float(accuracy_score(y_true, y_pred, sample_weight=sample_weight))
    macro_precision = _nanmean([precision[index] for index in present])
    macro_recall = _nanmean([recall[index] for index in present])
    macro_f1 = _nanmean([f1[index] for index in present])
    present_labels = [labels[index] for index in present] or labels
    weighted_precision, weighted_recall, weighted_f1, _ = precision_recall_fscore_support(
        y_true,
        y_pred,
        labels=present_labels,
        average="weighted",
        sample_weight=sample_weight,
        zero_division=np.nan,
    )
    matrix = confusion_matrix(y_true, y_pred, labels=labels, sample_weight=None)
    per_category = []
    for index, theme_id in enumerate(labels):
        count = float(support[index])
        per_category.append(
            {
                "theme": theme_id,
                "name": THEME_NAMES[theme_id],
                "precision": _clean(precision[index]) if count > 0 else None,
                "recall": _clean(recall[index]) if count > 0 else None,
                "f1": _clean(f1[index]) if count > 0 else None,
                "support": int(round(count)) if sample_weight is None else round(count, 4),
            }
        )
    return {
        "accuracy": _metric(accuracy, len(y_true)),
        "macro_precision": _metric(macro_precision, len(present)),
        "macro_recall": _metric(macro_recall, len(present)),
        "macro_f1": _metric(macro_f1, len(present)),
        "weighted_precision": _metric(_finite(weighted_precision), len(y_true)),
        "weighted_recall": _metric(_finite(weighted_recall), len(y_true)),
        "weighted_f1": _metric(_finite(weighted_f1), len(y_true)),
        "per_category": per_category,
        "confusion_matrix": {
            "labels": labels,
            "label_names": [THEME_NAMES[theme_id] for theme_id in labels],
            "counts": [[int(value) for value in row] for row in matrix.tolist()],
            "rows": "human_topic",
            "columns": "predicted_topic",
        },
    }


def _insight_block(insights: list[dict], by_item: dict[str, dict]) -> dict:
    total = len(insights)
    buckets = {"accept": 0, "reject": 0, "needs_revision": 0, "needs_more_evidence": 0}
    quality_scores: list[int] = []
    usefulness_scores: list[int] = []
    by_stakeholder: dict[str, dict[str, int]] = {}
    reviewed = 0
    for insight in insights:
        stakeholder = insight.get("stakeholder") or "unspecified"
        bucket = by_stakeholder.setdefault(
            stakeholder,
            {"accept": 0, "reject": 0, "needs_revision": 0, "needs_more_evidence": 0, "reviewed": 0, "total": 0},
        )
        bucket["total"] += 1
        decision = by_item.get(f"insight:{insight.get('insight_id')}")
        choice = (decision or {}).get("decision") or ""
        if choice not in INSIGHT_COUNTED:
            continue
        reviewed += 1
        bucket["reviewed"] += 1
        if choice in buckets:
            buckets[choice] += 1
            bucket[choice] += 1
        if decision:
            quality = decision.get("evidence_quality")
            usefulness = decision.get("business_usefulness")
            if isinstance(quality, int) and 1 <= quality <= 5:
                quality_scores.append(quality)
            if isinstance(usefulness, int) and 1 <= usefulness <= 5:
                usefulness_scores.append(usefulness)
    resolved = buckets["accept"] + buckets["reject"]
    awaiting = total - reviewed
    return {
        "total": total,
        "awaiting_review": awaiting,
        "reviewed": reviewed,
        "accepted": buckets["accept"],
        "rejected": buckets["reject"],
        "needs_revision": buckets["needs_revision"],
        "needs_more_evidence": buckets["needs_more_evidence"],
        "review_coverage": _rate(reviewed, total, kind="count"),
        "acceptance_rate": _rate(buckets["accept"], resolved, kind="metric") if resolved else _empty_metric(),
        "approval_coverage": _rate(buckets["accept"], total, kind="metric") if reviewed else _empty_metric(),
        "mean_evidence_quality": _mean_rating(quality_scores),
        "mean_business_usefulness": _mean_rating(usefulness_scores),
        "by_stakeholder": [
            _stakeholder_row(name, row) for name, row in sorted(by_stakeholder.items())
        ],
        "note": (
            "Acceptance rate is accepted / (accepted + rejected). "
            "Needs revision and needs more evidence are reviewed, and they are not in that denominator. "
            "If nothing has been accepted or rejected, the rate is N/A rather than 0% or 100%. "
            "Approval coverage is accepted / all insights, and is N/A when nothing has been reviewed. "
            "No insight is accepted by default."
        ),
    }


INSIGHT_COUNTED = frozenset({"accept", "reject", "needs_revision", "needs_more_evidence", "edit"})


def _stakeholder_row(name: str, row: dict) -> dict:
    resolved = row["accept"] + row["reject"]
    return {
        "stakeholder": name,
        "label": STAKEHOLDER_LABELS.get(name, name.replace("_", " ").title()),
        "total": row["total"],
        "reviewed": row["reviewed"],
        "accepted": row["accept"],
        "rejected": row["reject"],
        "needs_revision": row["needs_revision"],
        "needs_more_evidence": row["needs_more_evidence"],
        "acceptance_rate": _rate(row["accept"], resolved, kind="metric") if resolved else _empty_metric(),
    }


def _gold(decision: dict, predicted: str) -> str | None:
    choice = decision.get("decision") or ""
    human = (decision.get("human_topic") or decision.get("corrected_theme") or "").strip()
    if choice in {"approve", "accept"}:
        gold = human if human in THEME_IDS else predicted
        return gold if gold in THEME_IDS else None
    if choice in {"correct", "edit", "reject"}:
        return human if human in THEME_IDS else None
    return None


def _predicted(item: dict, meetings: dict[str, dict]) -> str:
    meeting = meetings.get(item.get("meeting_id") or "")
    if meeting and meeting.get("primary_theme") in THEME_IDS:
        return meeting["primary_theme"]
    predicted = item.get("predicted_topic") or ""
    return predicted


def _topic_status(assigned: int, eligible: int) -> tuple[str, bool, str]:
    if eligible <= 0:
        return (
            "not_yet_available",
            False,
            "No adjudicated human labels yet. Accuracy, precision, recall, and F1 are not calculated.",
        )
    needed = min(MIN_LABELED_TO_GENERALIZE, assigned) if assigned else MIN_LABELED_TO_GENERALIZE
    if eligible < needed:
        return (
            "insufficient_sample",
            False,
            (
                f"Only {eligible} adjudicated label{'s' if eligible != 1 else ''} "
                f"out of {assigned} assigned. The figures below describe those rows. "
                f"They do not generalize. The target for this set is {needed}."
            ),
        )
    return (
        "measured",
        True,
        (
            f"{eligible} adjudicated labels out of {assigned} assigned. "
            "This measures the reviewed sample. It is not a promise about the next quarter's calls."
        ),
    )


def _active_decisions(items: list[dict]) -> list[dict]:
    """Latest row per item. Duplicate review ids count once."""

    by_item: dict[str, tuple[int, dict]] = {}
    order: list[str] = []
    for index, item in enumerate(items):
        item_id = item.get("item_id") or item.get("review_id") or ""
        if not item_id:
            continue
        previous = by_item.get(item_id)
        if previous is None:
            order.append(item_id)
            by_item[item_id] = (index, item)
            continue
        if _later(item, index, previous[1], previous[0]):
            by_item[item_id] = (index, item)
    chosen = []
    seen_review: set[str] = set()
    for item_id in order:
        item = by_item[item_id][1]
        review_id = item.get("review_id") or ""
        if review_id:
            if review_id in seen_review:
                continue
            seen_review.add(review_id)
        chosen.append(item)
    return chosen


def _later(candidate: dict, candidate_index: int, current: dict, current_index: int) -> bool:
    candidate_stamp = candidate.get("reviewer_timestamp") or ""
    current_stamp = current.get("reviewer_timestamp") or ""
    if candidate_stamp != current_stamp:
        return candidate_stamp > current_stamp
    candidate_filled = bool(candidate.get("decision"))
    current_filled = bool(current.get("decision"))
    if candidate_filled != current_filled:
        return candidate_filled
    return candidate_index > current_index


def _duplicate_count(items: list[dict]) -> int:
    return max(0, len([item for item in items if item.get("item_id")]) - len(_active_decisions(items)))


def _model_version(report: dict) -> str:
    name = (report.get("dataset") or {}).get("topic_model") or "lexical-nmf"
    if name == "lexical-nmf":
        return MODEL_VERSION
    return f"{name}|{MODEL_VERSION}"


def _rate(numerator: int, denominator: int, *, kind: str) -> dict:
    if denominator <= 0:
        return _empty_metric()
    value = numerator / denominator
    if kind == "metric" and numerator == 0 and denominator == 0:
        return _empty_metric()
    return {
        "value": round(value, 6),
        "numerator": numerator,
        "denominator": denominator,
        "display": _display_rate(value, numerator, denominator, kind),
    }


def _empty_metric() -> dict:
    return {"value": None, "numerator": None, "denominator": None, "display": "N/A"}


def _display_rate(value: float, numerator: int, denominator: int, kind: str) -> str:
    if kind == "count":
        return f"{numerator}/{denominator}"
    return f"{numerator}/{denominator} ({value:.1%})"


def _metric(value: float | None, denominator: int) -> dict:
    if value is None or denominator <= 0:
        return _empty_metric()
    return {
        "value": round(float(value), 6),
        "numerator": None,
        "denominator": denominator,
        "display": f"{value:.1%}",
    }


def _mean_rating(values: list[int]) -> dict:
    if not values:
        return {"value": None, "count": 0, "display": "N/A"}
    mean = sum(values) / len(values)
    return {"value": round(mean, 4), "count": len(values), "display": f"{mean:.2f} (n={len(values)})"}


def _nanmean(values: list[float]) -> float | None:
    cleaned = [float(value) for value in values if value is not None and np.isfinite(value)]
    if not cleaned:
        return None
    return float(sum(cleaned) / len(cleaned))


def _clean(value) -> float | None:
    if value is None or not np.isfinite(value):
        return None
    return round(float(value), 6)


def _reviewer_disagreement(rows: list[dict]) -> dict:
    compared = []
    for row in rows:
        submissions = row.get("submissions") or []
        reviewers = {item.get("reviewer_id") for item in submissions if item.get("reviewer_id")}
        if len(reviewers) < 2:
            continue
        labels = {(item.get("decision"), item.get("human_topic") or "") for item in submissions}
        compared.append(len(labels) > 1)
    if not compared:
        return _empty_metric()
    return _rate(sum(1 for disagreed in compared if disagreed), len(compared), kind="metric")


def _wilson_interval(successes: int, total: int) -> dict:
    if total <= 0:
        return {
            "method": "wilson_95",
            "low": None,
            "high": None,
            "display": "N/A",
            "successes": 0,
            "total": 0,
            "caveat": "No adjudicated labels, so no interval is calculated.",
        }
    z = 1.96
    p = successes / total
    denom = 1 + z**2 / total
    center = (p + z**2 / (2 * total)) / denom
    margin = z * math.sqrt(p * (1 - p) / total + z**2 / (4 * total * total)) / denom
    low = max(0.0, center - margin)
    high = min(1.0, center + margin)
    return {
        "method": "wilson_95",
        "low": round(low, 6),
        "high": round(high, 6),
        "display": f"{low:.1%}–{high:.1%} (n={total})",
        "successes": successes,
        "total": total,
        "caveat": (
            "Wilson 95% interval on the labeled rows, as if those rows were a simple random sample. "
            "The review draw is stratified on the predicted theme and call type, so this is not a design-based "
            "confidence interval and it does not describe the challenging set."
        ),
    }


def _empty_evidence() -> dict:
    return {
        "human_review_status": "not_yet_available",
        "automated_quote_check": "not_run",
        "note": "Quote checks have not been attached. A quote match would still not be a human support judgment.",
        "findings": [],
    }


def _empty_claims() -> dict:
    return {
        "status": "not_run",
        "note": "The claims audit has not been attached. A passing count check is reproducibility, not human verification.",
        "claims": [],
    }


def _readiness(topic: dict, insights: dict, findings: dict, claims: dict) -> dict:
    return {
        "implemented": [
            "Topic review can confirm, correct, mark ambiguous, or mark insufficient evidence.",
            "Insight review can accept, reject, request revision, or request more evidence.",
            "Conflicting reviews stay unresolved until an explicit adjudication.",
            "Quote location and the headline counts can be checked from source files.",
        ],
        "awaiting_review": [
            f"Topic labels: {topic['reviewed']} reviewed / {topic['assigned']} assigned, {topic['eligible']} adjudicated.",
            f"Insight decisions: {insights['reviewed']} reviewed / {insights['total']} findings.",
            f"Finding support judgments: {findings.get('human_reviewed', 0)} reviewed / {findings.get('finding_count', 0)} findings.",
        ],
        "validated": [],
        "insufficient_evidence": (
            ["No human has marked a transcript or a finding as insufficient evidence."]
            if topic.get("insufficient_evidence", 0) == 0 and findings.get("human_insufficient_evidence", 0) == 0
            else [
                f"Topic rows marked insufficient evidence: {topic.get('insufficient_evidence', 0)}.",
                f"Findings marked insufficient evidence: {findings.get('human_insufficient_evidence', 0)}.",
            ]
        ),
        "automated_checks": claims.get("status", "not_run"),
        "note": "Validated stays empty until adjudicated human decisions exist. Automated checks do not fill it.",
    }


def _finite(value) -> float | None:
    if value is None or not np.isfinite(value):
        return None
    return float(value)


def _write_csv(payload: dict, path: Path) -> None:
    fields = [
        "section",
        "set",
        "metric",
        "status",
        "display",
        "value",
        "numerator",
        "denominator",
        "support",
        "notes",
    ]
    rows: list[dict] = []
    sampling = payload.get("sampling") or {}
    rows.append(
        {
            "section": "sampling",
            "set": "representative",
            "metric": "sample_size",
            "status": "",
            "display": str(sampling.get("representative_count")),
            "value": sampling.get("representative_count"),
            "numerator": sampling.get("representative_count"),
            "denominator": sampling.get("population_meetings"),
            "support": "",
            "notes": sampling.get("method") or "",
        }
    )
    rows.append(
        {
            "section": "sampling",
            "set": "challenging",
            "metric": "sample_size",
            "status": "biased",
            "display": str(sampling.get("challenging_count")),
            "value": sampling.get("challenging_count"),
            "numerator": "",
            "denominator": "",
            "support": "",
            "notes": sampling.get("challenging_bias") or "",
        }
    )
    for name, block in (payload.get("topic_classification") or {}).items():
        if name == "pooling_note" or not isinstance(block, dict):
            continue
        for metric in (
            "completion",
            "accuracy",
            "macro_precision",
            "macro_recall",
            "macro_f1",
            "weighted_precision",
            "weighted_recall",
            "weighted_f1",
            "disagreement_rate",
            "ambiguous_proportion",
            "unresolved_proportion",
        ):
            cell = block.get(metric) or {}
            rows.append(
                {
                    "section": "topic",
                    "set": name,
                    "metric": metric,
                    "status": block.get("status"),
                    "display": cell.get("display"),
                    "value": cell.get("value"),
                    "numerator": cell.get("numerator"),
                    "denominator": cell.get("denominator"),
                    "support": block.get("eligible"),
                    "notes": block.get("warning") or "",
                }
            )
        for category in block.get("per_category") or []:
            for metric in ("precision", "recall", "f1"):
                rows.append(
                    {
                        "section": "category",
                        "set": name,
                        "metric": f"{category['theme']}_{metric}",
                        "status": block.get("status"),
                        "display": "N/A" if category[metric] is None else f"{category[metric]:.1%}",
                        "value": category[metric],
                        "numerator": "",
                        "denominator": "",
                        "support": category["support"],
                        "notes": category["name"],
                    }
                )
        matrix = block.get("confusion_matrix") or {}
        labels = matrix.get("labels") or []
        for row_index, row in enumerate(matrix.get("counts") or []):
            for column_index, count in enumerate(row):
                if not count:
                    continue
                rows.append(
                    {
                        "section": "confusion",
                        "set": name,
                        "metric": f"{labels[row_index]}|{labels[column_index]}",
                        "status": block.get("status"),
                        "display": str(count),
                        "value": count,
                        "numerator": count,
                        "denominator": block.get("eligible"),
                        "support": "",
                        "notes": "row is the human topic, column is the predicted topic",
                    }
                )
    insights = payload.get("business_insights") or {}
    for metric in (
        "review_coverage",
        "acceptance_rate",
        "approval_coverage",
    ):
        cell = insights.get(metric) or {}
        rows.append(
            {
                "section": "insight",
                "set": "all",
                "metric": metric,
                "status": "not_yet_available" if cell.get("value") is None else "measured",
                "display": cell.get("display"),
                "value": cell.get("value"),
                "numerator": cell.get("numerator"),
                "denominator": cell.get("denominator"),
                "support": insights.get("reviewed"),
                "notes": insights.get("note") or "",
            }
        )
    for metric, cell in (
        ("mean_evidence_quality", insights.get("mean_evidence_quality") or {}),
        ("mean_business_usefulness", insights.get("mean_business_usefulness") or {}),
    ):
        rows.append(
            {
                "section": "insight",
                "set": "all",
                "metric": metric,
                "status": "not_yet_available" if cell.get("value") is None else "measured",
                "display": cell.get("display"),
                "value": cell.get("value"),
                "numerator": "",
                "denominator": "",
                "support": cell.get("count"),
                "notes": "",
            }
        )
    for row in insights.get("by_stakeholder") or []:
        cell = row["acceptance_rate"]
        rows.append(
            {
                "section": "stakeholder",
                "set": row["stakeholder"],
                "metric": "acceptance_rate",
                "status": "not_yet_available" if cell.get("value") is None else "measured",
                "display": cell.get("display"),
                "value": cell.get("value"),
                "numerator": cell.get("numerator"),
                "denominator": cell.get("denominator"),
                "support": row["reviewed"],
                "notes": row["label"],
            }
        )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Score saved human reviews. Does not create or modify reviewer decisions."
    )
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--sample", type=Path, default=None)
    parser.add_argument("--queue", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None, help="Directory, or a .json file path.")
    args = parser.parse_args(argv)
    report = json.loads(args.report.read_text(encoding="utf-8"))
    decisions = load_decisions(args.decisions)
    sample_path = args.sample or args.report.parent / "review_sample.json"
    if sample_path.exists():
        sample = json.loads(sample_path.read_text(encoding="utf-8"))
    else:
        queue_path = args.queue or args.report.parent / "review_queue.json"
        queue = json.loads(queue_path.read_text(encoding="utf-8")) if queue_path.exists() else {"items": []}
        sample = build_review_sample(report.get("meetings") or [], queue)
    payload = build_human_validation_report(report, sample, decisions)
    if args.output:
        directory = args.output.parent if args.output.suffix == ".json" else args.output
        write_human_validation_report(payload, directory)
        print(f"Wrote {directory / 'human_validation_report.json'}")
        print(f"Wrote {directory / 'human_validation_report.csv'}")
    else:
        print(json.dumps(_summary(payload), indent=2))
    topic = payload["topic_classification"]["representative"]
    insights = payload["business_insights"]
    print(
        f"Representative theme metrics: {topic['headline']} "
        f"({topic['reviewed']}/{topic['assigned']} reviewed, {topic['eligible']} adjudicated). "
        f"Insight acceptance: {insights['acceptance_rate']['display']}."
    )


def _summary(payload: dict) -> dict:
    topic = payload["topic_classification"]["representative"]
    challenge = payload["topic_classification"]["challenging"]
    insights = payload["business_insights"]
    return {
        "data_gap": payload["data_gap"],
        "representative": {
            "headline": topic["headline"],
            "reviewed": topic["reviewed"],
            "assigned": topic["assigned"],
            "eligible": topic["eligible"],
            "accuracy": topic["accuracy"]["display"],
        },
        "challenging": {
            "headline": challenge["headline"],
            "reviewed": challenge["reviewed"],
            "assigned": challenge["assigned"],
            "eligible": challenge["eligible"],
            "accuracy": challenge["accuracy"]["display"],
        },
        "insight_acceptance": insights["acceptance_rate"]["display"],
        "insight_coverage": insights["review_coverage"]["display"],
    }


if __name__ == "__main__":
    main()
