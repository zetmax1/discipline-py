"""
Smart Schedule — Pydantic Schemas
"""

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

DayName = Literal["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

_HHMM = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$|^24:00$")


class Commitment(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=100)
    startTime: str  # "HH:MM", 00:00–24:00
    endTime: str    # "HH:MM", 00:00–24:00; earlier than start = overnight (e.g. sleep)
    days: list[DayName] = Field(min_length=1, max_length=7)

    @field_validator("startTime", "endTime")
    @classmethod
    def _hhmm(cls, v: str) -> str:
        if not _HHMM.match(v):
            raise ValueError("must be HH:MM between 00:00 and 24:00")
        return v

    @field_validator("endTime")
    @classmethod
    def _not_empty_span(cls, v: str, info) -> str:
        if info.data.get("startTime") == v:
            raise ValueError("must differ from startTime")
        return v

    @field_validator("days")
    @classmethod
    def _unique_days(cls, v: list[str]) -> list[str]:
        if len(set(v)) != len(v):
            raise ValueError("must not repeat a day")
        return v


def _goal(default: float):
    return Field(default=default, ge=0, le=80, multiple_of=0.5, allow_inf_nan=False)


class WeeklyGoals(BaseModel):
    """Weekly hours per category: 0–80 in 0.5-hour steps."""
    deepWorkHours: float = _goal(15.0)
    studyHours: float = _goal(10.0)
    restHours: float = _goal(7.0)


class SmartScheduleRequest(BaseModel):
    commitments: list[Commitment] = Field(max_length=50)
    goals: WeeklyGoals


BlockLabel = Literal["deep_work", "study", "light_study", "rest"]


class ScheduleBlock(BaseModel):
    id: str
    name: str          # English; the web shows `label` (translated) or the commitment's own name
    category: str      # 'fixed', 'deep-work', 'study', 'rest'
    startTime: str     # "HH:MM"
    endTime: str       # "HH:MM"
    day: str           # e.g., "Monday"
    label: BlockLabel | None  # None for commitments


class ScheduleReason(BaseModel):
    """One `reasoning` line as data, so the web can translate it."""
    code: Literal["learned", "default", "shortfall"]
    category: str
    start_time: str | None = None   # learned/default: usual or default start "HH:MM"
    blocks: int | None = None       # learned: completed blocks in the last 30 days
    minutes: int | None = None      # shortfall: minutes that did not fit


class SmartScheduleResponse(BaseModel):
    blocks: list[ScheduleBlock]
    reasoning: list[str]                # English, kept for old clients
    reasons: list[ScheduleReason]
    placed_minutes: dict[str, int]      # per category
    shortfall_minutes: dict[str, int]   # requested but could not fit, per category
