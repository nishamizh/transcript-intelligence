# Assignment readiness

This note is the factual baseline for the briefing. Every count below was read from `output/report.json` after:

```bash
python3 -m src.pipeline.runner --data data --output output
python3 -m pytest -q
python3 -m src.review.evaluate --report output/report.json --decisions output/review_decisions.json --output output/evaluation.json
```

Pytest: 17 passed. The evaluation file reports theme metrics and insight acceptance as **unavailable**, because `review_decisions.json` has blank decisions. Citation completeness is a structural check, not accuracy: 9 of 9 insights cite meeting ids that exist and include a quote.

The slide deck was not rebuilt. The sentiment figures it already cites match this run.

## What the corpus is

100 meetings, 3 February 2026 through 28 April 2026, no load failures. Call types, assigned from who was in the room: support 27, external 43, internal 30. Support wins when the title starts with `Support Case`.

## Question 1 — categories

351 distinct free-text labels shipped with the summaries. 76% appear once. Those strings are evidence, not the published taxonomy.

Eight governed themes, primary theme only, so the counts sum to 100:

| Theme | Meetings | Mean source score |
| --- | ---: | ---: |
| Reliability and incidents | 43 | 2.87 |
| Compliance and audit | 21 | 4.29 |
| Identity and access | 12 | 3.33 |
| Renewal and churn | 8 | 3.39 |
| Product gaps and roadmap | 8 | 3.80 |
| Billing and packaging | 5 | 3.50 |
| Onboarding and adoption | 2 | 4.85 |
| Planning and delivery | 1 | 3.60 |

`topic_examples` holds one or two real meetings per theme. Selection is deterministic: more label hits, then higher theme score, then higher lexical overlap, then meeting id. The excerpt is a transcript sentence when one contains a matched keyword, otherwise the first summary sentence. Emails and phone numbers are redacted. Nothing in that list was written by hand.

A second pass, TF-IDF + NMF, 8 components, `random_state` 7, is fit on the summary and transcript sentences only. Labels are held out. Mean lexical overlap with the labels is 0.08. That number is a Jaccard diagnostic. It is not accuracy. 27 meetings share no content word with their generated terms and are marked `review recommended`. A low non-zero score is expected, because labels are phrases and the model emits words, and is not an error.

BERTopic implements the same `TopicModel` contract and is not the default. On about 100 documents the lexical model is deterministic and does not download an embedding model.

## Question 2 — sentiment

Meeting scores are `summary.json` `sentimentScore` on a 1–5 scale, copied unchanged. Labels are `overallSentiment`, copied unchanged. Turn polarity is `sentimentType` and is only a mix of turns. No new sentiment model is fit. `inferred_model_score` is null.

| Cohort | n | Mean |
| --- | ---: | ---: |
| Support | 27 | 2.94 |
| Internal | 30 | 3.42 |
| External | 43 | 3.71 |
| February | 26 | 3.68 |
| March | 36 | 2.78 |
| April | 38 | 3.83 |
| Incident titles | 10 | 2.18 |
| Everyone else | 90 | 3.55 |
| Outage mentioned | 49 | 2.93 |
| Outage not mentioned | 51 | 3.88 |

February support was already 2.89 (n=8) while external was 4.26 (n=10). March dropped all three: support 2.73 (n=10), external 2.90 (n=16), internal 2.64 (n=10). April external is 4.15 (n=17) and support is 3.21 (n=9). The week of 9 March is the low week: 2.16 across 13 meetings. These are descriptive gaps. They are not an estimate of what the outage caused.

Turn polarity, which is not the 1–5 score: support 1,072 turns (10% positive, 23% negative); external 1,940 turns (41% positive, 13% negative); internal 1,301 turns (20% positive, 17% negative).

## Question 3 — stakeholder findings

Nine findings, three citations each. All nine citations resolve to a meeting in the report.

- Support: reliability is 13 of 27 cases (48%). The support mean is 0.77 below external. 10 support calls use churn language and never turn toward a next step.
- Product: 51 feature-gap moments. Detect meetings average 2.73. Comply averages 4.28, with none under 3. That second figure is a module cohort in the insight, not a new score.
- Engineering: 10 incident-titled meetings. Five failure-language patterns from a keyword pass, not a new root-cause model.
- Sales: 24 accounts with churn language, ranked for a briefing, not forecast. SentinelShield is named in 18 meetings. The competitor list is configured. It was not discovered.

## What was not measured

- Theme precision, recall, or F1. The reviewer file is blank, so the evaluation CLI reports those as unavailable.
- Insight acceptance rate. Same reason.
- A sentiment model other than the source score.
- A causal effect of the outage.
- Bookings, saved revenue, or a churn probability. Any win/loss dollar figure in the deck is what an internal call recorded.

The quality composite is about 97%. It scores whether the briefing has themes, consistent labels, and actionable writeups. It does not score whether a reviewer would accept the conclusion.

## Review queue

57 items: 27 meetings with no shared tokens, 28 with the top two theme scores within 1 point, and 9 stakeholder insights. Some meetings are in the queue for both classification reasons, so the reason counts add to more than 57. Decisions go in `output/review_decisions.json`. Regenerating the pipeline adds blank rows for new ids and does not change a reason already stored. Source meetings are not rewritten.

```bash
python3 -m src.review.evaluate --report output/report.json --decisions output/review_decisions.json
```

## Checklist

| Requirement | Where it lives | State |
| --- | --- | --- |
| Categories with real transcript examples | `report.topic_examples`, dashboard Topics | Done. 15 examples, every id is in the corpus |
| Sentiment charts and interpretation, with n and source | Charts, Sentiment section, `sentiment.provenance` | Done. No new model score |
| At least three stakeholder insights | Support, product, engineering, sales | Done. Nine findings |
| Lexical overlap is not called accuracy | Display name `lexical_topic_overlap`; JSON keeps `topic_agreement` | Done. Zero overlap is `review recommended` |
| Methodology, including why NMF and how BERTopic differs | `report.methodology`, dashboard | Done |
| Review queue and decisions that do not overwrite source data | `output/review_queue.json`, `.csv`, `review_decisions.json` | Done |
| Evaluation CLI that refuses to invent accuracy | `python -m src.review.evaluate` | Done. Current run is unavailable |
| Tests for schema, exemplars, provenance, queue, math, unchanged scores | `tests/test_assignment.py`, `tests/test_pipeline.py` | 17 passed |
| Public dashboard redacts contact details in newly shown excerpts | `redact_public_text`, `redactDisplay` | Done |
