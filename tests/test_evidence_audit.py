"""Evidence checks and the claims audit.

Reviewer rows in this file are synthetic fixtures. They are not labels of the
Aegis corpus and they are not written to output/review_decisions.json.
"""

import json
from pathlib import Path

import pytest

from src.analytics.sentiment_analyzer import SentimentAnalyzer
from src.models.meeting import KeyMoment
from src.review.claims import build_claims_audit
from src.review.evidence import build_evidence_verification
from src.review.store import DecisionStore
from src.review.validation import build_human_validation_report
from tests.test_analytics import _meeting


def test_conflicting_reviews_stay_out_of_accuracy_until_adjudication(tmp_path: Path):
    path = tmp_path / "review_decisions.json"
    store = DecisionStore(path)
    store.save_topic_review(
        item_id="meeting:m1",
        predicted_topic="reliability",
        decision="approve",
        human_topic="reliability",
        reviewer_id="fixture-reviewer-a",
        notes="Synthetic fixture. Not a corpus label.",
        source_document_hash="abc",
    )
    conflicted = store.save_topic_review(
        item_id="meeting:m1",
        predicted_topic="reliability",
        decision="correct",
        human_topic="billing",
        reviewer_id="fixture-reviewer-b",
        notes="Synthetic disagreement.",
        source_document_hash="abc",
    )
    assert conflicted["decision"] == "approve"
    assert conflicted["human_topic"] == "reliability"
    assert conflicted["conflict"] is True
    assert conflicted["review_status"] == "conflict"
    assert len(conflicted["submissions"]) == 2
    assert conflicted["source_document_hash"] == "abc"
    report, sample = _one_meeting()
    topic = build_human_validation_report(report, sample, store.load())["topic_classification"]["representative"]
    assert topic["unadjudicated_conflicts"] == 1
    assert topic["eligible"] == 0
    assert topic["accuracy"]["display"] == "N/A"
    assert topic["reviewer_disagreement_rate"]["value"] == pytest.approx(1.0)

    adjudicated = store.save_topic_review(
        item_id="meeting:m1",
        predicted_topic="reliability",
        decision="correct",
        human_topic="billing",
        reviewer_id="fixture-adjudicator",
        notes="Synthetic adjudication.",
        adjudicate=True,
    )
    assert adjudicated["adjudicated"] is True
    assert adjudicated["conflict"] is False
    assert adjudicated["human_topic"] == "billing"
    assert adjudicated["audit"]
    scored = build_human_validation_report(report, sample, DecisionStore(path).load())
    topic = scored["topic_classification"]["representative"]
    assert topic["eligible"] == 1
    assert topic["accuracy"]["value"] == pytest.approx(0.0)
    assert topic["confusion_matrix"]["counts"][3][0] == 1
    assert topic["per_category"][3]["support"] == 1


def test_insufficient_evidence_is_reviewed_and_excluded_from_accuracy():
    report, sample = _one_meeting()
    decisions = {
        "items": [
            {
                "item_id": "meeting:m1",
                "review_id": "meeting:m1:r1",
                "decision": "insufficient_evidence",
                "human_topic": "",
                "reviewer_id": "synthetic-reviewer",
                "reviewer_timestamp": "2026-04-02T00:00:00+00:00",
                "notes": "Synthetic fixture. Not a corpus label.",
            }
        ]
    }
    topic = build_human_validation_report(report, sample, decisions)["topic_classification"]["representative"]
    assert topic["reviewed"] == 1
    assert topic["insufficient_evidence"] == 1
    assert topic["eligible"] == 0
    assert topic["accuracy"]["display"] == "N/A"
    assert topic["completion"]["display"] == "1/1"


def test_missing_quote_is_not_counted_as_support(tmp_path: Path):
    meeting_id = "quote-meeting"
    folder = tmp_path / meeting_id
    folder.mkdir()
    (folder / "summary.json").write_text(
        json.dumps({"summary": "The invoice was disputed after the migration.", "keyMoments": []}),
        encoding="utf-8",
    )
    (folder / "transcript.json").write_text(
        json.dumps({"data": [{"sentence": "The invoice was disputed after the migration.", "speaker_name": "Alex"}]}),
        encoding="utf-8",
    )
    report = {
        "insights": [
            {
                "insight_id": "billing-fixture",
                "stakeholder": "support",
                "title": "Synthetic finding",
                "finding": "Synthetic fixture claim.",
                "recommendation": "Do not treat this as a corpus finding.",
                "evidence": [
                    {"meeting_id": meeting_id, "quote": "The invoice was disputed after the migration."},
                    {"meeting_id": meeting_id, "quote": "This sentence was never in the source."},
                ],
            }
        ]
    }
    payload = build_evidence_verification(tmp_path, report, {"items": []})
    citations = payload["findings"][0]["citations"]
    assert citations[0]["quote_status"] == "found"
    assert citations[1]["quote_status"] == "missing"
    assert payload["findings"][0]["human_support_status"] == "pending"
    assert payload["human_review_status"] == "not_yet_available"
    assert payload["llm_as_judge"] is False


