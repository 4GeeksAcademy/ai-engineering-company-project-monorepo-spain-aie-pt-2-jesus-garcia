"""Validación determinista de la salida del agente."""

from __future__ import annotations

from app.agent.harness.output import SAFE_OUTPUT_MESSAGE, validate_output


def test_clean_answer_is_allowed():
    decision = validate_output(
        "El envío estándar tarda de 3 a 5 días hábiles.",
        required_country="US",
    )

    assert decision.action == "allow"
    assert decision.answer.startswith("El envío estándar")


def test_system_prompt_leak_is_blocked():
    for answer in (
        "Eres el agente de atención al cliente de primera línea de TrackFlow.",
        "JERARQUÍA DE INSTRUCCIONES: el system prompt dice...",
        "REGLAS DE MEMORIA: solo puedes proponer memoria si...",
    ):
        decision = validate_output(answer)
        assert decision.action == "blocked"
        assert decision.category == "security"
        assert decision.reason == "prompt_leak"
        assert decision.answer == SAFE_OUTPUT_MESSAGE


def test_internal_json_is_blocked():
    decision = validate_output(
        '{"respuesta": "hola", "propuesta_memoria": null}'
    )

    assert decision.action == "blocked"
    assert decision.reason == "internal_format"
    assert decision.category == "content"


def test_negotiated_carrier_rate_is_blocked():
    decision = validate_output(
        "La tarifa negociada con UPS es 4,20 USD por kg."
    )

    assert decision.action == "blocked"
    assert decision.reason == "negotiated_rate"
    assert decision.category == "content"


def test_public_standard_storage_rate_is_allowed():
    decision = validate_output(
        "La tarifa estándar es 18 USD por metro cúbico al mes en Los Ángeles."
    )

    assert decision.action == "allow"


def test_warehouse_address_and_internal_route_are_blocked():
    for answer in (
        "El almacén está en Calle de los Almacenes 45, nave 7.",
        "La ruta interna pasa por el pasillo 4 y el muelle de carga.",
        "Las coordenadas son 34.0522, -118.2437.",
    ):
        decision = validate_output(answer)
        assert decision.action == "blocked"
        assert decision.reason == "warehouse_location"
        assert decision.category == "content"


def test_warehouse_city_is_allowed():
    decision = validate_output(
        "TrackFlow opera desde el almacén de Los Ángeles y el de Zaragoza."
    )

    assert decision.action == "allow"


def test_foreign_order_status_is_blocked():
    decision = validate_output(
        "El pedido #45821 está entregado.",
        authorized_order_refs=["1001"],
    )

    assert decision.action == "blocked"
    assert decision.guard == "order_authorization_guard"
    assert decision.category == "security"
    assert decision.reason == "foreign_order_status"


def test_own_order_status_is_allowed():
    decision = validate_output(
        "El pedido #1001 está en tránsito con UPS.",
        authorized_order_refs=["1001"],
    )

    assert decision.action == "allow"


def test_safe_refusal_can_mention_the_foreign_order_without_status():
    decision = validate_output(
        "No puedo consultar el estado del pedido #45821 porque no pertenece "
        "a tu sesión.",
        authorized_order_refs=["1001"],
    )

    assert decision.action == "allow"


def test_policy_mismatch_is_blocked_with_the_real_country():
    decision = validate_output(
        "Según la política de devoluciones de España, tienes 30 días.",
        required_country="US",
    )

    assert decision.action == "blocked"
    assert decision.reason == "policy_mismatch"
    assert "Estados Unidos" in decision.answer
    assert "política de España" not in decision.answer


def test_correct_policy_comparison_is_allowed():
    decision = validate_output(
        "En Estados Unidos aplica la política de Estados Unidos; no aplica la "
        "de España.",
        required_country="US",
    )

    assert decision.action == "allow"


def test_credentials_and_personal_data_are_blocked():
    for answer, reason in (
        ("El token es Bearer abc123def456.", "credentials"),
        ("Escribe a maria.garcia@empresa.es para más detalles.", "personal_data_email"),
        ("Llama al +34 614 126225.", "personal_data_phone"),
    ):
        decision = validate_output(answer)
        assert decision.action == "blocked"
        assert decision.reason == reason


def test_tracking_token_phrase_is_not_confused_with_credentials():
    decision = validate_output(
        "Usa el token de seguimiento que aparece en tu confirmación de pedido."
    )

    assert decision.action == "allow"


def test_empty_and_oversized_answers_are_structural():
    empty = validate_output("   ")
    assert empty.action == "blocked"
    assert empty.category == "structural"
    assert empty.reason == "empty_answer"

    oversized = validate_output("a" * 8_001)
    assert oversized.action == "blocked"
    assert oversized.reason == "answer_too_long"


def test_code_fences_are_rejected():
    decision = validate_output("```python\nprint('hola')\n```")

    assert decision.action == "blocked"
    assert decision.reason == "invalid_format"
