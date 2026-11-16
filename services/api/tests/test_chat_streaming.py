"""Streaming token a token: extractor JSON, SSE y aborto."""

from __future__ import annotations

import json
import tempfile
import threading
import time

import pytest

from app.agent.graph import compile_agent_graph
from app.agent.memory.llm import chat_json_stream
from app.agent.memory.streaming import AnswerStreamExtractor
from app.agent.router import RoutingDecision
from app.agent.runner import run_agent
from app.agent.streaming import GenerationAborted


def _line(content: str) -> str:
    return "data: " + json.dumps(
        {"choices": [{"delta": {"content": content}}]},
        ensure_ascii=False,
    )


def _lines(*contents: str) -> list[str]:
    return [_line(content) for content in contents] + ["data: [DONE]"]


def _visible(chunks: list[str]) -> str:
    extractor = AnswerStreamExtractor()
    return "".join(
        text
        for text in (extractor.feed(chunk) for chunk in chunks)
        if text
    )


@pytest.mark.parametrize("size", [1, 2, 5, 11, 100])
def test_extractor_emits_only_respuesta_for_any_split(size: int) -> None:
    raw = (
        '{"respuesta": "La entrega tarda 3 a 5 días.\\n'
        '¿Quieres que lo recuerde?", "propuesta_memoria": null}'
    )
    chunks = [raw[index:index + size] for index in range(0, len(raw), size)]
    assert _visible(chunks) == (
        "La entrega tarda 3 a 5 días.\n¿Quieres que lo recuerde?"
    )


def test_extractor_handles_escapes_and_unicode() -> None:
    raw = (
        '{"respuesta": "Línea 1\\nLínea \\"2\\" y \\u00e9 \\ud83d\\ude00",'
        ' "propuesta_memoria": null}'
    )
    assert _visible(list(raw)) == 'Línea 1\nLínea "2" y é 😀'


def test_extractor_passthrough_when_model_ignores_json() -> None:
    assert _visible(list("Hola, no soy JSON")) == "Hola, no soy JSON"


def test_extractor_never_leaks_memory_proposal() -> None:
    raw = (
        '{"respuesta": "Respuesta visible", "propuesta_memoria": '
        '{"hecho": "dato interno"}}'
    )
    visible = _visible(list(raw))
    assert visible == "Respuesta visible"
    assert "dato interno" not in visible


def test_chat_json_stream_returns_parsed_json_and_tokens() -> None:
    tokens: list[str] = []
    parsed, raw = chat_json_stream(
        [],
        on_token=tokens.append,
        stream_lines=_lines(
            '{"respuesta": "Entre 24 y 72 horas',
            ' laborables.", "propuesta_memoria": null}',
        ),
    )
    assert parsed is not None
    assert parsed["respuesta"] == "Entre 24 y 72 horas laborables."
    assert "".join(tokens) == "Entre 24 y 72 horas laborables."
    assert "propuesta_memoria" not in "".join(tokens)


def test_chat_json_stream_aborts_before_any_token() -> None:
    abort = threading.Event()
    abort.set()
    tokens: list[str] = []
    with pytest.raises(GenerationAborted):
        chat_json_stream(
            [],
            on_token=tokens.append,
            abort=abort,
            stream_lines=_lines('{"respuesta": "no debería salir"}'),
        )
    assert tokens == []


def test_chat_json_stream_aborts_mid_generation() -> None:
    abort = threading.Event()
    tokens: list[str] = []

    def lines():
        yield _line('{"respuesta": "primera parte ')
        abort.set()
        yield _line('segunda parte"}')
        yield "data: [DONE]"

    with pytest.raises(GenerationAborted):
        chat_json_stream(
            [],
            on_token=tokens.append,
            abort=abort,
            stream_lines=lines(),
        )
    assert tokens == ["primera parte "]


def test_run_agent_uses_langgraph_custom_stream_and_aborts() -> None:
    tokens: list[str] = []

    def generator(question, context, memory_context, *, on_token=None, abort=None):
        for index in range(500):
            if abort is not None and abort.is_set():
                raise GenerationAborted()
            on_token(f"tok{index} ")
            time.sleep(0.002)
        return {"answer": "no debería llegar", "proposal": None}

    graph = compile_agent_graph(
        retriever=lambda question: [
            {
                "source_document": "doc.md",
                "section": "s",
                "text": "contexto",
                "chunk_index": 1,
            }
        ],
        classifier=lambda question: RoutingDecision(route="rag"),
        memory_generator=generator,
        memory_gate=lambda question: False,
    )
    abort = threading.Event()
    timer = threading.Timer(0.05, abort.set)
    timer.start()
    result = run_agent(
        "¿Cuánto tarda una entrega estándar en España?",
        graph=graph,
        token_sink=tokens.append,
        abort=abort,
        trace_dir=tempfile.mkdtemp(),
    )
    timer.cancel()

    assert result.status == "interrupted"
    assert tokens
    assert len(tokens) < 500
