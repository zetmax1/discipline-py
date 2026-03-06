"""
Weekly analysis module.
Uses pandas to compute weekly productivity breakdowns.
"""

from datetime import datetime, timedelta

import pandas as pd
from sqlalchemy.orm import Session

from app.services.metrics_service import MetricsService


class WeeklyAnalysis:
    """Detailed weekly breakdown analysis."""

    def __init__(self, db: Session):
        self.db = db

    def analyse(self, user_id: int, reference_date: datetime | None = None) -> dict:
        """
        Run a full weekly analysis.
        Returns per-day metrics, best/worst days, and streaks.
        """
        d = reference_date or datetime.now()
        monday = d - timedelta(days=d.weekday())
        sunday = monday + timedelta(days=6)
        start = monday.strftime("%Y-%m-%d")
        end = sunday.strftime("%Y-%m-%d")

        df = MetricsService.load_tasks(self.db, user_id, start, end)
        daily = MetricsService.daily_metrics(df)

        # Best and worst days
        best_day = None
        worst_day = None
        if daily:
            sorted_by_score = sorted(daily, key=lambda x: x["focus_score"], reverse=True)
            best_day = sorted_by_score[0]
            worst_day = sorted_by_score[-1]

        # Completion streak (consecutive days with ≥ 70% completion)
        streak = 0
        if daily:
            sorted_daily = sorted(daily, key=lambda x: x["date"], reverse=True)
            for day in sorted_daily:
                if day["completion_rate"] >= 70:
                    streak += 1
                else:
                    break

        # Category time breakdown
        category_breakdown = {}
        if not df.empty:
            completed = df[df["status"] == "completed"]
            if not completed.empty:
                cat_hours = completed.groupby("category")["duration_hours"].sum()
                total = cat_hours.sum()
                for cat, hours in cat_hours.items():
                    category_breakdown[cat] = {
                        "hours": round(float(hours), 2),
                        "percentage": round(float(hours / total * 100), 1) if total > 0 else 0,
                    }

        return {
            "period": f"{start} — {end}",
            "daily_metrics": daily,
            "best_day": best_day,
            "worst_day": worst_day,
            "completion_streak": streak,
            "category_breakdown": category_breakdown,
            "summary": {
                "total_tasks": len(df),
                "completed": int((df["status"] == "completed").sum()) if not df.empty else 0,
                "skipped": int((df["status"] == "skipped").sum()) if not df.empty else 0,
                "pending": int((df["status"] == "pending").sum()) if not df.empty else 0,
            },
        }
