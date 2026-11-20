"""
F13: metrics and rules use the category kind, never its name. A block's kind comes from its
category (categories.kind); until migration 00015, a block without category_id falls back to its
legacy string. Exceptions (cancelled/conflict) are not blocks: a date with one and no block is a
day with nothing planned, never a miss.
"""

import os
import secrets
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import reports, timeutil
from app.database import create_db_engine
from app.metrics import Block, day_metrics, kind_of

NOW = datetime(2026, 11, 4, 20, 0)
D = date(2026, 11, 4)


def b(start, end, kind=None, category="personal", status="done"):
    return Block(day=D, start=start, end=end, category=category, kind=kind, status=status)


def test_kind_comes_from_the_category_and_falls_back_to_the_legacy_string():
    assert kind_of(b("09:00", "10:00", kind="focus", category="Reading")) == "focus"
    assert kind_of(b("09:00", "10:00", category="deep-work")) == "focus"
    assert kind_of(b("09:00", "10:00", category="Gym ")) == "exercise"
    assert kind_of(b("09:00", "10:00", category="fixed")) == "personal"
    assert kind_of(b("09:00", "10:00", category="Reading")) == "personal"


def test_deep_work_counts_kind_focus_whatever_the_name():
    # A custom category "Coding" of kind focus counts; a "Deep Work"-named personal one does not.
    m = day_metrics(D, [b("09:00", "11:00", kind="focus", category="deep-work"),
                        b("11:00", "12:00", kind="personal", category="deep-work")], NOW)
    assert m.deep_work_minutes == 120
    m = day_metrics(D, [b("09:00", "10:00", kind="focus", category="personal")], NOW)
    assert m.deep_work_minutes == 60


def test_a_day_with_only_exceptions_is_nothing_planned_not_a_miss():
    m = day_metrics(D, [], NOW)
    assert m.completion is None and m.focus_score is None and m.blocks_total == 0


@pytest.fixture
def week(monkeypatch):
    monkeypatch.setattr(timeutil, "_utcnow", lambda: datetime(2026, 11, 4, 15, 0, tzinfo=UTC))
    blocks = [
        Block(day=D, start="09:00", end="10:00", category="personal", kind="personal", status="done"),
        Block(day=D, start="10:00", end="11:00", category="Reading", kind="personal", status="done"),
        Block(day=D, start="11:00", end="12:00", category="deep-work", kind="focus", status="done"),
        Block(day=D, start="12:00", end="13:00", category="gym", kind=None, status="done"),
    ]
    monkeypatch.setattr(reports, "load_blocks", lambda db, uid, s, e: [x for x in blocks if s <= x.day <= e])


def test_category_minutes_are_by_kind_with_the_legacy_keys(week):
    r = reports.period_report(None, 1, "Asia/Tashkent", "week")
    assert r["category_minutes"] == [
        {"category": "deep-work", "minutes": 60},
        {"category": "gym", "minutes": 60},
        {"category": "personal", "minutes": 120},
    ]


