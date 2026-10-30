"""Stakeholder-specific insights from the same canonical meetings.

Support, product, engineering, and sales do not want the same chart. They want
a finding, the reason it changes a decision, the meetings that justify it, and
a next action. Adding a stakeholder means adding a method that returns Insights.
It should not require a new pipeline.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from src.analytics.base import Analyzer
from src.analytics.topic_analyzer import _THEME_BY_ID
from src.models.meeting import Meeting

_PRODUCTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Detect", ("detect",)),
    ("Comply", ("comply",)),
    ("Protect", ("protect", "backup")),
    ("Identity", ("identity", "sso", "saml", "scim", "ldap", "mfa")),
)

_ROOT_CAUSES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Single point of failure", ("single point", "no redundancy", "no failover", "cascad")),
    ("Monitoring blind spot", ("health check", "status page", "failed to catch", "heartbeat", "wasn't updated")),
    ("Customer communication", ("not notified", "no proactive", "proactive customer", "hearing about", "first time")),
    ("Identity and access failures", ("sso", "saml", "scim", "ldap", "mfa", "provision")),
    ("Pipeline, latency, and data gaps", ("latency", "queue", "timeout", "data gap", "not processing")),
)


@dataclass(slots=True)
class Evidence:
    meeting_id: str
    title: str
    call_type: str
    date: str
    account_name: str
    sentiment: str
    sentiment_score: float
    quote: str


@dataclass(slots=True)
class InsightDetail:
    label: str
    value: str
    note: str


@dataclass(slots=True)
class Insight:
    insight_id: str
    stakeholder: str
    title: str
    finding: str
    why_it_matters: str
    recommendation: str
    metric_label: str
    metric_value: str
    evidence: list[Evidence] = field(default_factory=list)
    details: list[InsightDetail] = field(default_factory=list)


def _of_type(meetings: list[Meeting], call_type: str) -> list[Meeting]:
    return [meeting for meeting in meetings if meeting.call_type == call_type]


def _evidence(meeting: Meeting, quote: str) -> Evidence:
    return Evidence(
        meeting_id=meeting.meeting_id,
        title=meeting.title,
        call_type=meeting.call_type,
        date=meeting.date_key(),
        account_name=meeting.account_name,
        sentiment=meeting.sentiment,
        sentiment_score=meeting.sentiment_score,
        quote=_clip(quote),
    )


def _clip(text: str, limit: int = 280) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _theme_name(theme_id: str) -> str:
    theme = _THEME_BY_ID.get(theme_id)
    return theme.name if theme else theme_id.replace("_", " ").title()


def _has_moment(meeting: Meeting, moment_type: str) -> bool:
    return any(moment.moment_type == moment_type for moment in meeting.key_moments)


def _product_for(text: str) -> str:
    lowered = text.lower()
    for name, keywords in _PRODUCTS:
        if any(re.search(rf"\b{re.escape(keyword)}\b", lowered) for keyword in keywords):
            return name
    return "Unspecified"


def _blob(meeting: Meeting) -> str:
    moment_text = " ".join(moment.text for moment in meeting.key_moments)
    return f"{meeting.title} {meeting.summary} {' '.join(meeting.topics)} {moment_text}"


def _support_recurring_impl(support: list[Meeting]) -> Insight:
    counts = Counter(meeting.primary_theme or "unclassified" for meeting in support)
    ranked = [(theme_id, count) for theme_id, count in counts.most_common() if theme_id != "unclassified"]
    raw = Counter(topic.lower() for meeting in support for topic in meeting.topics)
    top_raw = raw.most_common(3)
    if not ranked:
        return Insight(
            insight_id="support-recurring",
            stakeholder="support",
            title="Support themes are not yet governed",
            finding="Support calls did not map onto the governed taxonomy.",
            why_it_matters="Without a theme, a weekly support review collapses into a list of case titles.",
            recommendation="Label the unclassified support cases before the next operating review.",
            metric_label="Support calls",
            metric_value=str(len(support)),
        )
    leader_id, leader_count = ranked[0]
    second = f" {_theme_name(ranked[1][0])} is next with {ranked[1][1]}." if len(ranked) > 1 else ""
    raw_text = ", ".join(f"{label} ({count})" for label, count in top_raw) if top_raw else "n/a"
    details = [
        InsightDetail(_theme_name(theme_id), str(count), f"{count / len(support):.0%} of support calls")
        for theme_id, count in ranked[:5]
    ]
    examples = [meeting for meeting in support if meeting.primary_theme == leader_id][:3]
    return Insight(
        insight_id="support-recurring",
        stakeholder="support",
        title="What keeps coming back to support",
        finding=(
            f"{_theme_name(leader_id)} is the primary theme on {leader_count} of {len(support)} support calls."
            f"{second} The raw labels underneath are fragmented ({raw_text}). "
            "The theme is the rollup a support leader can staff against. The raw label is the evidence."
        ),
        why_it_matters=(
            "Case titles make every ticket look unique. The theme count shows whether the queue is "
            "an incident aftershock, an identity problem, or a billing problem. Those are different rosters."
        ),
        recommendation=(
            f"Staff the weekly support review by theme, starting with {_theme_name(leader_id)}. "
            "Bring the engineering owner for that theme, not a rotating on-call who has to re-derive the pattern."
        ),
        metric_label=f"{_theme_name(leader_id)} share of support",
        metric_value=f"{leader_count / len(support):.0%}",
        evidence=[_evidence(meeting, meeting.summary) for meeting in examples],
        details=details,
    )


def _support_gap_impl(meetings: list[Meeting], support: list[Meeting]) -> Insight:
    support_mean = _mean([meeting.sentiment_score for meeting in support])
    others = [meeting for meeting in meetings if meeting.call_type != "support"]
    other_mean = _mean([meeting.sentiment_score for meeting in others])
    external = _of_type(meetings, "external")
    external_mean = _mean([meeting.sentiment_score for meeting in external]) if external else other_mean
    gap = external_mean - support_mean
    negative = [
        meeting
        for meeting in support
        if meeting.sentiment_score < 3
    ]
    negative.sort(key=lambda meeting: meeting.sentiment_score)
    return Insight(
        insight_id="support-sentiment",
        stakeholder="support",
        title="Support sentiment lags the account conversations",
        finding=(
            f"Support averages {support_mean:.2f}. External account calls average {external_mean:.2f}. "
            f"The gap is {gap:.2f} points on a 1–5 scale. "
            f"{len(negative)} of {len(support)} support calls score below 3."
        ),
        why_it_matters=(
            "Account managers can leave a renewal conversation mixed-positive while the open case "
            "is the thing the customer retells internally. The renewal narrative and the support "
            "experience are drifting apart, and the support score is the one the champion has to defend."
            if gap >= 0.25
            else "Support is not the cold channel in this cut. Look at the incident cohort before reallocating the team."
        ),
        recommendation=(
            "Put the five lowest-scoring open themes on the same weekly page as renewal risk. "
            "A case that is still negative after the next customer touch needs an owner outside the support queue."
        ),
        metric_label="Support vs external gap",
        metric_value=f"{gap:+.2f}",
        evidence=[_evidence(meeting, meeting.summary) for meeting in negative[:3]],
        details=[
            InsightDetail("Support mean", f"{support_mean:.2f}", f"{len(support)} calls"),
            InsightDetail("External mean", f"{external_mean:.2f}", f"{len(external)} calls"),
            InsightDetail("Calls below 3", str(len(negative)), "negative side of the score"),
        ],
    )


def _support_unresolved_impl(support: list[Meeting]) -> Insight:
    unresolved = [
        meeting
        for meeting in support
        if _has_moment(meeting, "churn_signal") and not _has_moment(meeting, "positive_pivot")
    ]
    unresolved.sort(key=lambda meeting: meeting.sentiment_score)
    with_churn = [meeting for meeting in support if _has_moment(meeting, "churn_signal")]
    return Insight(
        insight_id="support-unresolved",
        stakeholder="support",
        title="Churn language without a recovery moment",
        finding=(
            f"{len(with_churn)} support calls contain a churn signal. "
            f"{len(unresolved)} of them have no positive pivot in the recorded key moments. "
            "A pivot is the moment the conversation turns from the failure to a credible next step."
        ),
        why_it_matters=(
            "A churn signal with a pivot is a save in progress. A churn signal without one is a case "
            "that ended on the customer's terms. Those are the calls worth a same-day account-team follow-up, "
            "not a CSAT survey."
        ),
        recommendation=(
            "Route every support case that records a churn signal and no pivot to the account owner "
            "before the end of the day, with the quote attached."
        ),
        metric_label="Churn signals with no pivot",
        metric_value=str(len(unresolved)),
        evidence=[
            _evidence(meeting, _first_moment(meeting, "churn_signal"))
            for meeting in unresolved[:3]
        ],
        details=[
            InsightDetail(
                meeting.account_name or meeting.title,
                f"{meeting.sentiment_score:.1f}",
                _clip(_first_moment(meeting, "churn_signal"), 140),
            )
            for meeting in unresolved[:6]
        ],
    )


def _product_gaps_impl(meetings: list[Meeting]) -> Insight:
    by_product: dict[str, list[tuple[Meeting, str]]] = defaultdict(list)
    for meeting in meetings:
        for moment in meeting.key_moments:
            if moment.moment_type != "feature_gap":
                continue
            product = _product_for(f"{meeting.title} {moment.text}")
            by_product[product].append((meeting, moment.text))
    total = sum(len(rows) for rows in by_product.values())
    ranked = sorted(by_product.items(), key=lambda item: len(item[1]), reverse=True)
    details = [
        InsightDetail(product, str(len(rows)), _clip(rows[0][1], 140))
        for product, rows in ranked
        if product != "Unspecified"
    ]
    evidence: list[Evidence] = []
    seen_accounts: set[str] = set()
    for product, rows in ranked:
        for meeting, quote in rows:
            key = meeting.account_name or meeting.meeting_id
            if key in seen_accounts:
                continue
            evidence.append(_evidence(meeting, quote))
            seen_accounts.add(key)
            break
        if len(evidence) == 3:
            break
    leader = details[0].label if details else "Unspecified"
    leader_count = int(details[0].value) if details else 0
    return Insight(
        insight_id="product-gaps",
        stakeholder="product",
        title="Feature gaps, grouped by module",
        finding=(
            f"The corpus records {total} feature-gap moments. "
            f"{leader} accounts for {leader_count} of the gaps that name a module. "
            "These are not roadmap brainstorms. They are customers describing a workflow the product does not do, "
            "inside a support case or an account review."
        ),
        why_it_matters=(
            "A feature request in a planning doc is optional. A feature gap spoken next to a churn signal "
            "is a requirement the renewal conversation will use. Grouping by module tells product which squad "
            "owns the gap instead of dropping every request into one backlog."
        ),
        recommendation=(
            f"Take the {leader} gaps to that squad's next planning review with the quote and the account attached. "
            "Separate the ones already committed on a roadmap from the ones that have no owner."
        ),
        metric_label="Feature-gap moments",
        metric_value=str(total),
        evidence=evidence,
        details=details[:6],
    )


def _product_modules_impl(meetings: list[Meeting]) -> Insight:
    buckets: dict[str, list[Meeting]] = defaultdict(list)
    for meeting in meetings:
        seen: set[str] = set()
        for name, keywords in _PRODUCTS:
            blob = f"{meeting.title} {' '.join(meeting.topics)}".lower()
            if any(re.search(rf"\b{re.escape(keyword)}\b", blob) for keyword in keywords):
                if name not in seen:
                    buckets[name].append(meeting)
                    seen.add(name)
    details: list[InsightDetail] = []
    means: list[tuple[str, float, int]] = []
    for name, _keywords in _PRODUCTS:
        rows = buckets.get(name, [])
        if not rows:
            continue
        mean = _mean([meeting.sentiment_score for meeting in rows])
        means.append((name, mean, len(rows)))
        negative = sum(1 for meeting in rows if meeting.sentiment_score < 3)
        details.append(InsightDetail(name, f"{mean:.2f}", f"{len(rows)} meetings · {negative} below 3"))
    means.sort(key=lambda item: item[1])
    if not means:
        cold_name, cold_mean, cold_n = "n/a", 0.0, 0
        warm_name, warm_mean = "n/a", 0.0
    else:
        cold_name, cold_mean, cold_n = means[0]
        warm_name, warm_mean, _warm_n = means[-1]
    cold_examples = sorted(buckets.get(cold_name, []), key=lambda meeting: meeting.sentiment_score)[:3]
    return Insight(
        insight_id="product-modules",
        stakeholder="product",
        title="Module sentiment is not one product story",
        finding=(
            f"{cold_name} meetings average {cold_mean:.2f} across {cold_n} calls that name it. "
            f"{warm_name} averages {warm_mean:.2f}. "
            "A meeting can name more than one module. The score is the meeting score, not a sentence classifier."
        ),
        why_it_matters=(
            "Shipping a launch narrative for one module while another module is the reason accounts are angry "
            "splits the company's story. Product and marketing should not brief Comply as if Detect had a quiet quarter, "
            "or the reverse, unless the scores actually say that."
        ),
        recommendation=(
            f"Pair the {cold_name} reliability narrative with whatever is launching next. "
            "Do not take a positive module into a renewal meeting that is actually about the colder one "
            "without acknowledging the colder score."
        ),
        metric_label=f"Coldest module ({cold_name})",
        metric_value=f"{cold_mean:.2f}",
        evidence=[_evidence(meeting, meeting.summary) for meeting in cold_examples],
        details=details,
    )


def _engineering_incident_impl(meetings: list[Meeting]) -> Insight:
    incident = [meeting for meeting in meetings if re.search(r"outage|incident|war room|pipeline failure", meeting.title, re.I)]
    incident.sort(key=lambda meeting: meeting.start_time)
    if incident:
        start = incident[0].date_key()
        end = incident[-1].date_key()
        mean = _mean([meeting.sentiment_score for meeting in incident])
        span = f"{start} to {end}"
    else:
        mean = 0.0
        span = "n/a"
    technical = [meeting for meeting in meetings if _has_moment(meeting, "technical_issue")]
    return Insight(
        insight_id="engineering-incident",
        stakeholder="engineering",
        title="The incident is a cluster, not a bad day",
        finding=(
            f"{len(incident)} meetings are titled as an outage, incident, or war room"
            f"{f', from {span}' if incident else ''}. "
            f"Their mean sentiment is {mean:.2f}. "
            f"{len(technical)} meetings anywhere in the corpus record a technical-issue moment, "
            "so the engineering residue is larger than the bridge calendar."
        ),
        why_it_matters=(
            "A war-room timeline describes what the on-call team did. It does not describe how many later "
            "conversations still treat the failure as open. Engineering managers who close the incident "
            "when the pipeline recovers will miss the accounts that are still living in the gap."
        ),
        recommendation=(
            "Keep the incident's engineering owner assigned through the customer-communication tail, "
            "not only through the technical restore. Review every later meeting that still cites the outage."
        ),
        metric_label="Incident-titled meetings",
        metric_value=str(len(incident)),
        evidence=[_evidence(meeting, meeting.summary) for meeting in incident[:3]],
        details=[
            InsightDetail(meeting.date_key(), f"{meeting.sentiment_score:.1f}", meeting.title)
            for meeting in incident[:8]
        ],
    )


def _engineering_causes_impl(meetings: list[Meeting]) -> Insight:
    texts: list[tuple[Meeting, str]] = []
    for meeting in meetings:
        for moment in meeting.key_moments:
            if moment.moment_type == "technical_issue":
                texts.append((meeting, moment.text))
        if re.search(r"outage|incident|war room", meeting.title, re.I):
            texts.append((meeting, meeting.summary))
    counts: Counter[str] = Counter()
    samples: dict[str, tuple[Meeting, str]] = {}
    for meeting, text in texts:
        lowered = text.lower()
        for label, needles in _ROOT_CAUSES:
            if any(re.search(rf"\b{re.escape(needle)}", lowered) for needle in needles):
                counts[label] += 1
                samples.setdefault(label, (meeting, text))
    ranked = counts.most_common()
    details = [
        InsightDetail(label, str(count), _clip(samples[label][1], 140))
        for label, count in ranked
    ]
    evidence = [_evidence(samples[label][0], samples[label][1]) for label, _count in ranked[:3]]
    if ranked:
        leader, leader_count = ranked[0]
        finding = (
            f"Across technical-issue moments and incident summaries, the strongest repeated pattern is "
            f"'{leader}' ({leader_count} hits). "
            "These buckets are keyword passes over the recorded technical moments, not a new root-cause model. "
            "They exist so a review can start from the language engineers and customers already used."
        )
    else:
        leader = "n/a"
        finding = "No technical-issue moments matched the root-cause lexicon."
    return Insight(
        insight_id="engineering-causes",
        stakeholder="engineering",
        title="Repeated failure language",
        finding=finding,
        why_it_matters=(
            "Individual postmortems name a host, a deploy, or a queue. Repeated language across meetings "
            "names an architectural habit: a single pipeline, a health check that cannot see the failure, "
            "or a customer who finds out from their own users. Habits are what the next incident will reuse."
        ),
        recommendation=(
            f"Put '{leader}' on the reliability backlog as a theme, with the cited meetings as the acceptance examples, "
            "and separate it from the one-off bug list."
        ),
        metric_label="Distinct cause patterns",
        metric_value=str(len(ranked)),
        evidence=evidence,
        details=details,
    )


def _sales_risk_impl(customer_meetings: list[Meeting], competitors: tuple[str, ...]) -> Insight:
    by_account: dict[str, list[Meeting]] = defaultdict(list)
    for meeting in customer_meetings:
        key = meeting.account_name or meeting.customer_domains[0]
        by_account[key].append(meeting)

    rows: list[tuple[float, str, list[Meeting], int, list[str]]] = []
    for account, group in by_account.items():
        churn_count = sum(1 for meeting in group if _has_moment(meeting, "churn_signal"))
        if churn_count == 0:
            continue
        named = _competitors_in(group, competitors)
        mean = _mean([meeting.sentiment_score for meeting in group])
        renewal = any("renewal" in meeting.title.lower() or any("renewal" in topic.lower() for topic in meeting.topics) for meeting in group)
        risk = churn_count * 3 + max(0.0, 3.5 - mean) + (1.5 if named else 0) + (1.0 if renewal else 0)
        rows.append((risk, account, group, churn_count, named))
    rows.sort(key=lambda item: item[0], reverse=True)
    details = []
    evidence: list[Evidence] = []
    for risk, account, group, churn_count, named in rows[:8]:
        mean = _mean([meeting.sentiment_score for meeting in group])
        competitor_note = ", ".join(named) if named else "no named competitor"
        details.append(
            InsightDetail(
                account,
                f"{risk:.1f}",
                f"{churn_count} calls with churn language · mean {mean:.2f} · {competitor_note}",
            )
        )
        quote_meeting = min(group, key=lambda meeting: meeting.sentiment_score)
        quote = _first_moment(quote_meeting, "churn_signal") or quote_meeting.summary
        if len(evidence) < 3:
            evidence.append(_evidence(quote_meeting, quote))
    tracked = len(rows)
    return Insight(
        insight_id="sales-at-risk",
        stakeholder="sales",
        title="Accounts where the transcript is already a renewal problem",
        finding=(
            f"{tracked} accounts have at least one call with explicit churn language. "
            "The score weights repeated churn signals, a low mean, a named competitor, and a renewal already on the calendar. "
            "It is a briefing rank, not a forecast."
        ),
        why_it_matters=(
            "Pipeline reviews look at stage and close date. They miss the account whose champion has already "
            "said, on a recorded call, that another vendor is in the building. That sentence is the earliest "
            "renewal forecast the CRM does not have a field for."
        ),
        recommendation=(
            "Work the top of this list as one book: one owner, the quote, the competitor, and a date for the "
            "technical assurance the customer asked for. Do not leave it distributed across whoever last hosted the call."
        ),
        metric_label="Accounts on the risk list",
        metric_value=str(tracked),
        evidence=evidence,
        details=details,
    )


def _sales_competitors_impl(meetings: list[Meeting], competitors: tuple[str, ...]) -> Insight:
    counts: Counter[str] = Counter()
    accounts: dict[str, set[str]] = defaultdict(set)
    evidence: list[Evidence] = []
    for meeting in meetings:
        blob = _blob(meeting)
        for name in competitors:
            if re.search(rf"\b{re.escape(name)}\b", blob, flags=re.IGNORECASE):
                counts[name] += 1
                if meeting.account_name:
                    accounts[name].add(meeting.account_name)
                if len(evidence) < 3 and _has_moment(meeting, "churn_signal"):
                    evidence.append(_evidence(meeting, _first_moment(meeting, "churn_signal")))
    details = [
        InsightDetail(name, str(counts[name]), f"{len(accounts[name])} named accounts")
        for name in competitors
        if counts[name]
    ]
    details.sort(key=lambda item: int(item.value), reverse=True)
    leader = details[0].label if details else "none"
    leader_count = details[0].value if details else "0"
    return Insight(
        insight_id="sales-competitors",
        stakeholder="sales",
        title="Which competitors the transcripts actually name",
        finding=(
            f"{leader} is named in {leader_count} meetings. "
            "The lexicon is configured, not discovered on the fly, so a new competitor does not appear "
            "until someone adds the name. The counts are meetings, not mentions, so one angry call counts once."
        ),
        why_it_matters=(
            "Win/loss anecdotes travel faster than the count. A named competitor attached to a specific account "
            "is a battlecard problem and a save plan. A competitor who only appears in internal strategy calls "
            "is a different problem from one who is already in the customer's evaluation."
        ),
        recommendation=(
            f"Update the {leader} talk track with the failure the customers are citing, not a generic feature grid. "
            "Re-count this list after the next month of calls before declaring the competitive set stable."
        ),
        metric_label=f"Meetings naming {leader}",
        metric_value=str(leader_count),
        evidence=evidence,
        details=details,
    )


def _competitors_in(meetings: list[Meeting], competitors: tuple[str, ...]) -> list[str]:
    found: list[str] = []
    blob = " ".join(_blob(meeting) for meeting in meetings)
    for name in competitors:
        if re.search(rf"\b{re.escape(name)}\b", blob, flags=re.IGNORECASE) and name not in found:
            found.append(name)
    return found


def _first_moment(meeting: Meeting, moment_type: str) -> str:
    for moment in meeting.key_moments:
        if moment.moment_type == moment_type:
            speaker = f"{moment.speaker}: " if moment.speaker else ""
            return f"{speaker}{moment.text}"
    return meeting.summary


class InsightAnalyzer(Analyzer):
    def __init__(self, competitors: tuple[str, ...] = ("SentinelShield", "VaultEdge", "CyberNova")):
        self.competitors = competitors

    def analyze(self, meetings: list[Meeting]) -> list[Insight]:
        insights: list[Insight] = []
        support = _of_type(meetings, "support")
        if support:
            insights.append(_support_recurring_impl(support))
            insights.append(_support_gap_impl(meetings, support))
            insights.append(_support_unresolved_impl(support))
        insights.append(_product_gaps_impl(meetings))
        insights.append(_product_modules_impl(meetings))
        insights.append(_engineering_incident_impl(meetings))
        insights.append(_engineering_causes_impl(meetings))
        customer_meetings = [meeting for meeting in meetings if meeting.customer_domains]
        if customer_meetings:
            insights.append(_sales_risk_impl(customer_meetings, self.competitors))
            insights.append(_sales_competitors_impl(meetings, self.competitors))
        return insights
