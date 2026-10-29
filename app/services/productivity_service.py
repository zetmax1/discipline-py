"""
ProductivityService — higher-level aggregated analytics.
Builds on MetricsService for weekly / monthly / trend reports.
"""

from datetime import datetime, timedelta

import pandas as pd
from sqlalchemy.orm import Session

from app.services.metrics_service import MetricsService
from app.timeutil import local_now


class ProductivityService:
    """Weekly, monthly, and trend productivity analytics."""

    def __init__(self, db: Session):
        self.db = db
        self.metrics = MetricsService()

    # ------------------------------------------------------------------ #
    #  Helpers
    # ------------------------------------------------------------------ #

    def _load(self, user_id: int, start: str, end: str) -> pd.DataFrame:
        return MetricsService.load_tasks(self.db, user_id, start, end)

    @staticmethod
    def _week_range(reference: datetime):
        """Return (monday, sunday) as YYYY-MM-DD strings for the given week."""
        d = reference
        monday = d - timedelta(days=d.weekday())
        sunday = monday + timedelta(days=6)
        return monday.strftime("%Y-%m-%d"), sunday.strftime("%Y-%m-%d")

    @staticmethod
    def _month_range(reference: datetime):
        """Return (first_day, last_day) of the month as YYYY-MM-DD strings."""
        d = reference
        first = d.replace(day=1)
        # last day: jump to next month, subtract 1 day
        if d.month == 12:
            last = d.replace(year=d.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            last = d.replace(month=d.month + 1, day=1) - timedelta(days=1)
        return first.strftime("%Y-%m-%d"), last.strftime("%Y-%m-%d")

    # ------------------------------------------------------------------ #
    #  Weekly report
    # ------------------------------------------------------------------ #

    def weekly_report(self, user_id: int, reference_date: datetime | None = None, *, tz: str) -> dict:
        """
        Generate a full weekly analytics report.
        Returns metrics, daily breakdown, and category distribution.
        """
        reference_date = reference_date or local_now(tz)
        start, end = self._week_range(reference_date)
        df = self._load(user_id, start, end)

        # Overall metrics for the week
        overall = {
            "period": f"{start} — {end}",
            "completion_rate": MetricsService.completion_rate(df),
            "deep_work_hours": MetricsService.deep_work_hours(df),
            "total_hours": MetricsService.total_work_hours(df),
            "focus_score": MetricsService.focus_score(df),
            "avg_distractions": MetricsService.average_distractions(df),
            "avg_energy": MetricsService.average_energy(df),
            "total_tasks": len(df),
            "completed_tasks": int((df["status"] == "completed").sum()) if not df.empty else 0,
        }

        # Daily breakdown
        daily = MetricsService.daily_metrics(df)

        # Category distribution (hours per category)
        category_dist = {}
        if not df.empty:
            completed = df[df["status"] == "completed"]
            cat_hours = completed.groupby("category")["duration_hours"].sum()
            category_dist = {k: round(v, 2) for k, v in cat_hours.to_dict().items()}

        # Previous week comparison
        prev_ref = reference_date - timedelta(weeks=1)
        prev_start, prev_end = self._week_range(prev_ref)
        prev_df = self._load(user_id, prev_start, prev_end)
        prev_score = MetricsService.focus_score(prev_df)

        return {
            "metrics": overall,
            "daily_breakdown": daily,
            "category_distribution": category_dist,
            "comparison": {
                "prev_focus_score": prev_score,
                "change": overall["focus_score"] - prev_score,
            },
        }

    # ------------------------------------------------------------------ #
    #  Monthly report
    # ------------------------------------------------------------------ #

    def monthly_report(self, user_id: int, reference_date: datetime | None = None, *, tz: str) -> dict:
        """
        Generate a monthly analytics report.
        Includes weekly sub-breakdowns and overall monthly stats.
        """
        start, end = self._month_range(reference_date or local_now(tz))
        df = self._load(user_id, start, end)

        overall = {
            "period": f"{start} — {end}",
            "completion_rate": MetricsService.completion_rate(df),
            "deep_work_hours": MetricsService.deep_work_hours(df),
            "total_hours": MetricsService.total_work_hours(df),
            "focus_score": MetricsService.focus_score(df),
            "avg_distractions": MetricsService.average_distractions(df),
            "avg_energy": MetricsService.average_energy(df),
            "total_tasks": len(df),
            "completed_tasks": int((df["status"] == "completed").sum()) if not df.empty else 0,
        }

        # Weekly sub-breakdowns within the month
        weekly_data = []
        if not df.empty:
            df["date_parsed"] = pd.to_datetime(df["date"])
            df["week_num"] = df["date_parsed"].dt.isocalendar().week.astype(int)

            for week_num, week_group in df.groupby("week_num"):
                week_group_clean = week_group.drop(columns=["date_parsed", "week_num"])
                weekly_data.append({
                    "week": int(week_num),
                    "completion_rate": MetricsService.completion_rate(week_group_clean),
                    "deep_work_hours": MetricsService.deep_work_hours(week_group_clean),
                    "focus_score": MetricsService.focus_score(week_group_clean),
                    "total_tasks": len(week_group_clean),
                })

        # Category distribution
        category_dist = {}
        if not df.empty:
            cat_hours = df[df["status"] == "completed"].groupby("category")["duration_hours"].sum()
            category_dist = {k: round(v, 2) for k, v in cat_hours.to_dict().items()}

        return {
            "metrics": overall,
            "weekly_breakdown": weekly_data,
            "category_distribution": category_dist,
        }

    # ------------------------------------------------------------------ #
    #  Productivity trend
    # ------------------------------------------------------------------ #

    def productivity_trend(self, user_id: int, days: int = 30, *, tz: str) -> dict:
        """
        Return daily focus scores and completion rates for the last N days.
        Used for trend line charts.
        """
        end = local_now(tz)
        start = end - timedelta(days=days - 1)
        df = self._load(user_id, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))

        daily = MetricsService.daily_metrics(df)

        # Fill missing days with zeros
        all_dates = [
            (start + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)
        ]
        daily_map = {d["date"]: d for d in daily}

        trend = []
        for date_str in all_dates:
            if date_str in daily_map:
                trend.append(daily_map[date_str])
            else:
                trend.append({
                    "date": date_str,
                    "completion_rate": 0,
                    "deep_work_hours": 0,
                    "total_hours": 0,
                    "focus_score": 0,
                    "avg_distractions": 0,
                    "avg_energy": 0,
                    "task_count": 0,
                })

        return {
            "period_days": days,
            "trend": trend,
        }