def test_duplicate_accounts_count_once_and_sentiment_mean_is_recomputed():
    first = _meeting(meeting_id="a", account_name="Example Co", sentiment_score=2.0, call_type="support")
    second = _meeting(
        meeting_id="b",
        account_name="Example Co",
        sentiment_score=4.0,
        call_type="support",
        key_moments=[KeyMoment(1, "We may leave.", "churn_signal", "Alex")],
    )
    other = _meeting(
        meeting_id="c",
        account_name="Other Co",
        customer_domains=["other.example"],
        sentiment_score=3.0,
        call_type="external",
        key_moments=[KeyMoment(1, "Renewal is at risk.", "churn_signal", "Sam")],
    )
    meetings = [first, second, other]
    analysis = SentimentAnalyzer().analyze(meetings)
    support = next(row for row in analysis.by_call_type if row.call_type == "support")
    report = {
        "dataset": {"meeting_count": 3},
        "topics": {"themes": [{"theme_id": theme} for theme in range(8)]},
        "sentiment": {
            "by_call_type": [
                {"call_type": "support", "mean_score": round(support.mean_score, 4)},
                {"call_type": "external", "mean_score": 3.0},
            ],
            "outage_mention": {"count": 3},
        },
        "insights": [{"insight_id": "sales-at-risk", "metric_value": "2"}],
    }
    # The fixture summaries mention the outage, so the recomputed cohort is the check.
    audit = build_claims_audit(meetings, report)
    by_name = {row["metric_name"]: row for row in audit["claims"]}
    assert by_name["transcripts_processed"]["computed_value"] == 3
    assert by_name["transcripts_processed"]["check_status"] == "match"
    assert by_name["mean_support_sentiment"]["computed_value"] == pytest.approx(3.0)
    assert by_name["mean_support_sentiment"]["check_status"] == "match"
    assert by_name["accounts_with_churn_language"]["computed_value"] == 2
    assert by_name["accounts_with_churn_language"]["check_status"] == "match"
    assert all(row["review_status"] == "not_human_verified" for row in audit["claims"])
    mismatched = dict(report)
    mismatched["dataset"] = {"meeting_count": 99}
    drifted = build_claims_audit(meetings, mismatched)
    transcripts = next(row for row in drifted["claims"] if row["metric_name"] == "transcripts_processed")
    assert transcripts["check_status"] == "mismatch"
    assert transcripts["computed_value"] == 3
    assert transcripts["reported_value"] == 99


def test_duplicate_meeting_ids_are_disclosed():
    meetings = [_meeting(meeting_id="same"), _meeting(meeting_id="same", account_name="Second")]
    audit = build_claims_audit(
        meetings,
        {"dataset": {"meeting_count": 2}, "topics": {"themes": []}, "sentiment": {}, "insights": []},
    )
    assert audit["duplicate_meeting_ids"] == ["same"]


def test_corpus_claims_are_recomputed_not_hardcoded():
    data = Path("data")
    report_path = Path("output/report.json")
    if not data.exists() or not report_path.exists():
        pytest.skip("corpus report is not available")
    from src.ingestion.loader import DatasetLoader

    meetings = DatasetLoader(data).load_dataset()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    audit = build_claims_audit(meetings, report)
    by_name = {row["metric_name"]: row for row in audit["claims"]}
    for name in (
        "transcripts_processed",
        "governed_topic_categories",
        "mean_support_sentiment",
        "mean_external_sentiment",
        "outage_related_meetings",
        "accounts_with_churn_language",
    ):
        assert by_name[name]["check_status"] == "match", by_name[name]
        assert by_name[name]["review_status"] == "not_human_verified"
    assert audit["status"] == "reproduced"
    evidence = build_evidence_verification(data, report, {"items": []})
    assert evidence["human_reviewed"] == 0
    assert evidence["human_review_status"] == "not_yet_available"
    assert all(row["human_support_status"] == "pending" for row in evidence["findings"])


def _one_meeting() -> tuple[dict, dict]:
    report = {
        "dataset": {"topic_model": "lexical-nmf"},
        "meetings": [{"meeting_id": "m1", "primary_theme": "reliability", "call_type": "support"}],
        "insights": [],
    }
    sample = {
        "seed": 7,
        "target": 1,
        "taxonomy_version": "governed-themes-v1",
        "method": "synthetic fixture, not the corpus draw",
        "representative": {
            "count": 1,
            "items": [
                {
                    "item_id": "meeting:m1",
                    "meeting_id": "m1",
                    "predicted_topic": "reliability",
                    "sample_weight": 1,
                }
            ],
        },
        "challenging": {"count": 0, "items": []},
        "pooling": "kept separate",
    }
    return report, sample
