"""Tests del endpoint SSE de tiempo real.

Se prueba el wire real (headers, framing, nombre de evento, JSON de ``data``) y
no solo un dict aislado. El stream es infinito por diseño, así que estos tests
levantan uvicorn en un hilo y hablan HTTP de verdad: el ``TestClient`` de
Starlette bufferiza la respuesta completa y no sirve para SSE.
"""

from __future__ import annotations

import json
import socket
import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn
from sqlmodel import Session, delete

from app.realtime.broker import get_broker
from app.realtime.events import rfp_ticket_payload
from app.services import rfp_service
from database import engine
from models import RfpDepartmentSection, RfpMetadata, RfpTicket

MINIMAL_PDF = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF"

BRIEFING_FIELDS = {
    "ticket_id",
    "rfp_id",
    "client_name",
    "client_country",
    "services_requested",
    "status",
    "created_at",
}


@pytest.fixture(scope="module")
def live_server():
    """API real en uvicorn (hilo) para poder consumir el SSE sin buffering."""

    from app.main import create_app

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    config = uvicorn.Config(
        create_app(), host="127.0.0.1", port=port, log_level="warning"
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(200):
        if server.started:
            break
        time.sleep(0.025)
    assert server.started, "uvicorn no arrancó para los tests SSE"

    yield f"http://127.0.0.1:{port}"

    server.should_exit = True
    thread.join(timeout=10)


@pytest.fixture(autouse=True)
def _reset_realtime_broker():
    from app.realtime.broker import reset_broker

    reset_broker()
    yield
    reset_broker()


@pytest.fixture(autouse=True)
def _clean_rfp_tables():
    if engine is None:
        yield
        return
    for model in (RfpDepartmentSection, RfpMetadata, RfpTicket):
        model.__table__.create(engine, checkfirst=True)
    with Session(engine) as session:
        session.exec(delete(RfpDepartmentSection))
        session.exec(delete(RfpMetadata))
        session.exec(delete(RfpTicket))
        session.commit()
    yield


@pytest.fixture(autouse=True)
def _isolated_raw_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("RFP_RAW_DIR", str(tmp_path / "raw"))
    yield


def _ticket(**overrides) -> RfpTicket:
    data = {
        "rfp_id": "RFP-20261115-ABC123",
        "raw_pdf_path": "/tmp/rfp.pdf",
        "original_filename": "rfp.pdf",
        "file_sha256": "0" * 64,
        "status": "analizando",
        "pipeline_stage": "encolado",
    }
    data.update(overrides)
    return RfpTicket(**data)


def _read_frame(lines, *, max_lines: int = 400) -> dict[str, str]:
    frame: dict[str, str] = {}
    for _ in range(max_lines):
        try:
            line = next(lines)
        except StopIteration:  # pragma: no cover - stream cerrado inesperadamente
            break
        if not line:
            if frame:
                return frame
            continue
        if line.startswith(":"):
            continue
        key, _, value = line.partition(":")
        frame[key.strip()] = value.strip()
    raise AssertionError(f"No se completó ningún frame SSE (parcial={frame!r}).")


def _read_event_frame(lines) -> dict[str, str]:
    for _ in range(10):
        frame = _read_frame(lines)
        if "event" in frame:
            return frame
    raise AssertionError("No llegó ningún frame con event:.")


def _read_line_matching(lines, expected: str, *, max_lines: int = 400) -> str:
    for _ in range(max_lines):
        line = next(lines)
        if line == expected:
            return line
    raise AssertionError(f"No llegó la línea {expected!r}.")


def _patch_task(monkeypatch):
    from app.tasks import rfp_intake as task_module

    class FakeResult:
        id = "task-rfp-sse"

    def fake_delay(ticket_id: str):
        return FakeResult()

    monkeypatch.setattr(task_module.process_rfp_ticket, "delay", fake_delay)


def test_stream_requires_the_backoffice_jwt(live_server):
    with httpx.Client(base_url=live_server, timeout=10) as http_client:
        missing = http_client.get("/realtime/stream")
        assert missing.status_code in (401, 403)
        assert "text/event-stream" not in missing.headers.get("content-type", "")

        invalid = http_client.get(
            "/realtime/stream", headers={"Authorization": "Bearer not-a-jwt"}
        )
        assert invalid.status_code == 401
        assert "text/event-stream" not in invalid.headers.get("content-type", "")


def test_stream_sets_sse_headers_and_retry_preamble(live_server, auth_headers):
    with httpx.Client(base_url=live_server, timeout=10) as http_client:
        with http_client.stream(
            "GET", "/realtime/stream", headers=auth_headers
        ) as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith(
                "text/event-stream"
            )
            assert "no-cache" in response.headers["cache-control"]
            assert response.headers["x-accel-buffering"] == "no"
            lines = response.iter_lines()
            assert next(lines) == "retry: 3000"


def test_stream_sends_keepalive_and_live_events(
    live_server, auth_headers, monkeypatch
):
    monkeypatch.setenv("SSE_KEEPALIVE_SECONDS", "0.1")
    broker = get_broker()

    with httpx.Client(base_url=live_server, timeout=10) as http_client:
        with http_client.stream(
            "GET", "/realtime/stream", headers=auth_headers
        ) as response:
            lines = response.iter_lines()
            assert next(lines) == "retry: 3000"
            # Sin eventos, la conexión sigue viva con comentarios keep-alive.
            assert _read_line_matching(lines, ": keep-alive") == ": keep-alive"

            broker.publish("rfp_ticket_created", rfp_ticket_payload(_ticket()))
            frame = _read_event_frame(lines)

    assert frame["event"] == "rfp_ticket_created"


def test_rfp_ticket_created_frame_matches_the_briefing_payload(
    live_server, auth_headers
):
    broker = get_broker()
    ticket = _ticket()
    payload = rfp_ticket_payload(ticket)
    published = broker.publish("rfp_ticket_created", payload)

    with httpx.Client(base_url=live_server, timeout=10) as http_client:
        with http_client.stream(
            "GET",
            "/realtime/stream",
            headers={**auth_headers, "Last-Event-ID": "0"},
        ) as response:
            frame = _read_event_frame(response.iter_lines())

    assert frame["event"] == "rfp_ticket_created"
    assert frame["id"] == str(published.id)
    data = json.loads(frame["data"])
    assert data == payload
    assert BRIEFING_FIELDS <= set(data)
    assert data["ticket_id"] == ticket.id
    assert data["rfp_id"] == ticket.rfp_id
    assert data["status"] == "analizando"
    assert data["client_name"] is None
    assert data["services_requested"] == []
    # Sin sobre anidado: el nombre va en `event:` y `data:` son campos del
    # ticket, no {"event", "data"}.
    assert "event" not in data
    assert "data" not in data


def test_last_event_id_replays_only_newer_events(live_server, auth_headers):
    broker = get_broker()
    first = broker.publish(
        "rfp_ticket_created", {"ticket_id": "t1", "status": "analizando"}
    )
    second = broker.publish(
        "rfp_ticket_created", {"ticket_id": "t2", "status": "analizando"}
    )

    with httpx.Client(base_url=live_server, timeout=10) as http_client:
        with http_client.stream(
            "GET",
            "/realtime/stream",
            headers={**auth_headers, "Last-Event-ID": str(first.id)},
        ) as response:
            frame = _read_event_frame(response.iter_lines())

    assert frame["id"] == str(second.id)
    assert json.loads(frame["data"])["ticket_id"] == "t2"


def test_upload_publishes_rfp_ticket_created(client, auth_headers, monkeypatch):
    from app.routes import rfp as rfp_route

    captured: list[RfpTicket] = []
    monkeypatch.setattr(
        rfp_route,
        "publish_rfp_ticket_created",
        lambda ticket: captured.append(ticket),
    )
    _patch_task(monkeypatch)

    response = client.post(
        "/rfp/tickets",
        headers=auth_headers,
        files={"file": ("rfp.pdf", MINIMAL_PDF, "application/pdf")},
    )

    assert response.status_code == 202, response.text
    assert len(captured) == 1
    ticket = captured[0]
    assert ticket.id == response.json()["ticket_id"]
    assert ticket.status == "analizando"
    assert ticket.pipeline_stage == "encolado"

    payload = rfp_ticket_payload(ticket)
    assert payload["status"] == "analizando"
    assert payload["client_name"] is None
    assert payload["client_country"] is None
    assert payload["services_requested"] == []


def test_repository_publishes_metadata_ready_once(monkeypatch):
    captured: list[dict] = []
    monkeypatch.setattr(
        rfp_service,
        "publish_rfp_ticket_metadata_ready",
        lambda ticket, metadata: captured.append(
            rfp_ticket_payload(ticket, metadata)
        ),
    )

    with Session(engine) as session:
        ticket = rfp_service.create_ticket(
            session,
            filename="rfp.pdf",
            pdf_path=Path("/tmp/rfp.pdf"),
            file_sha256="0" * 64,
        )
        ticket_id = ticket.id
        repo = rfp_service.SqlRfpRepository(session)
        metadata = {
            "client_name": "Northline Apparel",
            "client_country": "US",
            "services_requested": ["warehousing", "last_mile"],
            "currency": "USD",
        }
        repo.save_metadata(
            ticket.id, metadata=metadata, classification={"is_rfp": True}
        )
        # Una reejecución sin reset previo no debe reemitir el enriquecimiento.
        repo.save_metadata(
            ticket.id, metadata=metadata, classification={"is_rfp": True}
        )

    assert len(captured) == 1
    payload = captured[0]
    assert payload["ticket_id"] == ticket_id
    assert payload["status"] == "analizando"
    assert payload["client_name"] == "Northline Apparel"
    assert payload["client_country"] == "US"
    assert payload["services_requested"] == ["warehousing", "last_mile"]
    assert payload["currency"] == "USD"
