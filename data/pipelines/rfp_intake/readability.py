"""Métricas de legibilidad y coste estimado de procesamiento.

Se implementan las fórmulas de Flesch (Reading Ease y Kincaid) y una
estimación de tokens de LLM. Se evaluó ``py-readability-metrics``, pero su
tokenización depende de descargar datos de NLTK en runtime: en Docker/CI eso
introduce red y no determinismo. Esta implementación es equivalente para el
objetivo del hito (anticipar el coste de procesar la RFP) y es determinista.
"""

from __future__ import annotations

import math
import re

_WORD_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9]+")
_SENTENCE_RE = re.compile(r"[.!?…]+|\n{2,}")
_SYLLABLE_RE = re.compile(r"[aeiouáéíóúüAEIOUÁÉÍÓÚÜ]+")
_MARKDOWN_LINK_RE = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_MARKDOWN_DECORATION_RE = re.compile(r"[#>*_`|]+")


def markdown_to_plain_text(markdown: str) -> str:
    text = _MARKDOWN_LINK_RE.sub(r"\1", markdown or "")
    text = _MARKDOWN_DECORATION_RE.sub(" ", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def _words(text: str) -> list[str]:
    return _WORD_RE.findall(text)


def _sentences(text: str) -> list[str]:
    parts = [part.strip() for part in _SENTENCE_RE.split(text)]
    return [part for part in parts if _words(part)]


def count_syllables(word: str) -> int:
    """Aproximación válida para español e inglés (grupos de vocales)."""

    groups = _SYLLABLE_RE.findall(word.lower())
    count = len(groups)
    if count == 0:
        return 1
    if word.lower().endswith("e") and count > 1 and not groups[-1].endswith("e"):
        count -= 1
    return max(1, count)


def _round(value: float) -> float:
    return round(float(value), 2)


def complexity_band(reading_ease: float) -> str:
    if reading_ease >= 60:
        return "baja"
    if reading_ease >= 30:
        return "media"
    return "alta"


def processing_cost_hint(tokens: int) -> str:
    if tokens <= 3_000:
        return "bajo"
    if tokens <= 10_000:
        return "medio"
    return "alto"


def compute_readability(markdown: str) -> dict:
    """Devuelve métricas serializables listas para PostgreSQL (JSONB)."""

    plain = markdown_to_plain_text(markdown)
    words = _words(plain)
    sentences = _sentences(plain)
    word_count = len(words)
    sentence_count = max(1, len(sentences))
    syllable_count = sum(count_syllables(word) for word in words) if words else 0

    words_per_sentence = word_count / sentence_count if word_count else 0.0
    syllables_per_word = syllable_count / word_count if word_count else 0.0

    if word_count:
        reading_ease = (
            206.835
            - 1.015 * words_per_sentence
            - 84.6 * syllables_per_word
        )
        grade = 0.39 * words_per_sentence + 11.8 * syllables_per_word - 15.59
    else:
        reading_ease = 0.0
        grade = 0.0

    char_count = len(plain)
    estimated_tokens = math.ceil(char_count / 4) if char_count else 0
    reading_minutes = _round(word_count / 200) if word_count else 0.0
    headings = len(re.findall(r"^#{1,6}\s+", markdown or "", flags=re.MULTILINE))

    return {
        "word_count": word_count,
        "sentence_count": len(sentences),
        "char_count": char_count,
        "heading_count": headings,
        "avg_words_per_sentence": _round(words_per_sentence),
        "avg_syllables_per_word": _round(syllables_per_word),
        "flesch_reading_ease": _round(reading_ease),
        "flesch_kincaid_grade": _round(grade),
        "estimated_llm_tokens": estimated_tokens,
        "estimated_reading_minutes": reading_minutes,
        "complexity_band": complexity_band(reading_ease),
        "processing_cost_hint": processing_cost_hint(estimated_tokens),
    }
