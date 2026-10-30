"""
Database engine and session management.
Connects to the same PostgreSQL database as the Go backend (read-only usage).
"""

import psycopg2.extensions
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

# Postgres type OIDs for DATE and TIME (without time zone).
_DATE_OID = 1082
_TIME_OID = 1083

# Return DATE as "YYYY-MM-DD" and TIME as "HH:MM" strings. The analytics code works
# on those strings, and psycopg2's default TIME parsing turns "24:00:00" into 00:00.
_DATE_AS_TEXT = psycopg2.extensions.new_type((_DATE_OID,), "DATE_AS_TEXT", lambda v, cur: v)
_TIME_AS_TEXT = psycopg2.extensions.new_type(
    (_TIME_OID,), "TIME_AS_TEXT", lambda v, cur: v[:5] if v is not None else None
)


def create_db_engine(url):
    """Create the engine with a bounded pool and text DATE/TIME results."""
    eng = create_engine(
        url,
        # One uvicorn worker; the Go backend uses up to 10 connections, so 5 + 5
        # stays far below Railway Postgres' connection limit.
        pool_size=5,
        max_overflow=5,
        pool_timeout=10,
        pool_recycle=1800,
        pool_pre_ping=True,
        echo=False,
    )

    @event.listens_for(eng, "connect")
    def _register_text_types(dbapi_conn, _record):
        psycopg2.extensions.register_type(_DATE_AS_TEXT, dbapi_conn)
        psycopg2.extensions.register_type(_TIME_AS_TEXT, dbapi_conn)

    return eng


engine = create_db_engine(settings.DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def ping() -> None:
    """Raise if the database cannot answer a trivial query (used by /health)."""
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))


def get_db():
    """FastAPI dependency — yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
