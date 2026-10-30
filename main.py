"""
Discipline Analytics Microservice — Entry Point.
Run: python main.py
Docs: http://localhost:8082/docs (only when ENABLE_DOCS=true)
"""

import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app import schemas
from app.config import settings
from app.observability import RequestIDMiddleware, setup_logging
from app.api.analytics_api import router as analytics_router
from app.smart_schedule.router import router as smart_schedule_router

def _field_path(loc) -> str:
    """("body", "commitments", 0, "startTime") -> "commitments[0].startTime" """
    path = ""
    for part in loc:
        if part == "body":
            continue
        if isinstance(part, int):
            path += f"[{part}]"
        else:
            path += ("." if path else "") + str(part)
    return path or "body"


async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    """422 with a readable message per field (input values are never echoed back)."""
    details = [{"field": _field_path(e["loc"]), "message": e["msg"].removeprefix("Value error, ")}
               for e in exc.errors()]
    error = "; ".join(f"{d['field']}: {d['message']}" for d in details)
    return JSONResponse(status_code=422, content={"error": error, "details": details})


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

    app.add_exception_handler(RequestValidationError, validation_error)

    # Request ID (from Gin's X-Request-ID) on every log line and response
    app.add_middleware(RequestIDMiddleware)

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


setup_logging()
app = create_app()


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.SERVICE_HOST,
        port=settings.SERVICE_PORT,
        reload=True,
        log_config=None,  # keep the JSON logging set up above
    )
