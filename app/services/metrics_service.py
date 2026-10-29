"""
MetricsService — core metric calculations.
Operates on pandas DataFrames built from Task records.
"""

from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.models.task import Task


class MetricsService:
    """Computes low-level productivity metrics from task data."""

    # ------------------------------------------------------------------ #
    #  Data loading helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _tasks_to_dataframe(tasks: list[Task]) -> pd.DataFrame:
        """Convert a list of Task ORM objects into a pandas DataFrame."""
        if not tasks:
            return pd.DataFrame(columns=[
                "id", "user_id", "name", "category", "start_time",
                "end_time", "status", "distractions", "energy", "date",
                "duration_hours",
            ])

        rows = []
        for t in tasks:
            rows.append({
                "id": t.id,
                "user_id": t.user_id,
                "name": t.name,
                "category": t.category,
                "start_time": t.start_time,
                "end_time": t.end_time,
                "status": t.status,
                "distractions": t.distractions,
                "energy": t.energy,
                "date": t.date,
                "duration_hours": t.duration_hours(),
            })
        return pd.DataFrame(rows)

    @staticmethod
    def load_tasks(
        db: Session,
        user_id: int,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        """Query tasks for a user within a date range and return as DataFrame."""
        tasks = (
            db.query(Task)
            .filter(
                Task.user_id == user_id,
                Task.date >= start_date,
                Task.date <= end_date,
            )
            .order_by(Task.date, Task.start_time)
            .all()
        )
        return MetricsService._tasks_to_dataframe(tasks)

    # ------------------------------------------------------------------ #
    #  Core metrics
    # ------------------------------------------------------------------ #

    @staticmethod
    def completion_rate(df: pd.DataFrame) -> float:
        """Percentage of tasks completed (0–100)."""
        if df.empty:
            return 0.0
        total = len(df)
        completed = len(df[df["status"] == "completed"])
        return round(completed / total * 100, 1)

    @staticmethod
    def deep_work_hours(df: pd.DataFrame) -> float:
        """Total completed deep-work hours."""
        mask = (df["category"] == "deep-work") & (df["status"] == "completed")
        return round(float(df.loc[mask, "duration_hours"].sum()), 2)

    @staticmethod
    def total_work_hours(df: pd.DataFrame) -> float:
        """Total hours of all completed tasks."""
        mask = df["status"] == "completed"
        return round(float(df.loc[mask, "duration_hours"].sum()), 2)

    @staticmethod
    def average_distractions(df: pd.DataFrame) -> float:
        """Mean distractions per task."""
        if df.empty:
            return 0.0
        return round(float(df["distractions"].mean()), 2)

    @staticmethod
    def average_energy(df: pd.DataFrame) -> float:
        """Mean energy across tasks."""
        if df.empty:
            return 0.0
        return round(float(df["energy"].mean()), 2)

    @staticmethod
    def focus_score(df: pd.DataFrame) -> int:
        """
        Composite focus score (0–100).

        Formula:
          deep_work_ratio × 40  +  completion_rate × 0.35  +  low_distraction_bonus × 25

        low_distraction_bonus = 1 - min(avg_distractions / 5, 1)
        """
        if df.empty:
            return 0

        total_hours = MetricsService.total_work_hours(df)
        dw_hours = MetricsService.deep_work_hours(df)
        comp_rate = MetricsService.completion_rate(df)
        avg_distr = MetricsService.average_distractions(df)

        dw_ratio = (dw_hours / total_hours) if total_hours > 0 else 0
        low_distr_bonus = 1 - min(avg_distr / 5, 1)

        score = dw_ratio * 40 + comp_rate * 0.35 + low_distr_bonus * 25
        return int(np.clip(round(score), 0, 100))

    # ------------------------------------------------------------------ #
    #  Per-day breakdown
    # ------------------------------------------------------------------ #

    @staticmethod
    def daily_metrics(df: pd.DataFrame) -> list[dict]:
        """Return a list of per-day metric dicts."""
        if df.empty:
            return []

        results = []
        for date, group in df.groupby("date"):
            results.append({
                "date": date,
                "completion_rate": MetricsService.completion_rate(group),
                "deep_work_hours": MetricsService.deep_work_hours(group),
                "total_hours": MetricsService.total_work_hours(group),
                "focus_score": MetricsService.focus_score(group),
                "avg_distractions": MetricsService.average_distractions(group),
                "avg_energy": MetricsService.average_energy(group),
                "task_count": len(group),
            })
        return results
