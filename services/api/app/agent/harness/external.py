"""Aislamiento de contenido externo (RAG y resultados de tools).

Todo texto que no lo ha escrito el sistema se considera **dato no confiable**:

* se eliminan caracteres de control y se acota su longitud;
* las líneas que parecen instrucciones para el modelo se neutralizan;
* se escapan los delimitadores para que el contenido no pueda "cerrar" su
  bloque;
* al construir el prompt se envuelve en ``<untrusted_content>``.

El prompt de sistema declara explícitamente que ese bloque es información, no
instrucciones. La neutralización se registra como evento de seguridad.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .injection import detect_injection
from .observability import GuardrailEvent, metrics

MAX_EXTERNAL_CHARS = 4_000
NEUTRALIZED_MARKER = "[instrucción externa neutralizada]"

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_TAG_RE = re.compile(r"</?\s*(?:untrusted_content|system|assistant)\s*>", re.I)


@dataclass(frozen=True)
class SanitizedText:
    text: str
    neutralized: bool = False
    reasons: tuple[str, ...] = ()


def _clean(text: str) -> str:
    return _CONTROL_RE.sub(" ", text or "")


def _escape_delimiters(text: str) -> str:
    text = re.sub(
        r"<\s*/\s*untrusted_content\s*>",
        "[/untrusted_content]",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"<\s*untrusted_content\b[^>]*>",
        "[untrusted_content]",
        text,
        flags=re.IGNORECASE,
    )
    return _TAG_RE.sub("", text)


def sanitize_external_text(
    text: str | None,
    *,
    source: str,
    max_chars: int = MAX_EXTERNAL_CHARS,
) -> SanitizedText:
    """Sanea un texto externo y neutraliza instrucciones incrustadas."""

    cleaned = _clean(str(text or ""))
    if len(cleaned) > max_chars:
        cleaned = cleaned[: max_chars - 1].rstrip() + "…"

    reasons: list[str] = []
    output_lines: list[str] = []
    for line in cleaned.splitlines():
        match = detect_injection(line)
        if match is not None:
            reasons.append(f"instruction:{match.kind}")
            output_lines.append(NEUTRALIZED_MARKER)
            continue
        # Marcadores de rol sueltos ("SYSTEM:", "### system", "<system>").
        if re.search(
            r"(?:^\s*###\s*(?:system|sistema)|"
            r"^\s*\[\s*system\s*\]|"
            r"^\s*<\s*system\s*>)",
            line,
            re.IGNORECASE,
        ):
            reasons.append("instruction:role_marker")
            output_lines.append(NEUTRALIZED_MARKER)
            continue
        role_marker = re.search(
            r"\b(?:system|assistant|sistema)\s*:", line, re.IGNORECASE
        )
        if role_marker:
            reasons.append("instruction:role_marker")
            line = re.sub(
                r"\b(?:system|assistant|sistema)\s*:",
                NEUTRALIZED_MARKER,
                line,
                flags=re.IGNORECASE,
            )
        output_lines.append(line)

    result = _escape_delimiters("\n".join(output_lines)).strip()
    return SanitizedText(
        text=result,
        neutralized=bool(reasons),
        reasons=tuple(dict.fromkeys(reasons)),
    )


def _sanitize_label(value: object, *, max_chars: int = 160) -> str:
    label = _escape_delimiters(_clean(str(value or "")))[:max_chars]
    return label.strip() or "desconocido"


def _sanitize_item(
    item: dict | None, *, source: str
) -> tuple[dict, tuple[str, ...]]:
    original = dict(item or {})
    sanitized = sanitize_external_text(
        str(original.get("text") or ""),
        source=source,
    )
    result = dict(original)
    result["text"] = sanitized.text
    result["source_document"] = _sanitize_label(
        original.get("source_document") or source
    )
    result["section"] = _sanitize_label(original.get("section") or "")
    return result, sanitized.reasons


def sanitize_external_item(item: dict | None, *, source: str) -> dict:
    """Copia un chunk/resultado y sanea sus campos textuales.

    No añade claves nuevas al diccionario: el contexto RAG conserva su forma
    original para no romper consumidores ni trazas existentes.
    """

    result, _ = _sanitize_item(item, source=source)
    return result


def isolate_context(
    items: list[dict] | None,
    *,
    run_id: str | None = None,
    session_id: str | None = None,
    log: bool = True,
) -> list[dict]:
    """Sanea una lista de chunks RAG y registra si hubo instrucciones."""

    isolated: list[dict] = []
    neutralized_reasons: list[str] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source_document") or "rag")
        sanitized, reasons = _sanitize_item(item, source=source)
        isolated.append(sanitized)
        neutralized_reasons.extend(reasons)

    if log and neutralized_reasons:
        metrics.record(
            GuardrailEvent(
                guard="external_content_guard",
                category="security",
                action="sanitized",
                reason=";".join(dict.fromkeys(neutralized_reasons)),
                run_id=run_id,
                session_id=session_id,
                snippet="contenido RAG con instrucciones neutralizadas",
            )
        )
    return isolated


def format_external_block(item: dict, *, index: int) -> str:
    """Envuelve un chunk saneado en un bloque no confiable."""

    source = _sanitize_label(item.get("source_document") or "externo")
    section = _sanitize_label(item.get("section") or "")
    text = _escape_delimiters(_clean(str(item.get("text") or "")))
    label = f' id="{index}" source="{source}"'
    if section:
        label += f' section="{section}"'
    return f"<untrusted_content{label}>\n{text}\n</untrusted_content>"


def format_external_context(items: list[dict] | None) -> str:
    """Formatea todo el contexto externo como bloques delimitados."""

    blocks: list[str] = []
    for index, item in enumerate(items or [], start=1):
        if not isinstance(item, dict):
            continue
        sanitized = (
            item
            if item.get("untrusted")
            else sanitize_external_item(
                item, source=str(item.get("source_document") or "externo")
            )
        )
        blocks.append(format_external_block(sanitized, index=index))
    return "\n\n".join(blocks) if blocks else "(sin contexto externo)"


def sanitize_tool_text(text: str | None) -> SanitizedText:
    """Atajo para resultados de tools que se añaden al contexto del LLM."""

    return sanitize_external_text(text, source="tool")


__all__ = [
    "MAX_EXTERNAL_CHARS",
    "NEUTRALIZED_MARKER",
    "SanitizedText",
    "format_external_block",
    "format_external_context",
    "isolate_context",
    "sanitize_external_item",
    "sanitize_external_text",
    "sanitize_tool_text",
]
