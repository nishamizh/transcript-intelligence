"""Corpus-level analytics share one contract so a new engine is a new class."""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.models.meeting import Meeting


class Analyzer(ABC):
    @abstractmethod
    def analyze(self, meetings: list[Meeting]):
        """Read meetings and return a structured result. Do not reload source files."""
