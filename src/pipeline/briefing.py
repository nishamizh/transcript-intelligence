"""The two sentences a leadership review should hear before any chart."""

from __future__ import annotations

from src.analytics.insight_analyzer import Insight
from src.analytics.sentiment_analyzer import SentimentAnalysis


def compose_headline(sentiment: SentimentAnalysis, insights: list[Insight]) -> tuple[str, str]:
    if not sentiment.by_call_type:
        return (
            "The corpus did not produce a call-type cut.",
            "Check ingestion before reading the rest of the briefing.",
        )
    ordered = sorted(sentiment.by_call_type, key=lambda row: row.mean_score)
    cold = ordered[0]
    warm = ordered[-1]
    gap = warm.mean_score - cold.mean_score
    incident = sentiment.incident
    risk = next((insight for insight in insights if insight.insight_id == "sales-at-risk"), None)
    risk_clause = ""
    if risk is not None:
        risk_clause = f" {risk.metric_value} accounts already have churn language on a recording."

    if incident.count and incident.mean_score + 0.4 < sentiment.overall_mean:
        event = (
            f" Incident-titled meetings average {incident.mean_score:.2f}, "
            f"against {sentiment.overall_mean:.2f} for the corpus, and the outage is still being discussed "
            f"in {sentiment.outage_mention.count} meetings."
        )
    else:
        event = ""

    headline = (
        f"{cold.call_type.title()} calls are the cold part of this book at {cold.mean_score:.2f} on a 1–5 scale, "
        f"{gap:.2f} points below {warm.call_type}."
        f"{event}{risk_clause}"
    )
    subhead = (
        "The same meetings feed four decisions: what support should staff, which module owns the gaps, "
        "which failure pattern engineering should stop repeating, and which accounts sales should treat as one book of work."
    )
    return headline, subhead


def method_notes(model_name: str) -> dict[str, str]:
    return {
        "architecture": (
            "Folders become Meeting objects in one loader. Feature extraction, topic analysis, "
            "sentiment analysis, and insight generation only see that object. The dashboard, the charts, "
            "and this report are consumers of the pipeline output, not readers of the raw JSON."
        ),
        "categorization": (
            "Categories are a governed taxonomy mapped from the provided topic labels, audited by a topic "
            f"model ({model_name}) fit on the summary and transcript with those labels held out. "
            "Raw labels stay attached as evidence. The model behind the audit is swappable: "
            "lexical NMF is the default, BERTopic implements the same TopicModel contract."
        ),
        "sentiment": (
            "Meeting scores and labels are used as recorded. Turns carry their own polarity and are "
            "rolled up by call type. The writing around the charts is generated from the gaps, so a "
            "different corpus produces a different sentence rather than a fixed March-outage story."
        ),
        "governance": (
            "Most provided labels appear once. Publishing them as categories would look precise and be unstable. "
            "The review queue is the set of meetings where the governed theme and the generated topic share no tokens."
        ),
        "extensibility": (
            "A new analytic implements Analyzer.analyze(meetings) and is called from the runner. "
            "A new stakeholder is a function that returns Insights. A new consumer reads report.json. "
            "None of those changes should reopen the loader."
        ),
        "consumption": (
            "Support, product, engineering, and sales read different sections of one report. "
            "They share evidence ids, so a quote in the sales book can be opened as the same meeting "
            "a support leader is already looking at."
        ),
    }
