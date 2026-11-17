"""Regresión de endurecimiento: autorización, secretos, rate limit y configs.

Estos tests son la evidencia reproducible de los fixes críticos del informe
OWASP. Cada uno falla contra el código vulnerable anterior.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.agent.rag_policy import filter_context_for_role
from app.agent.tools.mcp_auth import MCPSettings
from app.core.config import allowed_origins, validate_security_config
from app.core.rate_limit import reset_rate_limits
from app.core.security import create_token

REPO_ROOT = Path(__file__).resolve().parents[3]


# --------------------------------------------------------------------- A01
def test_telemetry_report_requires_authentication(client):
    assert client.get("/telemetry/report").status_code == 401


def test_telemetry_report_forbidden_for_normal_user(client, user_headers):
    assert client.get("/telemetry/report", headers=user_headers).status_code == 403


def test_inventory_products_forbidden_for_normal_user(client, user_headers):
    assert client.get("/inventory/products", headers=user_headers).status_code == 403


def test_agent_memory_forbidden_for_normal_user(client, user_headers):
    assert client.get("/agent/memory", headers=user_headers).status_code == 403


def test_knowledge_query_forbidden_for_normal_user(client, user_headers):
    response = client.post(
        "/knowledge/query",
        json={"question": "¿SLA estándar?"},
        headers=user_headers,
    )
    assert response.status_code == 403


def test_chat_client_id_forbidden_for_normal_user(client, user_headers):
    response = client.post(
        "/chat/sessions",
        json={"client_id": "otra-marca"},
        headers=user_headers,
    )
    assert response.status_code == 403


def test_chat_client_id_allowed_for_manager(client, auth_headers):
    response = client.post(
        "/chat/sessions",
        json={"client_id": "marca-propia"},
        headers=auth_headers,
    )
    assert response.status_code == 201


# --------------------------------------------------------------- A01 RAG
def _context() -> list[dict]:
    return [
        {"source_document": "sla-delivery", "text": "SLA público"},
        {"source_document": "returns-policy", "text": "Devoluciones públicas"},
        {"source_document": "storage-pricing", "text": "18 USD/m3"},
        {"source_document": "carrier-coverage", "text": "Tarifas de carriers"},
    ]


def test_rag_filter_hides_internal_documents_from_user():
    filtered = filter_context_for_role(_context(), "user")
    assert {item["source_document"] for item in filtered} == {
        "sla-delivery",
        "returns-policy",
    }


def test_rag_filter_keeps_all_documents_for_manager():
    filtered = filter_context_for_role(_context(), "manager")
    assert len(filtered) == 4


# --------------------------------------------------------- A02 / producción
def test_production_rejects_weak_secret(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", "change-this-to-a-random-secret-in-production")
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://app.trackflow.test")
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        validate_security_config()


def test_production_accepts_strong_config(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", "x" * 64)
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://app.trackflow.test")
    monkeypatch.setenv("TRACKFLOW_API_PASSWORD", "una-password-larga-y-rotada")
    validate_security_config()


def test_allowed_origins_rejects_wildcard(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", "*")
    with pytest.raises(RuntimeError, match="ALLOWED_ORIGINS"):
        allowed_origins()


def test_public_registration_disabled_in_production(client, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("ALLOW_PUBLIC_REGISTRATION", raising=False)
    response = client.post(
        "/api/users",
        json={"email": "prod-register@test.com", "password": "password-123"},
    )
    assert response.status_code == 403


# --------------------------------------------------------------- A07 rate
def test_login_rate_limit_returns_429(client, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "1")
    reset_rate_limits()
    payload = {"email": "nadie@test.com", "password": "incorrecta"}
    statuses = [
        client.post("/api/auth/login", json=payload).status_code
        for _ in range(11)
    ]
    assert statuses[:10] == [401] * 10
    assert statuses[10] == 429
    assert "Retry-After" in client.post("/api/auth/login", json=payload).headers


def test_agent_query_rate_limit_returns_429(client, auth_headers, monkeypatch):
    from app.agent.runner import AgentResult
    from app.routes import agent as agent_route

    monkeypatch.setattr(
        agent_route,
        "run_agent",
        lambda question, **kwargs: AgentResult(
            run_id="rate-limit-run",
            status="ok",
            answer="ok",
            error=None,
            trace_path=None,
        ),
    )
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "1")
    reset_rate_limits()
    payload = {"question": "¿SLA estándar?"}
    statuses = [
        client.post("/agent/query", json=payload, headers=auth_headers).status_code
        for _ in range(61)
    ]
    assert statuses[-1] == 429


# ------------------------------------------------------------ A05 headers
def test_api_security_headers_present(client):
    response = client.get("/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "referrer-policy" in response.headers


# ------------------------------------------------------- agente least privilege
def test_agent_mcp_scopes_are_read_only(monkeypatch):
    monkeypatch.setenv("MCP_OAUTH_SCOPES", "mcp:read mcp:write")
    monkeypatch.delenv("AGENT_MCP_ALLOW_WRITE", raising=False)
    settings = MCPSettings.from_env()
    assert settings.scopes == ["mcp:read"]


def test_agent_mcp_write_only_with_explicit_override(monkeypatch):
    monkeypatch.setenv("MCP_OAUTH_SCOPES", "mcp:read mcp:write")
    monkeypatch.setenv("AGENT_MCP_ALLOW_WRITE", "1")
    settings = MCPSettings.from_env()
    assert "mcp:write" in settings.scopes


# --------------------------------------------------------- infraestructura
def test_sshd_config_disables_root_and_password_login():
    text = (REPO_ROOT / "scripts/security/hardening/sshd_trackflow.conf").read_text()
    assert re.search(r"^PermitRootLogin no$", text, re.MULTILINE)
    assert re.search(r"^PasswordAuthentication no$", text, re.MULTILINE)
    assert re.search(r"^AllowUsers trackflow-ops$", text, re.MULTILINE)


def test_firewall_allows_only_ssh_http_https():
    text = (REPO_ROOT / "scripts/security/hardening/30-firewall.sh").read_text()
    assert "ufw allow 80/tcp" in text
    assert "ufw allow 443/tcp" in text
    assert "ufw limit" in text or "ufw allow from" in text


def test_compose_ports_are_loopback_only():
    text = (REPO_ROOT / "docker-compose.yml").read_text()
    assert not re.search(r'^\s+- "\d+:\d+"', text, re.MULTILINE)
    assert '127.0.0.1:' in text


def test_containers_run_as_non_root():
    services = (REPO_ROOT / "services/Dockerfile").read_text()
    uis = (REPO_ROOT / "uis/Dockerfile").read_text()
    assert re.search(r"^USER appuser$", services, re.MULTILINE)
    assert re.search(r"^USER node$", uis, re.MULTILINE)


def test_tokens_created_with_test_secret_are_readable(client):
    token = create_token({"sub": "1", "role": "admin"})
    response = client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
