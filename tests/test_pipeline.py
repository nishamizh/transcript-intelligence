from pathlib import Path

import pytest

from src.config.settings import Settings
from src.pipeline.runner import run

DATA = Path("data")


@pytest.mark.skipif(not DATA.exists(), reason="dataset is not in the workspace")
def test_pipeline_on_the_corpus(tmp_path: Path):
    report = run(
        Settings(
            data_dir=DATA,
            output_dir=tmp_path,
            web_data_path=tmp_path / "report.json",
        )
    )
    assert report["dataset"]["meeting_count"] == 100
    assert report["dataset"]["load_failures"] == 0
    assert report["dataset"]["call_types"] == {"support": 27, "external": 43, "internal": 30}

    by_type = {row["call_type"]: row["mean_score"] for row in report["sentiment"]["by_call_type"]}
    assert by_type["support"] < by_type["external"]
    assert report["sentiment"]["incident"]["count"] >= 5
    assert report["sentiment"]["incident"]["mean_score"] < report["sentiment"]["overall_mean"]

    themes = {theme["theme_id"]: theme["meeting_count"] for theme in report["topics"]["themes"]}
    assert sum(themes.values()) + report["topics"]["unclassified_count"] == 100
    assert themes["reliability"] > 0
    assert themes["compliance"] > 0

    stakeholders = {insight["stakeholder"] for insight in report["insights"]}
    assert stakeholders == {"support", "product", "engineering", "sales"}
    assert all(insight["evidence"] for insight in report["insights"])

    quality = report["quality"]
    assert quality["composite"] >= 0.6
    assert (tmp_path / "report.json").exists()
    assert (tmp_path / "charts" / "sentiment_by_call_type.png").exists()

    cited = {
        item["meeting_id"]
        for insight in report["insights"]
        for item in insight["evidence"]
    }
    known = {meeting["meeting_id"] for meeting in report["meetings"]}
    assert cited <= known

    import json

    for meeting in report["meetings"]:
        summary = json.loads((DATA / meeting["meeting_id"] / "summary.json").read_text(encoding="utf-8"))
        assert meeting["sentiment_score"] == summary["sentimentScore"]
        assert meeting["sentiment"] == str(summary["overallSentiment"]).strip().lower()
        assert meeting["lexical_topic_overlap"] == meeting["topic_agreement"]

    provenance = report["sentiment"]["provenance"]
    assert provenance["inferred_model_score"] is None
    assert "sentimentScore" in provenance["meeting_score_source"]
    assert "sentimentType" in provenance["turn_polarity_source"]

    examples = report["topic_examples"]["examples"]
    by_theme: dict[str, int] = {}
    for example in examples:
        assert example["meeting_id"] in known
        source = next(row for row in report["meetings"] if row["meeting_id"] == example["meeting_id"])
        assert example["assigned_theme"] == source["primary_theme"]
        assert example["original_labels"] == source["topics"]
        assert example["evidence_excerpt"]
        assert example["assigned_theme_name"] in example["classification_explanation"]
        by_theme[example["assigned_theme"]] = by_theme.get(example["assigned_theme"], 0) + 1
    for theme in report["topics"]["themes"]:
        if theme["meeting_count"]:
            assert 1 <= by_theme.get(theme["theme_id"], 0) <= 2

    assert report["methodology"]["approach"] == "hybrid"
    assert (tmp_path / "review_queue.json").exists()
    assert (tmp_path / "review_queue.csv").exists()
    assert (tmp_path / "review_decisions.json").exists()
    decisions = json.loads((tmp_path / "review_decisions.json").read_text(encoding="utf-8"))
    assert decisions["items"]
    assert all(item["decision"] == "" for item in decisions["items"])
    sample = json.loads((tmp_path / "review_sample.json").read_text(encoding="utf-8"))
    assert sample["seed"] == 7
    assert sample["representative"]["count"] == 30
    validation = json.loads((tmp_path / "human_validation_report.json").read_text(encoding="utf-8"))
    assert validation["data_gap"]["topic_classification"] == "NOT YET AVAILABLE"
    assert validation["topic_classification"]["representative"]["accuracy"]["display"] == "N/A"
    assert validation["business_insights"]["acceptance_rate"]["display"] == "N/A"
    assert validation["findings_verification"]["human_review_status"] == "not_yet_available"
    assert validation["claims_audit"]["review_status"] == "not_human_verified"
    assert (tmp_path / "human_validation_report.csv").exists()
    assert (tmp_path / "claims_audit.json").exists()
    assert (tmp_path / "evidence_verification.json").exists()
