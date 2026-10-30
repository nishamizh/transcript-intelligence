from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.analytics.features import MeetingFeatureExtractor
from src.ingestion.loader import (
    DatasetLoader,
    MeetingLoader,
    account_name_from_title,
    classify_call_type,
)

DATA = Path("data")
INTERNAL = "aegiscloud.com"


def test_call_type_precedence():
    emails = ["a@aegiscloud.com", "b@blackridgeinvest.com"]
    assert classify_call_type("Support Case #1 - Blackridge login", emails, INTERNAL) == "support"
    assert classify_call_type("Aegis / Blackridge Investments - Renewal", emails, INTERNAL) == "external"
    assert classify_call_type("URGENT: Cobalt Software - Detect down", emails, INTERNAL) == "external"
    assert classify_call_type("INCIDENT: Detect Pipeline Failure - War Room", ["a@aegiscloud.com"], INTERNAL) == "internal"
    assert classify_call_type("Weekly Engineering Standup", ["a@aegiscloud.com"], INTERNAL) == "internal"


def test_account_name_from_external_title():
    assert account_name_from_title("Aegis / Blackridge Investments - HIPAA Compliance Review") == "Blackridge Investments"
    assert account_name_from_title("URGENT: Cobalt Software - Aegis Detect Dashboard Down") == "Cobalt Software"


@pytest.mark.skipif(not DATA.exists(), reason="dataset is not in the workspace")
def test_loader_reads_a_real_meeting():
    meeting = MeetingLoader().load_folder(DATA / "01KQ03B0303900521BB089CA")
    assert meeting.meeting_id == "01KQ03B0303900521BB089CA"
    assert meeting.title == "Detect Outage - Remediation Plan Review"
    assert meeting.call_type == "internal"
    assert meeting.sentiment == "mixed-negative"
    assert meeting.sentiment_score == pytest.approx(2.4)
    assert "outage remediation" in meeting.topics
    assert len(meeting.action_items) == 4
    assert "Raj" in meeting.transcript
    assert meeting.turns
    assert meeting.key_moments

    features = MeetingFeatureExtractor().extract(meeting)
    assert features.participant_count == 3
    assert features.speaking_turns == len(meeting.turns)
    assert features.action_item_count == 4
    assert features.topic_count == len(meeting.topics)
    assert "churn_signal" in features.moment_counts


@pytest.mark.skipif(not DATA.exists(), reason="dataset is not in the workspace")
def test_dataset_call_types_and_account_names():
    meetings = DatasetLoader(DATA).load_dataset()
    assert len(meetings) == 100
    counts = {}
    for meeting in meetings:
        counts[meeting.call_type] = counts.get(meeting.call_type, 0) + 1
    assert counts == {"support": 27, "external": 43, "internal": 30}

    external = next(meeting for meeting in meetings if meeting.title.startswith("Aegis / Blackridge"))
    assert "blackridgeinvest.com" in external.customer_domains
    assert external.account_name == "Blackridge Investments"

    support = next(meeting for meeting in meetings if meeting.title.startswith("Support Case #8811"))
    assert support.call_type == "support"
    assert support.account_name == "Blackridge Investments"
    assert meeting_has_tz(external)


def meeting_has_tz(meeting) -> bool:
    assert isinstance(meeting.start_time, datetime)
    assert meeting.start_time.tzinfo is not None
    assert meeting.start_time.year == 2026
    assert meeting.start_time.tzinfo == timezone.utc or meeting.start_time.utcoffset() is not None
    return True
