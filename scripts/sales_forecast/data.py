"""Carga, validación de esquema y limpieza del dataset de ventas.

El dataset provisto (``data/raw/trackflow_sales.csv``) no tiene nulos, pero la
limpieza es defensiva: si en el futuro el ERP exporta un mes vacío o duplicado,
el pipeline lo repara y deja constancia en el informe de calidad en lugar de
entrenar en silencio con datos corruptos.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import EXPECTED_COLUMNS, MARKET, NUMERIC_COLUMNS, TARGET


class SalesDataError(ValueError):
    """Error de esquema o de calidad de datos del CSV de ventas."""


def load_sales_data(
    path: str | Path,
    *,
    market: str = MARKET,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Carga el CSV, filtra el mercado principal y devuelve ``(df, informe)``.

    El DataFrame resultante tiene una fila por mes, índice entero y columnas
    ``month`` (datetime), ``revenue_eur``, ``shipments_processed`` y
    ``avg_revenue_per_shipment_eur``.
    """

    csv_path = Path(path)
    if not csv_path.exists():
        raise FileNotFoundError(f"No se encuentra el dataset de ventas: {csv_path}")

    raw = pd.read_csv(csv_path)
    _validate_columns(raw, csv_path)

    report: dict[str, object] = {
        "source": str(csv_path),
        "rows_raw": int(len(raw)),
    }

    df = raw.copy()
    df["month"] = pd.to_datetime(df["month"], errors="coerce")
    if df["month"].isna().any():
        bad = int(df["month"].isna().sum())
        raise SalesDataError(f"{bad} filas tienen una fecha 'month' inválida")

    markets = sorted(str(value) for value in df["market"].dropna().unique())
    report["markets"] = markets
    if market not in markets:
        raise SalesDataError(
            f"El mercado '{market}' no está en el dataset (mercados: {markets})"
        )
    df = df.loc[df["market"] == market]

    for column in NUMERIC_COLUMNS:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    df = df.drop(columns=["market"]).sort_values("month").reset_index(drop=True)

    before_dedup = len(df)
    df = df.drop_duplicates(subset="month", keep="last")
    report["duplicates_removed"] = int(before_dedup - len(df))

    df = df.set_index("month").sort_index()
    full_range = pd.date_range(df.index.min(), df.index.max(), freq="MS")
    missing_months = full_range.difference(df.index).tolist()
    report["missing_months_detected"] = len(missing_months)
    df = df.reindex(full_range)
    df.index.name = "month"

    nulls_by_column = {
        column: int(count)
        for column, count in df.isna().sum().items()
        if int(count) > 0
    }
    report["nulls_imputed"] = nulls_by_column

    # Interpolación temporal para huecos internos y arrastre en los extremos.
    df = df.interpolate(method="linear", limit_direction="both")
    df["shipments_processed"] = df["shipments_processed"].round().astype("int64")

    df = df.reset_index()

    if df.isna().any().any():
        remaining = df.isna().sum().to_dict()
        raise SalesDataError(f"Quedan valores nulos tras la limpieza: {remaining}")
    if (df[TARGET] <= 0).any():
        bad_months = df.loc[df[TARGET] <= 0, "month"].dt.strftime("%Y-%m").tolist()
        raise SalesDataError(
            f"Hay ingresos no positivos en los meses: {bad_months}"
        )
    if df["month"].duplicated().any():
        raise SalesDataError("Hay meses duplicados tras la limpieza")
    if not df["month"].is_monotonic_increasing:
        raise SalesDataError("Los meses no están ordenados cronológicamente")

    report.update(
        {
            "rows_clean": int(len(df)),
            "first_month": df["month"].min().strftime("%Y-%m"),
            "last_month": df["month"].max().strftime("%Y-%m"),
            "months_total": int(len(df)),
        }
    )
    return df.reset_index(drop=True), report


def _validate_columns(df: pd.DataFrame, csv_path: Path) -> None:
    """Comprueba que el CSV tiene exactamente las columnas del contrato."""

    missing = [column for column in EXPECTED_COLUMNS if column not in df.columns]
    unexpected = [column for column in df.columns if column not in EXPECTED_COLUMNS]
    if missing or unexpected:
        raise SalesDataError(
            f"Esquema inesperado en {csv_path.name}: faltan={missing}, "
            f"sobran={unexpected}. Se esperaba {list(EXPECTED_COLUMNS)}"
        )
    if df.empty:
        raise SalesDataError(f"El dataset {csv_path.name} está vacío")
