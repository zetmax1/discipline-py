"""
Analytics payloads for every endpoint, built only from app.metrics.day_metrics.
All "today" / week / month boundaries use the user's IANA zone.
"""

import statistics
from collections import defaultdict
from dataclasses import asdict
from datetime import date, timedelta
from typing import Any, NamedTuple

import numpy as np
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from app.metrics import (
    DAILY_DEEP_WORK_TARGET_MIN,
    KIND_KEYS,
    Block,
    DayMetrics,
    day_metrics,
    kind_of,
    mean_score,
    streak_length,
)
from app.models.task import Category, Task
from app.timeutil import local_now

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
PATTERN_WINDOW_DAYS = 30
PATTERN_MIN_DAYS = 7
STREAK_LOOKBACK_DAYS = 365
DEEP_WORK_SLOTS = [("Morning (6–12)", 6, 12), ("Afternoon (12–17)", 12, 17), ("Evening (17–22)", 17, 22)]


UNDEFINED_TABLE, UNDEFINED_COLUMN = "42P01", "42703"
# The tasks columns that exist before migration 00014 (no category_id).
LEGACY_TASK_COLUMNS = (Task.date, Task.start_time, Task.end_time, Task.category, Task.status, Task.distractions,
                       Task.actual_start_min, Task.actual_end_min)


def load_blocks(db: Session, user_id: int, start: date, end: date) -> list[Block]:
    """The user's blocks with start <= date <= end (rows with an unreadable date are skipped)."""
    in_range = (Task.user_id == user_id, Task.date >= start.isoformat(), Task.date <= end.isoformat())
    rows: list[tuple[Any, str | None]]  # (a tasks row, its category's kind or None)
    try:
        # A savepoint: on the schema before migration 00014 (an API rollback, design §11) the join
        # fails, and only the savepoint is rolled back, not the caller's transaction.
        with db.begin_nested():
            rows = [(r, kind) for r, kind in db.query(Task, Category.kind)
                    .outerjoin(Category, Category.id == Task.category_id).filter(*in_range).all()]
    except ProgrammingError as err:
        if getattr(err.orig, "pgcode", None) not in (UNDEFINED_TABLE, UNDEFINED_COLUMN):
            raise
        # No categories yet: every block takes its kind from the legacy string (kind_of).
        rows = [(r, None) for r in db.query(*LEGACY_TASK_COLUMNS).filter(*in_range).all()]
    blocks = []
    for r, kind in rows:
        try:
            day = date.fromisoformat(str(r.date))
        except ValueError:
            continue
        blocks.append(Block(day=day, start=r.start_time, end=r.end_time, category=r.category,
                            status=r.status, distractions=r.distractions or 0,
                            actual_start_min=r.actual_start_min, actual_end_min=r.actual_end_min, kind=kind))
    return blocks


def daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def days_metrics(blocks: list[Block], start: date, end: date, now) -> list[DayMetrics]:
    by_day = defaultdict(list)
    for blk in blocks:
        by_day[blk.day].append(blk)
    return [day_metrics(d, by_day[d], now) for d in daterange(start, end)]


def week_bounds(day: date) -> tuple[date, date]:
    monday = day - timedelta(days=day.weekday())
    return monday, monday + timedelta(days=6)


def month_bounds(day: date) -> tuple[date, date]:
    first = day.replace(day=1)
    next_first = (first + timedelta(days=32)).replace(day=1)
    return first, next_first - timedelta(days=1)


def _rounded(x):
    return None if x is None else round(x, 1)


# ------------------------------------------------------------------ #
#  Today (dashboard)
# ------------------------------------------------------------------ #

def today_report(db: Session, user_id: int, tz: str) -> dict:
    now = local_now(tz)
    today = now.date()
    metrics = day_metrics(today, load_blocks(db, user_id, today, today), now)
    return {**asdict(metrics), "daily_deep_work_target_minutes": DAILY_DEEP_WORK_TARGET_MIN}


# ------------------------------------------------------------------ #
#  Week / month
# ------------------------------------------------------------------ #

def period_report(db: Session, user_id: int, tz: str, kind: str) -> dict:
    now = local_now(tz)
    today = now.date()
    bounds = week_bounds if kind == "week" else month_bounds
    start, period_end = bounds(today)
    end = min(period_end, today)   # never report future days

    blocks = load_blocks(db, user_id, start, end)
    days = days_metrics(blocks, start, end, now)

    prev_start, prev_end = bounds(start - timedelta(days=1))
    prev_days = days_metrics(load_blocks(db, user_id, prev_start, prev_end), prev_start, prev_end, now)

    focus = mean_score([d.focus_score for d in days])
    prev_focus = mean_score([d.focus_score for d in prev_days])

    category_minutes: defaultdict[str, int] = defaultdict(int)
    for blk in blocks:
        if blk.completed and blk.minutes > 0:
            category_minutes[KIND_KEYS[kind_of(blk)]] += blk.minutes

    return {
        "range": kind,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "period_end_date": period_end.isoformat(),
        "focus_score": focus,
        "planned_minutes": sum(d.planned_minutes for d in days),
        "completed_minutes": sum(d.completed_minutes for d in days),
        "deep_work_minutes": sum(d.deep_work_minutes for d in days),
        "days": [asdict(d) for d in days],
        "category_minutes": [{"category": c, "minutes": m} for c, m in sorted(category_minutes.items())],
        "streak": current_streak(db, user_id, now),
        "patterns": patterns(db, user_id, now),
        "comparison": {
            "previous_focus_score": prev_focus,
            "change": _rounded(focus - prev_focus) if focus is not None and prev_focus is not None else None,
        },
    }


