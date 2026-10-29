"""
Configuration for the analytics microservice.
Reads database credentials from the Go backend's .env or the environment.
Required secrets have no defaults: the service refuses to start without them.
"""

import os
from dotenv import load_dotenv

# Load .env from the Go backend if available
_backend_env = os.path.join(os.path.dirname(__file__), "..", "..", "discipline-back", ".env")
if os.path.exists(_backend_env):
    load_dotenv(_backend_env)

# Also load local .env if present
load_dotenv()


MIN_JWT_SECRET_LEN = 32


class ConfigError(RuntimeError):
    """Raised when a required setting is missing or invalid."""


def _require(name: str, problems: list[str]) -> str:
    """Return a required variable, recording a problem if it is unset or blank."""
    value = os.getenv(name, "").strip()
    if not value:
        problems.append(f"{name} is required")
    return value


class Settings:
    """Application settings."""

    def __init__(self) -> None:
        problems: list[str] = []

        # Database (same PostgreSQL as the Go backend)
        self.DB_HOST: str = os.getenv("DB_HOST", "localhost")
        self.DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
        self.DB_USER: str = os.getenv("DB_USER", "postgres")
        self.DB_PASSWORD: str = _require("DB_PASSWORD", problems)
        self.DB_NAME: str = os.getenv("DB_NAME", "discipline")

        # Security: shared with the Go backend, which signs per-request tokens with it
        self.INTERNAL_JWT_SECRET: str = _require("INTERNAL_JWT_SECRET", problems)
        if self.INTERNAL_JWT_SECRET and len(self.INTERNAL_JWT_SECRET) < MIN_JWT_SECRET_LEN:
            problems.append(f"INTERNAL_JWT_SECRET must be at least {MIN_JWT_SECRET_LEN} characters")

        # API docs (/docs, /redoc, /openapi.json) are served only when explicitly enabled
        self.ENABLE_DOCS: bool = os.getenv("ENABLE_DOCS", "").strip().lower() == "true"

        if problems:
            raise ConfigError("Invalid configuration: " + "; ".join(problems))

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



def load_settings() -> Settings:
    """Build settings from the environment; raises ConfigError if a secret is missing."""
    return Settings()


settings = load_settings()
