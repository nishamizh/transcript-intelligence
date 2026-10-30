# Transcript Intelligence

A briefing over 100 Aegis Cloud call transcripts, from 3 February 2026 through 28 April 2026. Support cases, account conversations, and internal meetings become one `Meeting` object. Topic analysis, sentiment, and stakeholder insights all read that object. The executive dashboard reads the report the pipeline writes.

Counts below are from the current `output/report.json`. The longer baseline, including what was not measured, is `docs/ASSIGNMENT_READINESS.md`.

## Question 1 — Categories, with examples

The summaries ship 351 free-text topic labels. 76% appear once, so those strings are evidence, not the categories we would publish.

Each meeting is mapped onto one primary governed theme. A label that contains a theme keyword counts more than a keyword in the title or summary. Separately, TF-IDF + NMF (8 topics, fixed seed) is fit on the summary and the transcript sentences, with the labels held out. BERTopic can replace that pass (`--topic-model bertopic`) and does not replace the theme list. NMF is the default because the corpus is about 100 documents and the audit needs to be repeatable.

`topic_examples` stores one or two real meetings per theme. The rule is in the report: more matching labels, then a higher theme score, then higher lexical overlap, then meeting id. The excerpt is a transcript sentence when one contains a matched keyword. Emails and phone numbers are redacted. These are the first exemplars:

| Theme | Meeting | What the text actually says |
| --- | --- | --- |
| Reliability | Detect Outage - Remediation Plan Review (`01KQ03B0303900521BB089CA`) | “Yep, I'm on. Give me one sec, I'm just pulling up the incident doc.” Labels include outage remediation and incident response. The held-out model says failure · breaker · circuit breaker. Lexical overlap is 0, so the display says review recommended. That is a missing shared word, not a failed category. |
| Compliance | Aegis / Maplewood Goods - SOC 2 Prep Review (`01KQAFB8DBF6E1E2FDEF0B75`) | “Hey Nathan, great to meet you. Really looking forward to digging into your SOC 2 prep situation and seeing how we can help.” |
| Renewal | Aegis / Cobalt Software - Q2 Planning (`01KQ0F8AFF3DA34FD4580008`) | “I wanted to walk through where things stand on the renewal, get your feedback on how the platform's been performing, and then we can talk about what your roadmap” |
| Billing | Support Case #9279 - Summit Trust Billing Inquiry (`01KQ0C1280EDA4E70AAD7C35`) | “I have a support case open — case number 9279 — regarding a billing question.” |
| Product gaps | Support Case #8811 - Blackridge Investments Custom Compliance Template (`01KQ92EA85FE4C537400227D`) | “I've got the case here, case number 8811, and it looks like you're coming in with a feature request around custom compliance templates in Aegis Comply.” Overlap with the generated topic is 0, so the row says review recommended. |
| Onboarding | Aegis / Coastal Living Co - Protect Module Expansion (`01KQ560FF1570C5E7F71D752`) | “And that's actually something we can help you model out as part of the onboarding — we have a business impact analysis template…” The held-out topic is backup · protect · cloudprime. |
| Identity | Aegis / Frostbyte AI - Identity Module Setup (`01KQC3A2EBC501837E973B16`) | “And I want to introduce Ananya Sharma — she's one of our senior engineers on the Identity side and she's going to be your main technical point of contact through the onboarding process.” Labels include SSO configuration and MFA policy. |
| Delivery | Detect Team - Sprint Planning (`01KQ4EE836687F95080D92AB`) | “Okay so let's get started, we've got a lot to get through today for sprint twelve.” |

Primary-theme counts: reliability 43 (mean 2.87), compliance 21 (4.29), identity 12 (3.33), renewal 8 (3.39), product 8 (3.80), billing 5 (3.50), onboarding 2 (4.85), delivery 1 (3.60). Means are the source 1–5 score.

`topic_agreement` in JSON is the same number as `lexical_topic_overlap`. Mean overlap is 0.08. It is not accuracy. Zero shared words is `review recommended`.

## Question 2 — Sentiment, with the source named

The charted number is `sentimentScore` from each summary, scale 1–5, copied unchanged. `overallSentiment` is copied unchanged. Turn `sentimentType` is reported only as a mix of turns. No second model rescores the text. Every cohort below has an n. None of the gaps is a causal estimate.

| Cohort | n | Mean |
| --- | ---: | ---: |
| Support | 27 | 2.94 |
| Internal | 30 | 3.42 |
| External | 43 | 3.71 |
| February | 26 | 3.68 |
| March | 36 | 2.78 |
| April | 38 | 3.83 |
| Incident-titled meetings | 10 | 2.18 |
| All other meetings | 90 | 3.55 |
| Meetings that mention the outage | 49 | 2.93 |
| Meetings that do not | 51 | 3.88 |

Support was already cold in February (2.89, n=8) while external calls were at 4.26 (n=10). March is the low month for every call type, and the week of 9 March is the low week (2.16, n=13). In April, external is 4.15 (n=17) and support is 3.21 (n=9). The outage is visible in the calendar. This run does not measure what it caused.

