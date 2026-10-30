"""Human review workspace.

    streamlit run src/review/app.py --server.port 43124 --server.address 0.0.0.0

Decisions are written to output/review_decisions.json. Metrics are rewritten
from those decisions. This file does not invent a label.
"""

from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from src.review.catalog import insight_cards, topic_cards
from src.review.context import load_meeting_context, source_document_hash
from src.review.decisions import load_decisions
from src.review.evidence import build_evidence_verification
from src.review.sample import build_review_sample, load_sample, write_review_sample
from src.review.schema import MODEL_VERSION, TAXONOMY_VERSION, THEME_IDS, DecisionSchemaError
from src.review.store import DecisionStore
from src.review.validation import build_human_validation_report, write_human_validation_report

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "output"
DATA = ROOT / "data"
REPORT_PATH = OUTPUT / "report.json"
DECISIONS_PATH = OUTPUT / "review_decisions.json"
SAMPLE_PATH = OUTPUT / "review_sample.json"
WEB_REPORT = ROOT / "web" / "src" / "data" / "human_validation_report.json"

TOPIC_CHOICES = [
    ("approve", "Confirm predicted topic"),
    ("correct", "Correct topic to another category"),
    ("ambiguous", "Mark ambiguous"),
    ("insufficient_evidence", "Mark insufficient evidence"),
]
FINDING_CHOICES = [
    ("supported", "Supported"),
    ("partially_supported", "Partially supported"),
    ("unsupported", "Unsupported"),
    ("insufficient_evidence", "Insufficient evidence"),
]
INSIGHT_CHOICES = [
    ("accept", "Accept"),
    ("reject", "Reject"),
    ("needs_revision", "Needs revision"),
    ("needs_more_evidence", "Needs more evidence"),
]


def main() -> None:
    st.set_page_config(page_title="Human Validation & Evidence Quality", layout="wide")
    st.title("Human Validation & Evidence Quality")
    st.caption(
        "Reviewers judge categories, stakeholder findings, and whether a cited passage supports the claim. "
        "Metrics stay N/A until those decisions are saved. A quote that exists in the file is not an acceptance."
    )
    if not REPORT_PATH.exists():
        st.error("output/report.json is missing. Run `python -m src.pipeline.runner --data data --output output` first.")
        return
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    sample = _sample(report)
    decisions = load_decisions(DECISIONS_PATH)

    with st.sidebar:
        st.header("Reviewer")
        reviewer_id = st.text_input("Reviewer id", placeholder="Your name or initials").strip()
        st.caption("Required before a decision can be saved. A second reviewer who disagrees opens an adjudication instead of erasing the first decision.")
        st.header("Filters")
        call_filter = st.selectbox("Call type", ["All", "support", "external", "internal"])
        theme_filter = st.selectbox("Theme", ["All", *list(THEME_IDS)])
        stakeholder_filter = st.selectbox("Stakeholder", ["All", "support", "sales", "product", "engineering"])
        status_filter = st.selectbox("Review status", ["All", "Needs a decision", "Reviewed", "Conflict"])
        reviewer_filter = st.text_input("Saved reviewer contains").strip().lower()
        if st.button("Refresh metrics from saved decisions"):
            _refresh_metrics(report, sample)
            st.rerun()
        st.divider()
        st.markdown(
            "Strata use the predicted theme, not a gold label. "
            "Representative metrics and challenging-case metrics are not averaged together. "
            "Corrections are not used to refit the topic model."
        )

    filters = {
        "call": call_filter,
        "theme": theme_filter,
        "stakeholder": stakeholder_filter,
        "status": status_filter,
        "reviewer": reviewer_filter,
    }
    representative, challenging, insights, findings = st.tabs(
        ["Representative sample", "Challenging cases", "Business insights", "Findings verification"]
    )
    with representative:
        _topic_tab(report, sample, decisions, "representative", reviewer_id, filters)
    with challenging:
        st.warning(sample.get("challenging", {}).get("bias") or "This set is biased toward hard cases.")
        st.caption(sample.get("method") or "")
        _topic_tab(report, sample, decisions, "challenging", reviewer_id, filters)
    with insights:
        _insight_tab(report, decisions, reviewer_id, filters)
    with findings:
        _findings_tab(report, decisions, reviewer_id, filters)

    st.divider()
    _evaluation(report, sample)


