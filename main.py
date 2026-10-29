"""
Discipline Analytics Microservice — Entry Point.
Run: python main.py
Docs: http://localhost:8082/docs (only when ENABLE_DOCS=true)
"""

import uvicorn
from fastapi import FastAPI

from app import schemas
from app.config import settings
from app.api.analytics_api import router as analytics_router
from app.smart_schedule.router import router as smart_schedule_router

def create_app(enable_docs: bool = settings.ENABLE_DOCS) -> FastAPI:
    """Build the FastAPI app; API docs are only mounted when enable_docs is true."""
    app = FastAPI(
        title="Discipline Analytics",
        description="Data analytics microservice for the Discipline Tracker app. "
                    "Provides productivity metrics, pattern detection, and visualizations.",
        version="1.0.0",
        docs_url="/docs" if enable_docs else None,
        redoc_url="/redoc" if enable_docs else None,
        openapi_url="/openapi.json" if enable_docs else None,
    )

    # No CORS middleware: this service is called only by the Go backend, never by browsers.

    # Mount analytics router
    app.include_router(analytics_router)

    # Mount smart schedule router
    app.include_router(smart_schedule_router)

    @app.get("/", tags=["Health"], response_model=schemas.ServiceInfo)
    def root():
        return {"service": "discipline-analytics", "status": "running", "version": "1.0.0"}

    @app.get("/health", tags=["Health"], response_model=schemas.Health)
    def health():
        return {"status": "ok"}

    return app


app = create_app()


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.SERVICE_HOST,
        port=settings.SERVICE_PORT,
        reload=True,
    )
