import statistics
import uuid
from datetime import timedelta
from typing import ClassVar

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.metrics import DONE, parse_clock
from app.models.task import Task
from app.smart_schedule.schemas import (
    BlockLabel,
    ScheduleBlock,
    ScheduleReason,
    SmartScheduleRequest,
    SmartScheduleResponse,
)
from app.timeutil import local_now

SLOT = 30                        # minutes; every placed block starts/ends on a 30-minute boundary
SLOTS_PER_DAY = 24 * 60 // SLOT
DAY_START = 6 * 60               # nothing is scheduled before 06:00
WORK_END = 22 * 60               # deep work / study end by 22:00
DAY_END = 24 * 60                # nothing crosses midnight
MIN_HISTORY_BLOCKS = 10          # completed blocks of a category needed to claim a learned preference

# category, label, label code (translated by the web), goal field, default start, window end
CATEGORIES: list[tuple[str, str, BlockLabel, str, int, int]] = [
    ("deep-work", "Deep Work", "deep_work", "deepWorkHours", 9 * 60, WORK_END),
    ("study", "Study", "study", "studyHours", 14 * 60, WORK_END),
    ("rest", "Rest", "rest", "restHours", 19 * 60, DAY_END),
]


def _fmt(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _round_to_slot(minutes: float) -> int:
    return round(minutes / SLOT) * SLOT


class ScheduleGenerator:
    DAYS: ClassVar[list[str]] = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

    # Which days each category uses and their relative share (existing pattern:
    # deep work on weekdays, lighter study on weekends, rest every day).
    DAY_WEIGHTS: ClassVar[dict[str, dict[str, int]]] = {
        "deep-work": {d: 1 for d in DAYS[:5]},
        "study": {**{d: 2 for d in DAYS[:5]}, "Saturday": 1, "Sunday": 1},
        "rest": {d: 1 for d in DAYS},
    }

    def __init__(self, db: Session, user_id: int, tz: str):
        self.db = db
        self.user_id = user_id
        self.tz = tz
        self._history: dict[str, list[int]] = {}

    def history_cutoff(self, days_back: int) -> str:
        """Earliest history date (YYYY-MM-DD), counted back from today in the user's zone."""
        return (local_now(self.tz) - timedelta(days=days_back)).strftime('%Y-%m-%d')

    def fetch_history(self, days_back: int = 30):
        """Start times (minutes) of completed blocks per category in the last `days_back` days."""
        tasks = self.db.query(Task).filter(
            Task.user_id == self.user_id,
            Task.date >= self.history_cutoff(days_back),
            Task.status.in_(DONE),
        ).order_by(desc(Task.date)).all()
        self._history = {cat: [] for cat, *_ in CATEGORIES}
        for t in tasks:
            start = parse_clock(t.start_time)
            if t.category in self._history and start is not None:
                self._history[t.category].append(start)

    def preferred_start(self, category: str, default: int, window_end: int) -> tuple[int, bool]:
        """Median completed start time with enough history, else the default; (minutes, learned)."""
        starts = self._history.get(category, [])
        learned = len(starts) >= MIN_HISTORY_BLOCKS
        start = _round_to_slot(statistics.median(starts)) if learned else default
        return min(max(start, DAY_START), window_end - SLOT), learned

    @staticmethod
    def _commitment_slots(start: str, end: str) -> set[int]:
        """Slots overlapping the commitment. An end before the start wraps (e.g. sleep 23:00-07:00
        occupies 23:00-24:00 and 00:00-07:00 of the same day, as before)."""
        s, e = parse_clock(start), parse_clock(end)
        if s is None or e is None:  # the request schema already rejects these
            raise ValueError(f"commitment times must be HH:MM, got {start!r}-{end!r}")
        spans = [(s, e)] if e > s else [(s, DAY_END), (0, e)]
        return {k for k in range(SLOTS_PER_DAY) for lo, hi in spans if k * SLOT < hi and k * SLOT + SLOT > lo}

    @staticmethod
    def _quotas(n: int, weights: dict[str, int]) -> dict[str, int]:
        """Split n slots across days by weight (largest remainder, ties in day order)."""
        total = sum(weights.values())
        exact = {d: n * w / total for d, w in weights.items()}
        quotas = {d: int(x) for d, x in exact.items()}
        rest = n - sum(quotas.values())
        for d in sorted(exact, key=lambda d: -(exact[d] - quotas[d]))[:rest]:
            quotas[d] += 1
        return quotas

    @staticmethod
    def _take(free: set[int], k: int, preferred: int, lo: int, hi: int) -> list[int]:
        """Take up to k free slots in [lo, hi), nearest to `preferred` first (later side on ties)."""
        order = sorted(range(lo, hi), key=lambda s: (abs(s - preferred), -s))
        chosen = [s for s in order if s in free][:k]
        free.difference_update(chosen)
        return chosen

    def generate(self, request: SmartScheduleRequest) -> SmartScheduleResponse:
        self.fetch_history()
        blocks: list[ScheduleBlock] = []
        reasoning: list[str] = []
        reasons: list[ScheduleReason] = []
        placed_minutes: dict[str, int] = {}
        shortfall_minutes: dict[str, int] = {}

        free = {day: set(range(SLOTS_PER_DAY)) for day in self.DAYS}
        for day in self.DAYS:
            for c in (c for c in request.commitments if day in c.days):
                free[day] -= self._commitment_slots(c.startTime, c.endTime)
                blocks.append(ScheduleBlock(id=str(uuid.uuid4()), name=c.name, category='fixed',
                                            startTime=c.startTime, endTime=c.endTime, day=day, label=None))

        for category, label, code, goal_field, default, window_end in CATEGORIES:
            preferred, learned = self.preferred_start(category, default, window_end)
            if learned:
                n = len(self._history[category])
                reasoning.append(f"{label}: learned from your history — usually starts around {_fmt(preferred)} "
                                 f"({n} completed blocks in the last 30 days).")
                reasons.append(ScheduleReason(code="learned", category=category, start_time=_fmt(preferred), blocks=n))
            else:
                reasoning.append(f"{label}: Default placement — not enough history yet (placed around {_fmt(preferred)}).")
                reasons.append(ScheduleReason(code="default", category=category, start_time=_fmt(preferred)))

            needed = round(getattr(request.goals, goal_field) * 60 / SLOT)
            weights = self.DAY_WEIGHTS[category]
            lo, hi, pref = DAY_START // SLOT, window_end // SLOT, preferred // SLOT
            taken = {day: self._take(free[day], q, pref, lo, hi) for day, q in self._quotas(needed, weights).items()}
            missing = needed - sum(len(s) for s in taken.values())
            for day in weights:                       # spill what didn't fit to other days
                if missing <= 0:
                    break
                extra = self._take(free[day], missing, pref, lo, hi)
                taken[day] += extra
                missing -= len(extra)

            placed_minutes[category] = (needed - missing) * SLOT
            shortfall_minutes[category] = missing * SLOT
            if missing:
                reasoning.append(f"Could not fit {missing * SLOT / 60:g} h of {label} — not enough free time this week.")
                reasons.append(ScheduleReason(code="shortfall", category=category, minutes=missing * SLOT))

            for day in self.DAYS:
                light = category == "study" and day in ("Saturday", "Sunday")
                name = "Light Study / Review" if light else label
                block_label: BlockLabel = "light_study" if light else code
                for start, end in self._runs(sorted(taken.get(day, []))):
                    blocks.append(ScheduleBlock(id=str(uuid.uuid4()), name=name, category=category,
                                                startTime=_fmt(start * SLOT), endTime=_fmt(end * SLOT), day=day,
                                                label=block_label))

        return SmartScheduleResponse(blocks=blocks, reasoning=reasoning, reasons=reasons,
                                     placed_minutes=placed_minutes, shortfall_minutes=shortfall_minutes)

    @staticmethod
    def _runs(slots: list[int]) -> list[tuple[int, int]]:
        """Merge sorted slot indices into contiguous [start, end) runs."""
        runs: list[tuple[int, int]] = []
        for s in slots:
            if runs and runs[-1][1] == s:
                runs[-1] = (runs[-1][0], s + 1)
            else:
                runs.append((s, s + 1))
        return runs
