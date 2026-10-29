"""
F-28: tasks.date/start_time/end_time are DATE/TIME columns now. psycopg2 would turn
TIME '24:00:00' into 00:00, so the engine must hand them to the app as text.
"""

import os

import pytest
from sqlalchemy import text

from app.database import create_db_engine, engine
from app.models.task import Task

TEST_URL = os.getenv("TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not TEST_URL, reason="TEST_DATABASE_URL not set (start docker-compose.test.yml)")


@needs_db
def test_time_and_date_columns_come_back_as_text():
    eng = create_db_engine(TEST_URL.replace("postgres://", "postgresql://", 1))
    with eng.connect() as conn:
        row = conn.execute(text("SELECT '24:00:00'::time, '09:30:00'::time, '2026-10-29'::date")).one()
    eng.dispose()
    assert tuple(row) == ("24:00", "09:30", "2026-10-29")


def test_end_of_day_block_has_full_duration():
    task = Task(start_time="21:00", end_time="24:00", date="2026-10-29")
    assert task.duration_hours() == 3.0


def test_pool_is_bounded():
    assert engine.pool.size() == 5
    assert engine.pool._max_overflow == 5
    assert engine.pool._timeout == 10
    assert engine.pool._recycle == 1800
