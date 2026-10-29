"""
Monthly analysis module.
Aggregates data by week within a month and tracks longer-term trends.
"""

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.services.metrics_service import MetricsService
from app.timeutil import local_now


class MonthlyAnalysis:
    """Detailed monthly breakdown analysis."""

    def __init__(self, db: Session):
        self.db = db

    def analyse(self, user_id: int, reference_date: datetime | None = None, *, tz: str) -> dict:
        """
        Full monthly analysis with weekly sub-breakdowns,
        discipline index trend, and category distribution.
        """
        d = reference_date or local_now(tz)
        first = d.replace(day=1)
        if d.month == 12:
            last = d.replace(year=d.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            last = d.replace(month=d.month + 1, day=1) - timedelta(days=1)

        start = first.strftime("%Y-%m-%d")
        end = last.strftime("%Y-%m-%d")

        df = MetricsService.load_tasks(self.db, user_id, start, end)

        # Weekly sub-breakdowns
        weekly_breakdown = []
        if not df.empty:
            df_copy = df.copy()
            df_copy["date_parsed"] = pd.to_datetime(df_copy["date"])
            df_copy["week_num"] = df_copy["date_parsed"].dt.isocalendar().week.astype(int)

            for week_num, group in df_copy.groupby("week_num"):
                clean = group.drop(columns=["date_parsed", "week_num"])
                dates = sorted(group["date"].unique())
                weekly_breakdown.append({
                    "week": int(week_num),
                    "start_date": dates[0],
                    "end_date": dates[-1],
                    "completion_rate": MetricsService.completion_rate(clean),
                    "deep_work_hours": MetricsService.deep_work_hours(clean),
                    "focus_score": MetricsService.focus_score(clean),
                    "total_tasks": len(clean),
                    "completed_tasks": int((clean["status"] == "completed").sum()),
                })

        # Discipline index trend (weekly focus scores)
        discipline_trend = [
            {"week": w["week"], "discipline_index": w["focus_score"]}
            for w in weekly_breakdown
        ]

        # Category distribution
        category_dist = {}
        if not df.empty:
            completed = df[df["status"] == "completed"]
            if not completed.empty:
                cat_hours = completed.groupby("category")["duration_hours"].sum()
                total = cat_hours.sum()
                for cat, hours in cat_hours.items():
                    category_dist[cat] = {
                        "hours": round(float(hours), 2),
                        "percentage": round(float(hours / total * 100), 1) if total > 0 else 0,
                    }

        # Month-over-month comparison
        prev_month = first - timedelta(days=1)
        prev_first = prev_month.replace(day=1)
        prev_df = MetricsService.load_tasks(
            self.db, user_id,
            prev_first.strftime("%Y-%m-%d"),
            prev_month.strftime("%Y-%m-%d"),
        )
        prev_focus = MetricsService.focus_score(prev_df)
        curr_focus = MetricsService.focus_score(df)

        return {
            "period": f"{start} — {end}",
            "month_name": d.strftime("%B %Y"),
            "metrics": {
                "completion_rate": MetricsService.completion_rate(df),
                "deep_work_hours": MetricsService.deep_work_hours(df),
                "total_hours": MetricsService.total_work_hours(df),
                "focus_score": curr_focus,
                "avg_distractions": MetricsService.average_distractions(df),
                "avg_energy": MetricsService.average_energy(df),
                "total_tasks": len(df),
                "completed_tasks": int((df["status"] == "completed").sum()) if not df.empty else 0,
            },
            "weekly_breakdown": weekly_breakdown,
            "discipline_trend": discipline_trend,
            "category_distribution": category_dist,
            "comparison": {
                "prev_month_focus": prev_focus,
                "change": curr_focus - prev_focus,
            },
        }
