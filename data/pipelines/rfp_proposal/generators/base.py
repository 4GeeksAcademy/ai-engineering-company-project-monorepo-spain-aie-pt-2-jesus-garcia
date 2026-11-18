"""Base común de los generadores de sección.

Cada departamento tiene su propio agente (``warehouse.py``, ``lastmile.py``,
``reverse.py``): prompts y formato distintos. Esta base solo aporta el
plumbing compartido: llamada al LLM, guardarraíl numérico, combinación de la
prosa del modelo con los datos deterministas de tarifa/política y renderizado.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Final

from data.pipelines.rfp_intake.llm import JsonLlm, LlmError
from data.pipelines.rfp_intake.worker import numeric_tokens

from ..contract import brief_numbers
from ..policy import (
    RETURNS_MIN_HOURS,
    SLA_COMPENSATION_PCT,
    SLA_ON_TIME_PCT,
    discount_tier_rows,
    policy_numbers,
)
from ..rate_card import rate_card_numbers
from ..render import render_section

logger = logging.getLogger(__name__)

MARKER: Final[str] = "generador de la sección de propuesta"
MAX_BRIEF_CHARS: Final[int] = 9_000
_MAX_ITEMS: Final[int] = 8

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


class GeneratorError(RuntimeError):
    """El generador no pudo producir un borrador utilizable."""


def _clean_strings(value: object, *, limit: int = _MAX_ITEMS) -> list[str]:
    if not isinstance(value, list):
        return []
    return [
        item.strip()
        for item in value
        if isinstance(item, str) and item.strip()
    ][:limit]


def _clean_offerings(value: object) -> list[dict]:
    if not isinstance(value, list):
        return []
    offerings: list[dict] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            offerings.append({"name": item.strip()[:120], "detail": ""})
        elif isinstance(item, dict):
            name = item.get("name") or item.get("nombre")
            detail = item.get("detail") or item.get("detalle") or ""
            if isinstance(name, str) and name.strip():
                offerings.append(
                    {
                        "name": name.strip()[:120],
                        "detail": str(detail).strip()[:600],
                    }
                )
    return offerings[:_MAX_ITEMS]


def _match_aspects(value: object, key_aspects: list[dict]) -> list[str]:
    """Mapea lo que el LLM dice cubrir con los nombres canónicos del handoff."""

    known = {aspect["aspect"] for aspect in key_aspects}
    if not isinstance(value, list):
        return []
    matched: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        candidate = item.strip()
        if candidate in known and candidate not in matched:
            matched.append(candidate)
            continue
        normalized = candidate.casefold()
        for aspect in known:
            if aspect.casefold() == normalized and aspect not in matched:
                matched.append(aspect)
                break
    return matched


class DepartmentGenerator:
    """Interfaz que implementa cada departamento."""

    department_id: str = ""
    label: str = ""
    responsible: str = ""
    service_label: str = ""
    prompt_guidance: str = ""

    # --- piezas específicas del departamento (implementadas por cada uno) ---

    def department_fields(self, brief: dict) -> dict:
        """Bloques propios: capacity/onboarding/carriers/process/turnaround."""

        raise NotImplementedError

    def pricing_rows(self, brief: dict) -> list[dict]:
        raise NotImplementedError

    def sla(self, brief: dict) -> dict:
        raise NotImplementedError

    # --- generación -------------------------------------------------------

    def system_prompt(self) -> str:
        return f"""Eres el {MARKER} económica de {self.label} de TrackFlow. Tu responsable es {self.responsible}.

{self.prompt_guidance}

Reglas obligatorias:
1. Escribe en español y en tercera persona, con lenguaje comercial sobrio.
2. Usa SOLO los datos del payload. No inventes cifras, volúmenes, capacidades,
   tarifas, plazos ni condiciones. Lo que no conste se declara pendiente.
