"""Human-validation metrics.

Reviewer rows in this file are synthetic fixtures. They are not labels of the
Aegis corpus, and they are not written to output/review_decisions.json.
"""

import json
from pathlib import Path

import numpy as np
import pytest
from sklearn.metrics import accuracy_score, confusion_matrix, precision_recall_fscore_support

from src.review.decisions import ensure_decision_template, load_decisions
from src.review.sample import allocate_theme_seats, build_review_sample
from src.review.schema import THEME_IDS, DecisionSchemaError
from src.review.store import DecisionStore
from src.review.validation import build_human_validation_report, write_human_validation_report

COUNTS = {
    "reliability": 43,
    "compliance": 21,
    "identity": 12,
    "commercial": 8,
    "product": 8,
    "billing": 5,
    "onboarding": 2,
    "delivery": 1,
}


def test_stratified_allocation_matches_the_fixed_design():
    allocation = allocate_theme_seats(COUNTS, 30)
    assert sum(allocation.values()) == 30
    assert allocation == {
        "reliability": 11,
        "compliance": 6,
        "identity": 3,
        "commercial": 3,
        "product": 3,
        "billing": 2,
        "onboarding": 1,
        "delivery": 1,
    }


def test_representative_sample_is_deterministic_and_covers_the_book():
    meetings = _population()
    queue = {
        "items": [
            {
                "item_id": "meeting:reliability-00",
                "item_type": "meeting_classification",
                "meeting_id": "reliability-00",
                "predicted_theme": "reliability",
                "call_type": "support",
                "reasons": ["ambiguous_theme"],
            }
        ]
    }
    first = build_review_sample(meetings, queue, seed=7, target=30)
    second = build_review_sample(meetings, queue, seed=7, target=30)
    assert [item["meeting_id"] for item in first["representative"]["items"]] == [
        item["meeting_id"] for item in second["representative"]["items"]
    ]
    assert first["representative"]["count"] == 30
    themes = {item["predicted_topic"] for item in first["representative"]["items"]}
    call_types = {item["call_type"] for item in first["representative"]["items"]}
    assert themes == set(COUNTS)
    assert call_types == {"support", "external", "internal"}
    assert first["challenging"]["count"] == 1
    assert first["challenging"]["items"][0]["selection_probability"] is None
    assert "not a probability sample" in first["method"]
    assert "not added together" in first["pooling"]
    for item in first["representative"]["items"]:
        assert 0 < item["selection_probability"] <= 1
        assert item["sample_weight"] == pytest.approx(1 / item["selection_probability"], rel=1e-4)


def test_blank_reviewer_decisions_produce_na_metrics():
    report, sample = _fixture()
    payload = build_human_validation_report(report, sample, {"version": 1, "items": []})
    topic = payload["topic_classification"]["representative"]
    assert topic["status"] == "not_yet_available"
    assert topic["headline"] == "NOT YET AVAILABLE"
    assert topic["accuracy"]["value"] is None
    assert topic["accuracy"]["display"] == "N/A"
    assert topic["macro_f1"]["display"] == "N/A"
    assert topic["weighted_f1"]["display"] == "N/A"
    assert topic["completion"]["display"] == "0/4"
    assert topic["eligible"] == 0
    assert payload["business_insights"]["acceptance_rate"]["display"] == "N/A"
    assert payload["business_insights"]["acceptance_rate"]["value"] is None
    assert payload["data_gap"]["resolved"] is False
    assert payload["llm_as_judge"] is False