def _sample(report: dict) -> dict:
    if SAMPLE_PATH.exists():
        return load_sample(SAMPLE_PATH)
    sample = build_review_sample(report.get("meetings") or [], report.get("review_queue") or {})
    write_review_sample(sample, SAMPLE_PATH)
    return sample


def _topic_tab(report: dict, sample: dict, decisions: dict, role: str, reviewer_id: str, filters: dict) -> None:
    cards = [card for card in topic_cards(report, sample, decisions, role) if _keep_topic(card, filters)]
    reviewed = sum(1 for card in cards if card["decision"])
    st.subheader("Transcript classification")
    st.progress(reviewed / len(cards) if cards else 0.0)
    st.write(f"Human review completion: **{reviewed} / {len(cards)}** assigned in this set.")
    method = sample.get("method") or ""
    if role == "representative":
        st.info(method)
        coverage = sample.get("representative", {}).get("coverage") or {}
        _coverage_table(coverage)
    if not cards:
        st.warning("This set has no transcripts.")
        return
    labels = []
    for card in cards:
        mark = "Reviewed" if card["decision"] else "Needs a decision"
        labels.append(f"{mark} · {card['transcript_id']} · {card['predicted_topic_name']}")
    index = st.selectbox(
        "Transcript",
        range(len(cards)),
        format_func=lambda item: labels[item],
        key=f"pick-{role}",
    )
    card = cards[index]
    _topic_card(card, reviewer_id, role)


