"""Tests del router HTTP de recepción de RFPs."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlmodel import Session, delete

from app.services.rfp_service import raw_base_dir
from database import engine
from models import RfpDepartmentSection, RfpMetadata, RfpTicket

MINIMAL_PDF = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF"


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


def _patch_task(monkeypatch):
    from app.tasks import rfp_intake as task_module

    calls: list[str] = []

    class FakeResult:
        id = "task-rfp-1"

    def fake_delay(ticket_id: str):
        calls.append(ticket_id)
        return FakeResult()

    monkeypatch.setattr(task_module.process_rfp_ticket, "delay", fake_delay)
    return calls


def test_upload_pdf_creates_ticket_and_enqueues(client, auth_headers, monkeypatch):
    calls = _patch_task(monkeypatch)

    response = client.post(
        "/rfp/tickets",
        headers=auth_headers,
        files={"file": ("rfp.pdf", MINIMAL_PDF, "application/pdf")},
    )

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "analizando"
    assert body["rfp_id"].startswith("RFP-")
    assert body["task_id"] == "task-rfp-1"
    assert calls == [body["ticket_id"]]

    stored = list(raw_base_dir().rglob("rfp.pdf"))
    assert len(stored) == 1
    assert stored[0].read_bytes() == MINIMAL_PDF

    detail = client.get(f"/rfp/tickets/{body['ticket_id']}", headers=auth_headers)
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["ticket_id"] == body["ticket_id"]
    assert payload["original_filename"] == "rfp.pdf"
    assert payload["pipeline_stage"] == "encolado"
    assert payload["metadata"] is None

    status = client.get(
        f"/rfp/tickets/{body['ticket_id']}/status", headers=auth_headers
    )
    assert status.status_code == 200
    assert status.json()["status"] == "analizando"
    assert status.json()["handoff_status"] == "none"


def test_upload_rejects_non_pdf(client, auth_headers, monkeypatch):
    _patch_task(monkeypatch)
    response = client.post(
        "/rfp/tickets",
        headers=auth_headers,
        files={"file": ("notes.txt", b"no soy un pdf", "text/plain")},
    )
    assert response.status_code == 400
    assert "PDF" in response.json()["detail"]


def test_upload_requires_manager_role(client, user_headers, monkeypatch):
    _patch_task(monkeypatch)
    response = client.post(
        "/rfp/tickets",
        headers=user_headers,
        files={"file": ("rfp.pdf", MINIMAL_PDF, "application/pdf")},
    )
    assert response.status_code == 403


def test_list_tickets_and_handoff_409(client, auth_headers, monkeypatch):
    _patch_task(monkeypatch)
    created = client.post(
        "/rfp/tickets",
        headers=auth_headers,
        files={"file": ("rfp.pdf", MINIMAL_PDF, "application/pdf")},
    ).json()

    listing = client.get("/rfp/tickets", headers=auth_headers)
    assert listing.status_code == 200
    assert [item["ticket_id"] for item in listing.json()] == [created["ticket_id"]]

    handoff = client.get(
        f"/rfp/handoff/{created['ticket_id']}", headers=auth_headers
    )
    assert handoff.status_code == 409


def test_detail_404_for_unknown_ticket(client, auth_headers):
    response = client.get("/rfp/tickets/no-existe", headers=auth_headers)
    assert response.status_code == 404


def test_raw_dir_is_under_data_raw_by_default(monkeypatch):
    monkeypatch.delenv("RFP_RAW_DIR", raising=False)
    path = raw_base_dir()
    assert path.parts[-3:] == ("data", "raw", "rfp")
    assert Path(path).name == "rfp"


def test_upload_rate_limit_returns_429(client, auth_headers, monkeypatch):
    from app.core.rate_limit import reset_rate_limits

    _patch_task(monkeypatch)
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "1")
    reset_rate_limits()

    statuses = [
        client.post(
            "/rfp/tickets",
            headers=auth_headers,
            files={"file": ("rfp.pdf", MINIMAL_PDF, "application/pdf")},
        ).status_code
        for _ in range(11)
    ]

    assert statuses[-1] == 429
