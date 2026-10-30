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