def _topic_card(card: dict, reviewer_id: str, role: str) -> None:
    left, right = st.columns([1.2, 1])
    with left:
        st.markdown(f"**Transcript ID**  \n`{card['transcript_id']}`")
        st.markdown(f"**Call type**  \n{card['call_type'] or '—'}")
        st.markdown("**Original supplied topic**")
        st.write("; ".join(card["original_topics"]) if card["original_topics"] else "None supplied.")
        st.markdown(f"**Model-assigned governed category**  \n{card['predicted_topic_name']}")
        st.markdown(
            f"**Model** {card.get('model_version') or 'lexical-nmf-8-seed-7'} · "
            f"**Taxonomy** {card.get('taxonomy_version') or 'governed-themes-v1'}"
        )
        st.caption("Lexical overlap and theme-score margin are heuristic evidence. They are not a calibrated accuracy probability.")
        st.markdown("**Excerpt**")
        st.write(card["excerpt"] or "No excerpt is stored.")
        context = load_meeting_context(DATA, card["transcript_id"])
        with st.expander(f"Source transcript context ({context['shown']} of {context['turn_count']} turns)"):
            st.caption(context["note"])
            if context["source_document_hash"]:
                st.caption(f"Source document hash {context['source_document_hash']}")
            if context["summary"]:
                st.markdown("**Summary**")
                st.write(context["summary"])
            for turn in context["turns"]:
                stamp = f"{turn['time_seconds']}s" if turn["time_seconds"] is not None else ""
                st.write(f"{turn['speaker']} {stamp}: {turn['sentence']}")
            if not context["available"]:
                st.info("The source transcript file is not in the data folder.")
    with right:
        st.markdown("**Classification rationale**")
        st.write(card["rationale"])
        st.markdown("**Quality indicators**")
        for indicator in card["indicators"]:
            st.write(f"- {indicator}")
        if card["selection_probability"] is not None:
            st.write(
                f"Selection probability in its stratum: **{card['selection_probability']}**. "
                f"Sample weight: **{card['sample_weight']}**."
            )
        if card["reasons"]:
            st.write("Queue reasons: " + ", ".join(card["reasons"]))
        if card["also_in_challenging"] or card["also_in_representative"]:
            st.caption("This transcript is also in the other sample. One saved decision is used in both denominators.")
        if card["decision"]:
            st.success(
                f"Saved decision: {card.get('review_status') or card['decision']}"
                + (f" → {card['human_topic']}" if card["human_topic"] else "")
                + (f" · {card['reviewer_id']} · {card['reviewer_timestamp']}" if card["reviewer_id"] else "")
            )
        if card.get("conflict"):
            st.error("Reviewers disagree. The first decision is still on file and is excluded from accuracy until someone adjudicates it.")
            for submission in card.get("submissions") or []:
                st.write(
                    f"{submission.get('reviewer_id')}: {submission.get('decision')}"
                    + (f" → {submission.get('human_topic')}" if submission.get("human_topic") else "")
                )

    choice_labels = ["Choose a decision", *[label for _, label in TOPIC_CHOICES]]
    current = next((position for position, (value, _) in enumerate(TOPIC_CHOICES) if value == card["decision"]), None)
    choice = st.radio(
        "Decision",
        choice_labels,
        index=0 if current is None else current + 1,
        key=f"topic-decision-{role}-{card['item_id']}",
    )
    decision = {label: value for value, label in TOPIC_CHOICES}.get(choice or "", "")
    human_topic = card["predicted_topic"]
    if decision == "correct":
        options = card["other_topics"] or [{"id": card["predicted_topic"], "name": card["predicted_topic_name"]}]
        names = [option["name"] for option in options]
        default = 0
        for position, option in enumerate(options):
            if option["id"] == card["human_topic"]:
                default = position
        picked = st.selectbox(
            "Corrected category",
            names,
            index=default,
            key=f"topic-gold-{role}-{card['item_id']}",
        )
        human_topic = options[names.index(picked)]["id"]
    notes = st.text_area(
        "Reviewer explanation",
        value=card["notes"],
        key=f"topic-notes-{role}-{card['item_id']}",
        placeholder="Why you approve, correct, or cannot tell.",
    )
    adjudicate = False
    if card.get("conflict"):
        adjudicate = st.checkbox(
            "Adjudicate this conflict. This explicitly replaces the active label and keeps every submission.",
            key=f"topic-adjudicate-{role}-{card['item_id']}",
        )
    if st.button("Save topic decision", type="primary", key=f"topic-save-{role}-{card['item_id']}"):
        if not decision:
            st.error("Choose a decision. A transcript is not human-reviewed until you do.")
            return
        try:
            stored = DecisionStore(DECISIONS_PATH).save_topic_review(
                item_id=card["item_id"],
                predicted_topic=card["predicted_topic"],
                decision=decision,
                human_topic=human_topic,
                reviewer_id=reviewer_id,
                notes=notes,
                model_version=MODEL_VERSION,
                taxonomy_version=TAXONOMY_VERSION,
                source_document_hash=source_document_hash(DATA, card["transcript_id"]),
                adjudicate=adjudicate,
            )
        except DecisionSchemaError as exc:
            st.error(str(exc))
            return
        _refresh_metrics_from_disk()
        st.success(f"Saved {stored['review_id']}. The evaluation report was regenerated from the file.")
        st.rerun()


