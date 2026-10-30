from pathlib import Path
import json

from src.models.meeting import Meeting


class DatasetLoader:

    def __init__(self, root_path: str):
        self.root_path = Path(root_path)

    def get_meeting_folders(self):
        return [
            folder
            for folder in self.root_path.iterdir()
            if folder.is_dir()
        ]

    @staticmethod
    def read_json(path: Path):

        with open(
            path,
            "r",
            encoding="utf-8"
        ) as file:

            return json.load(file)

    def load_raw_meeting(
        self,
        folder: Path
    ):

        meeting_info = self.read_json(
            folder / "meeting-info.json"
        )

        summary = self.read_json(
            folder / "summary.json"
        )

        transcript = self.read_json(
            folder / "transcript.json"
        )

        return {
            "meeting_info": meeting_info,
            "summary": summary,
            "transcript": transcript
        }

    def build_transcript_text(
        self,
        transcript: dict
    ) -> str:

        return " ".join(
            row["sentence"]
            for row in transcript["data"]
        )

    def load_meeting(
        self,
        folder: Path
    ) -> Meeting:

        raw = self.load_raw_meeting(folder)

        meeting_info = raw["meeting_info"]
        summary = raw["summary"]
        transcript = raw["transcript"]

        transcript_text = self.build_transcript_text(
            transcript
        )

        return Meeting(
            meeting_id=meeting_info["meetingId"],
            title=meeting_info["title"],
            duration_minutes=meeting_info["duration"],
            summary=summary["summary"],
            transcript=transcript_text,
            topics=summary["topics"],
            action_items=summary["actionItems"],
            sentiment=summary["overallSentiment"],
            sentiment_score=summary["sentimentScore"]
        )

    def load_dataset(self):

        meetings = []

        for folder in self.get_meeting_folders():

            try:

                meeting = self.load_meeting(folder)

                meetings.append(meeting)

            except Exception as ex:

                print(
                    f"Error loading "
                    f"{folder.name}: {ex}"
                )

        return meetings