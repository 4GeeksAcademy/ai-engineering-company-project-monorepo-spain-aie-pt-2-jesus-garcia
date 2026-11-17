"""Evaluador de legibilidad.

Combina métricas deterministas (Flesch en español, longitud de frase y de
párrafo) con ``py-readability-metrics`` cuando la librería y los datos de NLTK
están disponibles. La decisión pass/fail usa siempre la fórmula local
determinista; la librería se reporta en ``details`` como verificación
adicional y para no depender de descargas de NLTK en CI/Docker.
"""

from __future__ import annotations

import re
from typing import Final

from data.pipelines.rfp_intake.readability import (
    compute_readability,
    count_syllables,
    markdown_to_plain_text,
)

MIN_WORDS: Final[int] = 60
MIN_FLESCH_READING_EASE: Final[float] = 50.0
MAX_AVG_WORDS_PER_SENTENCE: Final[float] = 28.0
MAX_PARAGRAPH_WORDS: Final[int] = 120

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+|\n+")
_TABLE_LINE = re.compile(r"^\s*\|.*\|\s*$")


def _prose_markdown(markdown: str) -> str:
    """Quita tablas: la legibilidad evalúa prosa, no filas de datos."""

    return "\n".join(
        line
        for line in (markdown or "").splitlines()
        if not _TABLE_LINE.match(line)
    )


def _sentences(plain: str) -> list[str]:
    return [
        sentence.strip()
        for sentence in _SENTENCE_SPLIT.split(plain or "")
        if sentence.strip()
    ]


def _paragraphs(markdown: str) -> list[str]:
    """Cada línea renderizada es una unidad: viñetas y prosa, sin tablas."""

    paragraphs = [
        markdown_to_plain_text(line)
        for line in (markdown or "").splitlines()
        if line.strip()
    ]
    return [paragraph for paragraph in paragraphs if paragraph]


def third_party_flesch(plain: str, word_count: int) -> dict | None:
    """Flesch Reading Ease con py-readability-metrics, si es posible."""

    if word_count < 100:
        return None
    try:  # pragma: no cover - depende de datos de NLTK en el entorno
        from readability import Readability

        return {"flesch": round(float(Readability(plain).flesch().score), 2)}
    except Exception as exc:  # pragma: no cover - fallback silencioso
        return {"error": f"{type(exc).__name__}: {exc}"[:200]}


def spanish_flesch(plain: str, word_count: int, sentence_count: int) -> float:
    """Flesch-Fernández-Huerta, adaptado a español.

    La fórmula inglesa (206.835 - 1.015·P - 84.6·F) penaliza el español por su
    longitud silábica y da puntuaciones artificialmente bajas. Se usa la
    variante española sobre las mismas métricas deterministas.
    """

    words = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9]+", plain or "")
    if word_count <= 0 or not words:
        return 0.0
    syllables = sum(count_syllables(word) for word in words)
    syllables_per_100 = 100 * syllables / word_count
    words_per_sentence = word_count / max(1, sentence_count)
    return 206.84 - 0.60 * syllables_per_100 - 1.02 * words_per_sentence


def evaluate_readability(draft: dict) -> dict:
    markdown = draft.get("body_markdown") or ""
    prose = _prose_markdown(markdown)
    plain = markdown_to_plain_text(prose)
    metrics = compute_readability(prose)

    word_count = int(metrics.get("word_count") or 0)
    flesch = float(metrics.get("flesch_reading_ease") or 0.0)
    avg_sentence = float(metrics.get("avg_words_per_sentence") or 0.0)

    paragraphs = _paragraphs(prose)
    longest_paragraph = max(
        (len(paragraph.split()) for paragraph in paragraphs), default=0
    )

    sentences = sorted(
        _sentences(plain), key=lambda sentence: len(sentence.split()), reverse=True
    )
    longest_sentences = [
        sentence
        for sentence in sentences
        if len(sentence.split()) > MAX_AVG_WORDS_PER_SENTENCE
    ][:3]

    sentence_count = max(1, len(_sentences(plain)))
    score = spanish_flesch(plain, word_count, sentence_count)

    failures: list[str] = []
    if word_count < MIN_WORDS:
        failures.append(
            f"la sección tiene {word_count} palabras (mínimo {MIN_WORDS})"
        )
    if score < MIN_FLESCH_READING_EASE:
        failures.append(
            f"legibilidad Fernández-Huerta {score:.1f} < "
            f"{MIN_FLESCH_READING_EASE:g}"
        )
    if avg_sentence > MAX_AVG_WORDS_PER_SENTENCE:
        failures.append(
            f"media de {avg_sentence:.1f} palabras por frase "
            f"(máximo {MAX_AVG_WORDS_PER_SENTENCE:g})"
        )
    if longest_paragraph > MAX_PARAGRAPH_WORDS:
        failures.append(
            f"párrafo de {longest_paragraph} palabras "
            f"(máximo {MAX_PARAGRAPH_WORDS})"
        )

    details = {
        "engine": "local-fernandez-huerta",
        "word_count": word_count,
        "sentence_count": sentence_count,
        "spanish_flesch_score": round(score, 2),
        "flesch_reading_ease_english": flesch,
        "flesch_kincaid_grade": metrics.get("flesch_kincaid_grade"),
        "avg_words_per_sentence": avg_sentence,
        "longest_paragraph_words": longest_paragraph,
        "longest_sentences": longest_sentences,
        "failures": failures,
        "thresholds": {
            "min_words": MIN_WORDS,
            "min_flesch_reading_ease": MIN_FLESCH_READING_EASE,
            "max_avg_words_per_sentence": MAX_AVG_WORDS_PER_SENTENCE,
            "max_paragraph_words": MAX_PARAGRAPH_WORDS,
        },
        "py_readability_metrics": third_party_flesch(plain, word_count),
    }

    return {
        "pass": not failures,
        "score": round(score, 2),
        "details": details,
    }
