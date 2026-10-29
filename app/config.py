"""
Configuration for the analytics microservice.
Reads database credentials from the Go backend's .env or uses defaults.
"""

import os
from dotenv import load_dotenv

# Load .env from the Go backend if available
_backend_env = os.path.join(os.path.dirname(__file__), "..", "..", "discipline-back", ".env")
if os.path.exists(_backend_env):
    load_dotenv(_backend_env)

# Also load local .env if present
load_dotenv()


class Settings:
    """Application settings."""

    # Database (same PostgreSQL as the Go backend)
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
    DB_USER: str = os.getenv("DB_USER", "postgres")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "zetmax111")
    DB_NAME: str = os.getenv("DB_NAME", "discipline")

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    # Analytics service: Locally use ANALYTICS_PORT, in Railway fall back to dynamic PORT
    SERVICE_PORT: int = int(os.getenv("ANALYTICS_PORT") or os.getenv("PORT", "8082"))
    SERVICE_HOST: str = os.getenv("ANALYTICS_HOST", os.getenv("HOST", "0.0.0.0"))

    ALLOWED_ORIGINS: list = [
        "http://localhost:8081",
        "http://localhost:8080",
        "*",  # Production frontend domains or wildcard
    ]

    # Security
    API_KEY: str = os.getenv("ANALYTICS_API_KEY", "devet34tlt_)opment_inrtet43rnal_analytics_key_gwhuhg284yr44")


settings = Settings()
