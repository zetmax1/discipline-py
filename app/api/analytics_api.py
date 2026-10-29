"""
Analytics API — FastAPI router exposing analytics endpoints.
Every number comes from app.metrics via app.reports.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app import reports
from app.auth import get_current_tz, get_current_user, get_current_user_id
from app.database import get_db
from app.visualization import charts
from app.visualization.focus_heatmap import focus_heatmap
from app.visualization.productivity_plot import distraction_trend, focus_score_gauge


router = APIRouter(
    prefix="/analytics",
    tags=["Analytics"],
    dependencies=[Depends(get_current_user)]
)


def _period_charts(report: dict) -> dict:
    score = report["focus_score"]
    return {
        "focus_gauge": focus_score_gauge(round(score)) if score is not None else "",
        "category_distribution": charts.category_distribution(
            {c["category"]: c["minutes"] / 60 for c in report["category_minutes"]}
        ),
    }


# ------------------------------------------------------------------ #
#  GET /analytics/today
# ------------------------------------------------------------------ #

@router.get("/today")
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

@router.get("/weekly")
def get_weekly_analytics(
    user_id: int = Depends(get_current_user_id),
    tz: str = Depends(get_current_tz),
    db: Session = Depends(get_db),
):
    """This week's daily metrics, mean focus score, categories and comparison with last week."""
    report = reports.period_report(db, user_id, tz, "week")
    report["charts"] = _period_charts(report)
    return report


@router.get("/monthly")
def get_monthly_analytics(
    user_id: int = Depends(get_current_user_id),
    tz: str = Depends(get_current_tz),
    db: Session = Depends(get_db),
):
    """This month's daily metrics, mean focus score, categories and comparison with last month."""
    report = reports.period_report(db, user_id, tz, "month")
    report["charts"] = _period_charts(report)
    return report


# ------------------------------------------------------------------ #
#  GET /analytics/focus-patterns
# ------------------------------------------------------------------ #

@router.get("/focus-patterns")
def get_focus_patterns(
    user_id: int = Depends(get_current_user_id),
    tz: str = Depends(get_current_tz),
    days: int = Query(30, ge=7, le=365, description="Number of days"),
    db: Session = Depends(get_db),
):
    """Heatmap, weekday scores, deep-work slots and distraction trend over the last N days."""
    data = reports.focus_patterns(db, user_id, tz, days)
    heat = data["heatmap"]
    data["charts"] = {
        "focus_heatmap": focus_heatmap({**heat, "values": dict(zip(heat["weekdays"], heat["values"]))}),
        "distraction_trend": distraction_trend([
            {"date": p["date"], "avg_distractions": p["distractions_per_hour"]}
            for p in data["distraction_trend"] if p["distractions_per_hour"] is not None
        ]),
    }
    return data
