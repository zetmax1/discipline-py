"""
Pattern detection module.
Identifies recurring productivity patterns using numpy.
"""

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.services.metrics_service import MetricsService
from app.timeutil import local_now


class PatternDetection:
    """Detect productivity patterns and trends from historical data."""

    def __init__(self, db: Session):
        self.db = db

    def detect(self, user_id: int, days: int = 30, *, tz: str) -> dict:
        """
        Run pattern detection over the last N days.
        Returns identified patterns and recommendations.
        """
        end = local_now(tz)
        start = end - timedelta(days=days - 1)
        df = MetricsService.load_tasks(
            self.db, user_id,
            start.strftime("%Y-%m-%d"),
            end.strftime("%Y-%m-%d"),
        )

        return {
            "period_days": days,
            "most_productive_day": self._most_productive_day(df),
            "peak_productivity_time": self._peak_time(df),
            "trend_direction": self._trend_direction(df),
            "consistency_score": self._consistency_score(df),
            "category_preferences": self._category_preferences(df),
            "insights": self._generate_insights(df),
        }

    # ------------------------------------------------------------------ #
    #  Most productive weekday
    # ------------------------------------------------------------------ #

    @staticmethod
    def _most_productive_day(df: pd.DataFrame) -> dict:
        """Find the weekday with the highest average focus score."""
        weekday_names = ["Monday", "Tuesday", "Wednesday", "Thursday",
                         "Friday", "Saturday", "Sunday"]

        if df.empty:
            return {"day": "N/A", "avg_score": 0}

        df = df.copy()
        df["date_parsed"] = pd.to_datetime(df["date"])
        df["weekday_num"] = df["date_parsed"].dt.weekday

        scores_by_day = {}
        for wd_num, group in df.groupby("weekday_num"):
            daily_scores = []
            for _, day_group in group.groupby("date"):
                daily_scores.append(MetricsService.focus_score(day_group))
            scores_by_day[int(wd_num)] = float(np.mean(daily_scores))

        if not scores_by_day:
            return {"day": "N/A", "avg_score": 0}

        best_wd = max(scores_by_day, key=scores_by_day.get)
        return {
            "day": weekday_names[best_wd],
            "avg_score": round(scores_by_day[best_wd], 1),
            "all_days": {
                weekday_names[k]: round(v, 1)
                for k, v in sorted(scores_by_day.items())
            },
        }

    # ------------------------------------------------------------------ #
    #  Peak productivity time
    # ------------------------------------------------------------------ #

    @staticmethod
    def _peak_time(df: pd.DataFrame) -> dict:
        """Identify the time slot with the most completed deep-work."""
        time_slots = {
            "Early Morning (6–9)": (6, 9),
            "Morning (9–12)": (9, 12),
            "Afternoon (12–15)": (12, 15),
            "Late Afternoon (15–18)": (15, 18),
            "Evening (18–21)": (18, 21),
            "Night (21–24)": (21, 24),
        }

        if df.empty:
            return {"slot": "N/A", "hours": 0}

        deep = df[(df["category"] == "deep-work") & (df["status"] == "completed")]
        if deep.empty:
            return {"slot": "N/A", "hours": 0}

        slot_hours = {name: 0.0 for name in time_slots}
        for _, row in deep.iterrows():
            try:
                sh = int(row["start_time"].split(":")[0])
                for name, (s, e) in time_slots.items():
                    if s <= sh < e:
                        slot_hours[name] += row["duration_hours"]
                        break
            except (ValueError, IndexError):
                continue

        best_slot = max(slot_hours, key=slot_hours.get)
        return {
            "slot": best_slot,
            "hours": round(slot_hours[best_slot], 2),
            "all_slots": {k: round(v, 2) for k, v in slot_hours.items()},
        }

    # ------------------------------------------------------------------ #
    #  Trend direction
    # ------------------------------------------------------------------ #

    @staticmethod
    def _trend_direction(df: pd.DataFrame) -> dict:
        """
        Determine if productivity is improving, stable, or declining.
        Uses linear regression on daily focus scores.
        """
        if df.empty:
            return {"direction": "insufficient_data", "slope": 0}

        daily = MetricsService.daily_metrics(df)
        if len(daily) < 3:
            return {"direction": "insufficient_data", "slope": 0}

        scores = np.array([d["focus_score"] for d in daily], dtype=float)
        x = np.arange(len(scores), dtype=float)

        # Simple linear regression
        slope = float(np.polyfit(x, scores, 1)[0])

        if slope > 0.5:
            direction = "improving"
        elif slope < -0.5:
            direction = "declining"
        else:
            direction = "stable"

        return {
            "direction": direction,
            "slope": round(slope, 3),
            "description": {
                "improving": "Your productivity is trending upward! Keep it up.",
                "stable": "Your productivity is consistent. Consider pushing for new goals.",
                "declining": "Your productivity has been dipping. Consider adjusting your schedule.",
                "insufficient_data": "Not enough data yet to determine a trend.",
            }[direction],
        }

    # ------------------------------------------------------------------ #
    #  Consistency score
    # ------------------------------------------------------------------ #

    @staticmethod
    def _consistency_score(df: pd.DataFrame) -> dict:
        """
        How consistent is the user's daily routine?
        Based on standard deviation of daily completion rates.
        Lower variance = higher consistency.
        """
        if df.empty:
            return {"score": 0, "label": "No data"}

        daily = MetricsService.daily_metrics(df)
        if len(daily) < 2:
            return {"score": 0, "label": "Insufficient data"}

        rates = np.array([d["completion_rate"] for d in daily])
        std = float(np.std(rates))
        mean_rate = float(np.mean(rates))

        # Consistency = 100 - normalised std (lower std → higher score)
        score = max(0, min(100, int(100 - std)))

        if score >= 80:
            label = "Very consistent"
        elif score >= 60:
            label = "Fairly consistent"
        elif score >= 40:
            label = "Moderate"
        else:
            label = "Inconsistent"

        return {
            "score": score,
            "label": label,
            "std_deviation": round(std, 2),
            "mean_completion": round(mean_rate, 1),
        }

    # ------------------------------------------------------------------ #
    #  Category preferences
    # ------------------------------------------------------------------ #

    @staticmethod
    def _category_preferences(df: pd.DataFrame) -> list[dict]:
        """Rank categories by time spent."""
        if df.empty:
            return []

        completed = df[df["status"] == "completed"]
        if completed.empty:
            return []

        cat_hours = completed.groupby("category")["duration_hours"].sum().sort_values(ascending=False)
        total = cat_hours.sum()

        return [
            {
                "category": cat,
                "hours": round(float(hours), 2),
                "percentage": round(float(hours / total * 100), 1) if total > 0 else 0,
            }
            for cat, hours in cat_hours.items()
        ]

    # ------------------------------------------------------------------ #
    #  Generate insights (text-based recommendations)
    # ------------------------------------------------------------------ #

    def _generate_insights(self, df: pd.DataFrame) -> list[str]:
        """Produce human-readable insights from detected patterns."""
        insights = []

        if df.empty:
            return ["No task data available yet. Start tracking to get insights!"]

        # Insight: most productive day
        prod_day = self._most_productive_day(df)
        if prod_day["day"] != "N/A":
            insights.append(
                f"Your most productive day is {prod_day['day']} "
                f"with an average focus score of {prod_day['avg_score']}."
            )

        # Insight: peak time
        peak = self._peak_time(df)
        if peak["slot"] != "N/A":
            insights.append(
                f"You do your best deep work during {peak['slot']} "
                f"({peak['hours']}h total)."
            )

        # Insight: trend
        trend = self._trend_direction(df)
        insights.append(trend["description"])

        # Insight: consistency
        consistency = self._consistency_score(df)
        insights.append(
            f"Your consistency score is {consistency['score']}/100 ({consistency['label']})."
        )

        # Insight: distraction warning
        avg_distr = MetricsService.average_distractions(df)
        if avg_distr > 3:
            insights.append(
                f"⚠️ High average distractions ({avg_distr}/task). "
                "Consider using focus techniques like Pomodoro."
            )

        # Insight: deep work proportion
        dw = MetricsService.deep_work_hours(df)
        total = MetricsService.total_work_hours(df)
        if total > 0:
            pct = round(dw / total * 100, 1)
            if pct < 30:
                insights.append(
                    f"Only {pct}% of your work time is deep work. "
                    "Try to allocate more focused blocks."
                )
            elif pct > 60:
                insights.append(
                    f"Great! {pct}% of your work time is deep work. "
                    "You're maintaining excellent focus."
                )

        return insights
