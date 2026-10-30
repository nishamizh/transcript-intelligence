# Assignment readiness

This note is the factual baseline for the briefing. Every count below was read from `output/report.json` after:

```bash
python3 -m src.pipeline.runner --data data --output output
python3 -m pytest -q
python3 -m src.review.evaluate --report output/report.json --decisions output/review_decisions.json --output output/evaluation.json
```

Pytest: 27 passed. Theme precision, recall, F1, and insight acceptance are **NOT YET AVAILABLE**. `review_decisions.json` still has blank decisions, so the human-validation report keeps those metrics as N/A and shows the review count and the sample size. Citation completeness, from the older evaluation file, is a structural check, not accuracy: 9 of 9 insights cite meeting ids that exist and include a quote.

Three validation gaps remain **not resolved**:

1. Topic precision, recall, and F1. Human-adjudicated labels: 0 of 30 in the representative sample, 0 of 48 challenging cases.
2. Insight acceptance. Accepted 0, rejected 0, so the rate is N/A. Review coverage is 0 of 9.
3. Independent support for the findings. 27 of 27 cited quotations were located in source files. Human support judgments are 0 of 9. A located quote is not a judgment that the passage supports the claim.

They become resolved only after real reviewers save enough adjudicated labels and this report is regenerated from those labels. No prediction was copied into a human field. No LLM was used as a judge.

The claims audit in `output/claims_audit.json` recomputed the headline figures from the loaded meetings. All six checks match the report, and each row is `not_human_verified`: 100 transcripts, 8 governed categories, support mean 2.937 (n=27), external mean 3.7116 (n=43), 49 outage-related meetings, 24 accounts with churn language. No duplicate meeting ids. No domain was tied to two account names. That is reproducibility, not human validation. The briefing prints the sentiment means as 2.94 and 3.71; the stored means are the four-decimal values above.

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

- Theme precision, recall, F1, accuracy, and the confusion matrix. The reviewer file is blank, so these are N/A. Review completion is 0 reviewed over the assigned sample, which is a real count, not an accuracy.
- Insight acceptance. Accepted and rejected are both 0, so the rate is N/A, not 0% and not 100%. Needs revision and needs more evidence stay in their own counts.
- A sentiment model other than the source score.
- A causal effect of the outage.
- Bookings, saved revenue, or a churn probability. Any win/loss dollar figure in the deck is what an internal call recorded.

The quality composite is about 97%. It scores whether the briefing has themes, consistent labels, and actionable writeups. It does not score whether a reviewer would accept the conclusion.

## Review methodology

Classification is single-label. The published category is the primary governed theme. Other matched themes are shown to the reviewer and are not a second score.

The representative sample uses seed 7 and a target of 30. Every theme that occurs gets one seat first. The other 22 seats use largest remainder on `(count - 1)`, with ties broken by taxonomy order. Inside a theme, the same rule splits seats across support, external, and internal. The draw inside a stratum is `random.Random` seeded by `7|theme|call_type`. Selection probability is seats in that stratum divided by meetings in that stratum. A population estimate, when labels exist, weights each row by the inverse of that probability. If a call type would otherwise be missing, one seat is moved so support, external, and internal all appear.

The challenging sample is the 48 meeting rows already on the review queue. It is biased toward thin margins and zero lexical overlap. Its metrics are unweighted and are not pooled with the representative metrics. Twelve of those meetings are also in the representative sample. One saved decision can sit in both denominators.

Confirmed representative allocation from the current run: reliability 11, compliance 6, identity 3, renewal and churn 3, product 3, billing 2, onboarding 1, delivery 1. Call types in that draw: support 8, external 13, internal 9.

A topic row is human-reviewed only after an explicit decision: approve, correct (with one of the eight themes), or ambiguous. Ambiguous counts in completion and is excluded from correctness. Blank rows are unresolved.

An insight row is accept, reject, needs revision, or needs more evidence. The reviewer id, timestamp, comment, optional corrected recommendation, and optional 1–5 ratings are stored with the row. An edit appends the previous row to `audit` and keeps a new `review_id`. Duplicate ids are collapsed before metrics are counted.

Stored fields: `review_id`, `item_id` (the stable id, not a list position), `predicted_topic`, `human_topic`, `decision`, `reviewer_id`, `reviewer_timestamp`, `notes`, `model_version` (`lexical-nmf-8-seed-7`), `taxonomy_version` (`governed-themes-v1`).

### Metric definitions

| Metric | Numerator | Denominator | Empty case |
| --- | --- | --- | --- |
| Review completion | Explicit topic decisions, including ambiguous | Meetings assigned to that sample | 0/assigned |
| Accuracy, precision, recall, F1 | Adjudicated approve/correct rows only | Those same rows, via sklearn, labels fixed to the eight themes | N/A |
| Macro averages | Themes that have labeled support | That theme count. Undefined precision is skipped, not treated as 0 | N/A |
| Weighted averages | Same rows, weighted by labeled support | Adjudicated rows | N/A |
| Confusion matrix | Counts of (human category, model category) | Adjudicated rows. Unweighted | Empty grid |
| Disagreement | Adjudicated rows where the categories differ | Adjudicated rows | N/A |
| Insight review coverage | Insights with a saved decision | All insights | 0/total |
| Acceptance rate | Accepted | Accepted + rejected | N/A, never 0% or 100% |
| Approval coverage | Accepted | All insights | N/A when nothing is reviewed |
| Evidence quality / usefulness | Sum of 1–5 ratings | Ratings that were actually entered | N/A |

