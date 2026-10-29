"""
Analytics API — FastAPI router exposing analytics endpoints.
Every number comes from app.metrics via app.reports.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app import charts, reports, schemas
from app.auth import get_current_tz, get_current_user, get_current_user_id
from app.database import get_db


router = APIRouter(
    prefix="/analytics",
    tags=["Analytics"],
    dependencies=[Depends(get_current_user)]
)


def _period_charts(user_id: int, report: dict) -> dict:
    endpoint = "weekly" if report["range"] == "week" else "monthly"
    categories = [{"label": c["category"], "value": round(c["minutes"] / 60, 2)} for c in report["category_minutes"]]
    return {
        "focus_gauge": charts.gauge_chart(user_id, endpoint, report["range"], report["focus_score"]),
        "category_distribution": charts.category_chart(user_id, endpoint, report["range"], categories),
    }


# ------------------------------------------------------------------ #
#  GET /analytics/today
# ------------------------------------------------------------------ #

@router.get("/today", response_model=schemas.TodayResponse)
def get_today(
    user_id: int = Depends(get_current_user_id),
    tz: str = Depends(get_current_tz),
    db: Session = Depends(get_db),
):
    """Today's metrics in the user's zone (dashboard)."""
    return reports.today_report(db, user_id, tz)


# ------------------------------------------------------------------ #
#  GET /analytics/weekly, /analytics/monthly
# ------------------------------------------------------------------ #

@router.get("/weekly", response_model=schemas.PeriodReport)
def get_weekly_analytics(
    user_id: int = Depends(get_current_user_id),
    tz: str = Depends(get_current_tz),
    db: Session = Depends(get_db),
):
    """This week's daily metrics, mean focus score, categories and comparison with last week."""
    report = reports.period_report(db, user_id, tz, "week")
    report["charts"] = _period_charts(user_id, report)
    return report


@router.get("/monthly", response_model=schemas.PeriodReport)
def get_monthly_analytics(
    user_id: int = Depends(get_current_user_id),
    tz: str = Depends(get_current_tz),
    db: Session = Depends(get_db),
):
    """This month's daily metrics, mean focus score, categories and comparison with last month."""
    report = reports.period_report(db, user_id, tz, "month")
    report["charts"] = _period_charts(user_id, report)
    return report


# ------------------------------------------------------------------ #
#  GET /analytics/focus-patterns
# ------------------------------------------------------------------ #

@router.get("/focus-patterns", response_model=schemas.FocusPatternsResponse)
def get_focus_patterns(
    user_id: int = Depends(get_current_user_id),
    tz: str = Depends(get_current_tz),
    days: int = Query(30, ge=7, le=365, description="Number of days"),
    db: Session = Depends(get_db),
):
    """Heatmap, weekday scores, deep-work slots and distraction trend over the last N days."""
    data = reports.focus_patterns(db, user_id, tz, days)
    data["charts"] = {
        "focus_heatmap": charts.heatmap_chart(user_id, "focus-patterns", days, data["heatmap"]),
        "distraction_trend": charts.trend_chart(user_id, "focus-patterns", days, [
            {"label": p["date"], "value": p["distractions_per_hour"]} for p in data["distraction_trend"]
        ]),
    }
    return data
