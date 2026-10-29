"""
CLI script to generate a full analytics report for a user.
Usage: python scripts/generate_report.py --user-id 1 --output ./reports [--tz Asia/Tashkent]

Writes report.json (today, week, month, focus patterns) plus every chart as a PNG,
using exactly the payloads the API serves.
"""

import argparse
import base64
import json
import os
import sys

# Add parent dir to path so we can import app modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.api import analytics_api
from app.database import SessionLocal


def _as_dict(payload):
    return payload.model_dump() if hasattr(payload, "model_dump") else payload


def _save_charts(prefix: str, charts: dict, output_dir: str):
    for name, chart in charts.items():
        image = chart.get("image") if isinstance(chart, dict) else chart
        if image:
            path = os.path.join(output_dir, f"{prefix}_{name}.png")
            with open(path, "wb") as f:
                f.write(base64.b64decode(image))
            print(f"  ✓ {os.path.basename(path)}")


def generate_report(user_id: int, output_dir: str, tz: str):
    """Generate a full analytics report and save charts + JSON."""
    os.makedirs(output_dir, exist_ok=True)
    db = SessionLocal()

    try:
        print(f"Generating report for user {user_id}...")
        payloads = {
            "today": analytics_api.get_today(user_id=user_id, tz=tz, db=db),
            "week": analytics_api.get_weekly_analytics(user_id=user_id, tz=tz, db=db),
            "month": analytics_api.get_monthly_analytics(user_id=user_id, tz=tz, db=db),
            "focus": analytics_api.get_focus_patterns(user_id=user_id, tz=tz, days=30, db=db),
        }
        report = {}
        for name, payload in payloads.items():
            data = _as_dict(payload)
            _save_charts(name, data.pop("charts", {}), output_dir)
            report[name] = data

        json_path = os.path.join(output_dir, "report.json")
        with open(json_path, "w") as f:
            json.dump(report, f, indent=2, default=str)
        print(f"  ✓ JSON report saved to {json_path}")
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
