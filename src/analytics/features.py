"""Derived, per-meeting metrics. Analyzers should prefer these over ad hoc counts."""

from __future__ import annotations

import re
from collections import Counter

from src.models.meeting import Meeting, MeetingFeatures

_WORD = re.compile(r"[A-Za-z0-9']+")
_LATE_JOIN_SECONDS = 60.0


class MeetingFeatureExtractor:
    def extract(self, meeting: Meeting) -> MeetingFeatures:
        talk_totals: dict[str, float] = {}
        sentiment_counts: Counter[str] = Counter()
        for turn in meeting.turns:
            sentiment_counts[turn.sentiment] += 1
            elapsed = max(0.0, turn.end_seconds - turn.start_seconds)
            talk_totals[turn.speaker_name] = talk_totals.get(turn.speaker_name, 0.0) + elapsed

        turn_count = len(meeting.turns)
        negative_share = (
            sentiment_counts.get("negative", 0) / turn_count if turn_count else 0.0
        )
        positive_share = (
            sentiment_counts.get("positive", 0) / turn_count if turn_count else 0.0
        )
        total_talk = sum(talk_totals.values())
        top_share = max(talk_totals.values()) / total_talk if total_talk else 0.0

        late_people = {
            event.participant_name
            for event in meeting.events
            if event.event_type.lower() == "join" and event.time_seconds >= _LATE_JOIN_SECONDS
        }

        return MeetingFeatures(
            duration_minutes=meeting.duration_minutes,
            participant_count=len(meeting.speakers),
            invitee_count=len(meeting.participants),
            topic_count=len(meeting.topics),
            action_item_count=len(meeting.action_items),
            speaking_turns=turn_count,
            sentiment_score=meeting.sentiment_score,
            transcript_words=len(_WORD.findall(meeting.transcript)),
            key_moment_count=len(meeting.key_moments),
            late_join_count=len(late_people),
            negative_turn_share=round(negative_share, 4),
            positive_turn_share=round(positive_share, 4),
            talk_share_top_speaker=round(top_share, 4),
            moment_counts=dict(Counter(moment.moment_type for moment in meeting.key_moments)),
        )
