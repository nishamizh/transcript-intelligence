"""Turn a folder of JSON files into a Meeting.

MeetingLoader owns one folder. DatasetLoader owns the corpus and the
account-name pass that needs every meeting in view. Call type is assigned
here because it is a property of who was in the room, not a discovered theme.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.models.meeting import KeyMoment, Meeting, ParticipantEvent, SpeakerTurn

_ACCOUNT_PATTERNS = (
    re.compile(r"^Aegis\s*/\s*(.+?)\s+-\s+", re.IGNORECASE),
    re.compile(r"^URGENT:\s*(.+?)\s+-\s+", re.IGNORECASE),
    re.compile(r"^ESCALATION:\s*(.+?)\s+-\s+", re.IGNORECASE),
)


def classify_call_type(title: str, emails: list[str], internal_domain: str) -> str:
    """Classify a meeting into the three call types the business uses.

    Support wins on the title prefix even when a customer is present, because
    those calls are a different motion (a case) than an account review.
    Any other meeting with a non-employee domain is external. The rest are
    internal, including incident bridges where no customer was invited.
    """

    if title.lower().startswith("support case"):
        return "support"
    internal = internal_domain.lower()
    for email in emails:
        if "@" not in email:
            continue
        domain = email.split("@", 1)[1].lower()
        if domain != internal:
            return "external"
    return "internal"


def external_domains(emails: list[str], internal_domain: str) -> list[str]:
    internal = internal_domain.lower()
    found: list[str] = []
    for email in emails:
        if "@" not in email:
            continue
        domain = email.split("@", 1)[1].lower()
        if domain != internal and domain not in found:
            found.append(domain)
    return found


def account_name_from_title(title: str) -> str | None:
    for pattern in _ACCOUNT_PATTERNS:
        match = pattern.search(title)
        if match:
            name = re.sub(r"\s+", " ", match.group(1)).strip(" -")
            if name:
                return name
    return None


@dataclass(slots=True)
class LoadError:
    folder: str
    message: str


class MeetingLoader:
    def __init__(self, internal_domain: str = "aegiscloud.com"):
        self.internal_domain = internal_domain.lower()

    def load_folder(self, folder_path: Path) -> Meeting:
        folder = Path(folder_path)
        info = _read_json(folder / "meeting-info.json")
        summary = _read_json(folder / "summary.json")
        transcript_payload = _read_json(folder / "transcript.json")
        speakers_payload = _read_optional_json(folder / "speakers.json", default=[])
        events_payload = _read_optional_json(folder / "events.json", default=[])

        emails = _as_str_list(info.get("allEmails") or info.get("invitees"))
        turns, transcript = _build_turns(transcript_payload)
        speakers = _speaker_names(turns, speakers_payload)
        start = _parse_time(str(info.get("startTime") or ""))
        end = _parse_time(str(info.get("endTime") or "")) or start

        return Meeting(
            meeting_id=str(info.get("meetingId") or folder.name),
            title=str(info.get("title") or folder.name),
            duration_minutes=_as_float(info.get("duration")),
            summary=str(summary.get("summary") or "").strip(),
            transcript=transcript,
            topics=_as_str_list(summary.get("topics")),
            sentiment=str(summary.get("overallSentiment") or "unknown").strip().lower(),
            sentiment_score=_as_float(summary.get("sentimentScore")),
            action_items=_as_str_list(summary.get("actionItems")),
            call_type=classify_call_type(
                str(info.get("title") or ""),
                emails,
                self.internal_domain,
            ),
            start_time=start,
            end_time=end,
            organizer_email=str(info.get("organizerEmail") or ""),
            participants=emails,
            customer_domains=external_domains(emails, self.internal_domain),
            speakers=speakers,
            turns=turns,
            events=_build_events(events_payload),
            key_moments=_build_moments(summary.get("keyMoments")),
        )


class DatasetLoader:
    def __init__(
        self,
        root_path: str | Path,
        meeting_loader: MeetingLoader | None = None,
        internal_domain: str = "aegiscloud.com",
    ):
        self.root_path = Path(root_path)
        self.meeting_loader = meeting_loader or MeetingLoader(internal_domain)
        self.errors: list[LoadError] = []

    def iter_folders(self) -> list[Path]:
        if not self.root_path.exists():
            raise FileNotFoundError(f"Dataset path does not exist: {self.root_path}")
        return sorted(
            folder
            for folder in self.root_path.iterdir()
            if folder.is_dir() and (folder / "meeting-info.json").exists()
        )

    def load_dataset(self, root_path: str | Path | None = None) -> list[Meeting]:
        if root_path is not None:
            self.root_path = Path(root_path)
        self.errors = []
        meetings: list[Meeting] = []
        for folder in self.iter_folders():
            try:
                meetings.append(self.meeting_loader.load_folder(folder))
            except Exception as exc:  # one bad folder should not drop the corpus
                self.errors.append(LoadError(folder.name, str(exc)))
        _assign_account_names(meetings)
        return meetings


def _assign_account_names(meetings: list[Meeting]) -> None:
    """Learn account names from unambiguous titles, then apply them by domain.

    Support-case titles bury the customer name in free text. External titles
    use a stable 'Aegis / {Account} - {Subject}' pattern, so the domain map is
    learned there and reused everywhere that domain appears.
    """

    domain_to_name: dict[str, str] = {}
    for meeting in meetings:
        if len(meeting.customer_domains) != 1:
            continue
        name = account_name_from_title(meeting.title)
        if name:
            domain_to_name.setdefault(meeting.customer_domains[0], name)

    known = sorted(set(domain_to_name.values()), key=len, reverse=True)
    for meeting in meetings:
        if len(meeting.customer_domains) != 1:
            continue
        domain = meeting.customer_domains[0]
        if domain in domain_to_name:
            continue
        title_lower = meeting.title.lower()
        for name in known:
            if name.lower() in title_lower:
                domain_to_name[domain] = name
                break

    for meeting in meetings:
        names: list[str] = []
        for domain in meeting.customer_domains:
            name = domain_to_name.get(domain)
            if name and name not in names:
                names.append(name)
        if names:
            meeting.account_name = " · ".join(names)
        elif meeting.customer_domains:
            stem = meeting.customer_domains[0].split(".")[0]
            meeting.account_name = stem.replace("-", " ").title()


def _read_json(path: Path) -> dict | list:
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, (dict, list)):
        raise ValueError(f"{path.name} must be a JSON object or array")
    return payload


def _read_optional_json(path: Path, default: dict | list) -> dict | list:
    if not path.exists():
        return default
    return _read_json(path)


def _parse_time(value: str) -> datetime:
    text = value.strip()
    if not text:
        return datetime.fromtimestamp(0, datetime.now().astimezone().tzinfo)
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def _as_float(value: object) -> float:
    if value is None or value == "":
        return 0.0
    return float(value)  # type: ignore[arg-type]


def _as_str_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _build_turns(payload: dict | list) -> tuple[list[SpeakerTurn], str]:
    rows: list = []
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            rows = data
    elif isinstance(payload, list):
        rows = payload

    turns: list[SpeakerTurn] = []
    lines: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        sentence = str(row.get("sentence") or "").strip()
        speaker = str(row.get("speaker_name") or "Unknown").strip() or "Unknown"
        if not sentence:
            continue
        turns.append(
            SpeakerTurn(
                speaker_name=speaker,
                start_seconds=_as_float(row.get("time")),
                end_seconds=_as_float(row.get("endTime")),
                sentence=sentence,
                sentiment=str(row.get("sentimentType") or "neutral").strip().lower(),
                confidence=_as_float(row.get("averageConfidence")),
            )
        )
        lines.append(f"{speaker}: {sentence}")
    return turns, "\n".join(lines)


def _speaker_names(turns: list[SpeakerTurn], speakers_payload: dict | list) -> list[str]:
    names: list[str] = []
    for turn in turns:
        if turn.speaker_name not in names:
            names.append(turn.speaker_name)
    if names:
        return names
    if isinstance(speakers_payload, list):
        for row in speakers_payload:
            if isinstance(row, dict):
                name = str(row.get("speakerName") or "").strip()
                if name and name not in names:
                    names.append(name)
    return names


def _build_events(payload: dict | list) -> list[ParticipantEvent]:
    rows = payload if isinstance(payload, list) else []
    events: list[ParticipantEvent] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        events.append(
            ParticipantEvent(
                participant_name=str(row.get("participantName") or "Unknown"),
                event_type=str(row.get("type") or ""),
                time_seconds=_as_float(row.get("time")),
            )
        )
    return events


def _build_moments(payload: object) -> list[KeyMoment]:
    if not isinstance(payload, list):
        return []
    moments: list[KeyMoment] = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        text = str(row.get("text") or "").strip()
        if not text:
            continue
        moments.append(
            KeyMoment(
                time_seconds=_as_float(row.get("time")),
                text=text,
                moment_type=str(row.get("type") or "note").strip(),
                speaker=str(row.get("speaker") or "").strip(),
            )
        )
    return moments