def test_adjudicated_labels_match_sklearn_confusion_and_f1():
    report, sample = _fixture()
    decisions = {
        "version": 2,
        "items": [
            _topic("m1", "approve", "reliability"),
            _topic("m2", "correct", "compliance"),
            _topic("m3", "approve", "compliance"),
            _topic("m4", "approve", "billing"),
        ],
    }
    payload = build_human_validation_report(report, sample, decisions)
    topic = payload["topic_classification"]["representative"]
    y_true = ["reliability", "compliance", "compliance", "billing"]
    y_pred = ["reliability", "reliability", "compliance", "billing"]
    present = ["reliability", "compliance", "billing"]
    expected_accuracy = accuracy_score(y_true, y_pred)
    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true,
        y_pred,
        labels=present,
        average="macro",
        zero_division=np.nan,
    )
    weighted = precision_recall_fscore_support(
        y_true,
        y_pred,
        labels=present,
        average="weighted",
        zero_division=np.nan,
    )
    assert topic["status"] == "measured"
    assert topic["accuracy"]["value"] == pytest.approx(expected_accuracy)
    assert topic["macro_precision"]["value"] == pytest.approx(float(precision))
    assert topic["macro_recall"]["value"] == pytest.approx(float(recall))
    assert topic["macro_f1"]["value"] == pytest.approx(float(f1))
    assert topic["weighted_precision"]["value"] == pytest.approx(float(weighted[0]))
    assert topic["weighted_recall"]["value"] == pytest.approx(float(weighted[1]))
    assert topic["weighted_f1"]["value"] == pytest.approx(float(weighted[2]))
    matrix = confusion_matrix(y_true, y_pred, labels=list(THEME_IDS))
    assert topic["confusion_matrix"]["counts"] == [[int(value) for value in row] for row in matrix.tolist()]
    assert topic["confusion_matrix"]["counts"][0][0] == 1
    assert topic["confusion_matrix"]["counts"][1][0] == 1
    assert topic["per_category"][0]["support"] == 1
    assert topic["per_category"][1]["support"] == 2
    assert topic["disagreement_rate"]["numerator"] == 1
    assert topic["disagreement_rate"]["denominator"] == 4


def test_ambiguous_reviews_count_toward_coverage_and_not_accuracy():
    report, sample = _fixture(extra=True)
    decisions = {
        "version": 2,
        "items": [
            _topic("m1", "approve", "reliability"),
            _topic("m2", "correct", "compliance"),
            _topic("m3", "approve", "compliance"),
            _topic("m4", "approve", "billing"),
            _topic("m5", "ambiguous", ""),
        ],
    }
    topic = build_human_validation_report(report, sample, decisions)["topic_classification"]["representative"]
    assert topic["reviewed"] == 5
    assert topic["eligible"] == 4
    assert topic["ambiguous"] == 1
    assert topic["completion"]["display"] == "5/5"
    assert topic["accuracy"]["value"] == pytest.approx(0.75)
    assert topic["status"] == "insufficient_sample"
    assert topic["generalizes"] is False
    assert "do not generalize" in topic["warning"]


def test_rejected_and_unresolved_insights_do_not_invent_acceptance():
    insights = [
        {"insight_id": "s1", "stakeholder": "sales"},
        {"insight_id": "s2", "stakeholder": "sales"},
        {"insight_id": "p1", "stakeholder": "product"},
        {"insight_id": "e1", "stakeholder": "engineering"},
        {"insight_id": "u1", "stakeholder": "support"},
    ]
    report = {"dataset": {"topic_model": "lexical-nmf"}, "meetings": [], "insights": insights}
    sample = _empty_sample()
    pending = build_human_validation_report(
        report,
        sample,
        {"items": [_insight("p1", "needs_revision"), _insight("e1", "needs_more_evidence")]},
    )["business_insights"]
    assert pending["needs_revision"] == 1
    assert pending["needs_more_evidence"] == 1
    assert pending["accepted"] == 0
    assert pending["rejected"] == 0
    assert pending["acceptance_rate"]["display"] == "N/A"
    assert pending["acceptance_rate"]["value"] is None
    assert pending["review_coverage"]["display"] == "2/5"

    scored = build_human_validation_report(
        report,
        sample,
        {
            "items": [
                _insight("s1", "accept", evidence_quality=4, business_usefulness=5),
                _insight("s2", "reject", evidence_quality=2),
                _insight("p1", "needs_revision"),
                _insight("e1", "needs_more_evidence"),
            ]
        },
    )["business_insights"]
    assert scored["accepted"] == 1
    assert scored["rejected"] == 1
    assert scored["needs_revision"] == 1
    assert scored["acceptance_rate"]["value"] == pytest.approx(0.5)
    assert scored["acceptance_rate"]["denominator"] == 2
    assert scored["approval_coverage"]["display"].startswith("1/5")
    assert scored["mean_evidence_quality"]["value"] == pytest.approx(3.0)
    assert scored["mean_evidence_quality"]["count"] == 2
    assert scored["mean_business_usefulness"]["value"] == pytest.approx(5.0)
    assert scored["mean_business_usefulness"]["count"] == 1
    by_name = {row["stakeholder"]: row for row in scored["by_stakeholder"]}
    assert by_name["sales"]["acceptance_rate"]["value"] == pytest.approx(0.5)
    assert by_name["product"]["acceptance_rate"]["display"] == "N/A"
    assert by_name["product"]["needs_revision"] == 1


