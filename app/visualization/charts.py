"""
Charts module — generates matplotlib/seaborn charts and returns them as base64 PNG.
Used by the API to embed charts in JSON responses.
"""

import base64
import io
from typing import Optional

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import seaborn as sns
import numpy as np
import pandas as pd


# ------------------------------------------------------------------ #
#  Style setup
# ------------------------------------------------------------------ #

sns.set_theme(style="whitegrid", palette="muted")
COLORS = {
    "primary": "#1B2A4A",
    "secondary": "#2D5F2D",
    "accent": "#E8A838",
    "deep-work": "#1B2A4A",
    "study": "#2D5F2D",
    "admin": "#6B7280",
    "gym": "#DC2626",
    "rest": "#3B82F6",
}
CATEGORY_COLORS = ["#1B2A4A", "#2D5F2D", "#6B7280", "#DC2626", "#3B82F6"]


def _fig_to_base64(fig: plt.Figure) -> str:
    """Render a matplotlib figure as a base64-encoded PNG string."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")


def _save_fig(fig: plt.Figure, path: str):
    """Save chart to disk."""
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)


# ------------------------------------------------------------------ #
#  Completion Rate Trend (line chart)
# ------------------------------------------------------------------ #

def completion_rate_trend(
    daily_metrics: list[dict],
    title: str = "Completion rate trend",
    save_path: Optional[str] = None,
) -> str:
    """
    Line chart showing daily completion rate over time.
    Returns base64 PNG.
    """
    if not daily_metrics:
        return ""

    dates = [d["date"] for d in daily_metrics]
    rates = [d["completion_rate"] for d in daily_metrics]

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(dates, rates, color=COLORS["primary"], linewidth=2, marker="o", markersize=4)
    ax.fill_between(dates, rates, alpha=0.1, color=COLORS["primary"])

    ax.set_title(title, fontsize=14, fontweight="bold", pad=12)
    ax.set_ylabel("Completion rate (%)")
    ax.set_ylim(0, 105)
    ax.tick_params(axis="x", rotation=45)

    # Show every Nth label to avoid crowding
    if len(dates) > 14:
        for i, label in enumerate(ax.xaxis.get_ticklabels()):
            if i % (len(dates) // 7) != 0:
                label.set_visible(False)

    fig.tight_layout()

    if save_path:
        _save_fig(fig, save_path)
        return save_path

    return _fig_to_base64(fig)


# ------------------------------------------------------------------ #
#  Weekly Productivity Bar Chart
# ------------------------------------------------------------------ #

def weekly_productivity_bars(
    daily_metrics: list[dict],
    title: str = "Weekly productivity",
    save_path: Optional[str] = None,
) -> str:
    """
    Bar chart: completion rate + deep work hours per day (grouped bars).
    Returns base64 PNG.
    """
    if not daily_metrics:
        return ""

    dates = [d["date"][-5:] for d in daily_metrics]  # MM-DD short format
    comp_rates = [d["completion_rate"] for d in daily_metrics]
    dw_hours = [d["deep_work_hours"] for d in daily_metrics]

    x = np.arange(len(dates))
    width = 0.35

    fig, ax1 = plt.subplots(figsize=(10, 5))

    bars1 = ax1.bar(x - width / 2, comp_rates, width, color=COLORS["primary"],
                    label="Completion %", alpha=0.85)
    ax1.set_ylabel("Completion rate (%)", color=COLORS["primary"])
    ax1.set_ylim(0, 110)
    ax1.tick_params(axis="y", labelcolor=COLORS["primary"])

    ax2 = ax1.twinx()
    bars2 = ax2.bar(x + width / 2, dw_hours, width, color=COLORS["secondary"],
                    label="Deep work (h)", alpha=0.85)
    ax2.set_ylabel("Deep work (h)", color=COLORS["secondary"])
    ax2.tick_params(axis="y", labelcolor=COLORS["secondary"])

    ax1.set_xticks(x)
    ax1.set_xticklabels(dates, rotation=45)
    ax1.set_title(title, fontsize=14, fontweight="bold", pad=12)

    # Combined legend
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left")

    fig.tight_layout()

    if save_path:
        _save_fig(fig, save_path)
        return save_path

    return _fig_to_base64(fig)


# ------------------------------------------------------------------ #
#  Category Distribution (donut chart)
# ------------------------------------------------------------------ #

def category_distribution(
    cat_data: dict,
    title: str = "Time distribution by category",
    save_path: Optional[str] = None,
) -> str:
    """
    Donut chart showing how time is split across categories.
    cat_data: {"deep-work": 12.5, "study": 5.0, ...}
    Returns base64 PNG.
    """
    if not cat_data:
        return ""

    labels = list(cat_data.keys())
    sizes = list(cat_data.values())
    colors = [COLORS.get(l, "#9CA3AF") for l in labels]

    fig, ax = plt.subplots(figsize=(6, 6))
    wedges, texts, autotexts = ax.pie(
        sizes, labels=labels, colors=colors, autopct="%1.1f%%",
        startangle=90, pctdistance=0.75,
        wedgeprops=dict(width=0.4, edgecolor="white"),
    )

    for text in autotexts:
        text.set_fontsize(10)
        text.set_fontweight("bold")

    ax.set_title(title, fontsize=14, fontweight="bold", pad=16)

    fig.tight_layout()

    if save_path:
        _save_fig(fig, save_path)
        return save_path

    return _fig_to_base64(fig)


# ------------------------------------------------------------------ #
#  Productivity by Weekday (bar chart)
# ------------------------------------------------------------------ #

def productivity_by_weekday(
    weekday_data: list[dict],
    title: str = "Productivity by Weekday",
    save_path: Optional[str] = None,
) -> str:
    """
    Bar chart: average focus score per weekday.
    weekday_data: [{"day": "Mon", "avg_focus_score": 72, ...}, ...]
    """
    if not weekday_data:
        return ""

    days = [d["day"] for d in weekday_data]
    scores = [d["avg_focus_score"] for d in weekday_data]

    fig, ax = plt.subplots(figsize=(8, 4))

    bar_colors = [COLORS["primary"] if s >= 60 else COLORS["accent"] for s in scores]
    ax.bar(days, scores, color=bar_colors, alpha=0.85, edgecolor="white")

    ax.set_title(title, fontsize=14, fontweight="bold", pad=12)
    ax.set_ylabel("Focus Score")
    ax.set_ylim(0, 105)

    # Add value labels on bars
    for i, v in enumerate(scores):
        ax.text(i, v + 2, str(int(v)), ha="center", fontsize=10, fontweight="bold")

    fig.tight_layout()

    if save_path:
        _save_fig(fig, save_path)
        return save_path

    return _fig_to_base64(fig)
