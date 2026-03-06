"""
Focus heatmap — seaborn heatmap showing deep-work intensity by hour × weekday.
"""

import base64
import io
from typing import Optional

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import pandas as pd


def focus_heatmap(
    heatmap_data: dict,
    title: str = "Focus Heatmap — Deep Work by Hour & Day",
    save_path: Optional[str] = None,
) -> str:
    """
    Generate a seaborn heatmap from the FocusService heatmap_data.
    heatmap_data: {
        "weekdays": ["Mon", ..., "Sun"],
        "hours": [6, 7, ..., 23],
        "values": {"Mon": [0.0, 0.5, ...], ...}
    }
    Returns base64-encoded PNG.
    """
    weekdays = heatmap_data.get("weekdays", [])
    hours = heatmap_data.get("hours", [])
    values = heatmap_data.get("values", {})

    if not weekdays or not hours:
        return ""

    # Build matrix: rows = weekdays, cols = hours
    matrix = np.array([values.get(day, [0.0] * len(hours)) for day in weekdays])

    fig, ax = plt.subplots(figsize=(14, 4))

    sns.heatmap(
        matrix,
        ax=ax,
        xticklabels=[f"{h}:00" for h in hours],
        yticklabels=weekdays,
        cmap="YlOrRd",
        linewidths=0.5,
        linecolor="white",
        cbar_kws={"label": "Deep Work Hours", "shrink": 0.8},
        annot=True,
        fmt=".1f",
        annot_kws={"size": 8},
    )

    ax.set_title(title, fontsize=14, fontweight="bold", pad=14)
    ax.set_xlabel("Hour of Day")
    ax.set_ylabel("")
    ax.tick_params(axis="x", rotation=45)

    fig.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        return save_path

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")