3. La moneda y el país del payload son canónicos: no los cambies.
4. Debes cubrir TODOS los `key_aspects` y conservar las `open_questions` del handoff.
5. No prometas devoluciones en menos de {RETURNS_MIN_HOURS} horas ni reveles
   tarifas negociadas con transportistas.
6. Devuelve EXCLUSIVAMENTE este objeto JSON (sin texto adicional):
{{
  "executive_summary": "2-4 frases de resumen ejecutivo de la sección",
  "offerings": [{{"name": "nombre del servicio", "detail": "qué incluye"}}],
  "assumptions": ["supuesto operativo trazable a la RFP o a la tarifa publicada"],
  "additional_open_questions": ["pregunta nueva para el cliente o el responsable"],
  "addresses_aspects": ["nombre exacto de cada key_aspect cubierto"]
}}"""

    def _messages(
        self,
        brief: dict,
        *,
        previous_draft: dict | None,
        feedback: str | None,
    ) -> list[dict]:
        payload = {
            "departamento": {
                "department_id": self.department_id,
                "label": self.label,
                "responsable": self.responsible,
            },
            "cliente": brief.get("client"),
            "pais": brief.get("client_country"),
            "moneda": brief.get("currency"),
            "datos_rfp": brief.get("facts"),
            "foco_orquestador": brief.get("focus"),
            "key_aspects": [
                {
                    "aspect": aspect["aspect"],
                    "detail": aspect["detail"],
                    "evidence": aspect.get("evidence"),
                }
                for aspect in brief.get("key_aspects", [])
            ],
            "open_questions_heredadas": brief.get("open_questions", []),
            "preguntas_ventas": [
                question.get("question")
                for question in brief.get("questions_to_ask", [])
                if question.get("department_id") == self.department_id
            ],
        }
        user = json.dumps(payload, ensure_ascii=False, indent=2)[:MAX_BRIEF_CHARS]
        if previous_draft is not None:
            user += (
                "\n\n--- BORRADOR ANTERIOR (rechazado) ---\n"
                + json.dumps(
                    {
                        "executive_summary": previous_draft.get("executive_summary"),
                        "offerings": previous_draft.get("offerings"),
                        "assumptions": previous_draft.get("assumptions"),
                    },
                    ensure_ascii=False,
                )[:4_000]
            )
        if feedback:
            user += (
                "\n\n--- FEEDBACK DEL EVALUADOR (corrige esto exactamente) ---\n"
                + feedback[:4_000]
            )
        return [
            {"role": "system", "content": self.system_prompt()},
            {"role": "user", "content": user},
        ]

    def _allowed_numbers(self, brief: dict, deterministic: dict) -> set[str]:
        allowed = brief_numbers(brief)
        allowed |= rate_card_numbers()
        allowed |= policy_numbers()
        allowed |= numeric_tokens(json.dumps(deterministic, ensure_ascii=False))
        return allowed

    def _guard_prose(
        self,
        prose: dict,
        allowed: set[str],
    ) -> tuple[dict, list[dict]]:
        """Elimina frases/ítems con cifras no soportadas por las fuentes."""

        unsupported: list[dict] = []

        summary_sentences = _SENTENCE_SPLIT.split(prose.get("executive_summary") or "")
        kept_sentences: list[str] = []
        for sentence in summary_sentences:
            invented = sorted(numeric_tokens(sentence) - allowed)
            if invented:
                unsupported.append(
                    {"field": "executive_summary", "text": sentence, "numbers": invented}
                )
            elif sentence.strip():
                kept_sentences.append(sentence.strip())
        prose["executive_summary"] = " ".join(kept_sentences).strip()

        kept_offerings: list[dict] = []
        for offering in prose.get("offerings") or []:
            text = f"{offering.get('name', '')} {offering.get('detail', '')}"
            invented = sorted(numeric_tokens(text) - allowed)
            if invented:
                unsupported.append(
                    {"field": "offerings", "text": text.strip(), "numbers": invented}
                )
            else:
                kept_offerings.append(offering)
        prose["offerings"] = kept_offerings

        kept_assumptions: list[str] = []
        for assumption in prose.get("assumptions") or []:
            invented = sorted(numeric_tokens(assumption) - allowed)
            if invented:
                unsupported.append(
                    {"field": "assumptions", "text": assumption, "numbers": invented}
                )
            else:
                kept_assumptions.append(assumption)
        prose["assumptions"] = kept_assumptions

        prose["additional_open_questions"] = [
            question
            for question in prose.get("additional_open_questions") or []
            if not (numeric_tokens(question) - allowed)
        ]
        return prose, unsupported

    def _normalize_prose(self, payload: object) -> dict:
        if not isinstance(payload, dict):
            return {
                "executive_summary": "",
                "offerings": [],
                "assumptions": [],
                "additional_open_questions": [],
                "addresses_aspects": [],
            }
        return {
            "executive_summary": str(payload.get("executive_summary") or "").strip()[:2_000],
            "offerings": _clean_offerings(payload.get("offerings")),
            "assumptions": _clean_strings(payload.get("assumptions")),
            "additional_open_questions": _clean_strings(
                payload.get("additional_open_questions")
            ),
            "addresses_aspects": payload.get("addresses_aspects"),
        }

    def generate(
        self,
        brief: dict,
        llm: JsonLlm,
        *,
        previous_draft: dict | None = None,
        feedback: str | None = None,
        iteration: int = 1,
    ) -> dict:
        warning: str | None = None
        try:
            payload = llm(
                self._messages(
                    brief,
                    previous_draft=previous_draft,
                    feedback=feedback,
                ),
                max_tokens=1_800,
                temperature=0.1,
            )
        except LlmError as exc:
            logger.warning(
                "rfp_proposal generador %s sin LLM en iteración %d: %s",
                self.department_id,
                iteration,
                exc,
            )
            payload = {}
            warning = f"El generador no recibió respuesta del LLM: {exc}"

        prose = self._normalize_prose(payload)
        fields = self.department_fields(brief)
        pricing = self.pricing_rows(brief)
        tiers = discount_tier_rows()
        sla = self.sla(brief)

        deterministic = {
            **fields,
            "pricing": pricing,
            "discount_tiers": tiers,
            "sla": sla,
        }
        prose, unsupported = self._guard_prose(
            prose, self._allowed_numbers(brief, deterministic)
        )

        open_questions = list(brief.get("open_questions") or [])
        for question in prose["additional_open_questions"]:
            if question not in open_questions:
                open_questions.append(question)
        for item in unsupported:
            question = (
                "Confirmar las cifras no respaldadas por la RFP ni la tarifa "
                f"publicada en '{item['text'][:80]}': {', '.join(item['numbers'])}. "
                "El borrador las ha eliminado."
            )
            if question not in open_questions:
                open_questions.append(question)

        client_name = (brief.get("client") or {}).get("name") or "el cliente"
        draft = {
            "department_id": self.department_id,
            "department_label": self.label,
            "responsible": self.responsible,
            "title": f"Propuesta de {self.service_label} — {client_name}",
            "currency": brief.get("currency"),
            "client_country": brief.get("client_country"),
            "executive_summary": prose["executive_summary"],
            "offerings": prose["offerings"],
            "assumptions": prose["assumptions"],
            "open_questions": open_questions,
            "addresses_aspects": _match_aspects(
                prose["addresses_aspects"], brief.get("key_aspects") or []
            ),
            "unsupported_claims": unsupported,
            "generation_warning": warning,
            "iteration": iteration,
            **deterministic,
        }
        draft["body_markdown"] = render_section(draft)
        return draft


def sla_commitment(
    *,
    detail: str,
    notes: list[str] | None = None,
) -> dict:
    return {
        "on_time_pct": SLA_ON_TIME_PCT,
        "detail": detail,
        "notes": notes or [],
        "compensation_pct": SLA_COMPENSATION_PCT,
    }
