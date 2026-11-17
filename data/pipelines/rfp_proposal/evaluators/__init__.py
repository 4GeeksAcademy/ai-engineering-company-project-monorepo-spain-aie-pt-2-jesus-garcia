"""Evaluadores de sección: legibilidad, pertinencia y cumplimiento."""

from __future__ import annotations

from .compliance import evaluate_compliance
from .readability import evaluate_readability
from .relevance import evaluate_relevance
from .result import (
    aggregate_evaluation,
    evaluate_section,
    feedback_for_generator,
)

__all__ = [
    "aggregate_evaluation",
    "evaluate_compliance",
    "evaluate_readability",
    "evaluate_relevance",
    "evaluate_section",
    "feedback_for_generator",
]