Turn polarity, which is not the 1–5 score: support 1,072 turns are 10% positive and 23% negative; external 1,940 turns are 41% positive and 13% negative.

Charts: `output/charts/sentiment_by_call_type.png`, `output/charts/sentiment_trend.png`. Each states the source score and shows n.

## Question 3 — What each team can act on

- **Support.** Reliability is 13 of 27 cases. The support mean sits 0.77 below external. Ten support calls contain churn language and no positive pivot. Staff the weekly review by theme, and route a no-pivot churn line to the account owner the same day.
- **Product.** 51 feature-gap moments are already inside cases or account reviews. Detect meetings average 2.73. Do not brief a Comply launch over a Detect renewal without saying that score.
- **Engineering.** Ten meetings are titled as an incident, outage, or war room (mean 2.18). The repeated language is a single point of failure, a health check that could not see the failure, and pipeline delay. That is a keyword count, not a new root-cause study. Keep the owner on the later meetings that still cite the outage.
- **Sales.** 24 accounts already use churn language. SentinelShield is named in 18 meetings. The rank is a briefing order. It is not a forecast. The competitor names are configured, not discovered from a model.

## What this does not measure yet

Theme precision, recall, F1, and insight acceptance are **not yet available**. `output/review_decisions.json` has blank decisions. The validation report prints `N/A` with the review count and the sample size. It does not print 0% or 100% for an empty acceptance denominator. Citation completeness is separate and structural: 9 of 9 insights cite a real meeting. The quality composite (about 97%) scores the shape of the briefing, not whether a reviewer would accept it. No revenue, bookings, or churn probability is computed.

The data-validation gaps stay open until real reviewers save enough adjudicated decisions and the report is regenerated. Filling the file with the model's own prediction is not a human label.

## Human review

The task is single-label. Each meeting has one governed category. A meeting can match extra themes, and those are shown as context, not as a second grade.

**Representative sample.** Seed 7. Target 30 meetings, or every meeting if the corpus were smaller. One seat is reserved for each predicted theme, then the remaining seats follow the largest-remainder method on `(count - 1)`. Within a predicted theme, seats are split across support, external, and internal the same way. The stratum is the model's primary theme plus the call type recorded at ingestion. It is not a gold-label stratum. Meetings inside a stratum are drawn with `random.Random` seeded by `7`, the theme, and the call type. The selection probability is stratum seats divided by stratum size. Population estimates weight each labeled row by `1 / selection probability`. Corrected labels are not written back into the taxonomy or the TF-IDF/NMF fit. The lexical model did see every transcript before the sample was drawn; it is a diagnostic, not the category being graded.

**Challenging cases.** Every meeting already on the review queue (thin theme margin, or no shared words with the held-out topic). This is not a probability sample. Its accuracy is reported on its own and is not averaged with the representative sample. A meeting can be in both lists and still has one saved decision.

**Topic decision.** Confirm the predicted category, correct it to one of the other seven themes, mark it ambiguous, or mark insufficient evidence. A blank row is not a review. Ambiguous and insufficient-evidence rows count toward completion and stay out of accuracy, precision, recall, and F1. The card includes the model version, the taxonomy version, a source-document hash, and more of the transcript than the short excerpt. A second reviewer who disagrees does not erase the first decision. The row stays a conflict, out of the accuracy denominator, until someone explicitly adjudicates it.

**Insight decision.** Accept, reject, needs revision, or needs more evidence. Optional evidence-quality and usefulness ratings are 1–5. Nothing is auto-approved.

**Metrics, once labels exist.** Completion is reviewed / assigned. Accuracy, macro precision, macro recall, macro F1, and support-weighted precision, recall, and F1 use `sklearn.metrics` on the eight theme ids. The confusion matrix counts adjudicated rows: the row is the human category, the column is the model category. Predicted-versus-human disagreement is the share of those rows where the two differ. Reviewer disagreement is the share of items with two reviewers whose labels differ, and it is N/A when no item has two reviewers. Accuracy also carries a Wilson 95% interval on the labeled rows, with the caveat that the draw is stratified on the predicted theme. Per-category support is the number of human labels for that theme. Macro averages skip a theme with no labeled support, and they skip an undefined precision instead of calling it zero. Unadjudicated conflicts are excluded.

Insight acceptance is `accepted / (accepted + rejected)`. Needs revision and needs more evidence are reviewed and are not in that denominator. If that denominator is 0, the rate is N/A. Approval coverage is `accepted / all insights`, and it is N/A when nothing has been reviewed. Every percentage is stored with its numerator and denominator.

**Open the reviewer**

```bash
streamlit run src/review/app.py --server.port 43124 --server.address 0.0.0.0
```

The page is titled Human Validation & Evidence Quality. Enter a reviewer id. Use the filters for call type, theme, stakeholder, review status, and reviewer. Open Representative sample, Challenging cases, Business insights, or Findings verification. Choose a decision, add a comment, and save. On Findings verification, judge whether the cited passages support the claim: supported, partially supported, unsupported, or insufficient evidence. A quote that the audit already located is not that judgment. Saving writes `output/review_decisions.json` (an edit keeps the previous row in `audit`; a disagreement stays in `submissions`) and regenerates `output/human_validation_report.json` and `.csv`.

