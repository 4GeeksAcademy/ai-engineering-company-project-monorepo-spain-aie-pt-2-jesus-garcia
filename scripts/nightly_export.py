#!/usr/bin/env python3
"""Export nocturno de telemetría + disparo del pipeline de desempeño.

Ciclo de vida (la fila existe como estado, no solo como dato)::

    pending → processing → completed
                        ↘ failed

Reglas que implementa:

* la fila ``pending`` se crea **antes** de cualquier trabajo;
* el paso a ``processing`` se confirma **antes** del trabajo real;
* ``completed`` solo tras exportar y terminar el pipeline con éxito;
* ``failed`` ante cualquier error, con el diagnóstico guardado;
* ``processing`` huérfano (proceso muerto) se reconcilia a ``failed``;
* lock vía ``processing`` y idempotencia vía (``job_name``, ``target_date``).

Uso::

    python scripts/nightly_export.py
    python scripts/nightly_export.py --target-date 2026-10-29
    python scripts/nightly_export.py --dry-run
    python scripts/nightly_export.py --reconcile-only

Exit codes: 0 = completed / skipped / blocked, 1 = failed, 2 = configuración.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402
from sqlalchemy import bindparam, text  # noqa: E402
from sqlalchemy.exc import SQLAlchemyError  # noqa: E402
from sqlalchemy.types import DateTime  # noqa: E402
from sqlmodel import Session  # noqa: E402

from services.job_runner.db import get_engine  # noqa: E402
from services.job_runner.logs import JobLogger, configure_logging  # noqa: E402
from services.job_runner.models import (  # noqa: E402
    JOB_NAME_NIGHTLY_EXPORT,
    JobRun,
)
from services.job_runner.repository import (  # noqa: E402
    create_pending,
    get_run,
    has_completed_for_date,
    has_processing_lock,
    mark_completed,
    mark_failed,
    mark_processing,
    reconcile_stale_processing,
)

# El `.env` raíz es el que usa docker compose; `services/api/.env` cubre la
# ejecución local desde el venv de la API. Ninguno sobreescribe el entorno.
for _candidate in (REPO_ROOT / ".env", REPO_ROOT / "services" / "api" / ".env"):
    if _candidate.exists():
        load_dotenv(_candidate, override=False)

JOB_NAME = JOB_NAME_NIGHTLY_EXPORT
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "raw"
PIPELINE_ENTRYPOINT = REPO_ROOT / "data" / "pipelines" / "pipeline.py"

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_CONFIG = 2

#: Columnas del snapshot (mismo orden que la tabla de origen).
CSV_COLUMNS: tuple[str, ...] = (
    "event_id",
    "timestamp",
    "received_at",
    "event_type",
    "service",
    "session_id",
    "user_id",
    "schema_version",
    "request_id",
    "source",
    "tags",
)

SELECT_EVENTS_SQL = """
    select event_id, timestamp, received_at, event_type, service, session_id,
           user_id, schema_version, request_id, source, tags
    from telemetry_events
    where timestamp >= :start and timestamp < :end
    order by timestamp, event_id
