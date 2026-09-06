from contextlib import asynccontextmanager
from dotenv import load_dotenv
import logging

load_dotenv()

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlmodel import SQLModel

from database import engine
from .routes.incidents import router as incidents_router
from .routes.incidents_manager import router as incidents_manager_router
from .routes.inventory import router as inventory_router
from .routes.suppliers import router as suppliers_router
from .routes.auth import router as auth_router
from .routes.users import router as users_router
from .routes.profiles import router as profiles_router

logger = logging.getLogger(__name__)

ALLOWED_ORIGINS = "http://localhost:5173,http://localhost:3000,http://localhost:3001"


@asynccontextmanager
async def lifespan(app: FastAPI):
    if engine is not None:
        SQLModel.metadata.create_all(engine)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="TrackFlow API",
        description="API para gestión de proveedores y análisis de incidentes.",
        version="0.2.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin.strip() for origin in ALLOWED_ORIGINS.split(",")],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(incidents_router)
    app.include_router(incidents_manager_router)
    app.include_router(inventory_router)
    app.include_router(suppliers_router)
    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(profiles_router)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "Error no controlado en %s %s",
            request.method,
            request.url.path,
        )
        return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})

    @app.get("/health", tags=["health"])
    async def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
