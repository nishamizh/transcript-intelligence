"""Run ingestion and every analyzer, then write the report consumers share.

    python -m src.pipeline.runner --data data --output output
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path

from src.analytics.features import MeetingFeatureExtractor
from src.analytics.insight_analyzer import InsightAnalyzer
from src.analytics.quality import InsightQualityScore
from src.analytics.sentiment_analyzer import SentimentAnalyzer
from src.analytics.topic_analyzer import TopicAnalyzer, build_topic_model
from src.config.settings import Settings
from src.ingestion.loader import DatasetLoader
from src.models.meeting import Meeting
from src.pipeline.briefing import compose_headline, method_notes
from src.pipeline.methodology import build_methodology
from src.review.decisions import ensure_decision_template
from src.review.queue import build_review_queue, write_review_queue
from src.visualization.charts import render_charts


def run(settings: Settings | None = None) -> dict:
    settings = settings or Settings()
    loader = DatasetLoader(settings.data_dir, internal_domain=settings.internal_domain)
    meetings = loader.load_dataset()
    extractor = MeetingFeatureExtractor()
    for meeting in meetings:
        meeting.features = extractor.extract(meeting)

    topic_model = build_topic_model(settings.topic_model, settings.n_topics, settings.random_state)
    topics = TopicAnalyzer(topic_model).analyze(meetings)
    sentiment = SentimentAnalyzer().analyze(meetings)
    insights = InsightAnalyzer(settings.competitors).analyze(meetings)
    quality = InsightQualityScore.evaluate(meetings, insights, sentiment, topics)
    methodology = build_methodology(topics, sentiment, settings)
    review_queue = build_review_queue(meetings, insights)
    headline, subhead = compose_headline(sentiment, insights)

    dates = sorted(meeting.date_key() for meeting in meetings)
    call_types: dict[str, int] = {}
    for meeting in meetings:
        call_types[meeting.call_type] = call_types.get(meeting.call_type, 0) + 1

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "headline": headline,
        "subhead": subhead,
        "dataset": {
            "meeting_count": len(meetings),
            "load_failures": len(loader.errors),
            "failures": [asdict(error) for error in loader.errors],
            "start_date": dates[0] if dates else None,
            "end_date": dates[-1] if dates else None,
            "call_types": call_types,
            "internal_domain": settings.internal_domain,
            "topic_model": topics.model_name,
        },
        "meetings": [_public_meeting(meeting) for meeting in meetings],
        "sentiment": _jsonable(sentiment),
        "topics": _jsonable(topics),
        "insights": _jsonable(insights),
        "quality": _jsonable(quality),
        "method": method_notes(topics.model_name),
        "methodology": methodology,
        "review_queue": review_queue,
    }
    # The exemplar artifact is also the top-level name the assignment reads.
    # It stays inside topics as well so either path resolves the same object.
    report["topic_examples"] = report["topics"]["topic_examples"]

    settings.output_dir.mkdir(parents=True, exist_ok=True)
    report_path = settings.output_dir / "report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_review_queue(review_queue, settings.output_dir)
    ensure_decision_template(
        settings.output_dir / "review_decisions.json",
        [item["item_id"] for item in review_queue["items"]],
    )
    render_charts(sentiment, topics, settings.output_dir / "charts")
    if settings.web_data_path:
        settings.web_data_path.parent.mkdir(parents=True, exist_ok=True)
        settings.web_data_path.write_text(json.dumps(report), encoding="utf-8")
    _print_briefing(report, report_path)
    return report


def _public_meeting(meeting: Meeting) -> dict:
    features = meeting.features
    return {
        "meeting_id": meeting.meeting_id,
        "title": meeting.title,
        "call_type": meeting.call_type,
        "date": meeting.date_key(),
        "month": meeting.month_key(),
        "duration_minutes": round(meeting.duration_minutes, 2),
        "sentiment": meeting.sentiment,
        "sentiment_score": meeting.sentiment_score,
        "topics": meeting.topics,
        "primary_theme": meeting.primary_theme,
        "governed_themes": meeting.governed_themes,
        "generated_topic": meeting.generated_topic,
        "generated_terms": meeting.generated_terms,
        "topic_agreement": round(meeting.topic_agreement, 4),
        "lexical_topic_overlap": round(meeting.topic_agreement, 4),
        "lexical_overlap_status": _overlap_status(meeting.topic_agreement),
        "action_items": meeting.action_items,
        "account_name": meeting.account_name,
        "customer_domains": meeting.customer_domains,
        "summary": meeting.summary,
        "excerpt": meeting.excerpt(4),
        "key_moments": [
            {
                "time_seconds": moment.time_seconds,
                "text": moment.text,
                "moment_type": moment.moment_type,
                "speaker": moment.speaker,
            }
            for moment in meeting.key_moments
        ],
        "features": {
            "participant_count": features.participant_count if features else 0,
            "invitee_count": features.invitee_count if features else 0,
            "topic_count": features.topic_count if features else 0,
            "action_item_count": features.action_item_count if features else 0,
            "speaking_turns": features.speaking_turns if features else 0,
            "sentiment_score": features.sentiment_score if features else 0,
            "duration_minutes": features.duration_minutes if features else 0,
            "transcript_words": features.transcript_words if features else 0,
            "negative_turn_share": features.negative_turn_share if features else 0,
            "positive_turn_share": features.positive_turn_share if features else 0,
            "late_join_count": features.late_join_count if features else 0,
            "talk_share_top_speaker": features.talk_share_top_speaker if features else 0,
            "moment_counts": features.moment_counts if features else {},
        },
    }


def _jsonable(value):
    if is_dataclass(value) and not isinstance(value, type):
        return {key: _jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return round(value, 4)
    if isinstance(value, Path):
        return str(value)
    return value


def _print_briefing(report: dict, report_path: Path) -> None:
    dataset = report["dataset"]
    quality = report["quality"]
    print("Transcript Intelligence")
    print(
        f"Loaded {dataset['meeting_count']} meetings "
        f"({dataset['load_failures']} failures) from {dataset['start_date']} to {dataset['end_date']}."
    )
    print("Call types: " + ", ".join(f"{name} {count}" for name, count in dataset["call_types"].items()))
    print()
    print(report["headline"])
    print(report["subhead"])
    print()
    for insight in report["insights"]:
        print(f"[{insight['stakeholder']}] {insight['title']} — {insight['metric_label']}: {insight['metric_value']}")
    print()
    print(
        "Quality "
        f"composite {quality['composite']:.0%} "
        f"(coverage {quality['coverage']:.0%}, consistency {quality['consistency']:.0%}, "
        f"actionability {quality['actionability']:.0%}, confidence {quality['confidence']:.0%})."
    )
    print(quality["next_evolution"])
    print()
    queue = report["review_queue"]
    print(
        f"Review queue: {queue['item_count']} items. "
        "Theme accuracy is unavailable until review_decisions.json has accept, edit, or reject rows."
    )
    print(f"Wrote {report_path}")


def _overlap_status(score: float) -> str:
    from src.analytics.topic_analyzer import overlap_status

    return overlap_status(score)


def main() -> None:
    run(Settings.from_args())


if __name__ == "__main__":
    main()