**Regenerate the report without opening the app**

```bash
python -m src.pipeline.runner --data data --output output
python -m src.review.validation --report output/report.json --decisions output/review_decisions.json --output output
```

```bash
python -m src.review.claims --data data --report output/report.json --output output
```

The pipeline adds blank rows for new ids and does not change a decision already stored. It also writes `output/claims_audit.json` and `output/evidence_verification.json`. The claims audit recomputes the headline counts from the loaded meetings and compares them with the report. The current run matches: 100 transcripts, 8 governed categories, support mean 2.937, external mean 3.7116, 49 outage-related meetings, 24 accounts with churn language. Every claim is marked `not_human_verified`. The evidence file located 27 of 27 cited quotations in source transcripts or summaries. That string check is not a support judgment. Human finding support is 0 of 9.

The older command `python -m src.review.evaluate` still scores only the previous accept / edit / reject vocabulary. The human-validation report is the one that understands confirm, correct, ambiguous, insufficient evidence, insight decisions, and finding judgments.

**Known limits.** Thirty meetings is a sample, not the next quarter. Fewer than a full set of adjudicated labels is marked so it does not look like a population result. The Wilson interval is not a design-based variance for the stratified draw. Lexical overlap is still not accuracy. The quality composite is still not acceptance. A reproducible count is still not a human verification of meaning. No LLM is used as a judge. The three validation gaps stay open until people save decisions.

## Slide deck

`deck/Transcript-Intelligence-Briefing.pptx` is the leadership review: fourteen slides, findings first. Speaker notes are on each slide. Rebuild it after a pipeline run with `python scripts/build_deck.py`. The deck was not rebuilt for this pass. The sentiment figures it cites are the same ones in the table above.

## Slide deck

`deck/Transcript-Intelligence-Briefing.pptx` is the leadership review: fourteen slides, findings first. Speaker notes are on each slide. Rebuild it after a pipeline run with `python scripts/build_deck.py`.

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
  pipeline/methodology.py    Hybrid method, written from the run
  review/                    Queue, sample, decisions, validation, Streamlit reviewer
  config/settings.py
data/                        One folder per meeting
output/report.json           What every consumer reads
output/review_queue.json     Items to review; no decisions stored here
output/review_sample.json    Representative draw and the separate challenging set
output/review_decisions.json Reviewer file. The pipeline does not overwrite decisions
output/human_validation_report.json  Metrics from those decisions, or N/A
web/                         Executive dashboard
```

## Run the pipeline

```bash
pip install -r requirements.txt
python -m src.pipeline.runner --data data --output output
```

That writes `output/report.json`, `output/charts/*.png`, the review queue, the stratified sample, a decision template if one is missing, and `output/human_validation_report.json` plus `.csv`. It copies the report and the validation file to `web/src/data/` for the dashboard. It does not fill in reviewer decisions.

```bash
python -m pytest
python -m src.review.validation --report output/report.json --decisions output/review_decisions.json --output output
python -m src.review.evaluate --report output/report.json --decisions output/review_decisions.json
```

With a blank decision file, theme F1 and insight acceptance are N/A. The older evaluate command prints `unavailable` for the same reason.

## Run the dashboard

```bash
cd web
npm install
npm run dev
```

The dev server listens on port 43123. The human-review app listens on port 43124:

```bash
streamlit run src/review/app.py --server.port 43124 --server.address 0.0.0.0
```

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

Publish the governed themes. `lexical_topic_overlap` (still stored as `topic_agreement` in JSON) is the Jaccard overlap of label tokens and model terms. Zero shared words is `review recommended`. A small non-zero score is expected and is not an error. That is the governance loop: a stable taxonomy, an independent model, and a person on the disagreements.

## Sentiment

Meeting labels and 1–5 scores are used as recorded. The analyzer does not rescore the text. It cuts the source score by call type and by week, reports n for each cohort, separates incident-titled meetings from the rest, and writes the interpretation from those gaps. Turn polarity stays a separate mix. A different corpus produces a different sentence. The gaps are descriptive.

## Quality

`InsightQualityScore` scores the briefing:

- **Coverage** — themes assigned, stakeholders served, meetings cited
- **Consistency** — labels two ranks apart do not invert the score, and published means match a fresh average
- **Actionability** — each insight has a number, a reason, a recommendation, and evidence
- **Confidence** — sample size, the smallest call-type cell, and evidence depth

The composite measures whether the briefing is reviewable. It does not measure whether a person would accept the conclusion. That judgment is a saved decision in `output/review_decisions.json`. An LLM is not used as a judge.

## Call types

Assigned at ingestion, because they describe who was in the room:

- `support` when the title starts with `Support Case`
- `external` when any other attendee is outside `aegiscloud.com`
- `internal` otherwise, including incident bridges with no customer invited
