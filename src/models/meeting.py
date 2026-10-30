"""Canonical meeting model.

Every folder in the dataset becomes one Meeting. Topic, sentiment, and
insight analyzers all read this object and nothing upstream of it. Source
fields stay as recorded. Derived fields (features, governed themes,
generated topics) are filled in later by the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class KeyMoment:
    time_seconds: float
    text: str
    moment_type: str
    speaker: str


@dataclass(slots=True)
class SpeakerTurn:
    speaker_name: str
    start_seconds: float
    end_seconds: float
    sentence: str
    sentiment: str
    confidence: float


@dataclass(slots=True)
class ParticipantEvent:
    participant_name: str
    event_type: str
    time_seconds: float


@dataclass(slots=True)
class MeetingFeatures:
    """Row-level metrics leadership asks for without re-reading the transcript."""

    duration_minutes: float
    participant_count: int
    invitee_count: int
    topic_count: int
    action_item_count: int
    speaking_turns: int
    sentiment_score: float
    transcript_words: int
    key_moment_count: int
    late_join_count: int
    negative_turn_share: float
    positive_turn_share: float
    talk_share_top_speaker: float
    moment_counts: dict[str, int]


@dataclass(slots=True)
class Meeting:
    meeting_id: str
    title: str
    # Source field `duration` is already in minutes (a 35-minute call is 35.2).
    duration_minutes: float
    summary: str
    transcript: str
    # Labels shipped with the summary. Not the taxonomy we publish.
    topics: list[str]
    sentiment: str
    sentiment_score: float
    action_items: list[str]
    # support | external | internal. Assigned at ingestion from title and attendees.
    call_type: str
    start_time: datetime
    end_time: datetime
    organizer_email: str
    participants: list[str]
    customer_domains: list[str]
    speakers: list[str]
    turns: list[SpeakerTurn]
    events: list[ParticipantEvent]
    key_moments: list[KeyMoment]
    account_name: str = ""
    primary_theme: str = ""
    governed_themes: list[str] = field(default_factory=list)
    generated_topic: str = ""
    generated_terms: list[str] = field(default_factory=list)
    topic_agreement: float = 0.0
    features: MeetingFeatures | None = None

    def date_key(self) -> str:
        return self.start_time.date().isoformat()

    def month_key(self) -> str:
        return self.start_time.strftime("%Y-%m")

    def excerpt(self, lines: int = 4) -> str:
        parts = [line for line in self.transcript.splitlines() if line.strip()]
        return "\n".join(parts[:lines])

    def moment_texts(self, moment_type: str) -> list[KeyMoment]:
        return [moment for moment in self.key_moments if moment.moment_type == moment_type]
