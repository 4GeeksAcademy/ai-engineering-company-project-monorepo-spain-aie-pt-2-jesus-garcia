"""Reproceso manual de un ticket RFP sin pasar por HTTP ni por Celery.

Uso:
    python scripts/rfp_reprocess.py --ticket-id <uuid>
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

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
    parser.add_argument("--ticket-id", required=True)
    parser.add_argument(
        "--json", action="store_true", help="Imprime el resultado completo"
    )
    args = parser.parse_args()

    if engine is None:
        print("DATABASE_URL no está configurada.", file=sys.stderr)
        return 2

    from app.services.rfp_service import SqlRfpRepository
    from data.pipelines.rfp_intake import run_rfp_intake

    with Session(engine) as session:
        repo = SqlRfpRepository(session)
        result = run_rfp_intake(args.ticket_id, repo)

    summary = {
        "ticket_id": args.ticket_id,
        "status": result.get("status"),
        "stage": result.get("stage"),
        "departments": [
            section["department_id"]
            for section in result.get("sections", {}).values()
        ],
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
