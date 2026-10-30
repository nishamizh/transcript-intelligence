import json
from pathlib import Path

from src.analytics.sentiment_analyzer import SentimentAnalyzer
from src.analytics.text_safety import redact_public_text
from src.analytics.topic_analyzer import TopicAnalyzer, overlap_status
from src.ingestion.loader import DatasetLoader
from src.review.decisions import ensure_decision_template
from src.review.evaluate import evaluate
from src.review.queue import build_review_queue
from tests.test_analytics import _meeting


def test_overlap_status_is_a_review_flag_not_an_error():
    assert overlap_status(0) == "review recommended"
    assert overlap_status(0.04) == "recorded"


def test_redaction_hides_contact_details_and_does_not_paraphrase():
    text = "Email alex@example.com or call (415) 555-0134 about the outage."
    redacted = redact_public_text(text)
    assert "alex@example.com" not in redacted
    assert "555-0134" not in redacted
    assert "outage" in redacted
    assert "[redacted-email]" in redacted
    assert "[redacted-phone]" in redacted


def test_topic_examples_cite_real_meetings_only():
    billing = _meeting(
        meeting_id="bill-1",
        title="Support Case #2 - Example Co invoice",
        topics=["billing dispute", "seat overage"],
        summary="The invoice includes seats from a migration.",
        turns=[],
    )
    billing.turns = _meeting().turns
    billing.turns[0].sentence = "The invoice shows a seat overage after the migration. Reach me at alex@example.com."
    compliance = _meeting(
        meeting_id="comp-1",
        topics=["hipaa compliance", "audit preparation"],
        summary="Preparing the HIPAA evidence pack.",
    )
    meetings = [billing, compliance]
    artifact = TopicAnalyzer().analyze(meetings).topic_examples
    ids = {meeting.meeting_id for meeting in meetings}
    assert artifact.per_theme_limit == 2
    assert artifact.examples
    for example in artifact.examples:
        assert example.meeting_id in ids
        source = next(meeting for meeting in meetings if meeting.meeting_id == example.meeting_id)
        assert example.assigned_theme == source.primary_theme
        assert example.original_labels == source.topics
        assert "alex@example.com" not in example.evidence_excerpt
        assert example.assigned_theme_name in example.classification_explanation
        assert "not a measured accuracy" in example.classification_explanation


def test_sentiment_provenance_does_not_invent_a_model_score():
    meeting = _meeting(sentiment_score=1.8, sentiment="negative")
    analysis = SentimentAnalyzer().analyze([meeting])
    assert analysis.provenance.inferred_model_score is None
    assert analysis.by_call_type[0].count == 1
    assert analysis.by_call_type[0].turn_count == 2
    assert analysis.by_call_type[0].mean_score == 1.8
    assert meeting.sentiment_score == 1.8


def test_source_files_keep_their_sentiment_scores():
    data = Path("data")
    if not data.exists():
        return
    loaded = {meeting.meeting_id: meeting for meeting in DatasetLoader(data).load_dataset()}
    checked = 0
    for meeting in loaded.values():
        summary = json.loads((data / meeting.meeting_id / "summary.json").read_text(encoding="utf-8"))
        assert meeting.sentiment_score == summary["sentimentScore"]
        assert meeting.sentiment == str(summary["overallSentiment"]).strip().lower()
        checked += 1
    assert checked == 100


def test_decision_template_does_not_overwrite_a_reason(tmp_path: Path):
    path = tmp_path / "review_decisions.json"
    ensure_decision_template(path, ["meeting:a"])
    saved = json.loads(path.read_text(encoding="utf-8"))
    saved["items"][0]["decision"] = "reject"
    saved["items"][0]["reason"] = "The label is about billing, not reliability."
    path.write_text(json.dumps(saved), encoding="utf-8")
    wrote = ensure_decision_template(path, ["meeting:a", "meeting:b"])
    assert wrote is True
    again = json.loads(path.read_text(encoding="utf-8"))
    kept = next(item for item in again["items"] if item["item_id"] == "meeting:a")
    added = next(item for item in again["items"] if item["item_id"] == "meeting:b")
    assert kept["decision"] == "reject"
    assert kept["reason"] == "The label is about billing, not reliability."
    assert added["decision"] == ""
    assert ensure_decision_template(path, ["meeting:a", "meeting:b"]) is False


