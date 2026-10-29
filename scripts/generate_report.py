"""
CLI script to generate a full analytics report for a user.
Usage: python scripts/generate_report.py --user-id 1 --output ./reports
"""

import argparse
import json
import os
import sys

# Add parent dir to path so we can import app modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime

from app.database import SessionLocal
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


def generate_report(user_id: int, output_dir: str, tz: str):
    """Generate a full analytics report and save charts + JSON."""
    os.makedirs(output_dir, exist_ok=True)
    db = SessionLocal()

    try:
        print(f"Generating report for user {user_id}...")

        # Services
        prod_svc = ProductivityService(db)
        focus_svc = FocusService(db)

        # Analysis
        weekly = WeeklyAnalysis(db).analyse(user_id, tz=tz)
        monthly = MonthlyAnalysis(db).analyse(user_id, tz=tz)
        patterns = PatternDetection(db).detect(user_id, tz=tz)
        trend = prod_svc.productivity_trend(user_id, days=30, tz=tz)
        focus = focus_svc.focus_patterns(user_id, days=30, tz=tz)

        # Save JSON report
        report = {
            "generated_at": datetime.now().isoformat(),
            "user_id": user_id,
            "weekly": weekly,
            "monthly": monthly,
            "patterns": patterns,
            "trend": trend,
            "focus": focus,
        }

        json_path = os.path.join(output_dir, "report.json")
        with open(json_path, "w") as f:
            json.dump(report, f, indent=2, default=str)
        print(f"  ✓ JSON report saved to {json_path}")

        # Save charts as PNGs
        daily = weekly.get("daily_metrics", [])
        if daily:
            charts.completion_rate_trend(
                daily, title="Weekly Completion Rate",
                save_path=os.path.join(output_dir, "completion_trend.png"),
            )
            print("  ✓ completion_trend.png")

            charts.weekly_productivity_bars(
                daily, title="Weekly Productivity",
                save_path=os.path.join(output_dir, "weekly_productivity.png"),
            )
            print("  ✓ weekly_productivity.png")

        cat_dist = weekly.get("category_breakdown", {})
        if cat_dist:
            cat_hours = {k: v["hours"] for k, v in cat_dist.items()}
            charts.category_distribution(
                cat_hours, save_path=os.path.join(output_dir, "category_dist.png"),
            )
            print("  ✓ category_dist.png")

        # Focus heatmap
        heatmap = focus.get("heatmap_data", {})
        if heatmap.get("weekdays"):
            focus_heatmap(
                heatmap, save_path=os.path.join(output_dir, "focus_heatmap.png"),
            )
            print("  ✓ focus_heatmap.png")

        # Deep work distribution
        dw_dist = focus.get("deep_work_distribution", [])
        if dw_dist:
            deep_work_distribution(
                dw_dist, save_path=os.path.join(output_dir, "deep_work_dist.png"),
            )
            print("  ✓ deep_work_dist.png")

        # Distraction trend
        distr = focus.get("distraction_trend", [])
        if distr:
            distraction_trend(
                distr, save_path=os.path.join(output_dir, "distraction_trend.png"),
            )
            print("  ✓ distraction_trend.png")

        # Focus score gauge
        score = monthly.get("metrics", {}).get("focus_score", 0)
        focus_score_gauge(
            score, save_path=os.path.join(output_dir, "focus_gauge.png"),
        )
        print("  ✓ focus_gauge.png")

        print(f"\nReport complete! Files saved in {output_dir}/")

    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate analytics report")
    parser.add_argument("--user-id", type=int, required=True, help="User ID")
    parser.add_argument("--output", default="./reports", help="Output directory")
    parser.add_argument("--tz", default="Asia/Tashkent", help="User's IANA time zone")
    args = parser.parse_args()

    generate_report(args.user_id, args.output, args.tz)
