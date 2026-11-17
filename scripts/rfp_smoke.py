"""Smoke run del pipeline RFP sin UI, Redis ni Celery.

Crea un ticket real en la base configurada y ejecuta el pipeline de forma
síncrona. Útil para validar credenciales LLM y Supabase en local.

Uso:
    python scripts/rfp_smoke.py --pdf docs/workflows/rfp-requests/trackflow-request-1.pdf
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[1]
API_DIR = REPO_ROOT / "services" / "api"
sys.path.insert(0, str(API_DIR))
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(API_DIR / ".env")
load_dotenv(REPO_ROOT / ".env")

from sqlmodel import SQLModel, Session  # noqa: E402

from database import engine  # noqa: E402

if engine is not None:
    import models  # noqa: F401,E402

    SQLModel.metadata.create_all(engine)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if engine is None:
        print("DATABASE_URL no está configurada.", file=sys.stderr)
        return 2

    from app.services.rfp_service import (
        RfpUploadError,
        SqlRfpRepository,
        create_ticket,
        store_pdf_bytes,
    )
    from data.pipelines.rfp_intake import run_rfp_intake

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(f"No existe el PDF: {pdf_path}", file=sys.stderr)
        return 2

    ticket_id = str(uuid4())
    content = pdf_path.read_bytes()
    try:
        stored, filename, digest = store_pdf_bytes(
            ticket_id, pdf_path.name, content
        )
    except RfpUploadError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    with Session(engine) as session:
        ticket = create_ticket(
            session,
            filename=filename,
            pdf_path=stored,
            file_sha256=digest,
        )
        repo = SqlRfpRepository(session)
        rfp_id = ticket.rfp_id
        result = run_rfp_intake(ticket.id, repo)

    summary = {
        "ticket_id": ticket_id,
        "rfp_id": rfp_id,
        "status": result.get("status"),
        "stage": result.get("stage"),
        "departments": [
            section["department_id"]
            for section in result.get("sections", {}).values()
        ],
        "handoff": bool(result.get("handoff")),
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
