"""Configuración compartida del RAG de TrackFlow (MILESTONE 7)."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Las credenciales/modelos del RAG viven en services/api/.env; los scripts RAG
# deben funcionar también desde la raíz. Se carga primero el fichero de la API
# para que tenga prioridad (load_dotenv usa override=False por defecto).
load_dotenv(_REPO_ROOT / "services" / "api" / ".env")
load_dotenv(_REPO_ROOT / ".env")

COMPANY = "trackflow"
LANGUAGE = "es"

COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "trackflow_knowledge")
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY") or None

LLM_API_KEY = os.getenv("LLM_API_KEY") or ""


def join_url(base: str, *parts: str) -> str:
    """Une base y partes con exactamente una barra, sin duplicarla ni omitirla."""
    result = (base or "").strip().rstrip("/")
    for part in parts:
        cleaned = str(part).strip().strip("/")
        if cleaned:
            result = f"{result}/{cleaned}"
    return result


def normalize_llm_base_url(base: str) -> str:
    """Normaliza la base del proxy.

    Acepta bases con o sin `/v1` y tolera el sufijo `/litellm` que aparece en
    algunas rutas del programa. Las peticiones siempre se construyen como
    `{base}/v1/{embeddings|chat/completions}`.
    """
    result = (base or "").strip().rstrip("/")
    changed = True
    while changed:
        changed = False
        for suffix in ("/v1", "/litellm"):
            if result.endswith(suffix):
                result = result[: -len(suffix)].rstrip("/")
                changed = True
    return result


def build_api_url(base: str, path: str) -> str:
    return join_url(normalize_llm_base_url(base), "v1", path)


def build_model_url(base: str, model: str) -> str:
    """URL informativa base + modelo (una sola barra), p. ej. para trazas."""
    return join_url(base, model)


LLM_BASE_URL = normalize_llm_base_url(
    os.getenv("LLM_BASE_URL") or "https://llm.4geeks.ai",
)
EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL",
    "madrid-spain/openrouter/perplexity/pplx-embed-v1-0.6b",
)
GENERATION_MODEL = os.getenv(
    "GENERATION_MODEL",
    "madrid-spain/openrouter/deepseek/deepseek-v4-flash",
)
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1024"))

DEFAULT_TOP_K = int(os.getenv("RAG_TOP_K", "5"))
DEFAULT_MIN_SCORE = float(os.getenv("RAG_MIN_SCORE", "0.35"))

KNOWLEDGE_BASE_DIR = Path(
    os.getenv(
        "KNOWLEDGE_BASE_DIR",
        str(_REPO_ROOT / "docs" / "company-knowledge-base"),
    )
)

SOURCE_DOCUMENTS = {
    "trackflow-sla-delivery.es.md": "sla-delivery",
    "trackflow-returns-policy.es.md": "returns-policy",
    "trackflow-carrier-coverage.es.md": "carrier-coverage",
    "trackflow-storage-pricing.es.md": "storage-pricing",
}

# Unidades semánticas: se empaquetan bloques hasta ~700 caracteres y nunca se
# fuerza un corte dentro de una frase, un ítem de lista o una regla.
TARGET_CHUNK_CHARS = int(os.getenv("RAG_TARGET_CHUNK_CHARS", "700"))
MAX_CHUNK_CHARS = int(os.getenv("RAG_MAX_CHUNK_CHARS", "1100"))
MIN_CHUNKS_PER_DOCUMENT = 3


class RagError(RuntimeError):
    """Error controlado del pipeline RAG."""


class RagConfigurationError(RagError):
    """Falta configuración obligatoria o es incoherente."""


def validate_llm_config() -> None:
    if not LLM_BASE_URL:
        raise RagConfigurationError(
            "Falta LLM_BASE_URL. Configúrala en services/api/.env."
        )
    if not LLM_API_KEY:
        raise RagConfigurationError(
            "Falta LLM_API_KEY. Configúrala en services/api/.env."
        )


def validate_distinct_models() -> None:
    if EMBEDDING_MODEL == GENERATION_MODEL:
        raise RagConfigurationError(
            "EMBEDDING_MODEL y GENERATION_MODEL deben ser modelos distintos."
        )
