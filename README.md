# Transcript Intelligence

A briefing over about 100 Aegis Cloud call transcripts. Support cases, account conversations, and internal meetings become one `Meeting` object. Topic analysis, sentiment, and stakeholder insights all read that object. The executive dashboard reads the report the pipeline writes.

The point of the structure is that a new analytic, a new stakeholder, or a new consumer should not require a new loader.

## What the briefing says

Support calls are the cold part of the book. External account calls run warmer. Incident-titled meetings are a different population, and the March Detect outage is still the subject of many later conversations. Accounts with explicit churn language are ranked as one sales book. The numbers in the dashboard are computed by the pipeline, not typed into the page.

## Layout

```
src/
  models/meeting.py          Canonical Meeting, turns, events, features
  ingestion/loader.py        MeetingLoader and DatasetLoader
  analytics/
    base.py                  Analyzer contract
    features.py              Derived metrics
    topic_analyzer.py        Governed themes, audited by a held-out topic model
    sentiment_analyzer.py    Call type, time, and what the gap means
    insight_analyzer.py      Support, product, engineering, sales
    quality.py               Coverage, consistency, actionability, confidence
  visualization/charts.py    Static charts for the repo
  pipeline/runner.py         The only place that knows the file paths
  config/settings.py
data/                        One folder per meeting
output/report.json           What every consumer reads
web/                         Executive dashboard
```

## Run the pipeline

```bash
pip install -r requirements.txt
python -m src.pipeline.runner --data data --output output
```

That writes `output/report.json`, `output/charts/*.png`, and copies the report to `web/src/data/report.json`.

```bash
python -m pytest
```

## Run the dashboard

```bash
cd web
npm install
npm run dev
```

The dev server listens on port 43123.

## How a new analytic is added

Implement `Analyzer.analyze(meetings)` and call it from `src/pipeline/runner.py`. Do not open the raw JSON from the analyzer. If the analytic needs a new fact about a single meeting, add it in `MeetingFeatureExtractor` so the next analytic can reuse it.

A new stakeholder is a function in `insight_analyzer.py` that returns `Insight` objects with a finding, a reason it matters, a recommendation, and cited meetings.

A new consumer reads `output/report.json`. The dashboard is one consumer. A weekly digest would be another, and it would not get its own copy of the parsing logic.

## Topics

The summaries already ship free-text topic labels. 351 distinct labels, most of them used once, is not a taxonomy. The pipeline maps those labels onto a small governed theme list and keeps the raw label as evidence.

Separately, a topic model is fit on the summary and the transcript sentences, with the provided labels held out and speaker names removed so the model cannot discover people. The default model is TF-IDF + NMF (`--topic-model lexical`). It is deterministic on a corpus this size. BERTopic implements the same `TopicModel` contract:

```bash
pip install bertopic
python -m src.pipeline.runner --topic-model bertopic
```

Publish the governed themes. Treat low token-overlap between a theme and its generated topic as a review queue, not as a failure of either side. That is the governance loop: a stable taxonomy, an independent model, and a person on the disagreements.

## Sentiment

Meeting labels and 1–5 scores are used as recorded. The analyzer does not rescore the text. It cuts the score by call type and by week, separates incident-titled meetings from the rest, and writes the interpretation from those gaps. A different corpus produces a different sentence.

## Quality

`InsightQualityScore` scores the briefing:

- **Coverage** — themes assigned, stakeholders served, meetings cited
- **Consistency** — labels two ranks apart do not invert the score, and published means match a fresh average
- **Actionability** — each insight has a number, a reason, a recommendation, and evidence
- **Confidence** — sample size, the smallest call-type cell, and evidence depth

The composite measures whether the briefing is reviewable. It does not measure whether a person would accept the conclusion. The next step is a human accept, edit, or reject on each insight, then an LLM-as-judge that has to agree with those labels.

## Call types

Assigned at ingestion, because they describe who was in the room:

- `support` when the title starts with `Support Case`
- `external` when any other attendee is outside `aegiscloud.com`
- `internal` otherwise, including incident bridges with no customer invited
