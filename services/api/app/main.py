from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.incidents import router as incidents_router
from .api.suppliers import router as suppliers_router

ALLOWED_ORIGINS = "http://localhost:5173,http://localhost:3000"


def create_app() -> FastAPI:
    app = FastAPI(
        title="TrackFlow API",
        description="API para gestión de proveedores y análisis de incidentes.",
        version="0.2.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin.strip() for origin in ALLOWED_ORIGINS.split(",")],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(incidents_router, prefix="/api")
    app.include_router(suppliers_router, prefix="/api")

    @app.get("/health", tags=["health"])
    async def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
