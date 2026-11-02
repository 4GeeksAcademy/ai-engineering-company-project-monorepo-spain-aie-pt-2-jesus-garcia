from __future__ import annotations

from pathlib import Path

from sqlmodel import Session, SQLModel, delete, select

from database import engine
from import_sku_mapping import apply_mapping, parse_csv
from models import InventoryDiscrepancy, SKU, StockEntry, StockExit


def _clean():
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.exec(delete(InventoryDiscrepancy))
        session.exec(delete(StockExit))
        session.exec(delete(StockEntry))
        session.exec(delete(SKU))
        session.commit()


def test_parse_csv_validates_headers(tmp_path: Path):
    path = tmp_path / "mapping.csv"
    path.write_text("sku_code,client_id\nX,Y\n", encoding="utf-8")

    rows, errors = parse_csv(path)

    assert rows == []
    assert any("Faltan columnas" in error for error in errors)


def test_parse_csv_accepts_empty_values(tmp_path: Path):
    path = tmp_path / "mapping.csv"
    path.write_text(
        "sku_code,client_id,min_stock\nSKU-1,fashion-co,10\nSKU-2,,\n",
        encoding="utf-8",
    )

    rows, errors = parse_csv(path)

    assert errors == []
    assert rows == [
        {"sku_code": "SKU-1", "client_id": "fashion-co", "min_stock": 10},
        {"sku_code": "SKU-2", "client_id": None, "min_stock": None},
    ]


def test_parse_csv_rejects_invalid_min_stock(tmp_path: Path):
    path = tmp_path / "mapping.csv"
    path.write_text("sku_code,client_id,min_stock\nSKU-1,c,-1\n", encoding="utf-8")

    rows, errors = parse_csv(path)

    assert rows == []
    assert any("negativo" in error for error in errors)


def test_apply_mapping_updates_existing_skus():
    _clean()
    with Session(engine) as session:
        session.add(SKU(name="A", sku_code="SKU-A", warehouse="los_angeles"))
        session.add(SKU(name="B", sku_code="SKU-B", warehouse="zaragoza"))
        session.commit()

        summary = apply_mapping(
            session,
            [
                {"sku_code": "SKU-A", "client_id": "fashion-co", "min_stock": 10},
                {"sku_code": "SKU-B", "client_id": None, "min_stock": None},
            ],
        )

        assert summary["updated"] == 1
        assert summary["unchanged"] == 1
        assert summary["not_found"] == []

    with Session(engine) as session:
        sku = session.exec(select(SKU).where(SKU.sku_code == "SKU-A")).first()
        assert sku is not None
        assert sku.client_id == "fashion-co"
        assert sku.min_stock == 10
    _clean()


def test_apply_mapping_reports_unknown_skus():
    _clean()
    with Session(engine) as session:
        summary = apply_mapping(
            session,
            [{"sku_code": "MISSING", "client_id": "c", "min_stock": 1}],
        )
    assert summary["not_found"] == ["MISSING"]
    _clean()
