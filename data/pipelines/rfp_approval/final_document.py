"""Gate de cumplimiento y síntesis del documento final acordado."""

from __future__ import annotations

from datetime import datetime, timezone

from data.pipelines.rfp_proposal.evaluators.compliance import evaluate_compliance
from data.pipelines.rfp_proposal.policy import (
    RETURNS_MIN_HOURS,
    RULE_CARRIER_RATES_CONFIDENTIAL,
    RULE_CURRENCY_BY_COUNTRY,
    RULE_DELIVERY_SLA,
    RULE_RETURNS_MIN_48H,
    RULE_VOLUME_DISCOUNTS,
    SLA_ON_TIME_PCT,
)

from .conflicts import draft_for_evaluation, violations_with_rule
from .contracts import (
    APPROVAL_APPROVED,
    APPROVAL_REJECTED,
    FINAL_CONTRACT,
    fallback_brief,
)


def _ordered(sections: dict[str, dict]) -> list[dict]:
    from data.pipelines.rfp_intake.catalog import DEPARTMENT_ORDER

    return [
        sections[department]
        for department in DEPARTMENT_ORDER
        if department in sections
    ]


def final_gate(
    sections: dict[str, dict],
    *,
    briefs: dict[str, dict] | None = None,
    proposal: dict,
    intake: dict | None,
    currency: str | None,
) -> dict:
    """Valida que todas las secciones aprobadas cumplen el briefing §5."""

    briefs = briefs or {}
    intake = intake or {}
    checks: list[dict] = []
    violations: list[dict] = []

    for department_id, section in sections.items():
        if section.get("approval_status") != APPROVAL_APPROVED:
            checks.append(
                {
                    "check": "approved",
                    "department_id": department_id,
                    "pass": False,
                    "detail": section.get("approval_status"),
                }
            )
            violations.append(
                {
                    "rule_id": "APPROVAL-REQUIRED",
                    "department_id": department_id,
                    "message": "La sección no tiene aprobación humana.",
                }
            )
        else:
            checks.append(
                {
                    "check": "approved",
                    "department_id": department_id,
                    "pass": True,
                    "approver": section.get("approver"),
                }
            )

        payload = section.get("draft_payload") or {}
        section_currency = (payload.get("currency") or currency or "").upper()
        if currency and section_currency != currency.upper():
            checks.append(
                {
                    "check": "currency",
                    "department_id": department_id,
                    "pass": False,
                    "detail": section_currency,
                }
            )
            violations.append(
                {
                    "rule_id": RULE_CURRENCY_BY_COUNTRY,
                    "department_id": department_id,
                    "message": f"Moneda {section_currency} distinta de {currency}.",
                }
            )
        else:
            checks.append(
                {"check": "currency", "department_id": department_id, "pass": True}
            )

        brief = briefs.get(department_id) or fallback_brief(
            section, proposal=proposal, intake=intake
        )
        evaluation = evaluate_compliance(brief, draft_for_evaluation(section))
        for rule_id in (
            RULE_CURRENCY_BY_COUNTRY,
            RULE_DELIVERY_SLA,
            RULE_RETURNS_MIN_48H,
            RULE_VOLUME_DISCOUNTS,
            RULE_CARRIER_RATES_CONFIDENTIAL,
        ):
            found = violations_with_rule(evaluation, rule_id)
            checks.append(
                {
                    "check": rule_id,
                    "department_id": department_id,
                    "pass": not found,
                }
            )
            for violation in found:
                violations.append(
                    {
                        **violation,
                        "department_id": department_id,
                    }
                )

        if department_id == "reverse":
            turnaround = payload.get("turnaround") or {}
            hours = [
                turnaround.get("minimum_hours"),
                turnaround.get("committed_hours"),
            ]
            below = [
                value
                for value in hours
                if isinstance(value, (int, float))
                and float(value) < RETURNS_MIN_HOURS
            ]
            checks.append(
                {
                    "check": "returns_min_48h",
                    "department_id": department_id,
                    "pass": not below,
                }
            )
            if below:
                violations.append(
                    {
                        "rule_id": RULE_RETURNS_MIN_48H,
                        "department_id": department_id,
                        "message": (
                            "El turnaround de devoluciones es inferior a "
                            f"{RETURNS_MIN_HOURS} horas."
                        ),
                    }
                )

    rejected = [
        department_id
        for department_id, section in sections.items()
        if section.get("approval_status") == APPROVAL_REJECTED
    ]
    if rejected:
        violations.append(
            {
                "rule_id": "SECTION-REJECTED",
                "message": f"Secciones rechazadas: {', '.join(rejected)}.",
                "sections": rejected,
            }
        )

    return {
        "ok": not violations,
        "checks": checks,
        "violations": violations,
        "rejected_sections": rejected,
        "currency": currency,
        "sla_on_time_pct": SLA_ON_TIME_PCT,
        "returns_min_hours": RETURNS_MIN_HOURS,
    }


