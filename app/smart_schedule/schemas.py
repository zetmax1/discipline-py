"""
Smart Schedule — Pydantic Schemas
"""

from pydantic import BaseModel, Field
from typing import List

class Commitment(BaseModel):
    id: str
    name: str
    startTime: str  # "HH:MM"
    endTime: str    # "HH:MM"
    days: List[str] # ["Monday", "Tuesday", ...]

class WeeklyGoals(BaseModel):
    deepWorkHours: float = Field(default=15.0)
    studyHours: float = Field(default=10.0)
    restHours: float = Field(default=7.0)

class SmartScheduleRequest(BaseModel):
    commitments: List[Commitment]
    goals: WeeklyGoals

class ScheduleBlock(BaseModel):
    id: str
    name: str
    category: str      # 'fixed', 'deep-work', 'study', 'rest'
    startTime: str     # "HH:MM"
    endTime: str       # "HH:MM"
    day: str           # e.g., "Monday"

class SmartScheduleResponse(BaseModel):
    blocks: List[ScheduleBlock]
    reasoning: List[str]
