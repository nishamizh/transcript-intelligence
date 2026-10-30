"""Runtime settings. New behavior should land here before it lands in an analyzer."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path = Path("data")
    output_dir: Path = Path("output")
    web_data_path: Path = Path("web/src/data/report.json")
    internal_domain: str = "aegiscloud.com"
    topic_model: str = "lexical"
    n_topics: int = 8
    random_state: int = 7
    # Seeded from the corpus. Counting is automatic; adding a name is a config change.
    competitors: tuple[str, ...] = ("SentinelShield", "VaultEdge", "CyberNova")

    @staticmethod
    def from_args(argv: list[str] | None = None) -> Settings:
        parser = argparse.ArgumentParser(
            description="Run the Transcript Intelligence pipeline."
        )
        parser.add_argument("--data", type=Path, default=Path("data"))
        parser.add_argument("--output", type=Path, default=Path("output"))
        parser.add_argument(
            "--web-data",
            type=Path,
            default=Path("web/src/data/report.json"),
            help="Where to copy report.json for the executive dashboard.",
        )
        parser.add_argument(
            "--topic-model",
            choices=("lexical", "bertopic"),
            default="lexical",
            help="lexical is the deterministic default. bertopic uses the same contract.",
        )
        parser.add_argument("--topics", type=int, default=8)
        args = parser.parse_args(argv)
        return Settings(
            data_dir=args.data,
            output_dir=args.output,
            web_data_path=args.web_data,
            topic_model=args.topic_model,
            n_topics=args.topics,
        )