def _format_money(amount: float, currency: str | None) -> str:
    if float(amount).is_integer():
        value = f"{int(amount):,}".replace(",", ".")
    else:
        value = f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{value} {currency or ''}".strip()


def _pricing_table(rows: list[dict], currency: str | None) -> list[str]:
    if not rows:
        return []
    lines = [
        "| Concepto | Unidad | Tarifa | Base |",
        "| --- | --- | --- | --- |",
    ]
    for row in rows:
        amount = row.get("amount")
        price = (
            _format_money(float(amount), row.get("currency") or currency)
            if isinstance(amount, (int, float))
            else f"Pendiente de confirmación por {row.get('owner', 'el responsable')}"
        )
        lines.append(
            f"| {row.get('concept', '—')} | {row.get('unit', '—')} | {price} | "
            f"{row.get('basis') or row.get('note') or '—'} |"
        )
    return lines


def _discount_table(rows: list[dict]) -> list[str]:
    if not rows:
        return []
    lines = [
        "| Volumen mensual | Descuento | Nota |",
        "| --- | --- | --- |",
    ]
    for row in rows:
        minimum = row.get("min_monthly_volume")
        maximum = row.get("max_monthly_volume")
        volume = (
            f"{minimum}+ pedidos/mes"
            if maximum is None
            else f"{minimum}-{maximum} pedidos/mes"
        )
        lines.append(
            f"| {volume} | {row.get('discount_pct', 0)}% | "
            f"{row.get('notes') or '—'} |"
        )
    return lines


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = item.strip()
        if key and key not in seen:
            seen.add(key)
            result.append(key)
    return result


def _section_markdown(section: dict) -> tuple[str, str]:
    """Extrae el título de la sección y demota sus encabezados un nivel."""

    content = (section.get("draft_content") or "").strip()
    payload = section.get("draft_payload") or {}
    fallback_title = (
        payload.get("title")
        or f"{section.get('department_label')} — {section.get('responsible')}"
    )
    lines = content.splitlines()
    title = fallback_title
    if lines and lines[0].startswith("# "):
        title = lines[0][2:].strip() or fallback_title
        lines = lines[1:]
    demoted: list[str] = []
    for line in lines:
        if line.startswith("### "):
            demoted.append("#" + line)
        elif line.startswith("## "):
            demoted.append("#" + line)
        elif line.startswith("# "):
            demoted.append("## " + line[2:])
        else:
            demoted.append(line)
    return title, "\n".join(demoted).strip()