def _insight_tab(report: dict, decisions: dict, reviewer_id: str, filters: dict) -> None:
    cards = [card for card in insight_cards(report, decisions) if _keep_insight(card, filters)]
    reviewed = sum(1 for card in cards if card["decision"])
    st.subheader("Stakeholder findings")
    st.progress(reviewed / len(cards) if cards else 0.0)
    st.write(f"Reviewed **{reviewed} / {len(cards)}** insights. Nothing is accepted until you save a decision.")
    if not cards:
        st.warning("The report has no business insights.")
        return
    labels = [
        f"{'Reviewed' if card['decision'] else 'Awaiting'} · {card['stakeholder_label']} · {card['title']}"
        for card in cards
    ]
    index = st.selectbox("Insight", range(len(cards)), format_func=lambda item: labels[item])
    card = cards[index]
    st.markdown(f"**Insight ID**  \n`{card['insight_id']}`")
    st.markdown(f"**{card['title']}**")
    st.write(card["description"])
    if card["why_it_matters"]:
        st.write(card["why_it_matters"])
    st.markdown(f"**Stakeholder**  \n{card['stakeholder_label']}")
    st.markdown("**Source meetings**  \n" + (", ".join(card["source_meeting_ids"]) or "None cited."))
    st.markdown("**Supporting excerpts**")
    for item in card["evidence"]:
        st.write(f"`{item['meeting_id']}` {item['title']}")
        st.caption(item["quote"])
    st.markdown(f"**Recommended action**  \n{card['recommendation']}")
    st.markdown(f"**Evidence strength**  \n{card['evidence_indicator']}")
    verification = _evidence_payload(report, decisions)
    finding = next((row for row in verification.get("findings") or [] if row.get("insight_id") == card["insight_id"]), None)
    if finding:
        st.markdown(f"**Claim type** {finding.get('claim_kind')} · {finding.get('known_limitations')}")
        st.caption("Passages below are a contrast-word screen in the cited transcript. They are not a verdict, and the quote check is not an acceptance.")
        for citation in finding.get("citations") or []:
            st.write(f"Quote check `{citation.get('meeting_id')}`: {citation.get('quote_status')} {citation.get('location')}")
            for passage in citation.get("passages_to_check") or []:
                st.caption(f"{passage.get('speaker')}: {passage.get('sentence')}")
    if card["decision"]:
        st.success(
            f"Saved decision: {card['decision']}"
            + (f" · {card['reviewer_id']} · {card['reviewer_timestamp']}" if card["reviewer_id"] else "")
        )
    choice_labels = ["Choose a decision", *[label for _, label in INSIGHT_CHOICES]]
    current = next((position for position, (value, _) in enumerate(INSIGHT_CHOICES) if value == card["decision"]), None)
    choice = st.radio(
        "Decision",
        choice_labels,
        index=0 if current is None else current + 1,
        key=f"insight-decision-{card['item_id']}",
    )
    decision = {label: value for value, label in INSIGHT_CHOICES}.get(choice or "", "")
    corrected = ""
    if decision in {"reject", "needs_revision", "needs_more_evidence"}:
        corrected = st.text_area(
            "Corrected recommendation, if you have one",
            value=card["corrected_recommendation"],
            key=f"insight-fix-{card['item_id']}",
        )
    notes = st.text_area(
        "Rationale",
        value=card["notes"],
        key=f"insight-notes-{card['item_id']}",
    )
    quality = st.selectbox(
        "Evidence quality (optional)",
        ["Not rated", "1", "2", "3", "4", "5"],
        index=_rating_index(card["evidence_quality"]),
        key=f"insight-quality-{card['item_id']}",
    )
    usefulness = st.selectbox(
        "Business usefulness (optional)",
        ["Not rated", "1", "2", "3", "4", "5"],
        index=_rating_index(card["business_usefulness"]),
        key=f"insight-use-{card['item_id']}",
    )
    if st.button("Save insight decision", type="primary", key=f"insight-save-{card['item_id']}"):
        if not decision:
            st.error("Choose a decision. An insight is not reviewed until you do.")
            return
        try:
            stored = DecisionStore(DECISIONS_PATH).save_insight_review(
                item_id=card["item_id"],
                decision=decision,
                reviewer_id=reviewer_id,
                notes=notes,
                corrected_recommendation=corrected,
                evidence_quality=None if quality == "Not rated" else int(quality),
                business_usefulness=None if usefulness == "Not rated" else int(usefulness),
            )
        except DecisionSchemaError as exc:
            st.error(str(exc))
            return
        _refresh_metrics_from_disk()
        st.success(f"Saved {stored['review_id']}. Acceptance rate uses accepted and rejected decisions only.")
        st.rerun()


