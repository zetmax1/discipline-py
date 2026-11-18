"""
The one place analytics metrics are defined. Every endpoint builds on day_metrics().

For day D in the user's zone, a block is "due" once its end time has passed. Moved blocks count
nowhere (their replacement counts); skipped blocks are planned but never completed.
Completed minutes of a block: `done` -> its actual minutes when recorded, else its planned minutes;
`partial` -> its actual minutes (0 when none were recorded); anything else -> 0.
  planned_minutes / completed_minutes  all of D's blocks / their completed minutes ("Planned" / "Done")
  completion   = min(1, completed minutes of due blocks / planned minutes of due blocks) (None if nothing due)
  deep         = min(1, completed deep-work minutes / DAILY_DEEP_WORK_TARGET_MIN)
  distraction  = max(0, 1 - distractions per completed deep-work hour / DISTRACTIONS_PER_HOUR_LIMIT),
                 0 when no deep work was completed
  focus_score  = round half up of 100 * (0.5*completion + 0.3*deep + 0.2*distraction); None if nothing due
A week or month score is the mean of the daily scores that exist.
Streak: counting back from the most recent finished day, days with nothing due are
skipped, days with completion >= STREAK_COMPLETION_THRESHOLD count, the first day
below it ends the streak.
"""

import math
from dataclasses import dataclass
from datetime import date, datetime

DAILY_DEEP_WORK_TARGET_MIN = 180
DISTRACTIONS_PER_HOUR_LIMIT = 4

STREAK_COMPLETION_THRESHOLD = 0.7

WEIGHT_COMPLETION = 0.5
WEIGHT_DEEP = 0.3
WEIGHT_DISTRACTION = 0.2

DEEP_WORK = "deep-work"
DONE = {"done", "completed"}  # "completed" = legacy name of done
PARTIAL = "partial"
MOVED = "moved"


def parse_clock(value) -> int | None:
    """Minutes since midnight for "HH:MM" (00:00–24:00), else None."""
    try:
        hh, mm = str(value).split(":")[:2]
        h, m = int(hh), int(mm)
    except (ValueError, AttributeError):
        return None
    if not (0 <= h <= 24 and 0 <= m <= 59) or (h == 24 and m != 0):
        return None
    return h * 60 + m


@dataclass(frozen=True)
class Block:
    day: date
    start: str  # "HH:MM"
    end: str    # "HH:MM" ("24:00" allowed)
    category: str
    status: str
    distractions: int = 0
    actual_start_min: int | None = None
    actual_end_min: int | None = None

    @property
    def start_min(self) -> int | None:
        return parse_clock(self.start)

    @property
    def end_min(self) -> int | None:
        return parse_clock(self.end)

    @property
    def span(self) -> tuple[int, int] | None:
        """(start, end) in minutes; None for unparseable, zero-length or inverted (legacy) rows."""
        s, e = self.start_min, self.end_min
        if s is None or e is None or e <= s:
            return None
        return s, e

    @property
    def minutes(self) -> int:
        """Duration; unparseable, zero-length or inverted (legacy) rows count as 0."""
        span = self.span
        return span[1] - span[0] if span else 0

    @property
    def actual_minutes(self) -> int | None:
        """Recorded actual duration, or None when no (valid) actual times were recorded."""
        s, e = self.actual_start_min, self.actual_end_min
        if s is None or e is None or e <= s:
            return None
        return e - s

    @property
    def completed_minutes(self) -> int:
        if self.status in DONE:
            actual = self.actual_minutes
            return self.minutes if actual is None else actual
        if self.status == PARTIAL:
            return self.actual_minutes or 0
        return 0

    @property
    def completed(self) -> bool:
        return self.completed_minutes > 0 or (self.status in DONE and self.minutes == 0)

    def is_due(self, now: datetime) -> bool:
        """Due once its end time has passed (end <= now) in the user's zone."""
        today = now.date()
        if self.day < today:
            return True
        if self.day > today:
            return False
        end = self.end_min
        return end is not None and end <= now.hour * 60 + now.minute


@dataclass(frozen=True)
class DayMetrics:
    date: str
    planned_minutes: int
    completed_minutes: int
    due_planned_minutes: int
    due_completed_minutes: int
    deep_work_minutes: int
    distractions: int
    blocks_total: int
    blocks_due: int
    blocks_completed: int
    completion: float | None
    deep: float
    distraction: float
    focus_score: int | None


def round_half_up(x: float) -> int:
    return math.floor(x + 0.5)


def day_metrics(day: date, blocks: list[Block], now: datetime) -> DayMetrics:
    """Metrics for one calendar day; `now` is the current wall-clock time in the user's zone."""
    blocks = [b for b in blocks if b.day == day and b.status != MOVED]
    due = [b for b in blocks if b.is_due(now)]
    due_planned = sum(b.minutes for b in due)
    due_completed = sum(b.completed_minutes for b in due)

    deep_blocks = [b for b in blocks if b.completed and b.category == DEEP_WORK]
    deep_minutes = sum(b.completed_minutes for b in deep_blocks)
    deep_distractions = sum(max(0, b.distractions) for b in deep_blocks)

    completion = min(1.0, due_completed / due_planned) if due_planned > 0 else None
    deep = min(1.0, deep_minutes / DAILY_DEEP_WORK_TARGET_MIN)
    if deep_minutes > 0:
        per_hour = deep_distractions / (deep_minutes / 60)
        distraction = max(0.0, 1 - per_hour / DISTRACTIONS_PER_HOUR_LIMIT)
    else:
        distraction = 0.0

    focus = None
    if completion is not None:
        focus = round_half_up(100 * (WEIGHT_COMPLETION * completion + WEIGHT_DEEP * deep
                                     + WEIGHT_DISTRACTION * distraction))

    return DayMetrics(
        date=day.isoformat(),
        planned_minutes=sum(b.minutes for b in blocks),
        completed_minutes=sum(b.completed_minutes for b in blocks),
        due_planned_minutes=due_planned,
        due_completed_minutes=due_completed,
        deep_work_minutes=deep_minutes,
        distractions=deep_distractions,
        blocks_total=len(blocks),
        blocks_due=len(due),
        blocks_completed=sum(1 for b in blocks if b.completed),
        completion=completion,
        deep=deep,
        distraction=distraction,
        focus_score=focus,
    )


def mean_score(scores: list[int | None]) -> float | None:
    """Mean of the daily scores that exist (days without data are excluded), 1 decimal."""
    present = [s for s in scores if s is not None]
    if not present:
        return None
    return round(sum(present) / len(present), 1)


def streak_length(finished_days_newest_first: list[DayMetrics]) -> int:
    """Consecutive finished days at or above the completion threshold (empty days skipped)."""
    streak = 0
    for d in finished_days_newest_first:
        if d.completion is None:
            continue
        if d.completion < STREAK_COMPLETION_THRESHOLD:
            break
        streak += 1
    return streak
