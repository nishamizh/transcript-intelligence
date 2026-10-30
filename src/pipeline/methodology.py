"""How the briefing was produced. Figures come from the run, not from a fixed story."""

from __future__ import annotations

from src.analytics.sentiment_analyzer import SentimentAnalysis
from src.analytics.topic_analyzer import LEXICAL_OVERLAP_NOTE, TopicAnalysis
from src.config.settings import Settings


def build_methodology(
    topics: TopicAnalysis,
    sentiment: SentimentAnalysis,
    settings: Settings,
) -> dict:
    comparison = topics.comparison
    return {
        "approach": "hybrid",
        "label_inventory": {
            "distinct_labels": comparison.unique_provided_labels,
            "hapax_labels": comparison.hapax_labels,
            "hapax_share": round(comparison.hapax_share, 4),
            "note": (
                "Each meeting summary ships free-text topic labels. "
                "Those strings are evidence. A label that appears once is not a category."
            ),
        },
        "governed_mapping": (
            "The published categories are a fixed theme list. A provided label that contains a theme "
            "keyword adds 2 to that theme. A keyword in the title or summary adds 0.5. "
            "The highest score is the primary theme. Labels that match nothing do not invent a theme. "
            "Meetings with no positive score stay unclassified."
        ),
        "held_out_discovery": (
            f"A second pass fits {topics.model_name} on the summary plus transcript sentences. "
            "Provided topic labels are not in that text. Speaker-name tokens are stopped so the model "
            "does not cluster people. "
            f"The lexical default uses TF-IDF (unigrams and bigrams) and NMF with "
            f"{settings.n_topics} components and random_state {settings.random_state}."
        ),
        "why_this_corpus": (
            "The corpus is about 100 meetings. TF-IDF + NMF with a fixed seed is deterministic, "
            "has no extra model download, and can be refit in the same pipeline that writes the briefing. "
            "Embedding models move around on a corpus this small, so they are not the default audit."
        ),
        "bertopic": (
            "BERTopic implements the same TopicModel contract and is selected with --topic-model bertopic. "
            "It clusters embedding neighborhoods and can mark outliers. It is optional because this corpus "
            "is small, the dependency is heavy, and the briefing needs a repeatable audit rather than a "
            "second taxonomy. It does not replace the governed themes."
        ),
        "lexical_overlap": LEXICAL_OVERLAP_NOTE,
        "sentiment": sentiment.provenance.meeting_score_source,
        "not_measured": [
            "Classification accuracy, until a person saves adjudicated rows in review_decisions.json. The pipeline does not fill those rows, and a blank file stays not yet available.",
            "A new sentiment model. Meeting scores are the source 1–5 values, unchanged.",
            "Causal effect of the March outage on support sentiment. The time cut is descriptive.",
            "Revenue, bookings, or a churn forecast. The win/loss figure, when cited, is what an internal call recorded.",
            "Whether a stakeholder accepts an insight, until that person records accept or reject. Needs revision and needs more evidence are not acceptance. The quality composite scores briefing structure only.",
        ],
    }