def _findings_tab(report: dict, decisions: dict, reviewer_id: str, filters: dict) -> None:
    verification = _evidence_payload(report, decisions)
    st.subheader("Findings verification")
    st.info(verification.get("note") or "")
    st.write(
        f"Quotes located by string match: **{verification.get('quotes_found', 0)}**. "
        f"Missing: **{verification.get('quotes_missing', 0)}**. "
        f"Human support judgments: **{verification.get('human_reviewed', 0)} / {verification.get('finding_count', 0)}**."
    )
    rows = [
        row
        for row in verification.get("findings") or []
        if filters["stakeholder"] in {"All", row.get("stakeholder")}
        and _status_ok(row.get("human_support_status") or "pending", filters["status"])
        and (not filters["reviewer"] or filters["reviewer"] in (row.get("human_reviewer_id") or "").lower())
    ]
    if not rows:
        st.warning("No findings match these filters.")
        return
    labels = [
        f"{row.get('human_support_status') or 'pending'} · {row.get('stakeholder')} · {row.get('title')}"
        for row in rows
    ]
    index = st.selectbox("Finding", range(len(rows)), format_func=lambda item: labels[item], key="finding-pick")
    row = rows[index]
    st.markdown(f"**Insight ID** `{row.get('insight_id')}`")
    st.write(row.get("claim") or "")
    st.write(row.get("recommended_action") or "")
    st.caption(row.get("known_limitations") or "")
    source_ids = []
    for citation in row.get("citations") or []:
        source_ids.append(citation.get("meeting_id") or "")
        st.write(
            f"`{citation.get('meeting_id')}` automated quote status: **{citation.get('quote_status')}**"
            + (f" in {citation.get('source_file')} ({citation.get('location')})" if citation.get("location") else "")
        )
        st.caption(citation.get("quote") or "")
    choice_labels = ["Choose a judgment", *[label for _, label in FINDING_CHOICES]]
    current = next((position for position, (value, _) in enumerate(FINDING_CHOICES) if value == row.get("human_support_status")), None)
    choice = st.radio(
        "Does the source support the claim?",
        choice_labels,
        index=0 if current is None else current + 1,
        key=f"finding-decision-{row.get('insight_id')}",
    )
    decision = {label: value for value, label in FINDING_CHOICES}.get(choice or "", "")
    notes = st.text_area("Reviewer rationale", value=row.get("human_notes") or "", key=f"finding-notes-{row.get('insight_id')}")
    if st.button("Save finding judgment", type="primary", key=f"finding-save-{row.get('insight_id')}"):
        if not decision:
            st.error("Choose a judgment. A located quote is not a human review.")
            return
        try:
            stored = DecisionStore(DECISIONS_PATH).save_finding_review(
                insight_id=row["insight_id"],
                decision=decision,
                reviewer_id=reviewer_id,
                notes=notes,
                checked_sources=source_ids,
            )
        except DecisionSchemaError as exc:
            st.error(str(exc))
            return
        _refresh_metrics_from_disk()
        st.success(f"Saved {stored['review_id']}. This is a human support judgment, separate from quote location.")
        st.rerun()


