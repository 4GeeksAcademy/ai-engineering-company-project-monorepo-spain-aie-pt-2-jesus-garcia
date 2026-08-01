import csv
import io

import pandas as pd

from .analyzer import REQUIRED_COLUMNS, analyze_file, metrics_to_csv_rows
from .exceptions import EmptyFileError, InvalidFormatError, NoAnalysisError
from .schemas import AnalysisResponse

_last_analysis: AnalysisResponse | None = None


def reset() -> None:
    """Clear the in-memory last analysis (used by tests)."""
    global _last_analysis
    _last_analysis = None


def get_last_analysis() -> AnalysisResponse:
    if _last_analysis is None:
        raise NoAnalysisError("No hay análisis previo. Ejecuta POST /api/incidents/analyze primero.")
    return _last_analysis


def export_last_analysis_csv() -> str:
    """Return the last analysis summary as CSV text."""
    stats = get_last_analysis().model_dump()
    rows = metrics_to_csv_rows(stats)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=["metrica", "valor"])
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def analyze_upload(raw: bytes) -> AnalysisResponse:
    """Validate the uploaded CSV content and run the shared analysis."""
    if not raw or not raw.strip():
        raise EmptyFileError("El archivo está vacío.")

    content = raw.decode("utf-8-sig", errors="replace")
    stream = io.StringIO(content)

    try:
        first_lines = content.splitlines()[:1]
        if not first_lines or not first_lines[0].strip():
            raise InvalidFormatError("El archivo está vacío o no contiene encabezados.")

        header = next(csv.reader(first_lines))
    except csv.Error as exc:
        raise InvalidFormatError(f"Formato incorrecto: no se pudo leer la cabecera CSV. ({exc})")

    missing = [col for col in REQUIRED_COLUMNS if col not in header]
    if missing:
        raise InvalidFormatError(
            f"Formato incorrecto: faltan columnas obligatorias: {', '.join(missing)}."
        )

    try:
        stats = analyze_file(stream)
    except (pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise InvalidFormatError(f"Formato incorrecto: el CSV no es válido. ({exc})")

    global _last_analysis
    _last_analysis = AnalysisResponse(**stats)
    return _last_analysis