TEST_URL = os.getenv("TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not TEST_URL, reason="TEST_DATABASE_URL not set (start docker-compose.test.yml)")


@needs_db
def test_load_blocks_reads_the_kind_and_tolerates_a_missing_category():
    eng = create_db_engine(TEST_URL.replace("postgres://", "postgresql://", 1))
    schema = "f13_" + secrets.token_hex(4)
    try:
        with eng.begin() as conn:
            conn.execute(text(f"CREATE SCHEMA {schema}"))
            conn.execute(text(f"SET search_path TO {schema}"))
            conn.execute(text("""
                CREATE TABLE categories (id int PRIMARY KEY, user_id int NOT NULL, kind text NOT NULL);
                CREATE TABLE tasks (id serial PRIMARY KEY, user_id int NOT NULL, name text NOT NULL,
                    category text NOT NULL, category_id int, start_time time NOT NULL, end_time time NOT NULL,
                    status text NOT NULL, actual_start_min int, actual_end_min int, distractions int DEFAULT 0,
                    energy int DEFAULT 3, date date NOT NULL, created_at timestamptz DEFAULT now(),
                    updated_at timestamptz DEFAULT now());
                INSERT INTO categories VALUES (1, 1, 'focus');
                INSERT INTO tasks (user_id, name, category, category_id, start_time, end_time, status, date) VALUES
                    (1, 'a', 'Coding', 1, '09:00', '10:00', 'done', '2026-11-04'),
                    (1, 'b', 'gym', NULL, '10:00', '11:00', 'done', '2026-11-04'),
                    (2, 'c', 'deep-work', NULL, '10:00', '11:00', 'done', '2026-11-04');
            """))
            blocks = reports.load_blocks(Session(bind=conn), 1, D, D)
        assert sorted((blk.category, kind_of(blk)) for blk in blocks) == [("Coding", "focus"), ("gym", "exercise")]
    finally:
        with eng.begin() as conn:
            conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        eng.dispose()


@needs_db
def test_load_blocks_works_on_the_schema_before_00014():
    # Rollback (design §11): goose down 00014 drops categories and tasks.category_id while this
    # service keeps running. Blocks are still read, with the kind from the legacy string.
    eng = create_db_engine(TEST_URL.replace("postgres://", "postgresql://", 1))
    schema = "f13_" + secrets.token_hex(4)
    try:
        with eng.begin() as conn:
            conn.execute(text(f"CREATE SCHEMA {schema}"))
            conn.execute(text(f"SET search_path TO {schema}"))
            conn.execute(text("""
                CREATE TABLE tasks (id serial PRIMARY KEY, user_id int NOT NULL, name text NOT NULL,
                    category text NOT NULL, start_time time NOT NULL, end_time time NOT NULL,
                    status text NOT NULL, actual_start_min int, actual_end_min int, distractions int DEFAULT 0,
                    energy int DEFAULT 3, date date NOT NULL, created_at timestamptz DEFAULT now(),
                    updated_at timestamptz DEFAULT now());
                INSERT INTO tasks (user_id, name, category, start_time, end_time, status, date) VALUES
                    (1, 'a', 'deep-work', '09:00', '10:00', 'done', '2026-11-04'),
                    (1, 'b', 'gym', '10:00', '11:00', 'done', '2026-11-04');
            """))
            session = Session(bind=conn)
            blocks = reports.load_blocks(session, 1, D, D)
            # The session is still usable afterwards (the failed join did not abort it).
            assert len(reports.load_blocks(session, 1, D, D)) == 2
        assert sorted((blk.category, kind_of(blk)) for blk in blocks) == [("deep-work", "focus"), ("gym", "exercise")]
    finally:
        with eng.begin() as conn:
            conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        eng.dispose()


@needs_db
def test_smart_schedule_history_works_on_the_schema_before_00014(monkeypatch):
    from app.smart_schedule.generator import ScheduleGenerator

    monkeypatch.setattr(timeutil, "_utcnow", lambda: datetime(2026, 11, 4, 15, 0, tzinfo=UTC))
    eng = create_db_engine(TEST_URL.replace("postgres://", "postgresql://", 1))
    schema = "f13_" + secrets.token_hex(4)
    try:
        with eng.begin() as conn:
            conn.execute(text(f"CREATE SCHEMA {schema}"))
            conn.execute(text(f"SET search_path TO {schema}"))
            conn.execute(text("""
                CREATE TABLE tasks (id serial PRIMARY KEY, user_id int NOT NULL, name text NOT NULL,
                    category text NOT NULL, start_time time NOT NULL, end_time time NOT NULL,
                    status text NOT NULL, actual_start_min int, actual_end_min int, distractions int DEFAULT 0,
                    energy int DEFAULT 3, date date NOT NULL, created_at timestamptz DEFAULT now(),
                    updated_at timestamptz DEFAULT now());
                INSERT INTO tasks (user_id, name, category, start_time, end_time, status, date) VALUES
                    (1, 'a', 'deep-work', '09:00', '10:00', 'done', '2026-11-03');
            """))
            gen = ScheduleGenerator(Session(bind=conn), 1, "Asia/Tashkent")
            gen.fetch_history()
        assert gen._history["deep-work"] == [540]
    finally:
        with eng.begin() as conn:
            conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        eng.dispose()
