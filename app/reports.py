"""
Analytics payloads for every endpoint, built only from app.metrics.day_metrics.
All "today" / week / month boundaries use the user's IANA zone.
"""

from collections import defaultdict
from dataclasses import asdict
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.metrics import DAILY_DEEP_WORK_TARGET_MIN, DEEP_WORK, Block, DayMetrics, day_metrics, mean_score
from app.models.task import Task
from app.timeutil import local_now

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
DEEP_WORK_SLOTS = [("Morning (6–12)", 6, 12), ("Afternoon (12–17)", 12, 17), ("Evening (17–22)", 17, 22)]


def load_blocks(db: Session, user_id: int, start: date, end: date) -> list[Block]:
    """The user's blocks with start <= date <= end (rows with an unreadable date are skipped)."""
    rows = (
        db.query(Task)
        .filter(Task.user_id == user_id, Task.date >= start.isoformat(), Task.date <= end.isoformat())
        .all()
    )
    blocks = []
    for r in rows:
        try:
            day = date.fromisoformat(str(r.date))
        except ValueError:
            continue
        blocks.append(Block(day=day, start=r.start_time, end=r.end_time, category=r.category,
                            status=r.status, distractions=r.distractions or 0))
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
    end = period_end

    blocks = load_blocks(db, user_id, start, end)
    days = days_metrics(blocks, start, end, now)

    prev_start, prev_end = bounds(start - timedelta(days=1))
    prev_days = days_metrics(load_blocks(db, user_id, prev_start, prev_end), prev_start, prev_end, now)

    focus = mean_score([d.focus_score for d in days])
    prev_focus = mean_score([d.focus_score for d in prev_days])

    category_minutes = defaultdict(int)
    for blk in blocks:
        if blk.completed and blk.minutes > 0:
            category_minutes[blk.category] += blk.minutes

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
        "comparison": {
            "previous_focus_score": prev_focus,
            "change": _rounded(focus - prev_focus) if focus is not None and prev_focus is not None else None,
        },
    }


# ------------------------------------------------------------------ #
#  Focus patterns
# ------------------------------------------------------------------ #

def heatmap_matrix(blocks: list[Block]) -> dict:
    """Completed deep-work hours by weekday x hour (06–23)."""
    hours = list(range(6, 24))
    values = {day: [0.0] * len(hours) for day in WEEKDAYS}
    for blk in blocks:
        if not (blk.completed and blk.category == DEEP_WORK) or blk.minutes == 0:
            continue
        sh, eh = blk.start_min // 60, blk.end_min // 60
        wd = WEEKDAYS[blk.day.weekday()]
        for h in range(max(sh, 6), min(eh + 1, 24)):
            values[wd][h - 6] += (blk.minutes / 60) / max(eh - sh + 1, 1)
    return {"weekdays": WEEKDAYS, "hours": hours,
            "values": [[round(v, 2) for v in values[d]] for d in WEEKDAYS]}


def focus_patterns(db: Session, user_id: int, tz: str, days: int) -> dict:
    now = local_now(tz)
    end = now.date()
    start = end - timedelta(days=days - 1)
    blocks = load_blocks(db, user_id, start, end)
    daily = days_metrics(blocks, start, end, now)

    by_weekday = defaultdict(list)
    for d in daily:
        by_weekday[date.fromisoformat(d.date).weekday()].append(d.focus_score)

    slot_minutes = {name: 0 for name, _, _ in DEEP_WORK_SLOTS}
    for blk in blocks:
        if blk.completed and blk.category == DEEP_WORK and blk.minutes > 0:
            for name, lo, hi in DEEP_WORK_SLOTS:
                if lo * 60 <= blk.start_min < hi * 60:
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