def current_streak(db: Session, user_id: int, now) -> int:
    """Streak counted back from yesterday, the most recent finished day."""
    yesterday = now.date() - timedelta(days=1)
    start = yesterday - timedelta(days=STREAK_LOOKBACK_DAYS - 1)
    days = days_metrics(load_blocks(db, user_id, start, yesterday), start, yesterday, now)
    return streak_length(list(reversed(days)))


def deep_minutes_by_hour(blocks: list[Block]) -> list[int]:
    """Completed deep-work minutes overlapping each hour [h, h+1), h = 0..23."""
    minutes = [0] * 24
    for blk in blocks:
        span = blk.span
        if not (blk.completed and blk.is_focus) or span is None:
            continue
        start_min, end_min = span
        for h in range(24):
            overlap = min(end_min, (h + 1) * 60) - max(start_min, h * 60)
            if overlap > 0:
                minutes[h] += overlap
    return minutes


class DueDay(NamedTuple):
    """A day with due blocks: it always has a completion rate and a focus score."""
    date: str
    focus_score: int
    completion: float


def due_days(days: list[DayMetrics]) -> list[DueDay]:
    return [DueDay(d.date, d.focus_score, d.completion) for d in days
            if d.completion is not None and d.focus_score is not None]


def patterns(db: Session, user_id: int, now) -> dict:
    """Patterns over the trailing 30 days (up to today); needs 7 days with due blocks."""
    end = now.date()
    start = end - timedelta(days=PATTERN_WINDOW_DAYS - 1)
    blocks = load_blocks(db, user_id, start, end)
    daily = due_days(days_metrics(blocks, start, end, now))

    if len(daily) < PATTERN_MIN_DAYS:
        return {"insufficient_data": True, "days_needed": PATTERN_MIN_DAYS - len(daily),
                "days_with_data": len(daily), "window_days": PATTERN_WINDOW_DAYS}

    by_weekday: defaultdict[int, list[int]] = defaultdict(list)
    for d in daily:
        by_weekday[date.fromisoformat(d.date).weekday()].append(d.focus_score)
    best = max(by_weekday, key=lambda wd: (statistics.mean(by_weekday[wd]), -wd))
    best_score = round(statistics.mean(by_weekday[best]), 1)

    hour_minutes = deep_minutes_by_hour(blocks)
    peak_hour = hour_minutes.index(max(hour_minutes)) if max(hour_minutes) > 0 else None

    scores = np.array([d.focus_score for d in daily], dtype=float)
    slope = float(np.polyfit(np.arange(len(scores), dtype=float), scores, 1)[0])
    trend = "improving" if slope > 0.5 else "declining" if slope < -0.5 else "stable"

    consistency = max(0, min(100, round(100 - statistics.pstdev(d.completion * 100 for d in daily))))

    insights = [f"Your best day is {WEEKDAY_NAMES[best]}, with an average focus score of {best_score}."]
    if peak_hour is not None:
        insights.append(f"Most of your deep work happens around {peak_hour:02d}:00.")
    insights.append({
        "improving": "Your daily focus score is trending up.",
        "stable": "Your daily focus score is steady.",
        "declining": "Your daily focus score is trending down.",
    }[trend])
    insights.append(f"Consistency of completion: {consistency}/100.")

    return {
        "insufficient_data": False,
        "days_with_data": len(daily),
        "window_days": PATTERN_WINDOW_DAYS,
        "best_weekday": WEEKDAY_NAMES[best],
        "peak_hour": peak_hour,
        "trend": trend,
        "consistency_score": consistency,
        "insights": insights,
    }


# ------------------------------------------------------------------ #
#  Focus patterns
# ------------------------------------------------------------------ #

def heatmap_matrix(blocks: list[Block]) -> dict:
    """Completed deep-work hours by weekday x hour (00–23), bucketed by minute overlap with [h, h+1)."""
    by_weekday = defaultdict(list)
    for blk in blocks:
        by_weekday[blk.day.weekday()].append(blk)
    values = [[round(m / 60, 2) for m in deep_minutes_by_hour(by_weekday[wd])] for wd in range(7)]
    return {"weekdays": WEEKDAYS, "hours": list(range(24)), "values": values}


def focus_patterns(db: Session, user_id: int, tz: str, days: int) -> dict:
    now = local_now(tz)
    end = now.date()
    start = end - timedelta(days=days - 1)
    blocks = load_blocks(db, user_id, start, end)
    daily = days_metrics(blocks, start, end, now)

    by_weekday: defaultdict[int, list[int | None]] = defaultdict(list)
    for d in daily:
        by_weekday[date.fromisoformat(d.date).weekday()].append(d.focus_score)

    slot_minutes = {name: 0 for name, _, _ in DEEP_WORK_SLOTS}
    for blk in blocks:
        span = blk.span
        if blk.completed and blk.is_focus and span is not None:
            for name, lo, hi in DEEP_WORK_SLOTS:
                if lo * 60 <= span[0] < hi * 60:
                    slot_minutes[name] += blk.minutes
                    break

    return {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "days": days,
        "heatmap": heatmap_matrix(blocks),
        "productivity_by_weekday": [
            {"day": WEEKDAYS[i], "focus_score": mean_score(by_weekday[i])} for i in range(7)
        ],
        "deep_work_by_slot": [{"label": name, "minutes": m} for name, m in slot_minutes.items()],
        "distraction_trend": [
            {"date": d.date,
             "distractions_per_hour": round(d.distractions / (d.deep_work_minutes / 60), 2) if d.deep_work_minutes else None}
            for d in daily
        ],
    }