Fewer adjudicated labels than the sample size produces the figures for those rows, a warning, and headline NOT YET AVAILABLE. The numbers are not described as a property of all meetings.

### How a reviewer enters labels

```bash
streamlit run src/review/app.py --server.port 43124 --server.address 0.0.0.0
```

1. Enter a reviewer id in the sidebar. Filters for call type, theme, stakeholder, status, and reviewer are there too.
2. Representative sample: open a transcript. Read the id, call type, supplied topic, model category, model and taxonomy versions, the short excerpt, and the source-transcript expander. Choose confirm, a corrected category, ambiguous, or insufficient evidence. Add a comment. Save.
3. Challenging cases: same form. The banner explains the bias. Do not average this tab with the representative tab.
4. If a second person disagrees, their submission is kept and the row is excluded from accuracy. Check "Adjudicate this conflict" to replace the active label on purpose. The earlier submissions stay in the file.
5. Business insights: read the finding, stakeholder, source meetings, excerpts, passages flagged for a contrast word, and the recommended action. Choose accept, reject, needs revision, or needs more evidence. Save.
6. Findings verification: for each finding, read the automated quote location, then judge supported, partially supported, unsupported, or insufficient evidence. Use a different reviewer id from the person who would accept the business recommendation when you can. The quote check cannot be saved as that judgment.

The dashboard at port 43123 shows the scorecards, the claims table, and the readiness summary. It does not save decisions. The older review section only downloads a browser draft.

### How to regenerate

```bash
python3 -m src.pipeline.runner --data data --output output
python3 -m src.review.validation --report output/report.json --decisions output/review_decisions.json --output output
python3 -m src.review.claims --data data --report output/report.json --output output/claims_audit.json
```

Regeneration rewrites the queue, the sample, and the validation report. It does not overwrite a stored decision. Source meetings are not rewritten.

### Known limitations

- The current metrics are N/A because no person has reviewed the corpus in this file.
- Thirty labeled meetings would measure this sample. They would not measure a future quarter.
- Challenging-case accuracy, once it exists, will look worse than the book and must not be quoted as the book.
- Lexical overlap remains a word-sharing check.
- The quality composite remains a briefing-structure score.
- The older `python -m src.review.evaluate` command does not understand approve / correct / ambiguous. Use `src.review.validation` for the human metrics.

## Review queue

57 items: 27 meetings with no shared tokens, 28 with the top two theme scores within 1 point, and 9 stakeholder insights. Some meetings are in the queue for both classification reasons, so the reason counts add to more than 57. Decisions go in `output/review_decisions.json`. Regenerating the pipeline adds blank rows for new ids, including the representative sample, and does not change a decision or a reason already stored.

```bash
python3 -m src.review.evaluate --report output/report.json --decisions output/review_decisions.json
python3 -m src.review.validation --report output/report.json --decisions output/review_decisions.json --output output
python3 -m src.review.claims --data data --report output/report.json --output output/claims_audit.json
```

## Checklist

| Requirement | Where it lives | State |
| --- | --- | --- |
| Categories with real transcript examples | `report.topic_examples`, dashboard Topics | Done. 15 examples, every id is in the corpus |
| Sentiment charts and interpretation, with n and source | Charts, Sentiment section, `sentiment.provenance` | Done. No new model score |
| At least three stakeholder insights | Support, product, engineering, sales | Done. Nine findings |
| Lexical overlap is not called accuracy | Display name `lexical_topic_overlap`; JSON keeps `topic_agreement` | Done. Zero overlap is `review recommended` |
| Methodology, including why NMF and how BERTopic differs | `report.methodology`, dashboard | Done |
| Review queue and decisions that do not overwrite source data | `output/review_queue.json`, `.csv`, `review_decisions.json` | Done. Decisions are still blank |
| Representative sample and separate challenging sample | `output/review_sample.json` | Done. Seed 7, 30 meetings, not pooled |
| Human review app that saves a decision | `streamlit run src/review/app.py` on port 43124 | Done. No labels have been entered |
| Evaluation that refuses to invent accuracy | `python -m src.review.validation` and the dashboard Evaluation section | Done. Current metrics are N/A |
| Tests for schema, exemplars, provenance, queue, math, conflicts, quotes, claims, and unchanged scores | `tests/` | 33 passed. Synthetic labels stay inside tests |
| Claims audit recomputed from source meetings | `output/claims_audit.json` | Reproduced. Not human-verified |
| Quote location for cited findings | `output/evidence_verification.json` | 27/27 located. Human support still 0/9 |
| Public dashboard redacts contact details in newly shown excerpts | `redact_public_text`, `redactDisplay` | Done |
