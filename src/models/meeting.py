from dataclasses import dataclass
from typing import List


@dataclass(slots=True)
class Meeting:
    """
    Canonical representation of a meeting.

    All downstream analytics operate on this model.
    """

    meeting_id: str

    title: str

    duration_minutes: float

    summary: str

    transcript: str

    topics: List[str]

    action_items: List[str]

    sentiment: str

    sentiment_score: float