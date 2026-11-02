import logging
import os
from pathlib import Path
from uuid import uuid4

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response

from ..core.dependencies import require_manager
from ..incidents import service
from ..incidents.exceptions import EmptyFileError, InvalidFormatError, NoAnalysisError
from ..incidents.schemas import AnalysisResponse
from ..tasks.incidents import analyze_incidents_csv
from celery_app import celery_app
from schemas import AnalyzeTaskAccepted

router = APIRouter(prefix="/api", tags=["incidents"])

logger = logging.getLogger("api.incidents")

UPLOAD_DIR = Path(
    os.getenv("INCIDENT_UPLOAD_DIR", "/tmp/trackflow/uploads")
)


def _save_upload(task_id: str, raw: bytes) -> Path:
    """Write the CSV atomically to the volume shared with the worker."""

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    target = UPLOAD_DIR / f"{task_id}.csv"
    tmp = target.with_suffix(".csv.tmp")
    tmp.write_bytes(raw)
    os.replace(tmp, target)
    return target


def _export_task_csv(task_id: str) -> str:
    result = AsyncResult(task_id, app=celery_app)
    if result.state != "SUCCESS":
        raise HTTPException(
            status_code=409,
            detail="La tarea no ha terminado con éxito.",
        )

    payload = result.result
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=404,
            detail="El resultado de la tarea no está disponible.",
        )

    return service.export_analysis_csv(AnalysisResponse(**payload))


@router.post(
    "/incidents/analyze",
    response_model=AnalyzeTaskAccepted,
    status_code=202,
    summary="Encola el análisis de un CSV de incidentes y devuelve un task_id",
)
async def analyze_incidents(
    file: UploadFile = File(...),
    _=Depends(require_manager),
) -> AnalyzeTaskAccepted:
    if file is None or file.filename is None or file.filename == "":
        raise HTTPException(
            status_code=400,
            detail="Falta el archivo CSV en el campo 'file'.",
        )

    try:
        raw = await file.read()
    except OSError as exc:
        raise HTTPException(
            status_code=400,
            detail="No se pudo leer el archivo subido. Inténtalo de nuevo.",
        ) from exc

    try:
        service.validate_upload(raw)
    except (EmptyFileError, InvalidFormatError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    task_id = str(uuid4())
    target = _save_upload(task_id, raw)

    try:
        analyze_incidents_csv.apply_async(
            kwargs={"path": str(target), "filename": file.filename},
            task_id=task_id,
        )
    except Exception as exc:
        logger.exception("No se pudo encolar el análisis %s", task_id)
        target.unlink(missing_ok=True)
        raise HTTPException(
            status_code=503,
            detail="La cola de tareas no está disponible.",
        ) from exc

    return AnalyzeTaskAccepted(task_id=task_id)


@router.get(
    "/incidents/results/export",
    summary="Devuelve el último análisis en formato CSV descargable",
)
async def export_results(
    task_id: str | None = None,
    _=Depends(require_manager),
) -> Response:
    try:
        csv_text = (
            _export_task_csv(task_id)
            if task_id
            else service.export_last_analysis_csv()
        )
    except NoAnalysisError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="results.csv"'},
    )