"""

#: El tipo explícito del bind permite que SQLite y PostgreSQL compartan la
#: misma consulta (SQLite necesita convertir el datetime a texto).
SELECT_EVENTS = text(SELECT_EVENTS_SQL).bindparams(
    bindparam("start", type_=DateTime(timezone=True)),
    bindparam("end", type_=DateTime(timezone=True)),
)


class ConfigError(RuntimeError):
    """Configuración inválida (exit 2, sin tocar la BD)."""


class ExportError(RuntimeError):
    """No se pudo generar el snapshot CSV."""


class PipelineError(RuntimeError):
    """El pipeline lanzado como subproceso falló o expiró."""


@dataclass(frozen=True)
class ExportResult:
    path: Path
    rows: int | None
    skipped: bool


# --------------------------------------------------------------------------- #
# Configuración
# --------------------------------------------------------------------------- #


def resolve_target_date(raw: str | None = None) -> date:
    """``TARGET_DATE`` (YYYY-MM-DD) o ayer en UTC."""

    value = raw if raw is not None else os.getenv("TARGET_DATE")
    value = (value or "").strip()
    if not value:
        return datetime.now(timezone.utc).date() - timedelta(days=1)
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ConfigError(
            f"TARGET_DATE inválida: {value!r} (formato esperado YYYY-MM-DD)"
        ) from exc


def _int_env(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} debe ser un entero, recibido {raw!r}") from exc


def stale_minutes() -> int:
    return _int_env("JOB_STALE_MINUTES", 60)


def pipeline_timeout_seconds() -> int:
    return _int_env("PIPELINE_TIMEOUT_SECONDS", 1800)


# --------------------------------------------------------------------------- #
# Exportación a CSV
# --------------------------------------------------------------------------- #


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _csv_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return _as_utc(value).isoformat()
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def export_day(
    session: Session,
    target_date: date,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
) -> ExportResult:
    """Exporta el día UTC ``target_date`` a ``telemetry_<date>.csv``.

    Si el archivo ya existe **no se sobrescribe** (snapshot de auditoría) y se
    devuelve ``skipped=True``.
    """

    output_dir = Path(output_dir)
    path = output_dir / f"telemetry_{target_date.isoformat()}.csv"
    if path.exists():
        return ExportResult(path=path, rows=None, skipped=True)

    start = datetime.combine(target_date, time.min, tzinfo=timezone.utc)
    end = start + timedelta(days=1)

    try:
        rows = (
            session.execute(SELECT_EVENTS, {"start": start, "end": end})
            .mappings()
            .all()
        )
    except SQLAlchemyError as exc:
        raise ExportError(
            "no se pudo leer telemetry_events: "
            f"{type(exc).__name__}: {exc}"
        ) from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    try:
        with tmp_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(CSV_COLUMNS)
            for row in rows:
                writer.writerow([_csv_value(row[column]) for column in CSV_COLUMNS])
        os.replace(tmp_path, path)
    except OSError as exc:
        tmp_path.unlink(missing_ok=True)
        raise ExportError(f"no se pudo escribir {path}: {exc}") from exc

    return ExportResult(path=path, rows=len(rows), skipped=False)


# --------------------------------------------------------------------------- #
# Pipeline como subproceso
# --------------------------------------------------------------------------- #


def _tail(value, limit: int = 800) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    return " ".join(str(value).split())[-limit:]


_EXCEPTION_LINE = re.compile(
    r"^[\w.]*(?:Error|Exception|Exit)\b.*", re.MULTILINE
)


def _error_summary(stderr, stdout) -> str:
    """Línea de excepción más útil de un traceback (no la cola del stack)."""

    text = (stderr or "").strip() or (stdout or "").strip()
    if not text:
        return ""
    matches = _EXCEPTION_LINE.findall(text)
    if matches:
        return " ".join(matches[-1].split())[-500:]
    return _tail(text, 500)


def run_pipeline(
    *, repo_root: Path | str = REPO_ROOT, timeout: int | None = None
) -> int:
    """Lanza ``pipeline.py run --lookback 1`` y devuelve el returncode."""

    timeout = timeout if timeout is not None else pipeline_timeout_seconds()
    command = [
        sys.executable,
        str(Path(repo_root) / "data" / "pipelines" / "pipeline.py"),
        "run",
        "--lookback",
        "1",
        "--json",
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=os.environ.copy(),
        )
    except subprocess.TimeoutExpired as exc:
        raise PipelineError(
            f"timeout tras {timeout}s: {_tail(exc.stderr) or _tail(exc.stdout)}"
        ) from exc
    except OSError as exc:
        raise PipelineError(f"no se pudo lanzar el pipeline: {exc}") from exc

    if completed.returncode != 0:
        detail = _error_summary(completed.stderr, completed.stdout)
        raise PipelineError(f"rc={completed.returncode} {detail}".strip())
    return completed.returncode


# --------------------------------------------------------------------------- #
# Ciclo de vida
# --------------------------------------------------------------------------- #


def _mark_failed_safely(
    session: Session, run_id: int, exc: BaseException, log: JobLogger
) -> None:
    message = f"{type(exc).__name__}: {exc}"
    try:
        session.rollback()
    except Exception:  # pragma: no cover - la sesión ya está inservible
        pass
    try:
        mark_failed(session, run_id, message)
    except Exception as db_exc:  # pragma: no cover - BD caída
        log.error(
            "failed",
            f"no se pudo persistir el estado failed ({type(db_exc).__name__})",
            run_id=run_id,
        )
    log.error("failed", _tail(message), run_id=run_id)


def _ensure_terminal(session: Session, run_id: int, log: JobLogger) -> None:
    """Red de seguridad: ninguna fila queda en ``processing``."""

    try:
        row = get_run(session, run_id)
        if row is not None and row.status == "processing":
            mark_failed(
                session, run_id, "interrupted: ejecución sin estado terminal"
            )
            log.error(
                "failed",
                "estado processing residual convertido a failed",
                run_id=run_id,
            )
    except Exception:  # pragma: no cover - la BD ya no responde
        pass


def run(
    target_date: date,
    *,
    engine=None,
    export_fn=export_day,
    pipeline_fn=run_pipeline,
    log: JobLogger | None = None,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    stale_age_minutes: int | None = None,
) -> int:
    """Ejecuta el ciclo completo para ``target_date`` y devuelve el exit code."""

    log = log or JobLogger(JOB_NAME)
    engine = engine or get_engine()
    max_age = (
        stale_age_minutes if stale_age_minutes is not None else stale_minutes()
    )

    with Session(engine) as session:
        recovered = reconcile_stale_processing(
            session, JOB_NAME, max_age_minutes=max_age
        )
        for row in recovered:
            log.warning(
                "failed",
                "processing huérfano reconciliado",
                target_date=row.target_date,
                run_id=row.id,
            )

        if has_processing_lock(session, JOB_NAME):
            log.info(
                "blocked",
                "ya hay una ejecución en processing; se cancela esta",
                target_date=target_date,
            )
            return EXIT_OK

        if has_completed_for_date(session, JOB_NAME, target_date):
            log.info(
                "skipped",
                "target_date ya completada; no se reexporta ni se relanza",
                target_date=target_date,
            )
            return EXIT_OK

        run_row: JobRun | None = None
        try:
            run_row = create_pending(session, JOB_NAME, target_date)
            log.info(
                "pending",
                "registro creado antes de empezar el trabajo",
                target_date=target_date,
                run_id=run_row.id,
            )

            if not mark_processing(session, run_row.id):
                mark_failed(
                    session,
                    run_row.id,
                    "lock no adquirido: otra ejecución está en processing",
                )
                log.info(
                    "blocked",
                    "no se pudo adquirir el lock (carrera con otra ejecución)",
                    target_date=target_date,
                    run_id=run_row.id,
                )
                return EXIT_OK

            log.info(
                "processing",
                "trabajo iniciado",
                target_date=target_date,
                run_id=run_row.id,
            )

            result = export_fn(session, target_date, output_dir)
            if result.skipped:
                log.info(
                    "processing",
                    "csv existente; no se sobrescribe el snapshot",
                    target_date=target_date,
                    run_id=run_row.id,
                    path=result.path,
                )
            else:
                log.info(
                    "processing",
                    f"csv escrito rows={result.rows}",
                    target_date=target_date,
                    run_id=run_row.id,
                    path=result.path,
                )

            pipeline_rc = pipeline_fn()
            if pipeline_rc != 0:
                raise PipelineError(f"pipeline rc={pipeline_rc}")

            mark_completed(session, run_row.id)
            log.info(
                "completed",
                "export + pipeline OK",
                target_date=target_date,
                run_id=run_row.id,
                rows="unchanged" if result.skipped else result.rows,
                pipeline_rc=pipeline_rc,
            )
            return EXIT_OK
        except Exception as exc:
            if run_row is not None:
                _mark_failed_safely(session, run_row.id, exc, log)
            else:
                log.error("failed", f"{type(exc).__name__}: {exc}")
            return EXIT_FAILED
        except BaseException as exc:
            # SIGTERM/SIGINT/SystemExit: se registra el fallo y se propaga.
            if run_row is not None:
                _mark_failed_safely(session, run_row.id, exc, log)
            raise
        finally:
            if run_row is not None:
                _ensure_terminal(session, run_row.id, log)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def _parse_iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"fecha inválida: {value!r} (formato YYYY-MM-DD)"
        ) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python scripts/nightly_export.py",
        description=(
            "Exporta la telemetría del día a data/raw/ y lanza el pipeline de "
            "desempeño, con el ciclo de vida registrado en job_runs."
        ),
    )
    parser.add_argument(
        "--target-date",
        type=_parse_iso_date,
        default=None,
        help="Día UTC a exportar (YYYY-MM-DD). Por defecto: TARGET_DATE o ayer.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directorio del CSV (por defecto data/raw).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Muestra el plan sin escribir en la BD ni exportar.",
    )
    parser.add_argument(
        "--reconcile-only",
        action="store_true",
        help="Solo reconcilia filas processing huérfanas y sale.",
    )
    return parser


def _handle_sigterm(signum, frame):  # pragma: no cover - se prueba con SIGTERM real
    raise SystemExit(128 + signum)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure_logging(os.getenv("LOG_LEVEL", "INFO").upper())
    log = JobLogger(JOB_NAME)

    try:
        target_date = args.target_date or resolve_target_date()
        max_age = stale_minutes()
        timeout = pipeline_timeout_seconds()
    except ConfigError as exc:
        log.error("failed", f"configuración inválida: {exc}")
        return EXIT_CONFIG

    output_dir = Path(args.output_dir)

    if args.dry_run:
        plan = {
            "job_name": JOB_NAME,
            "target_date": target_date.isoformat(),
            "output": str(output_dir / f"telemetry_{target_date.isoformat()}.csv"),
            "pipeline": f"{PIPELINE_ENTRYPOINT} run --lookback 1 --json",
            "stale_minutes": max_age,
            "pipeline_timeout_seconds": timeout,
            "dry_run": True,
        }
        log.info("pending", "dry-run: sin escrituras", target_date=target_date)
        print(json.dumps(plan, indent=2))
        return EXIT_OK

    try:
        engine = get_engine()
    except Exception as exc:
        log.error("failed", f"configuración inválida: {exc}")
        return EXIT_CONFIG

    signal.signal(signal.SIGTERM, _handle_sigterm)

    if args.reconcile_only:
        with Session(engine) as session:
            recovered = reconcile_stale_processing(
                session, JOB_NAME, max_age_minutes=max_age
            )
        log.info(
            "completed",
            f"reconcile-only recovered={len(recovered)}",
            target_date=target_date,
        )
        return EXIT_OK

    return run(
        target_date,
        engine=engine,
        output_dir=output_dir,
        log=log,
        stale_age_minutes=max_age,
    )


if __name__ == "__main__":
    raise SystemExit(main())
