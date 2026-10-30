from src.models.meeting import Meeting
from src.models.meeting_features import MeetingFeatures


class MeetingFeatureExtractor:
    """
        Converts a Meeting into a set of derived metrics.
        """

    def extract(
        self,
        meeting: Meeting
    ) -> MeetingFeatures:

        return MeetingFeatures(

            meeting_id=meeting.meeting_id,

            title=meeting.title,

            duration_minutes=meeting.duration_minutes,

            topic_count=len(meeting.topics),

            action_item_count=len(
                meeting.action_items
            ),

            transcript_length=len(
                meeting.transcript
            ),

            sentiment=meeting.sentiment,

            sentiment_score=meeting.sentiment_score
        )