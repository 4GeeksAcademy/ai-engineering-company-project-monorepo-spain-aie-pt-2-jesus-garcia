"""Renderizado determinista de una sección a Markdown.

El texto que se evalúa (legibilidad) y que verá Ventas se compone aquí a
partir de campos estructurados. Las tablas de precio y descuento no las
escribe el LLM: salen de ``rate_card``/``policy``, así el evaluador de
cumplimiento puede verificar datos exactos.
"""

from __future__ import annotations

from typing import Any


def _format_amount(amount: float) -> str:
    if float(amount).is_integer():
        return f"{int(amount)}"
    return f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _money_row(row: dict) -> str:
    amount = row.get("amount")
    currency = row.get("currency") or ""
    unit = row.get("unit") or "—"
    if amount is None:
        price = f"Pendiente de confirmación por {row.get('owner', 'el responsable')}"
        basis = row.get("note") or ""
    else:
        price = f"{_format_amount(float(amount))} {currency}".strip()
        basis = row.get("basis") or row.get("source") or ""
    return f"| {row.get('concept', '—')} | {unit} | {price} | {basis} |"


def _discount_row(row: dict) -> str:
    minimum = row.get("min_monthly_volume")
    maximum = row.get("max_monthly_volume")
    if maximum is None:
        volume = f"{minimum}+ pedidos/mes"
    else:
        volume = f"{minimum}-{maximum} pedidos/mes"
    return (
        f"| {volume} | {row.get('discount_pct', 0)}% | "
        f"{row.get('notes') or '—'} |"
    )


def _bullets(items: list[Any], key: str | None = None) -> list[str]:
    lines: list[str] = []
    for item in items:
        if isinstance(item, str):
            lines.append(f"- {item}")
        elif isinstance(item, dict):
            label = item.get(key or "name") or item.get("aspect") or ""
            detail = item.get("detail") or item.get("description") or ""
            lines.append(f"- **{label}**: {detail}" if label else f"- {detail}")
    return lines


def _capacity_block(draft: dict) -> list[str]:
    capacity = draft.get("capacity") or {}
    if not capacity:
        return []
    lines = ["## Capacidad de almacenamiento", ""]
    sku_count = capacity.get("sku_count")
    lines.append(
        "- SKUs a almacenar: "
        + (f"{sku_count:,}".replace(",", ".") if sku_count else "pendiente de confirmación")
    )
    if capacity.get("storage_basis"):
        lines.append(f"- Base de facturación: {capacity['storage_basis']}")
    if capacity.get("locations"):
        lines.append(f"- Ubicaciones: {', '.join(capacity['locations'])}")
    if capacity.get("notes"):
        lines.append(f"- Nota: {capacity['notes']}")
    return lines


def _onboarding_block(draft: dict) -> list[str]:
    onboarding = draft.get("onboarding") or {}
    if not onboarding:
        return []
    days = onboarding.get("days")
    lines = ["## Onboarding", ""]
    if days is None:
        lines.append(
            f"- Tiempo de onboarding: pendiente de confirmación por "
            f"{onboarding.get('owner', 'el responsable')}."
        )
    else:
        lines.append(f"- Tiempo de onboarding: {days} días.")
    if onboarding.get("steps"):
        lines.extend(f"- {step}" for step in onboarding["steps"])
    return lines


def _carriers_block(draft: dict) -> list[str]:
    carriers = draft.get("carriers") or []
    if not carriers:
        return []
    lines = [
        "## Transportistas disponibles",
        "",
        "| Transportista | Cobertura | Fortaleza |",
        "| --- | --- | --- |",
    ]
    for item in carriers:
        lines.append(
            f"| {item.get('carrier', '—')} | {item.get('coverage', '—')} | "
            f"{item.get('strength', '—')} |"
        )
    return lines


def _process_block(draft: dict) -> list[str]:
    process = draft.get("process") or []
    if not process:
        return []
    lines = ["## Proceso de devoluciones", ""]
    for item in process:
        step = item.get("step") if isinstance(item, dict) else None
        detail = item.get("detail") if isinstance(item, dict) else item
        lines.append(f"{step}. {detail}" if step else f"- {detail}")
    return lines


def _turnaround_block(draft: dict) -> list[str]:
    turnaround = draft.get("turnaround") or {}
    if not turnaround:
        return []
    lines = ["## Tiempo de procesamiento", ""]
    minimum = turnaround.get("minimum_hours")
    if minimum is not None:
        lines.append(f"- Compromiso mínimo de procesamiento: {minimum} horas.")
    committed = turnaround.get("committed_hours")
    if committed is None:
        lines.append(
            f"- Tiempo comprometido por devolución: pendiente de confirmación "
            f"por {turnaround.get('owner', 'el responsable')}."
        )
    else:
        lines.append(f"- Tiempo comprometido por devolución: {committed} horas.")
    if turnaround.get("notes"):
        lines.append(f"- {turnaround['notes']}")
    return lines


def render_section(draft: dict) -> str:
    """Devuelve el Markdown completo de la sección."""

    lines: list[str] = [f"# {draft.get('title') or 'Sección de propuesta'}", ""]

    summary = (draft.get("executive_summary") or "").strip()
    if summary:
        lines.extend([summary, ""])

    offerings = draft.get("offerings") or []
    if offerings:
        lines.extend(["## Servicios incluidos", ""])
        lines.extend(_bullets(offerings))
        lines.append("")

    for block in (
        _capacity_block(draft),
        _onboarding_block(draft),
        _carriers_block(draft),
        _process_block(draft),
        _turnaround_block(draft),
    ):
        if block:
            lines.extend(block)
            lines.append("")

    pricing = draft.get("pricing") or []
    if pricing:
        lines.extend(
            [
                "## Tarifas",
                "",
                "| Concepto | Unidad | Tarifa | Base |",
                "| --- | --- | --- | --- |",
            ]
        )
        lines.extend(_money_row(row) for row in pricing)
        lines.append("")

    tiers = draft.get("discount_tiers") or []
    if tiers:
        lines.extend(
            [
                "## Descuentos por volumen",
                "",
                "| Volumen mensual | Descuento | Nota |",
                "| --- | --- | --- |",
            ]
        )
        lines.extend(_discount_row(row) for row in tiers)
        lines.append("")

    sla = draft.get("sla") or {}
    if sla:
        lines.extend(["## SLA de entrega", ""])
        if sla.get("on_time_pct") is not None:
            lines.append(
                f"- Compromiso de entregas a tiempo: {sla['on_time_pct']:g}% mensual."
            )
        if sla.get("detail"):
            lines.append(f"- {sla['detail']}")
        for note in sla.get("notes") or []:
            lines.append(f"- {note}")
        lines.append("")

    assumptions = draft.get("assumptions") or []
    if assumptions:
        lines.extend(["## Supuestos", ""])
        lines.extend(_bullets(assumptions))
        lines.append("")

    questions = draft.get("open_questions") or []
    if questions:
        lines.extend(["## Preguntas abiertas", ""])
        lines.extend(_bullets(questions))
        lines.append("")

    return "\n".join(lines).strip() + "\n"
