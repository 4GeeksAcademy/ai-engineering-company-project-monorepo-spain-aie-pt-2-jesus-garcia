"""CLI de consolidación de memoria.

Uso (desde ``services/api``):

    python -m app.agent.memory.consolidation

La consolidación también se ejecuta tras cada escritura y está expuesta en
``POST /agent/memory/consolidate`` para manager/admin.
"""

from __future__ import annotations

import json
import sys

from sqlmodel import Session

from database import engine

from .models import create_agent_memory_tables
from .store import consolidate


def main() -> int:
    if engine is None:
        print(
            "DATABASE_URL no está configurada; no hay store de memoria.",
            file=sys.stderr,
        )
        return 2
    create_agent_memory_tables(engine)
    with Session(engine) as session:
        counts = consolidate(session)
    print(json.dumps(counts, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
