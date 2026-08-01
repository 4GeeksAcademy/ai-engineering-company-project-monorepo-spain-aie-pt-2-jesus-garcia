from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response

from ..incidents import service
from ..incidents.exceptions import EmptyFileError, InvalidFormatError, NoAnalysisError
from ..incidents.schemas import AnalysisResponse

router = APIRouter(prefix="/incidents", tags=["incidents"])


@router.post(
    "/analyze",
    response_model=AnalysisResponse,
    summary="Analiza un CSV de incidentes y devuelve el resumen en JSON",
)
async def analyze_incidents(file: UploadFile = File(...)) -> AnalysisResponse:
    if file is None or file.filename is None or file.filename == "":
        raise HTTPException(status_code=400, detail="Falta el archivo CSV en el campo 'file'.")

    raw = await file.read()
    try:
        return service.analyze_upload(raw)
    except (EmptyFileError, InvalidFormatError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get(
    "/results/export",
    summary="Devuelve el último análisis en formato CSV descargable",
)
async def export_results() -> Response:
    try:
        csv_text = service.export_last_analysis_csv()
    except NoAnalysisError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="results.csv"'},
    )
