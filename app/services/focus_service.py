"""
FocusService — focus-specific analytics.
Analyses deep work patterns, distraction trends, and optimal focus windows.
"""

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.services.metrics_service import MetricsService


class FocusService:
    """Focus pattern analysis — when and how the user focuses best."""

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------ #
    #  Focus patterns report
    # ------------------------------------------------------------------ #

    def focus_patterns(self, user_id: int, days: int = 30) -> dict:
        """
        Analyse focus patterns over the last N days.
        Returns:
          - heatmap_data: hour × weekday matrix of deep-work hours
          - peak_hours: best hours for deep work
          - best_day: most productive weekday
          - distraction_trend: daily average distractions
        """
        end = datetime.now()
        start = end - timedelta(days=days - 1)
        df = MetricsService.load_tasks(
            self.db, user_id,
            start.strftime("%Y-%m-%d"),
            end.strftime("%Y-%m-%d"),
        )

        result = {
            "period_days": days,
            "heatmap_data": self._build_heatmap_data(df),
            "peak_hours": self._find_peak_hours(df),
            "productivity_by_weekday": self._productivity_by_weekday(df),
            "distraction_trend": self._distraction_trend(df),
            "deep_work_distribution": self._deep_work_by_time_slot(df),
        }
        return result

    # ------------------------------------------------------------------ #
    #  Heatmap: hour × weekday
    # ------------------------------------------------------------------ #

    @staticmethod
    def _build_heatmap_data(df: pd.DataFrame) -> dict:
        """
        Build a matrix (dict of lists) where rows = weekdays (Mon–Sun)
        and columns = hours (6–23), values = total deep-work hours.
        """
        weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        hours = list(range(6, 24))  # 06:00–23:00

        matrix = {day: [0.0] * len(hours) for day in weekdays}

        if df.empty:
            return {"weekdays": weekdays, "hours": hours, "values": matrix}

        deep = df[(df["category"] == "deep-work") & (df["status"] == "completed")].copy()
        if deep.empty:
            return {"weekdays": weekdays, "hours": hours, "values": matrix}

        deep["date_parsed"] = pd.to_datetime(deep["date"])
        deep["weekday"] = deep["date_parsed"].dt.day_name().str[:3]

        for _, row in deep.iterrows():
            try:
                sh = int(row["start_time"].split(":")[0])
                eh = int(row["end_time"].split(":")[0])
                wd = row["weekday"]
                if wd not in matrix:
                    continue
                for h in range(max(sh, 6), min(eh + 1, 24)):
                    idx = h - 6
                    if 0 <= idx < len(hours):
                        matrix[wd][idx] += row["duration_hours"] / max(eh - sh + 1, 1)
            except (ValueError, IndexError):
                continue

        # Round values
        for day in weekdays:
            matrix[day] = [round(v, 2) for v in matrix[day]]

        return {"weekdays": weekdays, "hours": hours, "values": matrix}

    # ------------------------------------------------------------------ #
    #  Peak deep-work hours
    # ------------------------------------------------------------------ #

    @staticmethod
    def _find_peak_hours(df: pd.DataFrame) -> list[dict]:
        """Find the hours of day with the most completed deep-work."""
        if df.empty:
            return []

        deep = df[(df["category"] == "deep-work") & (df["status"] == "completed")].copy()
        if deep.empty:
            return []

        deep["start_hour"] = deep["start_time"].apply(
            lambda t: int(t.split(":")[0]) if ":" in str(t) else 0
        )

        hour_counts = deep.groupby("start_hour").agg(
            sessions=("id", "count"),
            total_hours=("duration_hours", "sum"),
        ).reset_index()

        hour_counts = hour_counts.sort_values("total_hours", ascending=False)

        return [
            {
                "hour": int(row["start_hour"]),
                "label": f"{int(row['start_hour']):02d}:00",
                "sessions": int(row["sessions"]),
                "total_hours": round(float(row["total_hours"]), 2),
            }
            for _, row in hour_counts.head(5).iterrows()
        ]

    # ------------------------------------------------------------------ #
    #  Productivity by weekday
    # ------------------------------------------------------------------ #

    @staticmethod
    def _productivity_by_weekday(df: pd.DataFrame) -> list[dict]:
        """Compute average focus score per weekday."""
        weekday_order = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

        if df.empty:
            return [{"day": d, "avg_focus_score": 0, "avg_completion": 0} for d in weekday_order]

        df = df.copy()
        df["date_parsed"] = pd.to_datetime(df["date"])
        df["weekday"] = df["date_parsed"].dt.day_name().str[:3]

        results = []
        for day in weekday_order:
            day_df = df[df["weekday"] == day]
            if day_df.empty:
                results.append({"day": day, "avg_focus_score": 0, "avg_completion": 0})
            else:
                # Compute per-date metrics then average
                daily_scores = []
                daily_completions = []
                for _, group in day_df.groupby("date"):
                    daily_scores.append(MetricsService.focus_score(group))
                    daily_completions.append(MetricsService.completion_rate(group))

                results.append({
                    "day": day,
                    "avg_focus_score": round(float(np.mean(daily_scores)), 1),
                    "avg_completion": round(float(np.mean(daily_completions)), 1),
                })

        return results

    # ------------------------------------------------------------------ #
    #  Distraction trend
    # ------------------------------------------------------------------ #

    @staticmethod
    def _distraction_trend(df: pd.DataFrame) -> list[dict]:
        """Average distractions per day over the period."""
        if df.empty:
            return []

        daily = df.groupby("date")["distractions"].mean().reset_index()
        daily.columns = ["date", "avg_distractions"]
        daily = daily.sort_values("date")

        return [
            {"date": row["date"], "avg_distractions": round(float(row["avg_distractions"]), 2)}
            for _, row in daily.iterrows()
        ]

    # ------------------------------------------------------------------ #
    #  Deep work by time slot
    # ------------------------------------------------------------------ #

    @staticmethod
    def _deep_work_by_time_slot(df: pd.DataFrame) -> list[dict]:
        """
        Categorise deep work into time slots:
        Morning (6–12), Afternoon (12–17), Evening (17–22).
        """
        slots = [
            {"name": "Morning (6–12)", "start": 6, "end": 12, "hours": 0.0},
            {"name": "Afternoon (12–17)", "start": 12, "end": 17, "hours": 0.0},
            {"name": "Evening (17–22)", "start": 17, "end": 22, "hours": 0.0},
        ]

        if df.empty:
            return [{"name": s["name"], "hours": 0.0} for s in slots]

        deep = df[(df["category"] == "deep-work") & (df["status"] == "completed")]
        for _, row in deep.iterrows():
            try:
                sh = int(row["start_time"].split(":")[0])
                for slot in slots:
                    if slot["start"] <= sh < slot["end"]:
                        slot["hours"] += row["duration_hours"]
                        break
            except (ValueError, IndexError):
                continue

        return [{"name": s["name"], "hours": round(s["hours"], 2)} for s in slots]
