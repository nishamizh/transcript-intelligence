from dataclasses import dataclass


@dataclass(slots=True)
class MeetingFeatures:

    meeting_id: str

    title: str

    duration_minutes: float

    topic_count: int

    action_item_count: int

    transcript_length: int

    sentiment: str

    sentiment_score: float