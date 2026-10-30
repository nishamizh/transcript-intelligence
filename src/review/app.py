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
from src.review.decisions import load_decisions
from src.review.sample import build_review_sample, load_sample, write_review_sample
from src.review.schema import MODEL_VERSION, TAXONOMY_VERSION, DecisionSchemaError
from src.review.store import DecisionStore
from src.review.validation import build_human_validation_report, write_human_validation_report

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "output"
REPORT_PATH = OUTPUT / "report.json"
DECISIONS_PATH = OUTPUT / "review_decisions.json"
SAMPLE_PATH = OUTPUT / "review_sample.json"
WEB_REPORT = ROOT / "web" / "src" / "data" / "human_validation_report.json"

TOPIC_CHOICES = [
    ("approve", "Approve predicted category"),
    ("correct", "Reject and choose a corrected category"),
    ("ambiguous", "Ambiguous / needs additional review"),
]
INSIGHT_CHOICES = [
    ("accept", "Accept"),
    ("reject", "Reject"),
    ("needs_revision", "Needs revision"),
    ("needs_more_evidence", "Needs more evidence"),
]


def main() -> None:
    st.set_page_config(page_title="Human review", layout="wide")
    st.title("Evaluation and human review")
    st.caption(
        "Reviewers judge the model's category and the stakeholder findings. "
        "Metrics stay N/A until those decisions are saved. Predictions are not treated as labels."
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
        st.caption("Required before a decision can be saved. It is stored with the timestamp.")
        if st.button("Refresh metrics from saved decisions"):
            _refresh_metrics(report, sample)
            st.rerun()
        st.divider()
        st.markdown(
            "Representative metrics estimate the book. "
            "Challenging-case metrics describe the review queue only. They are not averaged together."
        )

    representative, challenging, insights = st.tabs(
        ["Representative sample", "Challenging cases", "Business insights"]
    )
    with representative:
        _topic_tab(report, sample, decisions, "representative", reviewer_id)
    with challenging:
        st.warning(sample.get("challenging", {}).get("bias") or "This set is biased toward hard cases.")
        _topic_tab(report, sample, decisions, "challenging", reviewer_id)
    with insights:
        _insight_tab(report, decisions, reviewer_id)

    st.divider()
    _evaluation(report, sample)


def _sample(report: dict) -> dict:
    if SAMPLE_PATH.exists():
        return load_sample(SAMPLE_PATH)
    sample = build_review_sample(report.get("meetings") or [], report.get("review_queue") or {})
    write_review_sample(sample, SAMPLE_PATH)
    return sample


def _topic_tab(report: dict, sample: dict, decisions: dict, role: str, reviewer_id: str) -> None:
    cards = topic_cards(report, sample, decisions, role)
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
        st.markdown("**Excerpt**")
        st.write(card["excerpt"] or "No excerpt is stored.")
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
                f"Saved decision: {card['decision']}"
                + (f" → {card['human_topic']}" if card["human_topic"] else "")
                + (f" · {card['reviewer_id']} · {card['reviewer_timestamp']}" if card["reviewer_id"] else "")
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
            )
        except DecisionSchemaError as exc:
            st.error(str(exc))
            return
        _refresh_metrics_from_disk()
        st.success(f"Saved {stored['review_id']}. The evaluation report was regenerated from the file.")
        st.rerun()


def _insight_tab(report: dict, decisions: dict, reviewer_id: str) -> None:
    cards = insight_cards(report, decisions)
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


def _evaluation(report: dict, sample: dict) -> None:
    st.header("Scorecards")
    payload = _current_report(report, sample)
    topic = payload["topic_classification"]
    insights = payload["business_insights"]
    if payload["data_gap"]["resolved"]:
        st.success("Both gaps have enough adjudicated human decisions to report.")
    else:
        st.warning(
            "Data-validation gaps are NOT YET AVAILABLE. "
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
    st.write(
        f"Disagreement rate (predicted vs reviewer category): **{_public_metric(block, disagreement)}**. "
        f"Ambiguous share: **{(block.get('ambiguous_proportion') or {}).get('display', 'N/A')}**. "
        f"Unresolved share: **{(block.get('unresolved_proportion') or {}).get('display', 'N/A')}**."
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
    more[2].metric("Acceptance rate", (insights.get("acceptance_rate") or {}).get("display") or "N/A")
    more[3].metric("Approval coverage", (insights.get("approval_coverage") or {}).get("display") or "N/A")
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
    payload = build_human_validation_report(report, sample, decisions)
    write_human_validation_report(payload, OUTPUT)
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