def test_duplicate_review_ids_do_not_inflate_metrics():
    report, sample = _fixture()
    duplicate = _topic("m1", "approve", "reliability", review_id="shared-review")
    other = _topic("m2", "approve", "reliability", review_id="shared-review")
    other["item_id"] = "meeting:m2"
    payload = build_human_validation_report(report, sample, {"items": [duplicate, other, dict(duplicate)]})
    topic = payload["topic_classification"]["representative"]
    assert topic["eligible"] == 1
    assert topic["confusion_matrix"]["counts"][0][0] == 1
    assert payload["ignored_duplicate_rows"] == 2


def test_decisions_persist_and_regeneration_keeps_them(tmp_path: Path):
    path = tmp_path / "review_decisions.json"
    store = DecisionStore(path)
    saved = store.save_topic_review(
        item_id="meeting:m1",
        predicted_topic="reliability",
        decision="approve",
        human_topic="reliability",
        reviewer_id="synthetic-reviewer",
        notes="Fixture only. Not a corpus label.",
    )
    reloaded = DecisionStore(path).load()
    row = next(item for item in reloaded["items"] if item["item_id"] == "meeting:m1")
    assert row["decision"] == "approve"
    assert row["reviewer_id"] == "synthetic-reviewer"
    assert row["review_id"] == saved["review_id"]

    edited = DecisionStore(path).save_topic_review(
        item_id="meeting:m1",
        predicted_topic="reliability",
        decision="correct",
        human_topic="billing",
        reviewer_id="synthetic-reviewer",
        notes="Corrected in the fixture.",
    )
    assert edited["review_id"].endswith(":r2")
    assert edited["audit"][0]["decision"] == "approve"
    assert len(load_decisions(path)["items"]) == 1

    assert ensure_decision_template(path, ["meeting:m1", "meeting:new"]) is True
    kept = next(item for item in load_decisions(path)["items"] if item["item_id"] == "meeting:m1")
    assert kept["decision"] == "correct"
    assert kept["human_topic"] == "billing"
    assert kept["notes"] == "Corrected in the fixture."
    added = next(item for item in load_decisions(path)["items"] if item["item_id"] == "meeting:new")
    assert added["decision"] == ""

    report, sample = _fixture()
    before = path.read_text(encoding="utf-8")
    payload = build_human_validation_report(report, sample, load_decisions(path))
    write_human_validation_report(payload, tmp_path)
    assert path.read_text(encoding="utf-8") == before
    still = next(item for item in load_decisions(path)["items"] if item["item_id"] == "meeting:m1")
    assert still["decision"] == "correct"
    assert still["human_topic"] == "billing"
    assert (tmp_path / "human_validation_report.json").exists()
    assert (tmp_path / "human_validation_report.csv").exists()


def test_scripts_do_not_silently_fill_reviewer_decisions(tmp_path: Path):
    meetings = _population()
    sample = build_review_sample(meetings, {"items": []}, seed=7, target=30)
    path = tmp_path / "review_decisions.json"
    ensure_decision_template(path, [item["item_id"] for item in sample["representative"]["items"]])
    original = path.read_text(encoding="utf-8")
    assert '"approve"' not in original
    assert '"accept"' not in original
    assert all(item["decision"] == "" for item in load_decisions(path)["items"])
    report = {
        "dataset": {"topic_model": "lexical-nmf"},
        "meetings": meetings,
        "insights": [{"insight_id": "one", "stakeholder": "support", "evidence": []}],
    }
    payload = build_human_validation_report(report, sample, load_decisions(path))
    write_human_validation_report(payload, tmp_path)
    assert path.read_text(encoding="utf-8") == original
    assert payload["synthetic_labels"] is False
    assert payload["topic_classification"]["representative"]["accuracy"]["display"] == "N/A"
    assert payload["business_insights"]["acceptance_rate"]["display"] == "N/A"
    with pytest.raises(DecisionSchemaError):
        DecisionStore(path).save_topic_review(
            item_id="meeting:reliability-00",
            predicted_topic="reliability",
            decision="",
            human_topic="",
            reviewer_id="synthetic-reviewer",
        )


