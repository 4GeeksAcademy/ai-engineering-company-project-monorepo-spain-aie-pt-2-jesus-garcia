"""Guard de seguridad para seeders destructivos.

Los seeders de TrackFlow truncan/borran tablas antes de repoblarlas. Ejecutarlos
sin querer contra la base local habitual destruye datos existentes, por lo que
exigen confirmación explícita:

  - ``--force`` / ``--reset`` : confirma el truncado destructivo.
  - ``--dry-run``             : muestra el plan y sale sin escribir.
  - ``--allow-remote-db``     : permite operar sobre una ``DATABASE_URL`` remota
                                (p. ej. Supabase) o el env
                                ``TRACKFLOW_ALLOW_REMOTE_SEED=1``.
"""

import os
import sys
from argparse import ArgumentParser
from urllib.parse import urlsplit, urlunsplit

REMOTE_OVERRIDE_ENV = "TRACKFLOW_ALLOW_REMOTE_SEED"


def add_safety_flags(parser: ArgumentParser) -> None:
    """Registra los flags de seguridad comunes en un parser de argparse."""
    parser.add_argument(
        "--force",
        "--reset",
        dest="force",
        action="store_true",
        help="Confirma el truncado destructivo de las tablas afectadas.",
    )
    parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Muestra el plan y sale sin modificar datos.",
    )
    parser.add_argument(
        "--allow-remote-db",
        dest="allow_remote_db",
        action="store_true",
        help="Permite operar sobre una DATABASE_URL remota (p. ej. Supabase).",
    )


def mask_database_url(url: str | None) -> str:
    """Devuelve la URL sin credenciales para poder imprimirla con seguridad."""
    if not url:
        return "(sin DATABASE_URL)"
    try:
        parts = urlsplit(url)
    except ValueError:
        return "(DATABASE_URL oculta)"
    if not parts.password:
        return url
    host = parts.hostname or ""
    if parts.port:
        host = f"{host}:{parts.port}"
    user = parts.username or ""
    netloc = f"{user}:***@{host}" if user else host
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def is_remote_database_url(url: str | None) -> bool:
    """True si la URL parece una base remota (no local ni sqlite)."""
    if not url:
        return False
    lowered = url.strip().lower()
    if lowered.startswith("sqlite"):
        return False
    if "localhost" in lowered or "127.0.0.1" in lowered or "[::1]" in lowered:
        return False
    return True


def enforce_destructive_guard(
    *,
    force: bool,
    dry_run: bool,
    allow_remote_db: bool,
    database_url: str | None,
    tinydb_tables: list[str] | None = None,
    sql_tables: list[str] | None = None,
    description: str = "seed",
) -> None:
    """Imprime el plan y aborta si la ejecución no está confirmada.

    Orden: (1) aviso de base remota, (2) ``--dry-run``, (3) exigir ``--force``.
    Cualquier aborto usa ``SystemExit(2)`` y no toca datos.
    """
    tinydb_tables = tinydb_tables or []
    sql_tables = sql_tables or []

    # El guard remoto solo aplica si se van a tocar tablas SQL; las TinyDB viven
    # siempre en un fichero local, por lo que DATABASE_URL es irrelevante allí.
    remote = bool(sql_tables) and is_remote_database_url(database_url)
    override = os.getenv(REMOTE_OVERRIDE_ENV) == "1"
    remote_allowed = allow_remote_db or override

    print(f"[{description}] Plan de ejecución destructiva:")
    if tinydb_tables:
        print(f"  TinyDB (truncate): {', '.join(tinydb_tables)}")
    if sql_tables:
        print(f"  SQL (delete): {', '.join(sql_tables)}  → {mask_database_url(database_url)}")
    if not tinydb_tables and not sql_tables:
        print("  (sin tablas afectadas)")

    remote_block = remote and not remote_allowed
    if remote_block:
        print(
            f"\n[AVISO] DATABASE_URL apunta a una base remota y no es una base de "
            f"rendimiento:\n  {mask_database_url(database_url)}\n"
            f"Se requiere una base local (p. ej. DATABASE_URL=sqlite:///./perf_measure.db) "
            f"o --allow-remote-db / {REMOTE_OVERRIDE_ENV}=1."
        )

    if dry_run:
        print("\n[dry-run] No se ha modificado ningún dato.")
        raise SystemExit(0)

    if remote_block:
        print("\n[ABORTADO] Base remota no autorizada.")
        raise SystemExit(2)

    if not force:
        print(
            "\n[ABORTADO] Este seeder es destructivo (trunca y repuebla).\n"
            "Reejecútalo con --force (o --reset) para confirmar."
        )
        raise SystemExit(2)
