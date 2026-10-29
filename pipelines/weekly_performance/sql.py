"""DDL y utilidades de esquema del pipeline.

El DDL se genera con SQLAlchemy para que los tests puedan correr en SQLite y
producción en PostgreSQL. En PostgreSQL se crean los esquemas ``reporting`` y
``ops``; en SQLite las tablas viven en el esquema por defecto.
"""

from __future__ import annotations

from sqlalchemy import Engine, text

from .schema import (
    ReportingTables,
    get_reporting_tables,
    outbox_table,
    sku_config_table,
    stock_table,
    telemetry_table,
)
from .settings import OPS_SCHEMA, REPORTING_SCHEMA


def reporting_schema_for(engine: Engine) -> str | None:
    return None if engine.dialect.name == "sqlite" else REPORTING_SCHEMA


def ops_schema_for(engine: Engine) -> str | None:
    return None if engine.dialect.name == "sqlite" else OPS_SCHEMA


def tables_for(engine: Engine) -> ReportingTables:
    return get_reporting_tables(reporting_schema_for(engine))


def create_reporting_schema(engine: Engine) -> ReportingTables:
    """Crea esquemas y tablas de ``reporting`` de forma idempotente."""

    if engine.dialect.name == "postgresql":
        with engine.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{REPORTING_SCHEMA}"'))
            conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{OPS_SCHEMA}"'))

    tables = tables_for(engine)
    tables.metadata.create_all(engine)
    outbox_table(ops_schema_for(engine)).metadata.create_all(engine)
    return tables


def create_telemetry_table(engine: Engine) -> None:
    """Solo para tests: crea una ``telemetry_events`` mínima.

    En producción la tabla ya existe y pertenece a la API; el pipeline nunca la
    crea ni la modifica.
    """

    telemetry_table().metadata.create_all(engine)


def create_inventory_tables(engine: Engine) -> None:
    """Solo para tests: crea ``stock_entry``/``stock_exit`` mínimas."""

    sku_config_table().metadata.create_all(engine)
    stock_table("stock_entry").metadata.create_all(engine)
    stock_table("stock_exit").metadata.create_all(engine)


def drop_reporting_schema(engine: Engine) -> None:
    """Borra las tablas del pipeline (tests y entornos efímeros)."""

    if engine.dialect.name == "postgresql":
        with engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{REPORTING_SCHEMA}" CASCADE'))
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{OPS_SCHEMA}" CASCADE'))
        return

    tables = tables_for(engine)
    outbox_table(ops_schema_for(engine)).metadata.drop_all(engine)
    tables.metadata.drop_all(engine)