def test_evaluator_math_and_empty_reviews():
    report = {
        "meetings": [{"meeting_id": "m1"}, {"meeting_id": "m2"}],
        "insights": [
            {"insight_id": "one", "evidence": [{"meeting_id": "m1", "quote": "A real quote."}]},
            {"insight_id": "two", "evidence": [{"meeting_id": "missing", "quote": "A real quote."}]},
        ],
    }
    queue = {
        "items": [
            {"item_id": "meeting:1", "item_type": "meeting_classification", "predicted_theme": "reliability"},
            {"item_id": "meeting:2", "item_type": "meeting_classification", "predicted_theme": "reliability"},
            {"item_id": "meeting:3", "item_type": "meeting_classification", "predicted_theme": "reliability"},
            {"item_id": "meeting:4", "item_type": "meeting_classification", "predicted_theme": "billing"},
            {"item_id": "insight:1", "item_type": "stakeholder_insight"},
            {"item_id": "insight:2", "item_type": "stakeholder_insight"},
        ]
    }
    empty = evaluate(report, queue, {"version": 1, "items": []})
    assert empty["theme_classification"]["status"] == "unavailable"
    assert empty["theme_classification"]["micro_f1"] is None
    assert empty["theme_classification"]["macro_f1"] is None
    assert empty["insight_acceptance"]["status"] == "unavailable"
    assert empty["insight_acceptance"]["rate"] is None
    assert empty["citation_completeness"]["status"] == "measured"
    assert empty["citation_completeness"]["rate"] == 0.5

    decisions = {
        "version": 1,
        "items": [
            {"item_id": "meeting:1", "decision": "accept", "corrected_theme": "", "reason": "Matches the labels."},
            {"item_id": "meeting:2", "decision": "accept", "corrected_theme": "", "reason": ""},
            {"item_id": "meeting:3", "decision": "edit", "corrected_theme": "compliance", "reason": "This is audit evidence."},
            {"item_id": "meeting:4", "decision": "reject", "corrected_theme": "", "reason": "Not enough to score."},
            {"item_id": "insight:1", "decision": "accept", "corrected_theme": "", "reason": ""},
            {"item_id": "insight:2", "decision": "reject", "corrected_theme": "", "reason": "The quote is the wrong call."},
        ],
    }
    scored = evaluate(report, queue, decisions)
    theme = scored["theme_classification"]
    assert theme["status"] == "measured"
    assert theme["usable_labels"] == 3
    by_theme = {row["theme"]: row for row in theme["per_theme"]}
    assert by_theme["reliability"]["precision"] == 0.6667
    assert by_theme["reliability"]["recall"] == 1.0
    assert by_theme["reliability"]["f1"] == 0.8
    assert by_theme["compliance"]["recall"] == 0.0
    assert by_theme["compliance"]["precision"] is None
    assert theme["micro_f1"] == 0.6667
    assert theme["macro_f1"] == 0.8
    assert scored["insight_acceptance"]["rate"] == 0.5
    assert scored["insight_acceptance"]["reviewed"] == 2


def test_review_queue_uses_real_ids_and_redacts():
    meeting = _meeting(meeting_id="q1", topics=["billing dispute"], summary="Invoice dispute.")
    meeting.turns[0].sentence = "Send the invoice dispute to alex@example.com."
    meetings = [meeting]
    TopicAnalyzer().analyze(meetings)
    queue = build_review_queue(meetings, [])
    assert queue["items"]
    assert queue["items"][0]["meeting_id"] == "q1"
    assert "alex@example.com" not in queue["items"][0]["evidence_excerpt"]
    assert "[redacted-email]" in queue["items"][0]["evidence_excerpt"]
    assert "decision" not in queue["items"][0]