def _evaluation(report: dict, sample: dict) -> None:
    st.header("Scorecards")
    payload = _current_report(report, sample)
    topic = payload["topic_classification"]
    insights = payload["business_insights"]
    if payload["data_gap"]["resolved"]:
        st.success(
            "Topic accuracy, insight acceptance, and finding support all have adjudicated human decisions."
        )
    else:
        st.warning(
            "Topic accuracy, insight acceptance, and finding support are NOT YET AVAILABLE. "
            + payload["data_gap"]["reason"]
        )
    representative_tab, challenge_tab = st.tabs(["Representative sample", "Challenging cases"])
    with representative_tab:
        _topic_scorecard(topic["representative"], "Representative sample")
    with challenge_tab:
        st.warning(topic["challenging"].get("warning") or sample.get("challenging", {}).get("bias") or "")
        st.caption(topic.get("pooling_note") or "")
        _topic_scorecard(topic["challenging"], "Challenging cases")
    st.subheader("Business insight approval")
    _insight_scorecard(insights)
    st.subheader("Findings verification and claims audit")
    findings = payload.get("findings_verification") or {}
    claims = payload.get("claims_audit") or {}
    st.write(findings.get("note") or "")
    st.write(
        f"Human finding support: **{findings.get('human_review_status', 'not_yet_available')}**. "
        f"Automated quote check: **{findings.get('automated_quote_check', 'not_run')}** "
        f"({findings.get('quotes_found', 0)} located, {findings.get('quotes_missing', 0)} missing)."
    )
    claim_rows = []
    for claim in claims.get("claims") or []:
        claim_rows.append(
            {
                "Metric": claim.get("metric_name"),
                "Computed": claim.get("computed_value"),
                "Reported": claim.get("reported_value"),
                "Source count": claim.get("source_count"),
                "Check": claim.get("check_status"),
                "Human review": claim.get("review_status"),
            }
        )
    if claim_rows:
        st.caption(claims.get("note") or "")
        st.dataframe(claim_rows, hide_index=True, width="stretch")
    else:
        st.info("The claims audit has not been generated yet. Run the pipeline.")
    readiness = payload.get("readiness") or {}
    st.subheader("Readiness")
    for label, key in (
        ("Implemented", "implemented"),
        ("Awaiting review", "awaiting_review"),
        ("Validated", "validated"),
        ("Insufficient evidence", "insufficient_evidence"),
    ):
        st.markdown(f"**{label}**")
        entries = readiness.get(key) or []
        if entries:
            for entry in entries:
                st.write(f"- {entry}")
        else:
            st.write("- None.")
    if readiness.get("note"):
        st.caption(readiness["note"])
    json_path = OUTPUT / "human_validation_report.json"
    csv_path = OUTPUT / "human_validation_report.csv"
    if json_path.exists() and csv_path.exists():
        left, right = st.columns(2)
        left.download_button(
            "Download evaluation report (JSON)",
            data=json_path.read_bytes(),
            file_name="human_validation_report.json",
            mime="application/json",
        )
        right.download_button(
            "Download evaluation report (CSV)",
            data=csv_path.read_bytes(),
            file_name="human_validation_report.csv",
            mime="text/csv",
        )
    audit_path = OUTPUT / "claims_audit.json"
    evidence_path = OUTPUT / "evidence_verification.json"
    if audit_path.exists() or evidence_path.exists():
        audit_col, evidence_col = st.columns(2)
        if audit_path.exists():
            audit_col.download_button(
                "Download claims audit (JSON)",
                data=audit_path.read_bytes(),
                file_name="claims_audit.json",
                mime="application/json",
            )
        if evidence_path.exists():
            evidence_col.download_button(
                "Download evidence verification (JSON)",
                data=evidence_path.read_bytes(),
                file_name="evidence_verification.json",
                mime="application/json",
            )


def _topic_scorecard(block: dict, title: str) -> None:
    st.markdown(f"### {title}")
    st.markdown(f"**{block.get('headline', 'NOT YET AVAILABLE')}**")
    if block.get("warning"):
        st.warning(block["warning"])
    completion = block.get("completion") or {}
    columns = st.columns(4)
    columns[0].metric("Review completion", completion.get("display") or "N/A")
    columns[1].metric("Adjudicated labels", str(block.get("eligible", 0)))
    columns[2].metric("Ambiguous", str(block.get("ambiguous", 0)))
    columns[3].metric("Unresolved", str(block.get("unresolved", 0)))
    extra = st.columns(3)
    extra[0].metric("Insufficient evidence", str(block.get("insufficient_evidence", 0)))
    extra[1].metric("Unadjudicated conflicts", str(block.get("unadjudicated_conflicts", 0)))
    reviewer_gap = block.get("reviewer_disagreement_rate") or {}
    extra[2].metric("Reviewer disagreement", reviewer_gap.get("display") or "N/A")
    score_columns = st.columns(4)
    for column, key, label in (
        (score_columns[0], "accuracy", "Accuracy"),
        (score_columns[1], "macro_f1", "Macro F1"),
        (score_columns[2], "macro_precision", "Macro precision"),
        (score_columns[3], "macro_recall", "Macro recall"),
    ):
        cell = block.get(key) or {}
        column.metric(label, _public_metric(block, cell))
    weighted = st.columns(3)
    for column, key, label in (
        (weighted[0], "weighted_precision", "Weighted precision"),
        (weighted[1], "weighted_recall", "Weighted recall"),
        (weighted[2], "weighted_f1", "Weighted F1"),
    ):
        column.metric(label, _public_metric(block, block.get(key) or {}))
    disagreement = block.get("disagreement_rate") or {}
    interval = block.get("accuracy_interval") or {}
    st.write(
        f"Disagreement rate (predicted vs reviewer category): **{_public_metric(block, disagreement)}**. "
        f"Ambiguous share: **{(block.get('ambiguous_proportion') or {}).get('display', 'N/A')}**. "
        f"Unresolved share: **{(block.get('unresolved_proportion') or {}).get('display', 'N/A')}**."
    )
    st.write(
        f"Accuracy interval (Wilson 95% on labeled rows): **{interval.get('display') or 'N/A'}**. "
        f"{interval.get('caveat') or ''}"
    )
    if block.get("status") == "insufficient_sample":
        st.caption("The percentages above, when shown in the table, describe the labeled rows only.")
    _category_table(block)
    _confusion(block)
    estimates = block.get("population_estimates")
    if estimates:
        st.markdown("**Population estimates for this stratified sample**")
        st.caption(estimates.get("note") or "")
        estimate_columns = st.columns(4)
        for column, key, label in (
            (estimate_columns[0], "accuracy", "Weighted accuracy"),
            (estimate_columns[1], "macro_f1", "Weighted macro F1"),
            (estimate_columns[2], "weighted_precision", "Support-weighted precision"),
            (estimate_columns[3], "weighted_recall", "Support-weighted recall"),
        ):
            column.metric(label, (estimates.get(key) or {}).get("display") or "N/A")


