"""Lógica pura del pipeline semanal (sin dependencias de Prefect).

``execute_week`` es el orquestador que usan tanto el CLI como el flow de
Prefect. Las etapas se inyectan como callables (``WeekSteps``) para que la
versión de Prefect pueda sustituirlas por tasks sin duplicar la secuencia.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import json
import logging
import math
from typing import Any, Callable
from uuid import uuid4

import pandas as pd
from sqlalchemy import Engine, delete, func, insert, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .alerts import send_alert
from .db import get_engine
from .locks import week_lock
from .schema import sku_config_table, stock_table, telemetry_table
from .settings import (
    DEFAULT_LOOKBACK_WEEKS,
    DISCREPANCY,
    EVENT_TYPES,
    INBOUND,
    OUTBOUND,
    PIPELINE_NAME,
    PIPELINE_VERSION,
    REJECT_BLOCK_RATE,
    REJECT_MIN_ROWS_FOR_BLOCK,
    REJECT_WARN_RATE,
    STOCKOUT,
    WAREHOUSES,
)
from .sql import tables_for

logger = logging.getLogger("pipeline.weekly_performance")


# ---------------------------------------------------------------------------
# Tipos de resultado
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NormalizeResult:
    valid: list[dict]
    rejects: list[dict]
    duplicates: int


@dataclass(frozen=True)
class QualityReport:
    status: str
    blockers: list[str]
    warnings: list[str]
    summary: str
    reject_rate: float = 0.0

    @property
    def passed(self) -> bool:
        return self.status != "failed"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class WeekResult:
    run_id: str
    week_start: date
    status: str
    rows_extracted: int = 0
    rows_valid: int = 0
    rows_rejected: int = 0
    rows_written: int = 0
    quality_status: str | None = None
    error: str | None = None
    skipped_reason: str | None = None
    source_fingerprint: str | None = None

    def to_dict(self) -> dict:
        data = asdict(self)
        data["week_start"] = self.week_start.isoformat()
        return data


@dataclass(frozen=True)
class WeekSteps:
    extract: Callable[[date], list[dict]]
    normalize: Callable[[list[dict], date], NormalizeResult]
    aggregate: Callable[[list[dict]], list[dict]]
    quality: Callable[..., QualityReport]
    load: Callable[[list[dict], date, str], int]
    reconcile: Callable[[list[dict], date], int]


# ---------------------------------------------------------------------------
# Ventana temporal
# ---------------------------------------------------------------------------


def resolve_target_weeks(
    lookback_weeks: int = DEFAULT_LOOKBACK_WEEKS,
    today: date | None = None,
) -> list[date]:
    """Semanas ISO cerradas a procesar, de la más reciente a la más antigua.

    La semana en curso nunca se procesa: el lunes se calcula la última semana
    cerrada (la que empezó 7 días antes del lunes actual).
    """

    if not 1 <= lookback_weeks <= 12:
        raise ValueError("lookback_weeks debe estar entre 1 y 12")

    today = today or datetime.now(timezone.utc).date()
    this_monday = today - timedelta(days=today.isoweekday() - 1)
    last_closed = this_monday - timedelta(days=7)
    return [last_closed - timedelta(days=7 * i) for i in range(lookback_weeks)]


def week_bounds(week_start: date) -> tuple[datetime, datetime]:
    start = datetime.combine(week_start, time.min, tzinfo=timezone.utc)
    return start, start + timedelta(days=7)


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------


def extract_week(engine: Engine, week_start: date) -> list[dict]:
    """Lee solo los 4 tipos obligatorios de la semana (push-down SQL)."""

    start, end = week_bounds(week_start)
    table = telemetry_table()
    stmt = (
        select(
            table.c.event_id,
            table.c.event_type,
            table.c.timestamp,
            table.c.received_at,
            table.c.tags,
        )
        .where(
            table.c.event_type.in_(EVENT_TYPES),
            table.c.timestamp >= start,
            table.c.timestamp < end,
        )
        .order_by(table.c.timestamp, table.c.event_id)
    )
    with engine.connect() as conn:
        rows = conn.execute(stmt).mappings().all()
    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Normalize / validate
# ---------------------------------------------------------------------------


def _clean(value: Any) -> str:
    return str(value).strip().lower() if value is not None else ""


def _as_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) else number


def normalize_validate(rows: list[dict], week_start: date) -> NormalizeResult:
    """Normaliza, deduplica por ``event_id`` y separa válidos de cuarentena."""

    valid: list[dict] = []
    rejects: list[dict] = []
    seen: set[str] = set()
    duplicates = 0

    for row in rows:
        event_id = str(row.get("event_id") or "")
        if not event_id:
            rejects.append(_reject(row, "missing_event_id"))
            continue
        if event_id in seen:
            duplicates += 1
            continue
        seen.add(event_id)

        event_type = row.get("event_type")
        tags = row.get("tags")
        if not isinstance(tags, dict):
            rejects.append(_reject(row, "invalid_tags"))
            continue

        warehouse = _clean(tags.get("warehouse"))
        client_id = _clean(tags.get("client_id"))
        if warehouse not in WAREHOUSES:
            rejects.append(_reject(row, "invalid_warehouse"))
            continue
        if not client_id:
            rejects.append(_reject(row, "missing_client_id"))
            continue

        quantity = _as_number(tags.get("quantity"))
        if event_type == INBOUND:
            if quantity is None or quantity < 0:
                rejects.append(_reject(row, "invalid_quantity"))
                continue
        elif quantity is not None and quantity < 0:
            rejects.append(_reject(row, "invalid_quantity"))
            continue

        order_id = tags.get("order_id")
        if event_type == DISCREPANCY and order_id in (None, ""):
            rejects.append(_reject(row, "missing_order_id"))
            continue

        valid.append(
            {
                "event_id": event_id,
                "event_type": event_type,
                "timestamp": row.get("timestamp"),
                "warehouse": warehouse,
                "client_id": client_id,
                "quantity": quantity,
                "order_id": order_id,
                # Clave para D1: un pedido cuenta una vez aunque tenga varios eventos.
                "order_key": str(order_id) if order_id not in (None, "") else event_id,
            }
        )

    return NormalizeResult(valid=valid, rejects=rejects, duplicates=duplicates)


def _reject(row: dict, reason: str) -> dict:
    return {
        "event_id": str(row.get("event_id") or ""),
        "reason": reason,
        "payload": {
            "event_type": row.get("event_type"),
            "tags": row.get("tags"),
            "timestamp": _iso(row.get("timestamp")),
        },
    }


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------


def aggregate_kpis(valid_rows: list[dict]) -> list[dict]:
    """Agrupa por almacén y cliente y calcula los 5 campos del briefing."""

    if not valid_rows:
        return []

    frame = pd.DataFrame(valid_rows)
    result: list[dict] = []

    for (warehouse, client_id), group in frame.groupby(
        ["warehouse", "client_id"], sort=True
    ):
        event_types = group["event_type"]
        inbound = group.loc[event_types == INBOUND, "quantity"].dropna().sum()
        outbound = group.loc[event_types == OUTBOUND]
        outbound_count = int(outbound["order_key"].nunique())
        stockout_count = int((event_types == STOCKOUT).sum())
        discrepancy_count = int((event_types == DISCREPANCY).sum())
        rate = (
            round(discrepancy_count / outbound_count, 6) if outbound_count else 0.0
        )
        result.append(
            {
                "warehouse": str(warehouse),
                "client_id": str(client_id),
                "inbound_units_count": int(round(float(inbound))),
                "outbound_orders_count": outbound_count,
                "stockout_events_count": stockout_count,
                "discrepancy_events_count": discrepancy_count,
                "discrepancy_rate": rate,
            }
        )

    return result


def count_duplicate_order_ids(valid_rows: list[dict]) -> int:
    """Eventos de salida extra para un mismo ``order_id`` (señal G12)."""

    order_ids = [
        row["order_key"]
        for row in valid_rows
        if row.get("event_type") == OUTBOUND
    ]
    counts = Counter(order_ids)
    return sum(count - 1 for count in counts.values() if count > 1)


# ---------------------------------------------------------------------------
# Quality gates
# ---------------------------------------------------------------------------


def evaluate_quality(
    kpis: list[dict],
    *,
    rejects: int,
    total_rows: int,
    week_start: date,
    duplicate_order_ids: int = 0,
    instrumentation_since: date | None = None,
    previous_kpis: list[dict] | None = None,
    source_freshness_hours: float | None = None,
    reject_reasons: dict[str, int] | None = None,
    configuration_gaps: dict | None = None,
) -> QualityReport:
    blockers: list[str] = []
    warnings: list[str] = []
    reject_rate = (rejects / total_rows) if total_rows else 0.0

    seen_keys: set[tuple[str, str]] = set()
    for row in kpis:
        key = (row["warehouse"], row["client_id"])
        if key in seen_keys:
            blockers.append(f"duplicate_key:{key[0]}/{key[1]}")
        seen_keys.add(key)

        if row["warehouse"] not in WAREHOUSES:
            blockers.append(f"invalid_warehouse:{row['warehouse']}")
        for field in (
            "inbound_units_count",
            "outbound_orders_count",
            "stockout_events_count",
            "discrepancy_events_count",
        ):
            if int(row[field]) < 0:
                blockers.append(f"negative_{field}:{key[0]}/{key[1]}")
        if not 0 <= float(row["discrepancy_rate"]) <= 1:
            blockers.append(f"invalid_discrepancy_rate:{key[0]}/{key[1]}")

    if not kpis:
        warnings.append("empty_week")
        if reject_reasons and set(reject_reasons) == {"missing_client_id"}:
            blockers.append("client_mapping_missing")

    if configuration_gaps:
        without_client = int(configuration_gaps.get("without_client", 0))
        without_min_stock = int(configuration_gaps.get("without_min_stock", 0))
        if without_client or without_min_stock:
            warnings.append(
                "configuration_gaps:"
                f"client={without_client},min_stock={without_min_stock}"
            )

    if total_rows and reject_rate > REJECT_BLOCK_RATE:
        if total_rows >= REJECT_MIN_ROWS_FOR_BLOCK:
            blockers.append(f"reject_rate:{reject_rate:.2%}")
        else:
            warnings.append(f"reject_rate_small_sample:{reject_rate:.2%}")
    elif total_rows and reject_rate > REJECT_WARN_RATE:
        warnings.append(f"reject_rate:{reject_rate:.2%}")

    if (
        instrumentation_since
        and week_start >= instrumentation_since
        and kpis
        and all(
            row["stockout_events_count"] == 0
            and row["discrepancy_events_count"] == 0
            for row in kpis
        )
    ):
        blockers.append("instrumentation_missing")

    if duplicate_order_ids:
        warnings.append(f"duplicate_order_ids:{duplicate_order_ids}")

    if previous_kpis:
        previous_inbound = sum(
            int(row["inbound_units_count"]) for row in previous_kpis
        )
        current_inbound = sum(int(row["inbound_units_count"]) for row in kpis)
        if previous_inbound > 0:
            variation = (current_inbound - previous_inbound) / previous_inbound
            if abs(variation) > 0.5:
                warnings.append(f"volume_variation:{variation:+.0%}")

        previous_active = len(previous_kpis)
        if previous_active > 0:
            drop = (previous_active - len(kpis)) / previous_active
            if drop > 0.3:
                warnings.append(f"active_combinations_drop:{drop:.0%}")

    if source_freshness_hours is not None and source_freshness_hours > 24:
        warnings.append(f"stale_source:{source_freshness_hours:.1f}h")

    if blockers:
        status = "failed"
    elif warnings:
        status = "warning"
    else:
        status = "passed"

    summary = "; ".join(blockers + warnings) if (blockers or warnings) else "ok"
    return QualityReport(
        status=status,
        blockers=blockers,
        warnings=warnings,
        summary=summary,
        reject_rate=reject_rate,
    )


# ---------------------------------------------------------------------------
# Load / reconcile
# ---------------------------------------------------------------------------


def load_week(
    engine: Engine,
    kpis: list[dict],
    week_start: date,
    run_id: str | None = None,
) -> int:
    """Upsert atómico por ``(warehouse, client_id, week_start)``."""

    if week_start.isoweekday() != 1:
        raise ValueError(f"{week_start} no es lunes (week_start debe ser lunes)")

    if not kpis:
        return 0

    tables = tables_for(engine)
    now = datetime.now(timezone.utc)
    rows = [
        {
            "id": str(uuid4()),
            "warehouse": row["warehouse"],
            "client_id": row["client_id"],
            "week_start": week_start,
            "inbound_units_count": int(row["inbound_units_count"]),
            "outbound_orders_count": int(row["outbound_orders_count"]),
            "stockout_events_count": int(row["stockout_events_count"]),
            "discrepancy_events_count": int(row["discrepancy_events_count"]),
            "discrepancy_rate": float(row["discrepancy_rate"]),
            "computed_at": now,
        }
        for row in kpis
    ]

    dialect = engine.dialect.name
    if dialect == "postgresql":
        base = postgresql_insert(tables.performance)
    elif dialect == "sqlite":
        base = sqlite_insert(tables.performance)
    else:
        base = None

    if base is None:
        stmt = insert(tables.performance)
    else:
        update_columns = {
            "inbound_units_count": base.excluded.inbound_units_count,
            "outbound_orders_count": base.excluded.outbound_orders_count,
            "stockout_events_count": base.excluded.stockout_events_count,
            "discrepancy_events_count": base.excluded.discrepancy_events_count,
            "discrepancy_rate": base.excluded.discrepancy_rate,
            "computed_at": base.excluded.computed_at,
        }
        stmt = base.on_conflict_do_update(
            index_elements=["warehouse", "client_id", "week_start"],
            set_=update_columns,
        )

    with engine.begin() as conn:
        conn.execute(stmt, rows)
    return len(rows)


def reconcile_week(engine: Engine, kpis: list[dict], week_start: date) -> int:
    """Elimina combinaciones de la semana que ya no existen en la fuente."""

    tables = tables_for(engine)
    keys = [(row["warehouse"], row["client_id"]) for row in kpis]

    stmt = delete(tables.performance).where(
        tables.performance.c.week_start == week_start
    )
    if keys:
        stmt = stmt.where(
            tuple_(
                tables.performance.c.warehouse,
                tables.performance.c.client_id,
            ).notin_(keys)
        )

    with engine.begin() as conn:
        result = conn.execute(stmt)
    return int(result.rowcount or 0)


# ---------------------------------------------------------------------------
# Ledger, watermarks y congelación
# ---------------------------------------------------------------------------


def compute_fingerprint(rows: list[dict]) -> str:
    payload = {
        "count": len(rows),
        "max_event_id": max((str(r.get("event_id")) for r in rows), default=None),
        "max_timestamp": _max_iso(rows, "timestamp"),
        "max_received_at": _max_iso(rows, "received_at"),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def _max_iso(rows: list[dict], field: str) -> str | None:
    values = [_iso(row.get(field)) for row in rows if row.get(field) is not None]
    return max(values) if values else None


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def start_run(
    engine: Engine,
    run_id: str,
    week_start: date,
    triggered_by: str,
    instrumentation_since: date | None = None,
) -> None:
    tables = tables_for(engine)
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        conn.execute(
            insert(tables.runs).values(
                run_id=run_id,
                pipeline_name=PIPELINE_NAME,
                week_start=week_start,
                status="running",
                triggered_by=triggered_by,
                started_at=now,
                heartbeat_at=now,
                code_version=PIPELINE_VERSION,
                instrumentation_since=instrumentation_since,
            )
        )


def finish_run(
    engine: Engine,
    run_id: str,
    *,
    status: str,
    rows_extracted: int = 0,
    rows_valid: int = 0,
    rows_rejected: int = 0,
    rows_written: int = 0,
    source_fingerprint: str | None = None,
    quality_status: str | None = None,
    error_message: str | None = None,
) -> None:
    tables = tables_for(engine)
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        conn.execute(
            update(tables.runs)
            .where(tables.runs.c.run_id == run_id)
            .values(
                status=status,
                finished_at=now,
                heartbeat_at=now,
                rows_extracted=rows_extracted,
                rows_valid=rows_valid,
                rows_rejected=rows_rejected,
                rows_written=rows_written,
                source_fingerprint=source_fingerprint,
                quality_status=quality_status,
                error_message=(error_message or "")[:2048] or None,
            )
        )


def record_step(
    engine: Engine,
    run_id: str,
    step: str,
    status: str,
    started_at: datetime,
    *,
    detail: dict | None = None,
) -> None:
    tables = tables_for(engine)
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        conn.execute(
            insert(tables.steps).values(
                run_id=run_id,
                step=step,
                status=status,
                started_at=started_at,
                finished_at=now,
                detail=detail,
            )
        )
        conn.execute(
            update(tables.runs)
            .where(tables.runs.c.run_id == run_id)
            .values(heartbeat_at=now)
        )


def is_frozen(engine: Engine, week_start: date) -> bool:
    tables = tables_for(engine)
    with engine.connect() as conn:
        row = conn.execute(
            select(tables.published.c.frozen).where(
                tables.published.c.week_start == week_start
            )
        ).first()
    return bool(row and row[0])


def should_skip(engine: Engine, week_start: date, fingerprint: str) -> bool:
    tables = tables_for(engine)
    with engine.connect() as conn:
        row = conn.execute(
            select(tables.watermarks.c.source_fingerprint).where(
                tables.watermarks.c.week_start == week_start
            )
        ).first()
    return bool(row and row[0] == fingerprint)


def save_watermark(
    engine: Engine,
    week_start: date,
    run_id: str,
    fingerprint: str,
    rows_written: int,
) -> None:
    tables = tables_for(engine)
    now = datetime.now(timezone.utc)
    values = {
        "week_start": week_start,
        "last_run_id": run_id,
        "source_fingerprint": fingerprint,
        "rows_written": rows_written,
        "computed_at": now,
    }
    dialect = engine.dialect.name
    if dialect == "postgresql":
        stmt = postgresql_insert(tables.watermarks).on_conflict_do_update(
            index_elements=["week_start"], set_=values
        )
    elif dialect == "sqlite":
        stmt = sqlite_insert(tables.watermarks).on_conflict_do_update(
            index_elements=["week_start"], set_=values
        )
    else:
        stmt = insert(tables.watermarks)
    with engine.begin() as conn:
        conn.execute(stmt, values)


def store_rejects(
    engine: Engine, run_id: str, week_start: date, rejects: list[dict]
) -> None:
    if not rejects:
        return
    tables = tables_for(engine)
    now = datetime.now(timezone.utc)
    rows = [
        {
            "run_id": run_id,
            "event_id": reject["event_id"][:64],
            "week_start": week_start,
            "reason": reject["reason"],
            "payload": reject["payload"],
            "created_at": now,
        }
        for reject in rejects
    ]
    with engine.begin() as conn:
        conn.execute(insert(tables.rejects), rows)


def heartbeat(engine: Engine, run_id: str) -> None:
    """Renueva el latido de una corrida (watchdog de zombies)."""

    tables = tables_for(engine)
    with engine.begin() as conn:
        conn.execute(
            update(tables.runs)
            .where(tables.runs.c.run_id == run_id)
            .values(heartbeat_at=datetime.now(timezone.utc))
        )


def mark_zombie_runs(
    engine: Engine,
    max_age_minutes: int = 120,
    now: datetime | None = None,
) -> int:
    """Marca como ``failed`` las corridas ``running`` sin latido reciente."""

    tables = tables_for(engine)
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=max_age_minutes)
    with engine.begin() as conn:
        result = conn.execute(
            update(tables.runs)
            .where(
                tables.runs.c.status == "running",
                tables.runs.c.heartbeat_at < cutoff,
            )
            .values(
                status="failed",
                finished_at=now,
                error_message="watchdog: heartbeat timeout",
            )
        )
    return int(result.rowcount or 0)


def source_is_tripped(engine: Engine, threshold: int = 3) -> bool:
    """Circuit breaker: las últimas ``threshold`` corridas fallaron en extract."""

    tables = tables_for(engine)
    with engine.connect() as conn:
        recent = conn.execute(
            select(tables.runs.c.run_id, tables.runs.c.status)
            .where(tables.runs.c.pipeline_name == PIPELINE_NAME)
            .order_by(tables.runs.c.started_at.desc())
            .limit(threshold)
        ).all()
        if len(recent) < threshold or any(status != "failed" for _, status in recent):
            return False
        run_ids = [row[0] for row in recent]
        failed_extract = conn.execute(
            select(tables.steps.c.run_id).where(
                tables.steps.c.run_id.in_(run_ids),
                tables.steps.c.step == "extract",
                tables.steps.c.status == "failed",
            )
        ).scalars().all()
    return len(set(failed_extract)) >= threshold


def freeze_week(
    engine: Engine,
    week_start: date,
    published_by: str = "auto",
) -> None:
    """Congela una semana para que el lookback no la reescriba."""

    tables = tables_for(engine)
    now = datetime.now(timezone.utc)
    values = {
        "week_start": week_start,
        "published_at": now,
        "published_by": published_by,
        "frozen": True,
    }
    dialect = engine.dialect.name
    if dialect == "postgresql":
        stmt = postgresql_insert(tables.published).on_conflict_do_update(
            index_elements=["week_start"], set_=values
        )
    elif dialect == "sqlite":
        stmt = sqlite_insert(tables.published).on_conflict_do_update(
            index_elements=["week_start"], set_=values
        )
    else:
        stmt = insert(tables.published)
    with engine.begin() as conn:
        conn.execute(stmt, values)


def maybe_freeze_week(
    engine: Engine,
    week_start: date,
    min_successful_runs: int = 2,
) -> bool:
    """Congela la semana tras N corridas exitosas posteriores a su cierre."""

    tables = tables_for(engine)
    close_at = datetime.combine(
        week_start + timedelta(days=7), time.min, tzinfo=timezone.utc
    )
    with engine.connect() as conn:
        successful = conn.execute(
            select(func.count())
            .select_from(tables.runs)
            .where(
                tables.runs.c.pipeline_name == PIPELINE_NAME,
                tables.runs.c.week_start == week_start,
                tables.runs.c.status == "success",
                tables.runs.c.started_at >= close_at,
            )
        ).scalar()

    if int(successful or 0) >= min_successful_runs:
        freeze_week(engine, week_start, published_by="auto")
        return True
    return False


def snapshot_week(
    engine: Engine,
    week_start: date,
    run_id: str,
    reason: str,
    forced_by: str,
) -> int:
    """Guarda una revisión inmutable antes de reescribir una semana congelada."""

    tables = tables_for(engine)
    with engine.connect() as conn:
        rows = conn.execute(
            select(tables.performance).where(
                tables.performance.c.week_start == week_start
            )
        ).mappings().all()

    snapshot = [_jsonable_row(dict(row)) for row in rows]
    with engine.begin() as conn:
        conn.execute(
            insert(tables.revisions).values(
                week_start=week_start,
                run_id=run_id,
                reason=reason[:512],
                forced_by=forced_by[:128],
                snapshot=snapshot,
                created_at=datetime.now(timezone.utc),
            )
        )
    return len(snapshot)


def _jsonable_row(row: dict) -> dict:
    result = {}
    for key, value in row.items():
        if hasattr(value, "isoformat"):
            result[key] = value.isoformat()
        elif hasattr(value, "__float__"):
            result[key] = float(value)
        else:
            result[key] = value
    return result


def replay_rejects(
    engine: Engine,
    run_id: str,
    *,
    triggered_by: str = "replay",
) -> WeekResult:
    """Reprocesa la semana de una corrida y marca sus rechazos como rejugados."""

    tables = tables_for(engine)
    with engine.connect() as conn:
        row = conn.execute(
            select(tables.runs.c.week_start).where(tables.runs.c.run_id == run_id)
        ).first()
    if row is None or row[0] is None:
        raise ValueError(f"No existe una corrida con week_start: {run_id}")

    week_start = row[0]
    result = execute_week(
        engine,
        week_start,
        triggered_by=triggered_by,
        force=True,
        reason=f"replay rejects from {run_id}",
    )
    if result.status in {"success", "skipped"}:
        with engine.begin() as conn:
            conn.execute(
                update(tables.rejects)
                .where(
                    tables.rejects.c.run_id == run_id,
                    tables.rejects.c.replayed_at.is_(None),
                )
                .values(replayed_at=datetime.now(timezone.utc))
            )
    return result


def previous_week_kpis(engine: Engine, week_start: date) -> list[dict]:
    """KPIs ya persistidos de la semana anterior (para G7/G8)."""

    tables = tables_for(engine)
    previous = week_start - timedelta(days=7)
    with engine.connect() as conn:
        rows = conn.execute(
            select(tables.performance).where(
                tables.performance.c.week_start == previous
            )
        ).mappings().all()
    return [dict(row) for row in rows]


def source_freshness_hours(
    rows: list[dict], now: datetime | None = None
) -> float | None:
    """Horas desde el evento más reciente recibido (G11)."""

    timestamps = [
        value
        for value in (_as_utc(row.get("received_at")) for row in rows)
        if value is not None
    ]
    if not timestamps:
        return None
    now = now or datetime.now(timezone.utc)
    return max(0.0, (now - max(timestamps)).total_seconds() / 3600)


def _as_utc(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def sku_configuration_gaps(engine: Engine) -> dict:
    """Cuenta SKUs sin cliente y/o sin umbral configurado.

    No bloquea la corrida por sí solo: es una señal de configuración. El gate
    `client_mapping_missing` bloquea cuando además no hay ninguna fila válida.
    """

    table = sku_config_table()
    with engine.connect() as conn:
        total = int(
            conn.execute(select(func.count()).select_from(table)).scalar() or 0
        )
        without_client = int(
            conn.execute(
                select(func.count())
                .select_from(table)
                .where(table.c.client_id.is_(None))
            ).scalar()
            or 0
        )
        without_min_stock = int(
            conn.execute(
                select(func.count())
                .select_from(table)
                .where(table.c.min_stock.is_(None))
            ).scalar()
            or 0
        )
    return {
        "total": total,
        "without_client": without_client,
        "without_min_stock": without_min_stock,
    }


def reconcile_source(
    engine: Engine,
    start_date: date,
    end_date: date,
) -> list[dict]:
    """Compara órdenes SQL (stock_entry/stock_exit) con eventos persistidos.

    Cada día devuelve los conteos y el delta. Un delta distinto de cero indica
    que la instrumentación perdió eventos (o que la fuente no está al día).
    """

    if end_date < start_date:
        raise ValueError("end_date no puede ser anterior a start_date")

    telemetry = telemetry_table()
    entries = stock_table("stock_entry")
    exits = stock_table("stock_exit")
    results: list[dict] = []

    current = start_date
    while current <= end_date:
        start = datetime.combine(current, time.min, tzinfo=timezone.utc)
        end = start + timedelta(days=1)
        with engine.connect() as conn:
            inbound_events = int(
                conn.execute(
                    select(func.count())
                    .select_from(telemetry)
                    .where(
                        telemetry.c.event_type == INBOUND,
                        telemetry.c.timestamp >= start,
                        telemetry.c.timestamp < end,
                    )
                ).scalar()
                or 0
            )
            outbound_events = int(
                conn.execute(
                    select(func.count())
                    .select_from(telemetry)
                    .where(
                        telemetry.c.event_type == OUTBOUND,
                        telemetry.c.timestamp >= start,
                        telemetry.c.timestamp < end,
                    )
                ).scalar()
                or 0
            )
            inbound_orders = int(
                conn.execute(
                    select(func.count())
                    .select_from(entries)
                    .where(
                        entries.c.created_at >= start,
                        entries.c.created_at < end,
                    )
                ).scalar()
                or 0
            )
            outbound_orders = int(
                conn.execute(
                    select(func.count())
                    .select_from(exits)
                    .where(
                        exits.c.created_at >= start,
                        exits.c.created_at < end,
                    )
                ).scalar()
                or 0
            )

        delta_in = inbound_events - inbound_orders
        delta_out = outbound_events - outbound_orders
        results.append(
            {
                "date": current.isoformat(),
                "inbound_orders": inbound_orders,
                "inbound_events": inbound_events,
                "outbound_orders": outbound_orders,
                "outbound_events": outbound_events,
                "delta_inbound": delta_in,
                "delta_outbound": delta_out,
                "ok": delta_in == 0 and delta_out == 0,
            }
        )
        current += timedelta(days=1)

    return results


# ---------------------------------------------------------------------------
# Orquestación
# ---------------------------------------------------------------------------


def default_steps(engine: Engine) -> WeekSteps:
    return WeekSteps(
        extract=lambda week_start: extract_week(engine, week_start),
        normalize=normalize_validate,
        aggregate=aggregate_kpis,
        quality=evaluate_quality,
        load=lambda kpis, week_start, run_id: load_week(
            engine, kpis, week_start, run_id
        ),
        reconcile=lambda kpis, week_start: reconcile_week(engine, kpis, week_start),
    )


def _record_skipped_run(
    engine: Engine,
    run_id: str,
    week_start: date,
    triggered_by: str,
    instrumentation_since: date | None,
    reason: str,
) -> WeekResult:
    start_run(engine, run_id, week_start, triggered_by, instrumentation_since)
    finish_run(engine, run_id, status="skipped", quality_status=reason)
    return WeekResult(
        run_id=run_id,
        week_start=week_start,
        status="skipped",
        skipped_reason=reason,
    )


def execute_week(
    engine: Engine | None,
    week_start: date,
    *,
    triggered_by: str = "manual",
    force: bool = False,
    reason: str | None = None,
    instrumentation_since: date | None = None,
    steps: WeekSteps | None = None,
    run_id: str | None = None,
) -> WeekResult:
    """Ejecuta una semana con lock, circuit breaker y watchdog.

    El flow de Prefect convierte un ``status="failed"`` en excepción; el CLI lo
    traduce a exit code 1. Así los tests pueden inspeccionar el fallo sin
    capturar excepciones.
    """

    engine = engine or get_engine()
    run_id = run_id or str(uuid4())

    mark_zombie_runs(engine)

    with week_lock(engine, week_start) as acquired:
        if not acquired:
            return _record_skipped_run(
                engine,
                run_id,
                week_start,
                triggered_by,
                instrumentation_since,
                "locked",
            )

        if not force and source_is_tripped(engine):
            start_run(engine, run_id, week_start, triggered_by, instrumentation_since)
            record_step(
                engine,
                run_id,
                "extract",
                "failed",
                datetime.now(timezone.utc),
                detail={"error": "source_unavailable"},
            )
            finish_run(
                engine,
                run_id,
                status="failed",
                error_message="source_unavailable",
            )
            send_alert(
                "Circuit breaker abierto",
                f"3 fallos consecutivos de extract; semana {week_start} bloqueada. "
                "Usa backfill --force --reason para reintentar.",
            )
            return WeekResult(
                run_id=run_id,
                week_start=week_start,
                status="failed",
                error="source_unavailable",
            )

        return _execute_week_inner(
            engine,
            week_start,
            triggered_by=triggered_by,
            force=force,
            reason=reason,
            instrumentation_since=instrumentation_since,
            steps=steps,
            run_id=run_id,
        )


def _execute_week_inner(
    engine: Engine | None,
    week_start: date,
    *,
    triggered_by: str = "manual",
    force: bool = False,
    reason: str | None = None,
    instrumentation_since: date | None = None,
    steps: WeekSteps | None = None,
    run_id: str | None = None,
) -> WeekResult:
    """Cuerpo de la corrida, ya protegido por el lock de la semana."""

    engine = engine or get_engine()
    steps = steps or default_steps(engine)
    run_id = run_id or str(uuid4())

    start_run(engine, run_id, week_start, triggered_by, instrumentation_since)

    frozen = is_frozen(engine, week_start)
    if frozen and not force:
        finish_run(engine, run_id, status="skipped", quality_status="frozen")
        return WeekResult(
            run_id=run_id,
            week_start=week_start,
            status="skipped",
            skipped_reason="frozen",
        )
    if frozen and force:
        snapshot_week(
            engine,
            week_start,
            run_id,
            reason or "forced backfill",
            triggered_by,
        )

    try:
        rows = _run_step(engine, run_id, "extract", lambda: steps.extract(week_start))
        fingerprint = compute_fingerprint(rows)

        if not force and should_skip(engine, week_start, fingerprint):
            finish_run(
                engine,
                run_id,
                status="skipped",
                rows_extracted=len(rows),
                source_fingerprint=fingerprint,
                quality_status="unchanged",
            )
            return WeekResult(
                run_id=run_id,
                week_start=week_start,
                status="skipped",
                rows_extracted=len(rows),
                skipped_reason="fingerprint_unchanged",
                source_fingerprint=fingerprint,
            )

        normalized = _run_step(
            engine,
            run_id,
            "normalize",
            lambda: steps.normalize(rows, week_start),
        )
        store_rejects(engine, run_id, week_start, normalized.rejects)

        kpis = _run_step(
            engine,
            run_id,
            "aggregate",
            lambda: steps.aggregate(normalized.valid),
        )
        duplicate_order_ids = count_duplicate_order_ids(normalized.valid)
        previous = previous_week_kpis(engine, week_start)
        # G11 solo aplica a la última semana cerrada: en backfill histórico la
        # antigüedad de la fuente es esperada.
        freshness = (
            source_freshness_hours(rows)
            if week_start == resolve_target_weeks(1)[0]
            else None
        )
        reject_reasons = Counter(
            reject["reason"] for reject in normalized.rejects
        )
        configuration_gaps = sku_configuration_gaps(engine)

        quality = _run_step(
            engine,
            run_id,
            "quality",
            lambda: steps.quality(
                kpis,
                rejects=len(normalized.rejects),
                total_rows=len(rows),
                week_start=week_start,
                duplicate_order_ids=duplicate_order_ids,
                instrumentation_since=instrumentation_since,
                previous_kpis=previous,
                source_freshness_hours=freshness,
                reject_reasons=dict(reject_reasons),
                configuration_gaps=configuration_gaps,
            ),
        )

        if not quality.passed:
            finish_run(
                engine,
                run_id,
                status="failed",
                rows_extracted=len(rows),
                rows_valid=len(normalized.valid),
                rows_rejected=len(normalized.rejects),
                source_fingerprint=fingerprint,
                quality_status=quality.status,
                error_message=quality.summary,
            )
            send_alert(
                "Quality gate bloqueante",
                f"Semana {week_start}: {quality.summary}",
            )
            return WeekResult(
                run_id=run_id,
                week_start=week_start,
                status="failed",
                rows_extracted=len(rows),
                rows_valid=len(normalized.valid),
                rows_rejected=len(normalized.rejects),
                quality_status=quality.status,
                error=quality.summary,
                source_fingerprint=fingerprint,
            )

        written = _run_step(
            engine,
            run_id,
            "load",
            lambda: steps.load(kpis, week_start, run_id),
        )
        _run_step(
            engine,
            run_id,
            "reconcile",
            lambda: steps.reconcile(kpis, week_start),
        )
        save_watermark(engine, week_start, run_id, fingerprint, written)

        finish_run(
            engine,
            run_id,
            status="success",
            rows_extracted=len(rows),
            rows_valid=len(normalized.valid),
            rows_rejected=len(normalized.rejects),
            rows_written=written,
            source_fingerprint=fingerprint,
            quality_status=quality.status,
        )
        if quality.status == "warning":
            send_alert(
                "Pipeline semanal con advertencias",
                f"Semana {week_start}: {quality.summary}",
                level="warning",
            )
        try:
            maybe_freeze_week(engine, week_start)
        except Exception:  # pragma: no cover - la congelación no invalida la carga
            logger.exception("No se pudo congelar la semana %s", week_start)
        return WeekResult(
            run_id=run_id,
            week_start=week_start,
            status="success",
            rows_extracted=len(rows),
            rows_valid=len(normalized.valid),
            rows_rejected=len(normalized.rejects),
            rows_written=written,
            quality_status=quality.status,
            source_fingerprint=fingerprint,
        )
    except Exception as exc:  # noqa: BLE001 - se registra en el ledger
        logger.exception("Fallo procesando la semana %s", week_start)
        send_alert("Pipeline semanal falló", f"Semana {week_start}: {exc}")
        try:
            finish_run(
                engine,
                run_id,
                status="failed",
                error_message=str(exc),
            )
        except Exception:  # pragma: no cover - la BD puede estar caída
            logger.exception("No se pudo registrar el fallo de la corrida %s", run_id)
        return WeekResult(
            run_id=run_id,
            week_start=week_start,
            status="failed",
            error=str(exc),
        )


def _run_step(
    engine: Engine,
    run_id: str,
    name: str,
    fn: Callable[[], Any],
) -> Any:
    started = datetime.now(timezone.utc)
    try:
        result = fn()
    except Exception as exc:
        _safe_record_step(
            engine,
            run_id,
            name,
            "failed",
            started,
            detail={"error": str(exc)},
        )
        raise
    _safe_record_step(
        engine,
        run_id,
        name,
        "success",
        started,
        detail={
            "duration_ms": round(
                (datetime.now(timezone.utc) - started).total_seconds() * 1000, 2
            )
        },
    )
    return result


def _safe_record_step(
    engine: Engine,
    run_id: str,
    name: str,
    status: str,
    started: datetime,
    detail: dict | None = None,
) -> None:
    try:
        record_step(engine, run_id, name, status, started, detail=detail)
    except Exception:  # pragma: no cover - no debe tumbar la corrida
        logger.exception("No se pudo registrar el step %s de %s", name, run_id)


def run_week(
    engine: Engine,
    week_start: date,
    *,
    triggered_by: str = "manual",
    force: bool = False,
    reason: str | None = None,
    instrumentation_since: date | None = None,
) -> WeekResult:
    """Atajo para tests y CLI: ejecuta una semana con las etapas por defecto."""

    return execute_week(
        engine,
        week_start,
        triggered_by=triggered_by,
        force=force,
        reason=reason,
        instrumentation_since=instrumentation_since,
    )