def test_population_weights_change_the_estimate_and_sets_stay_separate():
    meetings = [
        {"meeting_id": "m1", "primary_theme": "reliability", "call_type": "support"},
        {"meeting_id": "m2", "primary_theme": "reliability", "call_type": "support"},
    ]
    representative = [
        _member("m1", "reliability", weight=1),
        _member("m2", "reliability", weight=2),
    ]
    challenging = [
        _member("m1", "reliability", weight=1),
        _member("m2", "reliability", weight=1),
    ]
    report = {"dataset": {"topic_model": "lexical-nmf"}, "meetings": meetings, "insights": []}
    sample = {
        "seed": 7,
        "target": 2,
        "taxonomy_version": "governed-themes-v1",
        "method": "synthetic fixture, not the corpus draw",
        "population_meetings": 2,
        "representative": {"count": 2, "items": representative, "allocation": [], "strata": [], "coverage": {}},
        "challenging": {"count": 2, "items": challenging, "bias": "synthetic hard cases"},
        "overlap_count": 2,
        "pooling": "kept separate",
    }
    decisions = {
        "items": [
            _topic("m1", "approve", "reliability"),
            _topic("m2", "correct", "compliance"),
        ]
    }
    payload = build_human_validation_report(report, sample, decisions)
    representative_metrics = payload["topic_classification"]["representative"]
    challenging_metrics = payload["topic_classification"]["challenging"]
    assert representative_metrics["accuracy"]["value"] == pytest.approx(0.5)
    assert representative_metrics["population_estimates"]["accuracy"]["value"] == pytest.approx(1 / 3)
    assert challenging_metrics["accuracy"]["value"] == pytest.approx(0.5)
    assert challenging_metrics["population_estimates"] is None
    assert "combined" not in payload["topic_classification"]


def _population() -> list[dict]:
    cycle = ["support", "external", "internal"]
    meetings = []
    for theme, count in COUNTS.items():
        for index in range(count):
            meetings.append(
                {
                    "meeting_id": f"{theme}-{index:02d}",
                    "primary_theme": theme,
                    "call_type": cycle[index % 3],
                    "topics": [theme],
                }
            )
    return meetings


def _fixture(extra: bool = False) -> tuple[dict, dict]:
    ids = ["m1", "m2", "m3", "m4"] + (["m5"] if extra else [])
    themes = ["reliability", "reliability", "compliance", "billing"] + (["product"] if extra else [])
    meetings = [
        {"meeting_id": meeting_id, "primary_theme": theme, "call_type": "support"}
        for meeting_id, theme in zip(ids, themes, strict=True)
    ]
    items = [_member(meeting_id, theme, weight=1) for meeting_id, theme in zip(ids, themes, strict=True)]
    report = {"dataset": {"topic_model": "lexical-nmf"}, "meetings": meetings, "insights": []}
    return report, {
        "seed": 7,
        "target": len(items),
        "taxonomy_version": "governed-themes-v1",
        "method": "synthetic fixture, not the corpus draw",
        "population_meetings": len(items),
        "representative": {"count": len(items), "items": items, "allocation": [], "strata": [], "coverage": {}},
        "challenging": {"count": 0, "items": [], "bias": "synthetic"},
        "overlap_count": 0,
        "pooling": "kept separate",
    }


def _empty_sample() -> dict:
    return {
        "seed": 7,
        "target": 0,
        "representative": {"count": 0, "items": []},
        "challenging": {"count": 0, "items": [], "bias": ""},
        "pooling": "kept separate",
    }


def _member(meeting_id: str, theme: str, weight: float) -> dict:
    return {
        "item_id": f"meeting:{meeting_id}",
        "meeting_id": meeting_id,
        "predicted_topic": theme,
        "call_type": "support",
        "selection_probability": round(1 / weight, 6),
        "sample_weight": weight,
    }


def _topic(meeting_id: str, decision: str, human_topic: str, review_id: str | None = None) -> dict:
    return {
        "item_id": f"meeting:{meeting_id}",
        "review_id": review_id or f"meeting:{meeting_id}:r1",
        "decision": decision,
        "human_topic": human_topic,
        "corrected_theme": human_topic if decision == "correct" else "",
        "predicted_topic": "",
        "reviewer_id": "synthetic-reviewer",
        "reviewer_timestamp": "2026-04-01T00:00:00+00:00",
        "notes": "Synthetic fixture. Not a human label of the corpus.",
    }


def _insight(
    insight_id: str,
    decision: str,
    evidence_quality: int | None = None,
    business_usefulness: int | None = None,
) -> dict:
    return {
        "item_id": f"insight:{insight_id}",
        "review_id": f"insight:{insight_id}:r1",
        "decision": decision,
        "reviewer_id": "synthetic-reviewer",
        "reviewer_timestamp": "2026-04-01T00:00:00+00:00",
        "notes": "Synthetic fixture. Not a stakeholder decision on the corpus.",
        "evidence_quality": evidence_quality,
        "business_usefulness": business_usefulness,
    }