def build_final_document(
    *,
    ticket_id: str,
    proposal: dict,
    intake: dict | None,
    sections: dict[str, dict],
    currency: str | None,
) -> dict:
    """Consolida las secciones aprobadas en el documento final."""

    intake = intake or {}
    ordered = _ordered(sections)
    client = proposal.get("client") or {}
    facts = intake.get("facts") or {}
    generated_at = datetime.now(timezone.utc).isoformat()

    lines: list[str] = [
        f"# Propuesta comercial — {client.get('name') or 'Cliente'}",
        "",
        f"**RFP:** {proposal.get('rfp_id') or '—'}  ",
        f"**País:** {proposal.get('client_country') or '—'}  ",
        f"**Moneda:** {currency or '—'}  ",
        f"**Fecha:** {generated_at[:10]}  ",
        f"**Servicios:** {', '.join(proposal.get('services_requested') or []) or '—'}  ",
        f"**Preparada por:** TrackFlow",
        "",
    ]
    if facts.get("deadline"):
        lines.append(f"**Fecha límite de la RFP:** {facts['deadline']}  ")
    if facts.get("budget_range"):
        lines.append(f"**Presupuesto de referencia:** {facts['budget_range']}  ")
    lines.append("")

    lines.extend(
        [
            "## Aprobaciones",
            "",
            "| Departamento | Responsable | Decisión | Fecha | Comentario |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for section in ordered:
        lines.append(
            f"| {section.get('department_label')} | "
            f"{section.get('responsible')} | Aprobada | "
            f"{(section.get('approved_at') or '')[:10]} | "
            f"{(section.get('approval_comment') or '—')} |"
        )
    lines.append("")

    for index, section in enumerate(ordered, start=1):
        title, content = _section_markdown(section)
        lines.extend(
            [
                f"## {index}. {title}",
                "",
                content,
                "",
            ]
        )

    lines.extend(["## Condiciones comerciales comunes", ""])
    lines.append(
        f"- **Moneda:** todas las tarifas se expresan en {currency or 'la moneda del cliente'}."
    )
    lines.append(
        f"- **SLA de entrega:** {SLA_ON_TIME_PCT:g}% de entregas a tiempo al mes por país."
    )
    lines.append(
        f"- **Devoluciones:** el procesamiento nunca se compromete por debajo de "
        f"{RETURNS_MIN_HOURS} horas."
    )
    lines.append(
        "- **Transportistas:** solo se publica el coste final ofrecido al cliente; "
        "las tarifas negociadas son confidenciales."
    )
    lines.append("")

    tiers: list[dict] = []
    for section in ordered:
        tiers = (section.get("draft_payload") or {}).get("discount_tiers") or []
        if tiers:
            break
    if tiers:
        lines.extend(["### Descuentos por volumen", ""])
        lines.extend(_discount_table(tiers))
        lines.append("")

    questions = _dedupe(
        [
            question
            for section in ordered
            for question in (
                (section.get("draft_payload") or {}).get("open_questions") or []
            )
            if isinstance(question, str)
        ]
    )
    if questions:
        lines.extend(["## Preguntas abiertas", ""])
        lines.extend(f"- {question}" for question in questions)
        lines.append("")

    markdown = "\n".join(lines).strip() + "\n"
    approved_by = [
        {
            "department_id": section.get("department_id"),
            "department_label": section.get("department_label"),
            "responsible": section.get("responsible"),
            "approver": section.get("approver"),
            "approved_at": section.get("approved_at"),
            "comment": section.get("approval_comment"),
            "provisional": bool(section.get("provisional")),
        }
        for section in ordered
    ]
    return {
        "contract_version": FINAL_CONTRACT,
        "ticket_id": ticket_id,
        "rfp_id": proposal.get("rfp_id"),
        "currency": currency,
        "generated_at": generated_at,
        "client": client,
        "client_country": proposal.get("client_country"),
        "services_requested": list(proposal.get("services_requested") or []),
        "sections": [
            {
                "department_id": section.get("department_id"),
                "department_label": section.get("department_label"),
                "responsible": section.get("responsible"),
                "draft_content": section.get("draft_content"),
                "draft_payload": section.get("draft_payload"),
                "evaluation_results": section.get("evaluation_results"),
                "approval_status": section.get("approval_status"),
                "approver": section.get("approver"),
                "approved_at": section.get("approved_at"),
                "approval_comment": section.get("approval_comment"),
                "provisional": bool(section.get("provisional")),
            }
            for section in ordered
        ],
        "approved_by": approved_by,
        "markdown": markdown,
    }


__all__ = ["build_final_document", "final_gate"]