def _public_metric(block: dict, cell: dict) -> str:
    if block.get("status") != "measured":
        if block.get("eligible") and cell.get("value") is not None:
            return f"N/A · labeled rows {cell.get('display')}"
        return "N/A"
    return cell.get("display") or "N/A"


def _category_table(block: dict) -> None:
    rows = []
    for category in block.get("per_category") or []:
        rows.append(
            {
                "Category": category["name"],
                "Precision": _cell(block, category["precision"]),
                "Recall": _cell(block, category["recall"]),
                "F1": _cell(block, category["f1"]),
                "Labeled support": category["support"],
            }
        )
    st.dataframe(rows, hide_index=True, width="stretch")


def _cell(block: dict, value) -> str:
    if value is None:
        return "N/A"
    if block.get("status") != "measured":
        return f"n/a to generalize ({value:.1%})"
    return f"{value:.1%}"


def _confusion(block: dict) -> None:
    matrix = block.get("confusion_matrix") or {}
    counts = matrix.get("counts") or []
    names = matrix.get("label_names") or []
    if not counts or not any(any(row) for row in counts):
        st.info("Confusion matrix counts are empty until adjudicated labels exist. Rows will be the human category. Columns will be the model category.")
        return
    table = []
    for index, row in enumerate(counts):
        if not any(row):
            continue
        record = {"Human category": names[index]}
        for column, count in enumerate(row):
            record[names[column]] = count
        table.append(record)
    st.markdown("**Confusion matrix** — row is the reviewer category, column is the model category.")
    st.dataframe(table, hide_index=True, width="stretch")


def _insight_scorecard(insights: dict) -> None:
    columns = st.columns(4)
    columns[0].metric("Awaiting review", str(insights.get("awaiting_review", 0)))
    columns[1].metric("Accepted", str(insights.get("accepted", 0)))
    columns[2].metric("Rejected", str(insights.get("rejected", 0)))
    columns[3].metric("Needs revision", str(insights.get("needs_revision", 0)))
    more = st.columns(4)
    more[0].metric("Needs more evidence", str(insights.get("needs_more_evidence", 0)))
    more[1].metric("Review coverage", (insights.get("review_coverage") or {}).get("display") or "N/A")
    more[2].metric("Resolved acceptance", (insights.get("acceptance_rate") or {}).get("display") or "N/A")
    more[3].metric("Accepted share of findings", (insights.get("approval_coverage") or {}).get("display") or "N/A")
    quality = insights.get("mean_evidence_quality") or {}
    usefulness = insights.get("mean_business_usefulness") or {}
    st.write(
        f"Average evidence quality: **{quality.get('display', 'N/A')}**. "
        f"Average business usefulness: **{usefulness.get('display', 'N/A')}**."
    )
    st.caption(insights.get("note") or "")
    rows = []
    for row in insights.get("by_stakeholder") or []:
        rows.append(
            {
                "Stakeholder": row["label"],
                "Reviewed": f"{row['reviewed']}/{row['total']}",
                "Accepted": row["accepted"],
                "Rejected": row["rejected"],
                "Needs revision": row["needs_revision"],
                "Needs more evidence": row["needs_more_evidence"],
                "Acceptance": row["acceptance_rate"]["display"],
            }
        )
    st.dataframe(rows, hide_index=True, width="stretch")


