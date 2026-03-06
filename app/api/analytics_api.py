"""
Analytics API — FastAPI router exposing analytics endpoints.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query, Header, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import settings
from app.services.productivity_service import ProductivityService
from app.services.focus_service import FocusService
from app.analytics.weekly_analysis import WeeklyAnalysis
from app.analytics.monthly_analysis import MonthlyAnalysis
from app.analytics.pattern_detection import PatternDetection
from app.visualization import charts
from app.visualization.focus_heatmap import focus_heatmap
from app.visualization.productivity_plot import (
    deep_work_distribution,
    distraction_trend,
    focus_score_gauge,
)


def verify_api_key(x_api_key: str = Header(None)):
    if not x_api_key or x_api_key != settings.API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API Key")


router = APIRouter(
    prefix="/analytics",
    tags=["Analytics"],
    dependencies=[Depends(verify_api_key)]
)


# ------------------------------------------------------------------ #
#  GET /analytics/weekly
# ------------------------------------------------------------------ #

@router.get("/weekly")
def get_weekly_analytics(
    user_id: int = Query(..., description="User ID"),
    db: Session = Depends(get_db),
):
    """
    Full weekly analytics report with metrics, daily breakdown,
    category distribution, charts, and week-over-week comparison.
    """
    svc = ProductivityService(db)
    analysis = WeeklyAnalysis(db)

    report = svc.weekly_report(user_id)
    detailed = analysis.analyse(user_id)

    # Generate charts
    daily = report["daily_breakdown"]
    chart_completion = charts.completion_rate_trend(daily, title="Weekly Completion Rate")
    chart_weekly = charts.weekly_productivity_bars(daily, title="This Week's Productivity")
    chart_category = charts.category_distribution(report["category_distribution"])

    return {
        "report": report,
        "analysis": detailed,
        "charts": {
            "completion_trend": chart_completion,
            "weekly_bars": chart_weekly,
            "category_distribution": chart_category,
        },
    }


# ------------------------------------------------------------------ #
#  GET /analytics/monthly
# ------------------------------------------------------------------ #

@router.get("/monthly")
def get_monthly_analytics(
    user_id: int = Query(..., description="User ID"),
    db: Session = Depends(get_db),
):
    """
    Monthly analytics: overall metrics, weekly sub-breakdowns,
    discipline index trend, category distribution, and charts.
    """
    svc = ProductivityService(db)
    analysis = MonthlyAnalysis(db)

    report = svc.monthly_report(user_id)
    detailed = analysis.analyse(user_id)

    # Charts
    weekly_metrics = [
        {
            "date": w.get("start_date", f"Week {w['week']}"),
            "completion_rate": w["completion_rate"],
            "deep_work_hours": w["deep_work_hours"],
            "focus_score": w["focus_score"],
        }
        for w in detailed.get("weekly_breakdown", [])
    ]
    chart_trend = charts.completion_rate_trend(weekly_metrics, title="Monthly Completion Trend")
    monthly_cat_data = detailed.get("category_distribution", {})
    chart_cat_data = {
        cat: data.get("hours", 0) 
        for cat, data in monthly_cat_data.items()
    }

    chart_category = charts.category_distribution(
        chart_cat_data,
        title="Monthly Time Distribution",
    )
    chart_gauge = focus_score_gauge(
        detailed.get("metrics", {}).get("focus_score", 0),
        title="Monthly Focus Score",
    )

    return {
        "report": report,
        "analysis": detailed,
        "charts": {
            "completion_trend": chart_trend,
            "category_distribution": chart_category,
            "focus_gauge": chart_gauge,
        },
    }


# ------------------------------------------------------------------ #
#  GET /analytics/productivity-trend
# ------------------------------------------------------------------ #

@router.get("/productivity-trend")
def get_productivity_trend(
    user_id: int = Query(..., description="User ID"),
    days: int = Query(30, ge=7, le=365, description="Number of days"),
    db: Session = Depends(get_db),
):
    """
    Productivity trend over the last N days.
    Returns daily metrics and trend line chart.
    """
    svc = ProductivityService(db)
    trend_data = svc.productivity_trend(user_id, days=days)

    # Pattern detection
    patterns = PatternDetection(db)
    detected = patterns.detect(user_id, days=days)

    # Chart
    chart = charts.completion_rate_trend(
        trend_data["trend"],
        title=f"Productivity Trend ({days} days)",
    )

    return {
        "trend": trend_data,
        "patterns": detected,
        "charts": {
            "trend_line": chart,
        },
    }


# ------------------------------------------------------------------ #
#  GET /analytics/focus-patterns
# ------------------------------------------------------------------ #

@router.get("/focus-patterns")
def get_focus_patterns(
    user_id: int = Query(..., description="User ID"),
    days: int = Query(30, ge=7, le=365, description="Number of days"),
    db: Session = Depends(get_db),
):
    """
    Focus pattern analysis: heatmap, peak hours, productivity by weekday,
    distraction trends, and deep work distribution.
    """
    svc = FocusService(db)
    data = svc.focus_patterns(user_id, days=days)

    # Charts
    chart_heatmap = focus_heatmap(data["heatmap_data"])
    chart_weekday = charts.productivity_by_weekday(data["productivity_by_weekday"])
    chart_dw_dist = deep_work_distribution(data["deep_work_distribution"])
    chart_distr = distraction_trend(data["distraction_trend"])

    return {
        "data": data,
        "charts": {
            "focus_heatmap": chart_heatmap,
            "productivity_by_weekday": chart_weekday,
            "deep_work_distribution": chart_dw_dist,
            "distraction_trend": chart_distr,
        },
    }
