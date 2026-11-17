"""Tests de las métricas deterministas de legibilidad."""

from __future__ import annotations

from data.pipelines.rfp_intake.readability import (
    compute_readability,
    count_syllables,
    markdown_to_plain_text,
)


def test_readability_returns_cost_and_complexity_metrics():
    metrics = compute_readability(
        "# RFP\n\nModaViva busca almacenamiento y devoluciones. "
        "El volumen es de 5.000 pedidos al mes. La fecha límite es el 28 de agosto."
    )
    assert metrics["word_count"] > 10
    assert metrics["sentence_count"] >= 2
    assert metrics["estimated_llm_tokens"] > 0
    assert metrics["complexity_band"] in {"baja", "media", "alta"}
    assert metrics["processing_cost_hint"] in {"bajo", "medio", "alto"}
    assert isinstance(metrics["flesch_reading_ease"], float)
    assert isinstance(metrics["flesch_kincaid_grade"], float)


def test_empty_markdown_produces_zero_metrics_without_dividing_by_zero():
    metrics = compute_readability("")
    assert metrics["word_count"] == 0
    assert metrics["estimated_llm_tokens"] == 0
    assert metrics["avg_words_per_sentence"] == 0.0


def test_markdown_decoration_is_removed():
    assert markdown_to_plain_text("## Hola **mundo** [link](http://x)") == "Hola mundo link"


def test_syllable_counter_handles_spanish_and_acronyms():
    assert count_syllables("logística") >= 3
    assert count_syllables("3PL") == 1
