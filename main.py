"""
Discipline Analytics Microservice — Entry Point.
Run: python main.py
Docs: http://localhost:8082/docs
"""

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.analytics_api import router as analytics_router

app = FastAPI(
    title="Discipline Analytics",
    description="Data analytics microservice for the Discipline Tracker app. "
                "Provides productivity metrics, pattern detection, and visualizations.",
    version="1.0.0",
)

# CORS — allow frontend origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount analytics router
app.include_router(analytics_router)


@app.get("/", tags=["Health"])
def root():
    return {"service": "discipline-analytics", "status": "running", "version": "1.0.0"}


@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.SERVICE_HOST,
        port=settings.SERVICE_PORT,
        reload=True,
    )