def _coverage_table(coverage: dict) -> None:
    theme_rows = []
    for row in coverage.get("by_theme") or []:
        theme_rows.append(
            {
                "Theme": row.get("label") or row.get("name"),
                "Population": row.get("population"),
                "Sampled": row.get("sampled"),
                "Fraction": row.get("fraction"),
            }
        )
    type_rows = []
    for row in coverage.get("by_call_type") or []:
        type_rows.append(
            {
                "Call type": row.get("name"),
                "Population": row.get("population"),
                "Sampled": row.get("sampled"),
                "Fraction": row.get("fraction"),
            }
        )
    if theme_rows:
        st.markdown("**Sample coverage by theme**")
        st.dataframe(theme_rows, hide_index=True, width="stretch")
    if type_rows:
        st.markdown("**Sample coverage by call type**")
        st.dataframe(type_rows, hide_index=True, width="stretch")


def _keep_topic(card: dict, filters: dict) -> bool:
    if filters["call"] != "All" and card.get("call_type") != filters["call"]:
        return False
    if filters["theme"] != "All" and card.get("predicted_topic") != filters["theme"]:
        return False
    if not _status_ok(card.get("review_status") or "", filters["status"], bool(card.get("decision")), bool(card.get("conflict"))):
        return False
    if filters["reviewer"] and filters["reviewer"] not in (card.get("reviewer_id") or "").lower():
        return False
    return True


def _keep_insight(card: dict, filters: dict) -> bool:
    if filters["stakeholder"] != "All" and card.get("stakeholder") != filters["stakeholder"]:
        return False
    if not _status_ok(card.get("decision") or "", filters["status"], bool(card.get("decision")), False):
        return False
    if filters["reviewer"] and filters["reviewer"] not in (card.get("reviewer_id") or "").lower():
        return False
    return True


def _status_ok(status: str, selected: str, reviewed: bool = False, conflict: bool = False) -> bool:
    if selected == "All":
        return True
    if selected == "Needs a decision":
        return status in {"", "pending"} or not reviewed
    if selected == "Conflict":
        return conflict or status == "conflict"
    if selected == "Reviewed":
        return reviewed or status not in {"", "pending"}
    return True


def _evidence_payload(report: dict, decisions: dict) -> dict:
    return build_evidence_verification(DATA, report, decisions)


def _rating_index(value) -> int:
    if value in {1, 2, 3, 4, 5}:
        return int(value)
    return 0


def _refresh_metrics_from_disk() -> None:
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    sample = load_sample(SAMPLE_PATH)
    _refresh_metrics(report, sample)


def _refresh_metrics(report: dict, sample: dict) -> None:
    decisions = load_decisions(DECISIONS_PATH)
    evidence = build_evidence_verification(DATA, report, decisions)
    claims_path = OUTPUT / "claims_audit.json"
    claims = json.loads(claims_path.read_text(encoding="utf-8")) if claims_path.exists() else None
    payload = build_human_validation_report(report, sample, decisions, evidence, claims)
    write_human_validation_report(payload, OUTPUT)
    from src.review.evidence import write_evidence_verification

    write_evidence_verification(evidence, OUTPUT)
    if WEB_REPORT.parent.exists():
        WEB_REPORT.write_text(json.dumps(payload), encoding="utf-8")


def _current_report(report: dict, sample: dict) -> dict:
    path = OUTPUT / "human_validation_report.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    decisions = load_decisions(DECISIONS_PATH)
    return build_human_validation_report(report, sample, decisions)


if __name__ == "__main__":
    main()
