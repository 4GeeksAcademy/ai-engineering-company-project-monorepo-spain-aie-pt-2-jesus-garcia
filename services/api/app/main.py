from contextlib import asynccontextmanager
from dotenv import load_dotenv
import logging
import os
from pathlib import Path
import sys
import time

load_dotenv()

# `services/reporting` vive fuera de `services/api`; se añade la raíz del
# monorepo para poder importarlo tanto en local como en Docker.
try:
    _REPO_ROOT = Path(__file__).resolve().parents[3]
except IndexError:  # Docker: /app/app/main.py -> raíz /
    _REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlmodel import SQLModel

from database import engine
from models import HealthResponse
from app.agent.memory.models import create_agent_memory_tables
from app.chat.models import create_chat_tables
from app.chat.store import reconcile_streaming_messages
from app.core.config import allowed_origins, is_production, validate_security_config
from app.telemetry.outbox import create_outbox_table
from .routes.incidents import router as incidents_router
from .routes.incidents_manager import router as incidents_manager_router
from .routes.inventory import router as inventory_router
from .routes.suppliers import router as suppliers_router
from .routes.auth import router as auth_router
from .routes.users import router as users_router
from .routes.profiles import router as profiles_router
from .routes.telemetry import router as telemetry_router
from .routes.tasks import router as tasks_router
from .routes.knowledge import router as knowledge_router
from .routes.agent import router as agent_router
from .routes.agent_harness import router as agent_harness_router
from .routes.agent_memory import router as agent_memory_router
from .routes.rfp import router as rfp_router
from .routes.realtime import router as realtime_router
from .routes.chat import router as chat_router
from services.reporting.router import router as reporting_router
from services.reporting.sla import ensure_sla_table

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(levelname)s:%(name)s:%(message)s")

logger = logging.getLogger(__name__)

TELEMETRY_ENDPOINT = os.getenv("TELEMETRY_ENDPOINT")


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_security_config()
    if engine is not None:
        SQLModel.metadata.create_all(engine)
        create_agent_memory_tables(engine)
        create_chat_tables(engine)
        create_outbox_table(engine)
        try:
            ensure_sla_table(engine)
        except Exception:  # pragma: no cover - el read model no debe tumbar el API
            logger.exception("No se pudo preparar la tabla de SLA de reporting.")
        try:
            reconcile_streaming_messages()
        except Exception:  # pragma: no cover - no impide arrancar la API
            logger.exception("No se pudieron reconciliar mensajes de chat parciales.")
    logger.info("Telemetry endpoint configured: %s", TELEMETRY_ENDPOINT or "<unset>")
    yield


def create_app() -> FastAPI:
    production = is_production()
    app = FastAPI(
        title="TrackFlow API",
        description="API para gestión de proveedores y análisis de incidentes.",
        version="0.2.0",
        lifespan=lifespan,
        docs_url=None if production else "/docs",
        redoc_url=None if production else "/redoc",
        openapi_url=None if production else "/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    logger = logging.getLogger("api.timing")

    @app.middleware("http")
    async def security_headers_middleware(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault(
            "Referrer-Policy", "strict-origin-when-cross-origin"
        )
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
        )
        if production:
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        return response

    @app.middleware("http")
    async def timing_middleware(request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration = (time.perf_counter() - start) * 1000  # ms

        logger.info(
            f"{request.method} {request.url.path} → {response.status_code} | {duration:.1f}ms"
        )
        return response

    app.include_router(incidents_router)
    app.include_router(incidents_manager_router)
    app.include_router(inventory_router)
    app.include_router(suppliers_router)
    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(profiles_router)
    app.include_router(telemetry_router)
    app.include_router(tasks_router)
    app.include_router(knowledge_router)
    app.include_router(agent_router)
    app.include_router(agent_harness_router)
    app.include_router(agent_memory_router)
    app.include_router(rfp_router)
    app.include_router(realtime_router)
    app.include_router(chat_router)
    app.include_router(reporting_router)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "Error no controlado en %s %s",
            request.method,
            request.url.path,
        )
        return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})

    @app.get("/health", tags=["health"], response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(status="ok")

    return app


app = create_app()
