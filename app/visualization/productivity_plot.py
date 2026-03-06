"""
Productivity plots — deep work distribution, distraction trends, energy charts.
"""

import base64
import io
from typing import Optional

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np


COLORS = {
    "primary": "#1B2A4A",
    "secondary": "#2D5F2D",
    "accent": "#E8A838",
    "danger": "#DC2626",
}


def _fig_to_base64(fig: plt.Figure) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")


def deep_work_distribution(
    slot_data: list[dict],
    title: str = "Deep work distribution",
    save_path: Optional[str] = None,
) -> str:
    if not slot_data:
        return ""

    names = [d["name"] for d in slot_data]
    hours = [d["hours"] for d in slot_data]

    fig, ax = plt.subplots(figsize=(8, 3.5))
    bars = ax.barh(names, hours, color=[COLORS["primary"], COLORS["secondary"], COLORS["accent"]],
                   alpha=0.85, edgecolor="white", height=0.5)

    ax.set_title(title, fontsize=14, fontweight="bold", pad=12)
    ax.set_xlabel("Hours")

    for bar, h in zip(bars, hours):
        ax.text(bar.get_width() + 0.1, bar.get_y() + bar.get_height() / 2,
                f"{h:.1f}h", va="center", fontsize=10, fontweight="bold")

    ax.invert_yaxis()
    fig.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        return save_path

    return _fig_to_base64(fig)


def distraction_trend(
    trend_data: list[dict],
    title: str = "Distraction trend",
    save_path: Optional[str] = None,
) -> str:
    if not trend_data:
        return ""

    dates = [d["date"] for d in trend_data]
    values = [d["avg_distractions"] for d in trend_data]

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(dates, values, color=COLORS["danger"], linewidth=2, marker="o", markersize=4)
    ax.fill_between(dates, values, alpha=0.1, color=COLORS["danger"])

    ax.set_title(title, fontsize=14, fontweight="bold", pad=12)
    ax.set_ylabel("Avg distractions / task")
    ax.set_ylim(bottom=0)
    ax.tick_params(axis="x", rotation=45)

    if len(dates) > 14:
        for i, label in enumerate(ax.xaxis.get_ticklabels()):
            if i % (len(dates) // 7) != 0:
                label.set_visible(False)

    fig.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        return save_path

    return _fig_to_base64(fig)


def focus_score_gauge(
    score: int,
    title: str = "Focus Score",
    save_path: Optional[str] = None,
) -> str:
    fig, ax = plt.subplots(figsize=(5, 3.5), subplot_kw={"projection": "polar"})

    theta = np.linspace(np.pi, 0, 100)
    ax.plot(theta, [1] * 100, color="#E5E7EB", linewidth=18, solid_capstyle="round")

    filled = int(score / 100 * 100)
    if score >= 70:
        color = COLORS["secondary"]
    elif score >= 40:
        color = COLORS["accent"]
    else:
        color = COLORS["danger"]

    filled_theta = np.linspace(np.pi, np.pi - (score / 100 * np.pi), max(filled, 1))
    ax.plot(filled_theta, [1] * len(filled_theta), color=color, linewidth=18,
            solid_capstyle="round")

    ax.set_ylim(0, 1.5)
    ax.set_yticklabels([])
    ax.set_xticklabels([])
    ax.spines["polar"].set_visible(False)
    ax.grid(False)

    ax.text(np.pi / 2, 0.4, str(score), ha="center", va="center",
            fontsize=36, fontweight="bold", color=color)
    ax.text(np.pi / 2, -0.1, title, ha="center", va="center",
            fontsize=12, color="#6B7280")

    fig.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        return save_path

    return _fig_to_base64(fig)
