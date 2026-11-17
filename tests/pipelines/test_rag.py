"""Tests unitarios del pipeline RAG de TrackFlow."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from data.pipelines import rag
from data.process import rag_index
from data.process.rag_config import (
    build_api_url,
    build_model_url,
    join_url,
    normalize_llm_base_url,
)


class StubQdrant:
    def __init__(self, points: list[tuple[float, dict]]):
        self.points = points
        self.calls: list[dict] = []

    def query_points(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            points=[
                SimpleNamespace(score=score, payload=payload)
                for score, payload in self.points
            ]
        )


@pytest.mark.parametrize(
    "base",
    [
        "https://llm.4geeks.ai",
        "https://llm.4geeks.ai/",
        "https://llm.4geeks.ai/v1",
        "https://llm.4geeks.ai/v1/",
        "https://llm.4geeks.ai/litellm",
        "https://llm.4geeks.ai/litellm/",
        "https://llm.4geeks.ai/litellm/v1",
    ],
)
def test_build_api_url_handles_slashes_and_suffixes(base):
    assert build_api_url(base, "embeddings") == (
        "https://llm.4geeks.ai/v1/embeddings"
    )
    assert build_api_url(base, "/chat/completions") == (
        "https://llm.4geeks.ai/v1/chat/completions"
    )


def test_join_url_and_model_url_use_exactly_one_slash():
    assert join_url("https://llm.4geeks.ai/", "/v1/", "/embeddings/") == (
        "https://llm.4geeks.ai/v1/embeddings"
    )
    assert build_model_url(
        "https://llm.4geeks.ai/litellm/",
        "/madrid-spain/openrouter/deepseek/deepseek-v4-flash",
    ) == (
        "https://llm.4geeks.ai/litellm/"
        "madrid-spain/openrouter/deepseek/deepseek-v4-flash"
    )


def test_normalize_llm_base_url():
    assert normalize_llm_base_url("https://llm.4geeks.ai/litellm/v1/") == (
        "https://llm.4geeks.ai"
    )
    assert normalize_llm_base_url("https://llm.4geeks.ai/v1") == (
        "https://llm.4geeks.ai"
    )


def _payload(text: str, source: str = "sla-delivery", section: str = "SLA de Entrega"):
    return {
        "company": "trackflow",
        "source_document": source,
        "section": section,
        "language": "es",
        "chunk_index": 0,
        "text": text,
    }


@pytest.fixture()
def stub_qdrant(monkeypatch):
    stub = StubQdrant(
        [
            (0.91, _payload("chunk relevante")),
            (0.62, _payload("chunk secundario")),
            (0.18, _payload("chunk irrelevante")),
        ]
    )
    monkeypatch.setattr(rag, "get_qdrant_client", lambda: stub)
    monkeypatch.setattr(rag, "embed", lambda text: [1.0, 0.0, 0.0])
    return stub


def test_retrieve_filters_below_min_score(stub_qdrant):
    result = rag.retrieve("¿SLA estándar?", k=5, min_score=0.5)

    assert [item["text"] for item in result] == [
        "chunk relevante",
        "chunk secundario",
    ]
    assert all(isinstance(item, dict) for item in result)
    assert all("score" not in item for item in result)


def test_retrieve_can_return_fewer_than_k(stub_qdrant):
    result = rag.retrieve("¿SLA estándar?", k=10, min_score=0.5)

    assert len(result) == 2
    assert stub_qdrant.calls[0]["limit"] == 10
    assert stub_qdrant.calls[0]["score_threshold"] == 0.5


def test_retrieve_returns_empty_when_nothing_passes_threshold(stub_qdrant):
    assert rag.retrieve("¿SLA estándar?", k=5, min_score=0.99) == []


def test_retrieve_rejects_empty_query(stub_qdrant):
    with pytest.raises(ValueError):
        rag.retrieve("   ")


def test_query_returns_generated_answer_not_raw_chunks(monkeypatch):
    context = [
        _payload(
            "TEXTO_CRUDO_DEL_CHUNK: envío estándar de 3 a 5 días hábiles.",
        )
    ]
    captured: dict = {}

    monkeypatch.setattr(rag, "retrieve", lambda question, **kwargs: context)
    monkeypatch.setattr(rag, "validate_llm_config", lambda: None)
    monkeypatch.setattr(rag, "validate_distinct_models", lambda: None)

    def fake_chat(messages: list[dict]) -> str:
        captured["messages"] = messages
        return "El envío estándar tarda de 3 a 5 días hábiles."

    monkeypatch.setattr(rag, "_chat_completion", fake_chat)

    answer = rag.query("¿Cuánto tarda un envío estándar?")

    assert answer == "El envío estándar tarda de 3 a 5 días hábiles."
    assert "TEXTO_CRUDO_DEL_CHUNK" not in answer
    prompt = captured["messages"][1]["content"]
    assert "TEXTO_CRUDO_DEL_CHUNK" in prompt
    assert "sla-delivery" in prompt
    assert "SLA de Entrega" in prompt


def test_query_without_context_returns_honest_message(monkeypatch):
    monkeypatch.setattr(rag, "retrieve", lambda question, **kwargs: [])
    monkeypatch.setattr(
        rag,
        "_chat_completion",
        lambda *args, **kwargs: pytest.fail("No debe llamarse al LLM sin contexto."),
    )

    answer = rag.query("¿Cuánto cuesta un descuento especial?")

    assert "No tengo información suficiente" in answer
    assert "equipo comercial" in answer


def test_generate_answer_without_context_does_not_call_llm(monkeypatch):
    monkeypatch.setattr(
        rag,
        "_chat_completion",
        lambda *args, **kwargs: pytest.fail("No debe llamarse al LLM sin contexto."),
    )

    answer = rag.generate_answer("¿Hay descuentos?", [])

    assert "No tengo información suficiente" in answer


def test_source_documents_and_chunks_preserve_metadata():
    documents = rag_index.load_source_documents()

    assert [doc.source_document for doc in documents] == [
        "sla-delivery",
        "returns-policy",
        "carrier-coverage",
        "storage-pricing",
    ]
    for document in documents:
        chunks = rag_index.chunk_document(document)
        assert len(chunks) >= 3
        for index, chunk in enumerate(chunks):
            payload = chunk.payload()
            assert chunk.chunk_index == index
            assert payload["company"] == "trackflow"
            assert payload["source_document"] == document.source_document
            assert payload["section"] == document.title
            assert payload["language"] == "es"
            assert payload["text"] == chunk.text
            assert chunk.text.strip()
            assert len(chunk.text) <= rag_index.MAX_CHUNK_CHARS
            assert chunk.point_id() == chunk.point_id()


def test_chunking_does_not_split_rules_or_conditions():
    chunks = []
    for document in rag_index.load_source_documents():
        chunks.extend(rag_index.chunk_document(document))

    def chunk_with(fragment: str) -> str:
        matches = [chunk.text for chunk in chunks if fragment in chunk.text]
        assert len(matches) == 1, f"Fragmento no encontrado o duplicado: {fragment}"
        return matches[0]

    assert "día 181" in chunk_with("Inventario con más de 180 días")
    assert "gestión manual" in chunk_with("Las devoluciones internacionales")
    assert "40% adicional" in chunk_with("no garantiza SLA de entrega")
    assert "Miguel Torres" in chunk_with("tarifa preferencial")


class StubIndexClient:
    def __init__(self):
        self.exists = False
        self.deleted = 0
        self.created = 0
        self.upserts: list[list] = []

    def collection_exists(self, collection_name: str) -> bool:
        return self.exists

    def delete_collection(self, collection_name: str) -> None:
        self.deleted += 1
        self.exists = False

    def create_collection(self, **kwargs) -> None:
        self.created += 1
        self.exists = True
        self.last_create = kwargs

    def upsert(self, collection_name: str, points: list, wait: bool = True) -> None:
        self.upserts.append(list(points))


def test_setup_is_idempotent_with_clean_and_reload(monkeypatch):
    stub = StubIndexClient()
    monkeypatch.setattr(rag_index, "get_qdrant_client", lambda: stub)
    monkeypatch.setattr(
        rag_index,
        "embed_batch",
        lambda texts, batch_size=32: [
            [0.0] * (rag_index.EMBEDDING_DIM - 1) + [1.0] for _ in texts
        ],
    )

    first = rag_index.setup(recreate=True)
    second = rag_index.setup(recreate=True)

    assert first["collection"] == "trackflow_knowledge"
    assert first["chunks"] == second["chunks"]
    assert first["by_document"] == second["by_document"]
    assert stub.created == 2
    assert stub.deleted == 1
    assert len(stub.upserts) == 2

    first_ids = [point.id for point in stub.upserts[0]]
    second_ids = [point.id for point in stub.upserts[1]]
    assert first_ids == second_ids
    assert len(set(first_ids)) == len(first_ids)
