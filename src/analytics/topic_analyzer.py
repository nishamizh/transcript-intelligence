"""Governed themes, checked against topics generated from the text itself.

The summaries already carry free-text topic labels. Those labels are evidence,
not a taxonomy: hundreds of near-unique strings will not survive contact with
a leadership review. This analyzer does two things and keeps them separate.

1. Map provided labels onto a small governed theme list (the categories we publish).
2. Fit an unsupervised topic model on the summary and transcript only, so the
   provided labels cannot leak into the generated topics, then compare the two.

The generator sits behind TopicModel. The default is TF-IDF + NMF because this
corpus is about 100 documents and the result needs to be deterministic. BERTopic
is the same interface when embedding quality is worth the dependency.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections import Counter, defaultdict
from dataclasses import dataclass

from sklearn.decomposition import NMF
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer

from src.analytics.base import Analyzer
from src.models.meeting import Meeting

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = set(ENGLISH_STOP_WORDS) | {
    "aegis",
    "meeting",
    "meetings",
    "team",
    "customer",
    "customers",
    "call",
    "discussion",
    "discussed",
    "today",
    "just",
    "like",
    "know",
    "think",
    "going",
    "want",
    "need",
    "yeah",
    "okay",
    "thanks",
    "thank",
}


@dataclass(frozen=True, slots=True)
class Theme:
    theme_id: str
    name: str
    description: str
    keywords: tuple[str, ...]


THEMES: tuple[Theme, ...] = (
    Theme(
        "reliability",
        "Reliability and incidents",
        "Outages, pipeline failures, alert quality, and the Detect incident.",
        (
            "outage",
            "incident",
            "reliability",
            "latency",
            "downtime",
            "pipeline",
            "false positive",
            "postmortem",
            "post-mortem",
            "war room",
            "visibility",
            "alert",
            "data gap",
            "technical issue",
            "backup",
            "threat monitoring",
            "sla",
            "escalation",
            "customer communication",
            "siem",
        ),
    ),
    Theme(
        "compliance",
        "Compliance and audit",
        "Framework evidence, HIPAA, PCI DSS, SOC 2, ISO, and audit preparation.",
        (
            "compliance",
            "hipaa",
            "pci",
            "soc 2",
            "soc",
            "iso",
            "audit",
            "regulatory",
            "evidence",
            "framework",
        ),
    ),
    Theme(
        "commercial",
        "Renewal and churn",
        "Renewals, pricing, competitive evaluations, and explicit churn language.",
        (
            "renewal",
            "churn",
            "pricing",
            "contract",
            "competitive",
            "retention",
            "win/loss",
            "vendor comparison",
            "competitor",
        ),
    ),
    Theme(
        "billing",
        "Billing and packaging",
        "Invoices, seat counts, overages, and license disputes.",
        ("billing", "invoice", "overage", "seat", "license", "charge"),
    ),
    Theme(
        "product",
        "Product gaps and roadmap",
        "Feature requests, roadmap commitments, launch risk, and product gaps.",
        ("feature", "roadmap", "feedback", "launch", "workaround", "product bug", "demo", "early access"),
    ),
    Theme(
        "onboarding",
        "Onboarding and adoption",
        "Deployments, kickoffs, module setup, and early adoption.",
        ("onboarding", "deployment", "kickoff", "implementation", "adoption", "setup"),
    ),
    Theme(
        "identity",
        "Identity and access",
        "SSO, SCIM, MFA, LDAP, and access lifecycle.",
        ("identity", "sso", "saml", "scim", "ldap", "mfa", "provisioning", "login", "access control", "iam"),
    ),
    Theme(
        "delivery",
        "Planning and delivery",
        "Sprints, retros, and technical debt inside the building.",
        ("sprint", "retrospective", "technical debt"),
    ),
)

_THEME_BY_ID = {theme.theme_id: theme for theme in THEMES}


@dataclass(slots=True)
class ThemeExample:
    meeting_id: str
    title: str
    call_type: str
    date: str
    sentiment: str
    sentiment_score: float
    account_name: str
    provided_topics: list[str]
    summary: str
    excerpt: str


@dataclass(slots=True)
class GovernedThemeStat:
    theme_id: str
    name: str
    description: str
    meeting_count: int
    by_call_type: dict[str, int]
    mean_sentiment: float
    examples: list[ThemeExample]


@dataclass(slots=True)
class GeneratedTopic:
    topic_id: int
    label: str
    terms: list[str]
    meeting_count: int
    mean_sentiment: float
    examples: list[ThemeExample]


@dataclass(slots=True)
class TopicComparison:
    unique_provided_labels: int
    hapax_labels: int
    hapax_share: float
    governed_coverage: float
    label_mapping_coverage: float
    mean_jaccard: float
    weighted_purity: float
    matrix: list[dict[str, int | str]]
    disagreements: list[ThemeExample]
    commentary: list[str]


@dataclass(slots=True)
class TopicAnalysis:
    model_name: str
    themes: list[GovernedThemeStat]
    generated: list[GeneratedTopic]
    comparison: TopicComparison
    unclassified_count: int


@dataclass(slots=True)
class GeneratedFit:
    model_name: str
    labels: list[int]
    terms: list[list[str]]
    weights: list[float]


class TopicModel(ABC):
    name: str

    @abstractmethod
    def fit(self, documents: list[str]) -> GeneratedFit:
        """Fit on raw text that must not include the provided topic labels."""


class LexicalTopicModel(TopicModel):
    name = "lexical-nmf"

    def __init__(self, n_topics: int = 8, random_state: int = 7, extra_stops: set[str] | None = None):
        self.n_topics = n_topics
        self.random_state = random_state
        self.extra_stops = extra_stops or set()

    def fit(self, documents: list[str]) -> GeneratedFit:
        if len(documents) < 2:
            return GeneratedFit(self.name, [0] * len(documents), [["insufficient corpus"]], [1.0] * len(documents))

        # Speaker names repeat on every turn and will otherwise become the topics.
        stops = _STOP | {token for token in self.extra_stops if len(token) > 2}
        vectorizer = TfidfVectorizer(
            stop_words=sorted(stops),
            ngram_range=(1, 2),
            min_df=2,
            max_df=0.85,
            max_features=4000,
        )
        try:
            matrix = vectorizer.fit_transform(documents)
        except ValueError:
            vectorizer.set_params(min_df=1, max_df=1.0)
            matrix = vectorizer.fit_transform(documents)

        n_topics = max(2, min(self.n_topics, matrix.shape[1], matrix.shape[0] - 1))
        model = NMF(
            n_components=n_topics,
            random_state=self.random_state,
            init="nndsvda",
            max_iter=400,
        )
        weights = model.fit_transform(matrix)
        feature_names = vectorizer.get_feature_names_out()
        terms: list[list[str]] = []
        for component in model.components_:
            order = component.argsort()[::-1]
            chosen: list[str] = []
            for index in order:
                term = str(feature_names[index])
                if term in _STOP or len(term) < 3:
                    continue
                chosen.append(term)
                if len(chosen) == 6:
                    break
            terms.append(chosen or ["untitled"])
        labels = [int(row.argmax()) for row in weights]
        strengths = [float(row.max()) if len(row) else 0.0 for row in weights]
        return GeneratedFit(self.name, labels, terms, strengths)


class BertopicTopicModel(TopicModel):
    """Optional generator. Same output contract as the lexical model."""

    name = "bertopic"

    def __init__(self, n_topics: int = 8):
        self.n_topics = n_topics

    def fit(self, documents: list[str]) -> GeneratedFit:
        try:
            from bertopic import BERTopic
        except ImportError as exc:
            raise RuntimeError(
                "BERTopic is not installed. Install the bertopic extra, "
                "or run with --topic-model lexical."
            ) from exc

        model = BERTopic(nr_topics=self.n_topics, calculate_probabilities=False, verbose=False)
        topic_ids, _ = model.fit_transform(documents)
        grouped: dict[int, list[str]] = {}
        for topic_id in sorted(set(int(value) for value in topic_ids)):
            if topic_id < 0:
                grouped[topic_id] = ["outlier"]
                continue
            pairs = model.get_topic(topic_id) or []
            grouped[topic_id] = [term for term, _weight in pairs[:6]] or ["untitled"]

        # Compact ids to 0..k-1 while remembering the original BERTopic id in the terms.
        ordered = sorted(grouped)
        remap = {original: index for index, original in enumerate(ordered)}
        terms = [grouped[original] for original in ordered]
        labels = [remap[int(value)] for value in topic_ids]
        return GeneratedFit(self.name, labels, terms, [1.0] * len(documents))


def keyword_in(text: str, keyword: str) -> bool:
    variants = [keyword]
    if not keyword.endswith("s"):
        variants.append(f"{keyword}s")
    return any(
        re.search(rf"\b{re.escape(variant)}\b", text, flags=re.IGNORECASE)
        for variant in variants
    )


def theme_scores(meeting: Meeting) -> dict[str, float]:
    """Score governed themes. Provided labels count more than prose mentions."""

    scores = {theme.theme_id: 0.0 for theme in THEMES}
    for topic in meeting.topics:
        for theme in THEMES:
            if any(keyword_in(topic, keyword) for keyword in theme.keywords):
                scores[theme.theme_id] += 2.0
    prose = f"{meeting.title}. {meeting.summary}"
    for theme in THEMES:
        hits = sum(1 for keyword in theme.keywords if keyword_in(prose, keyword))
        scores[theme.theme_id] += hits * 0.5
    return scores


def assign_governed_theme(meeting: Meeting) -> tuple[str, list[str]]:
    scores = theme_scores(meeting)
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    primary, best = ranked[0]
    if best <= 0:
        return "unclassified", []
    matched = [theme_id for theme_id, score in ranked if score >= 2.0]
    if primary not in matched and best >= 1.0:
        matched.insert(0, primary)
    if not matched:
        matched = [primary]
    return primary, matched


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in _TOKEN.findall(text.lower())
        if len(token) > 2 and token not in _STOP
    }


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def _speaker_tokens(meetings: list[Meeting]) -> set[str]:
    tokens: set[str] = set()
    for meeting in meetings:
        for speaker in meeting.speakers:
            for token in re.findall(r"[a-z]+", speaker.lower()):
                if len(token) > 2:
                    tokens.add(token)
    return tokens


def _analysis_document(meeting: Meeting) -> str:
    """Text the topic model is allowed to see.

    Provided topic labels are held out. Speaker names are not part of the
    sentence body, so a formatted transcript (which prefixes every line with
    a name) is not used. Otherwise the model discovers people instead of themes.
    """

    sentences = [turn.sentence.strip() for turn in meeting.turns if turn.sentence.strip()]
    body = " ".join(sentences) if sentences else meeting.transcript
    document = f"{meeting.summary}\n{body}".strip()
    return document or meeting.title


def _example(meeting: Meeting) -> ThemeExample:
    return ThemeExample(
        meeting_id=meeting.meeting_id,
        title=meeting.title,
        call_type=meeting.call_type,
        date=meeting.date_key(),
        sentiment=meeting.sentiment,
        sentiment_score=meeting.sentiment_score,
        account_name=meeting.account_name,
        provided_topics=list(meeting.topics),
        summary=meeting.summary,
        excerpt=meeting.excerpt(4),
    )


class TopicAnalyzer(Analyzer):
    def __init__(self, model: TopicModel | None = None):
        self.model = model or LexicalTopicModel()

    def analyze(self, meetings: list[Meeting]) -> TopicAnalysis:
        if isinstance(self.model, LexicalTopicModel):
            self.model.extra_stops = _speaker_tokens(meetings)
        documents = [_analysis_document(meeting) for meeting in meetings]
        fit = self.model.fit(documents) if meetings else GeneratedFit(self.model.name, [], [], [])
        self._annotate(meetings, fit)
        return TopicAnalysis(
            model_name=fit.model_name,
            themes=self._theme_stats(meetings),
            generated=self._generated_stats(meetings, fit),
            comparison=self._compare(meetings),
            unclassified_count=sum(1 for meeting in meetings if meeting.primary_theme == "unclassified"),
        )

    def _annotate(self, meetings: list[Meeting], fit: GeneratedFit) -> None:
        labels_for_id: dict[int, str] = {}
        for index, terms in enumerate(fit.terms):
            label = " · ".join(terms[:3]) if terms else f"topic {index}"
            labels_for_id[index] = label

        for meeting, topic_id, weight in zip(meetings, fit.labels, fit.weights, strict=True):
            primary, matched = assign_governed_theme(meeting)
            terms = fit.terms[topic_id] if fit.terms else []
            meeting.primary_theme = primary
            meeting.governed_themes = matched
            meeting.generated_topic = labels_for_id.get(topic_id, "unclassified")
            meeting.generated_terms = list(terms)
            meeting.topic_agreement = _jaccard(_tokens(" ".join(meeting.topics)), _tokens(" ".join(terms)))
            del weight

    def _theme_stats(self, meetings: list[Meeting]) -> list[GovernedThemeStat]:
        grouped: dict[str, list[Meeting]] = defaultdict(list)
        for meeting in meetings:
            if meeting.primary_theme and meeting.primary_theme != "unclassified":
                grouped[meeting.primary_theme].append(meeting)

        stats: list[GovernedThemeStat] = []
        for theme in THEMES:
            rows = grouped.get(theme.theme_id, [])
            by_type = dict(Counter(row.call_type for row in rows))
            mean = _mean([row.sentiment_score for row in rows])
            examples = [_example(row) for row in _pick_examples(rows, 3)]
            stats.append(
                GovernedThemeStat(
                    theme_id=theme.theme_id,
                    name=theme.name,
                    description=theme.description,
                    meeting_count=len(rows),
                    by_call_type=by_type,
                    mean_sentiment=mean,
                    examples=examples,
                )
            )
        return stats

    def _generated_stats(self, meetings: list[Meeting], fit: GeneratedFit) -> list[GeneratedTopic]:
        grouped: dict[int, list[Meeting]] = defaultdict(list)
        for meeting, topic_id in zip(meetings, fit.labels, strict=True):
            grouped[topic_id].append(meeting)

        generated: list[GeneratedTopic] = []
        for topic_id, terms in enumerate(fit.terms):
            rows = grouped.get(topic_id, [])
            generated.append(
                GeneratedTopic(
                    topic_id=topic_id,
                    label=" · ".join(terms[:3]) if terms else f"topic {topic_id}",
                    terms=list(terms),
                    meeting_count=len(rows),
                    mean_sentiment=_mean([row.sentiment_score for row in rows]),
                    examples=[_example(row) for row in _pick_examples(rows, 2)],
                )
            )
        generated.sort(key=lambda topic: topic.meeting_count, reverse=True)
        return generated

    def _compare(self, meetings: list[Meeting]) -> TopicComparison:
        label_counts = Counter(topic.strip().lower() for meeting in meetings for topic in meeting.topics)
        unique = len(label_counts)
        hapax = sum(1 for count in label_counts.values() if count == 1)
        mapped_labels = 0
        for label in label_counts:
            if any(any(keyword_in(label, keyword) for keyword in theme.keywords) for theme in THEMES):
                mapped_labels += 1

        agreements = [meeting.topic_agreement for meeting in meetings]
        classified = [meeting for meeting in meetings if meeting.primary_theme != "unclassified"]
        coverage = len(classified) / len(meetings) if meetings else 0.0

        matrix_counts: dict[tuple[str, str], int] = Counter()
        purity_weight = 0.0
        purity_mass = 0
        for theme in THEMES:
            rows = [meeting for meeting in classified if meeting.primary_theme == theme.theme_id]
            if not rows:
                continue
            topic_counts = Counter(meeting.generated_topic for meeting in rows)
            top_count = max(topic_counts.values())
            purity_weight += top_count
            purity_mass += len(rows)
            for label, count in topic_counts.items():
                matrix_counts[(theme.theme_id, label)] = count

        disagreements = [
            meeting
            for meeting in classified
            if meeting.topic_agreement == 0 and meeting.generated_terms
        ]
        disagreements.sort(key=lambda meeting: meeting.sentiment_score)
        hapax_share = hapax / unique if unique else 0.0
        mean_jaccard = _mean(agreements)
        purity = purity_weight / purity_mass if purity_mass else 0.0
        commentary = _commentary(
            meetings=len(meetings),
            unique=unique,
            hapax_share=hapax_share,
            coverage=coverage,
            label_coverage=mapped_labels / unique if unique else 0.0,
            mean_jaccard=mean_jaccard,
            purity=purity,
            model_name=self.model.name,
        )
        return TopicComparison(
            unique_provided_labels=unique,
            hapax_labels=hapax,
            hapax_share=hapax_share,
            governed_coverage=coverage,
            label_mapping_coverage=mapped_labels / unique if unique else 0.0,
            mean_jaccard=mean_jaccard,
            weighted_purity=purity,
            matrix=[
                {"theme_id": theme_id, "generated_topic": label, "count": count}
                for (theme_id, label), count in sorted(matrix_counts.items(), key=lambda item: -item[1])
            ],
            disagreements=[_example(meeting) for meeting in disagreements[:6]],
            commentary=commentary,
        )


def _pick_examples(meetings: list[Meeting], limit: int) -> list[Meeting]:
    """Prefer a mix of call types, then the sharpest sentiment, so examples are not clones."""

    chosen: list[Meeting] = []
    seen_types: set[str] = set()
    ordered = sorted(meetings, key=lambda meeting: abs(meeting.sentiment_score - 3.0), reverse=True)
    for meeting in ordered:
        if meeting.call_type in seen_types:
            continue
        chosen.append(meeting)
        seen_types.add(meeting.call_type)
        if len(chosen) == limit:
            return chosen
    for meeting in ordered:
        if meeting in chosen:
            continue
        chosen.append(meeting)
        if len(chosen) == limit:
            break
    return chosen


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _commentary(
    meetings: int,
    unique: int,
    hapax_share: float,
    coverage: float,
    label_coverage: float,
    mean_jaccard: float,
    purity: float,
    model_name: str,
) -> list[str]:
    return [
        (
            f"The source file ships {unique} distinct topic labels across {meetings} meetings. "
            f"{hapax_share:.0%} of those labels appear once. A label that appears once cannot be a category."
        ),
        (
            f"The governed taxonomy covers {coverage:.0%} of meetings and maps {label_coverage:.0%} of the "
            "raw labels. What it does not map stays visible as unclassified instead of being forced into a bucket."
        ),
        (
            f"Topics generated by {model_name} were fit on summaries and transcripts only, "
            "with the provided labels held out. Mean token overlap with the provided labels is "
            f"{mean_jaccard:.0%}, and the average governed theme lands in one generated topic "
            f"{purity:.0%} of the time. High purity means the taxonomy tracks the text. "
            "Low overlap means the raw labels and the text are using different words for the same meeting, "
            "which is exactly the review queue."
        ),
        (
            "Publish the governed themes. Keep the raw labels as evidence under each theme. "
            "Review zero-overlap meetings before anyone treats a generated topic name as a product category. "
            "That is the governance loop: a stable taxonomy, an independent model, and a human on the disagreements."
        ),
    ]


def build_topic_model(name: str, n_topics: int, random_state: int) -> TopicModel:
    if name == "bertopic":
        return BertopicTopicModel(n_topics=n_topics)
    if name != "lexical":
        raise ValueError(f"Unknown topic model '{name}'. Use lexical or bertopic.")
    return LexicalTopicModel(n_topics=n_topics, random_state=random_state)
