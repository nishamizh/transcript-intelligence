"""Recompute the headline counts from the loaded meetings.

A match means the published report is reproducible from this code and this
corpus. It does not mean a person has verified the meaning of the claim.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from src.analytics.insight_analyzer import InsightAnalyzer
from src.analytics.sentiment_analyzer import _mentions_outage
from src.analytics.topic_analyzer import THEMES
from src.ingestion.loader import DatasetLoader
from src.models.meeting import Meeting
from src.review.decisions import atomic_write_json

CALCULATION_VERSION = "claims-audit-v1"


def build_claims_audit(meetings: list[Meeting], report: dict) -> dict:
    duplicate_ids = [meeting_id for meeting_id, count in Counter(meeting.meeting_id for meeting in meetings).items() if count > 1]
    churn_keys, churn_rule = _churn_account_keys(meetings)
    analyzer_value = _analyzer_churn_count(meetings)
    ambiguous_accounts = _ambiguous_account_names(meetings)
    support_mean, support_n = _mean(meetings, "support")
    external_mean, external_n = _mean(meetings, "external")
    outage_count = sum(1 for meeting in meetings if _mentions_outage(meeting))
    reported_support = _reported_call_mean(report, "support")
    reported_external = _reported_call_mean(report, "external")
    reported_outage = ((report.get("sentiment") or {}).get("outage_mention") or {}).get("count")
    reported_meetings = (report.get("dataset") or {}).get("meeting_count")
    reported_themes = len((report.get("topics") or {}).get("themes") or [])
    sales = _reported_insight(report, "sales-at-risk")

    claims = [
        _claim(
            "transcripts_processed",
            len(meetings),
            reported_meetings,
            len(meetings),
            "Count of meeting folders that loaded. One folder is one meeting. Duplicate meeting ids are listed separately and are not dropped.",
        ),
        _claim(
            "governed_topic_categories",
            len(THEMES),
            reported_themes,
            len(THEMES),
            "Count of theme definitions in the governed taxonomy. This is the list length, not the number of meetings that received a theme.",
        ),
        _claim(
            "mean_support_sentiment",
            support_mean,
            reported_support,
            support_n,
            "Arithmetic mean of summary.json sentimentScore for meetings whose call type is support. Compared at two decimal places, which is how the briefing prints the mean.",
            tolerance=0.005,
        ),
        _claim(
            "mean_external_sentiment",
            external_mean,
            reported_external,
            external_n,
            "Arithmetic mean of summary.json sentimentScore for meetings whose call type is external. Compared at two decimal places.",
            tolerance=0.005,
        ),
        _claim(
            "outage_related_meetings",
            outage_count,
            reported_outage,
            len(meetings),
            "Meetings whose title, summary, or supplied topics contain 'outage' or 'pipeline failure'. This is the sentiment analyzer's outage cohort, which is wider than incident-titled meetings.",
        ),
        _claim(
            "accounts_with_churn_language",
            len(churn_keys),
            _as_int(sales),
            len(churn_keys),
            churn_rule,
        ),
    ]
    if analyzer_value is not None and analyzer_value != len(churn_keys):
        claims.append(
            _claim(
                "churn_account_definition_drift",
                len(churn_keys),
                analyzer_value,
                len(churn_keys),
                "The audit's account rollup disagreed with InsightAnalyzer. Both numbers are shown. The data was not edited.",
            )
        )
    return {
        "version": 1,
        "calculation_version": CALCULATION_VERSION,
        "review_status": "not_human_verified",
        "status": "reproduced" if all(row["check_status"] == "match" for row in claims) else "difference_disclosed",
        "duplicate_meeting_ids": duplicate_ids,
        "ambiguous_account_matches": ambiguous_accounts,
        "note": (
            "check_status is whether this run recomputes the published number. "
            "review_status stays not_human_verified. A match is not acceptance of the business conclusion. "
            "Account identity uses account_name, and falls back to the only external domain when the name is blank. "
            "Meetings that share a domain but carry different account names are listed as ambiguous matches and are not silently merged."
        ),
        "claims": claims,
    }


def write_claims_audit(payload: dict, output_dir: Path) -> Path:
    path = output_dir / "claims_audit.json"
    atomic_write_json(path, payload)
    return path


def _claim(
    name: str,
    computed,
    reported,
    source_count: int,
    method: str,
    tolerance: float = 0.0,
) -> dict:
    status = _compare(computed, reported, tolerance)
    return {
        "metric_name": name,
        "computed_value": computed,
        "reported_value": reported,
        "source_count": source_count,
        "aggregation_method": method,
        "calculation_version": CALCULATION_VERSION,
        "check_status": status,
        "review_status": "not_human_verified",
    }


def _compare(computed, reported, tolerance: float) -> str:
    if reported is None:
        return "reported_value_missing"
    if isinstance(computed, float) or isinstance(reported, float):
        try:
            if abs(float(computed) - float(reported)) <= tolerance:
                return "match"
        except (TypeError, ValueError):
            return "not_comparable"
        return "mismatch"
    return "match" if computed == reported else "mismatch"


def _mean(meetings: list[Meeting], call_type: str) -> tuple[float | None, int]:
    scores = [meeting.sentiment_score for meeting in meetings if meeting.call_type == call_type]
    if not scores:
        return None, 0
    return round(sum(scores) / len(scores), 4), len(scores)


def _churn_account_keys(meetings: list[Meeting]) -> tuple[set[str], str]:
    keys: set[str] = set()
    for meeting in meetings:
        if not meeting.customer_domains:
            continue
        if not any(moment.moment_type == "churn_signal" for moment in meeting.key_moments):
            continue
        key = meeting.account_name or meeting.customer_domains[0]
        if key:
            keys.add(key)
    rule = (
        "Distinct account keys among meetings that have an external domain and at least one source key moment "
        "of type churn_signal. The key is account_name, or the only fallback customer_domains[0] when account_name is blank. "
        "Several meetings for one account count once. This is the same rollup the sales-at-risk finding publishes. "
        "It is not a forecast."
    )
    return keys, rule


def _analyzer_churn_count(meetings: list[Meeting]) -> int | None:
    for insight in InsightAnalyzer().analyze(meetings):
        if insight.insight_id == "sales-at-risk":
            try:
                return int(insight.metric_value)
            except (TypeError, ValueError):
                return None
    return None


def _ambiguous_account_names(meetings: list[Meeting]) -> list[dict]:
    names: dict[str, set[str]] = defaultdict(set)
    for meeting in meetings:
        if len(meeting.customer_domains) != 1 or not meeting.account_name:
            continue
        names[meeting.customer_domains[0]].add(meeting.account_name)
    return [
        {"domain": domain, "account_names": sorted(found)}
        for domain, found in sorted(names.items())
        if len(found) > 1
    ]


def _reported_call_mean(report: dict, call_type: str):
    for row in (report.get("sentiment") or {}).get("by_call_type") or []:
        if row.get("call_type") == call_type:
            return row.get("mean_score")
    return None


def _reported_insight(report: dict, insight_id: str):
    for insight in report.get("insights") or []:
        if insight.get("insight_id") == insight_id:
            return insight.get("metric_value")
    return None


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Recompute headline counts from the dataset. Does not create reviewer labels.")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--report", type=Path, default=Path("output/report.json"))
    parser.add_argument("--output", type=Path, default=Path("output"))
    args = parser.parse_args(argv)
    meetings = DatasetLoader(args.data).load_dataset()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    payload = build_claims_audit(meetings, report)
    path = write_claims_audit(payload, args.output)
    print(f"Wrote {path}")
    print(f"Claims audit: {payload['status']}. Human review status: {payload['review_status']}.")
    for claim in payload["claims"]:
        print(f"{claim['metric_name']}: computed {claim['computed_value']} reported {claim['reported_value']} {claim['check_status']}")


if __name__ == "__main__":
    main()
