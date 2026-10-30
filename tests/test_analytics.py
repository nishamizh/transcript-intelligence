from datetime import datetime, timezone

import pytest

from src.analytics.features import MeetingFeatureExtractor
from src.analytics.insight_analyzer import InsightAnalyzer
from src.analytics.quality import InsightQualityScore
from src.analytics.sentiment_analyzer import SentimentAnalyzer
from src.analytics.topic_analyzer import (
    BertopicTopicModel,
    TopicAnalyzer,
    assign_governed_theme,
)
from src.models.meeting import KeyMoment, Meeting, SpeakerTurn


def _meeting(**overrides) -> Meeting:
    start = datetime(2026, 3, 12, tzinfo=timezone.utc)
    payload = dict(
        meeting_id="m1",
        title="Support Case #9 - Example Co SSO failures",
        duration_minutes=22.0,
        summary="The customer cannot log in with SSO after the outage and is evaluating SentinelShield.",
        transcript="Alex: SSO is down for forty users.\nJamie: We are failing over the identity provider.",
        topics=["sso login", "outage"],
        sentiment="negative",
        sentiment_score=1.8,
        action_items=["Fail over the identity provider"],
        call_type="support",
        start_time=start,
        end_time=start,
        organizer_email="jamie@aegiscloud.com",
        participants=["jamie@aegiscloud.com", "alex@example.com"],
        customer_domains=["example.com"],
        speakers=["Alex", "Jamie"],
        turns=[
            SpeakerTurn("Alex", 0, 5, "SSO is down for forty users.", "negative", 0.9),
            SpeakerTurn("Jamie", 6, 12, "We are failing over the identity provider.", "neutral", 0.9),
        ],
        events=[],
        key_moments=[
            KeyMoment(30, "Alex says they are evaluating SentinelShield.", "churn_signal", "Alex"),
        ],
        account_name="Example Co",
    )
    payload.update(overrides)
    meeting = Meeting(**payload)
    meeting.features = MeetingFeatureExtractor().extract(meeting)
    return meeting


def test_governed_theme_prefers_provided_labels():
    billing = _meeting(
        meeting_id="b",
        title="Support Case #2 - Example Co invoice",
        topics=["billing dispute", "seat overage"],
        summary="The invoice includes seats from a migration.",
    )
    primary, matched = assign_governed_theme(billing)
    assert primary == "billing"
    assert "billing" in matched

    compliance = _meeting(topics=["hipaa compliance", "audit preparation"], summary="Preparing for HIPAA.")
    assert assign_governed_theme(compliance)[0] == "compliance"

    commercial = _meeting(topics=["renewal", "churn risk"], summary="Renewal is at risk.")
    assert assign_governed_theme(commercial)[0] == "commercial"


def test_generated_topics_do_not_require_provided_labels():
    meetings = []
    for index, topic in enumerate(["outage pipeline latency"] * 3 + ["hipaa audit evidence"] * 3):
        meetings.append(
            _meeting(
                meeting_id=f"t{index}",
                topics=["unrelated label that should not steer the model"],
                summary=f"{topic} {topic} during the customer conversation about {topic}.",
                transcript=f"Speaker: We discussed {topic} and then {topic} again with the account team.",
            )
        )
    analysis = TopicAnalyzer().analyze(meetings)
    assert analysis.model_name == "lexical-nmf"
    assert analysis.generated
    assert all(meeting.primary_theme for meeting in meetings)
    # The held-out label is not a generated term.
    flat_terms = " ".join(term for topic in analysis.generated for term in topic.terms)
    assert "unrelated" not in flat_terms


def test_bertopic_contract_without_the_package(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name == "bertopic":
            raise ImportError("bertopic missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    with pytest.raises(RuntimeError, match="BERTopic is not installed"):
        BertopicTopicModel().fit(["one document about outages", "another document about renewals"])


def test_sentiment_and_insights_on_a_small_book():
    support = _meeting(meeting_id="s", call_type="support", sentiment_score=1.8, sentiment="negative")
    external = _meeting(
        meeting_id="e",
        call_type="external",
        title="Aegis / Example Co - Renewal",
        sentiment="mixed-positive",
        sentiment_score=3.8,
        topics=["renewal"],
        key_moments=[KeyMoment(10, "They are evaluating SentinelShield before renewal.", "churn_signal", "Alex")],
    )
    internal = _meeting(
        meeting_id="i",
        call_type="internal",
        title="INCIDENT: Detect Pipeline Failure - War Room",
        sentiment="negative",
        sentiment_score=1.8,
        topics=["outage", "incident response"],
        customer_domains=[],
        account_name="",
        key_moments=[KeyMoment(4, "The health check never saw the stuck node.", "technical_issue", "Raj")],
    )
    meetings = [support, external, internal]
    sentiment = SentimentAnalyzer().analyze(meetings)
    assert sentiment.by_call_type
    assert any(note.interpretation_id == "call-type-gap" for note in sentiment.interpretations)

    insights = InsightAnalyzer().analyze(meetings)
    stakeholders = {insight.stakeholder for insight in insights}
    assert {"support", "product", "engineering", "sales"} <= stakeholders
    sales = next(insight for insight in insights if insight.insight_id == "sales-at-risk")
    assert any(detail.label == "Example Co" for detail in sales.details)

    topics = TopicAnalyzer().analyze(meetings)
    quality = InsightQualityScore.evaluate(meetings, insights, sentiment, topics)
    for value in (quality.coverage, quality.consistency, quality.actionability, quality.confidence, quality.composite):
        assert 0.0 <= value <= 1.0
    assert "human-in-the-loop" in quality.next_evolution
