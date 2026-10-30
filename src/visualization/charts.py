"""Static charts for the repo and the walkthrough. The dashboard reads the same numbers."""

from __future__ import annotations

from pathlib import Path

import math

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.analytics.sentiment_analyzer import SentimentAnalysis
from src.analytics.topic_analyzer import TopicAnalysis

_INK = "#1c1915"
_MUTED = "#6b645c"
_PAPER = "#f4efe6"
_SUPPORT = "#9a3412"
_EXTERNAL = "#1e4d6b"
_INTERNAL = "#3d5a45"
_ACCENT = "#8c4a2f"
_CALL_COLORS = {"support": _SUPPORT, "external": _EXTERNAL, "internal": _INTERNAL}


def render_charts(
    sentiment: SentimentAnalysis,
    topics: TopicAnalysis,
    output_dir: Path,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = [
        _sentiment_by_call_type(sentiment, output_dir / "sentiment_by_call_type.png"),
        _sentiment_trend(sentiment, output_dir / "sentiment_trend.png"),
        _theme_mix(topics, output_dir / "theme_mix.png"),
        _topic_purity(topics, output_dir / "topic_agreement.png"),
    ]
    return paths


def _style(ax, title: str, subtitle: str) -> None:
    ax.set_facecolor(_PAPER)
    ax.figure.set_facecolor(_PAPER)
    ax.set_title(title, loc="left", color=_INK, fontsize=14, pad=16)
    ax.text(0.0, 1.02, subtitle, transform=ax.transAxes, color=_MUTED, fontsize=9, va="bottom")
    ax.tick_params(colors=_INK, labelsize=9)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color("#d9d1c5")
    ax.grid(axis="y", color="#e6dfd4", linewidth=0.8)
    ax.set_axisbelow(True)


def _sentiment_by_call_type(sentiment: SentimentAnalysis, path: Path) -> Path:
    rows = sentiment.by_call_type
    labels = [row.call_type for row in rows]
    values = [row.mean_score for row in rows]
    figure, axis = plt.subplots(figsize=(8.2, 4.6))
    colors = [_CALL_COLORS.get(label, _ACCENT) for label in labels]
    bars = axis.bar(labels, values, color=colors, width=0.62)
    axis.set_ylim(1, 5)
    axis.axhline(sentiment.overall_mean, color=_ACCENT, linestyle="--", linewidth=1)
    axis.set_ylabel("Mean sentiment score", color=_INK)
    for bar, row in zip(bars, rows, strict=True):
        axis.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.08,
            f"{row.mean_score:.2f}\n{row.count} calls",
            ha="center",
            va="bottom",
            color=_INK,
            fontsize=9,
        )
    _style(axis, "Sentiment by call type", "Dashed line is the corpus mean. Scale is 1–5.")
    figure.tight_layout()
    figure.savefig(path, dpi=140)
    plt.close(figure)
    return path


def _sentiment_trend(sentiment: SentimentAnalysis, path: Path) -> Path:
    weeks = [row for row in sentiment.by_week if row.count]
    figure, axis = plt.subplots(figsize=(8.6, 4.6))
    axis.plot(
        [row.period for row in weeks],
        [row.mean_score for row in weeks],
        color=_INK,
        marker="o",
        linewidth=1.8,
        label="All calls",
    )
    for call_type, color in _CALL_COLORS.items():
        series = [
            row.by_call_type.get(call_type)
            if row.by_call_type.get(call_type) is not None
            else math.nan
            for row in weeks
        ]
        axis.plot(
            [row.period for row in weeks],
            series,
            color=color,
            linewidth=1.2,
            alpha=0.9,
            label=call_type,
        )
    axis.set_ylim(1, 5)
    axis.tick_params(axis="x", rotation=40)
    axis.legend(frameon=False, fontsize=8, loc="lower left")
    axis.set_ylabel("Mean sentiment score", color=_INK)
    _style(axis, "Weekly sentiment", "Missing points are weeks with no calls of that type.")
    figure.tight_layout()
    figure.savefig(path, dpi=140)
    plt.close(figure)
    return path


def _theme_mix(topics: TopicAnalysis, path: Path) -> Path:
    rows = [theme for theme in topics.themes if theme.meeting_count]
    rows.sort(key=lambda theme: theme.meeting_count)
    figure, axis = plt.subplots(figsize=(8.4, 4.8))
    axis.barh(
        [theme.name for theme in rows],
        [theme.meeting_count for theme in rows],
        color=_ACCENT,
    )
    axis.set_xlabel("Meetings (primary theme)", color=_INK)
    _style(axis, "Governed themes", "A meeting can match several themes. This chart uses the primary one.")
    figure.tight_layout()
    figure.savefig(path, dpi=140)
    plt.close(figure)
    return path


def _topic_purity(topics: TopicAnalysis, path: Path) -> Path:
    comparison = topics.comparison
    figure, axis = plt.subplots(figsize=(8.2, 4.4))
    labels = ["Theme coverage", "Label mapping", "Generated purity", "Token overlap"]
    values = [
        comparison.governed_coverage,
        comparison.label_mapping_coverage,
        comparison.weighted_purity,
        comparison.mean_jaccard,
    ]
    axis.bar(labels, [value * 100 for value in values], color=[_INTERNAL, _EXTERNAL, _ACCENT, _SUPPORT])
    axis.set_ylim(0, 100)
    axis.set_ylabel("Percent", color=_INK)
    _style(
        axis,
        "Provided labels versus generated topics",
        f"Model: {topics.model_name}. Overlap is intentionally not the thing we maximize.",
    )
    figure.tight_layout()
    figure.savefig(path, dpi=140)
    plt.close(figure)
    return path
