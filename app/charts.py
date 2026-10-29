"""
Server-side charts, rendered with matplotlib's object-oriented API only.

- No pyplot and no global style/rcParams changes: every figure is a private
  matplotlib.figure.Figure, styled explicitly and cleared in `finally`.
- At most RENDER_CONCURRENCY renders run at once (CPU-heavy).
- Rendered images are cached for CACHE_TTL_SECONDS per
  (user, endpoint, range, chart, data hash); changed data is a new key.
- Every chart is returned as {"image": base64 PNG, "data": <what was plotted>}.
"""

import base64
import hashlib
import io
import json
import threading
import time
from collections import OrderedDict
from typing import Callable

import numpy as np
from matplotlib.figure import Figure

RENDER_CONCURRENCY = 2
CACHE_TTL_SECONDS = 300
CACHE_MAX_ENTRIES = 512
DPI = 150

COLORS = {
    "primary": "#1B2A4A",
    "secondary": "#2D5F2D",
    "accent": "#E8A838",
    "danger": "#DC2626",
    "muted": "#6B7280",
    "track": "#E5E7EB",
    "deep-work": "#1B2A4A",
    "study": "#2D5F2D",
    "admin": "#6B7280",
    "gym": "#DC2626",
    "rest": "#3B82F6",
}

_render_slots = threading.BoundedSemaphore(RENDER_CONCURRENCY)


def _new_figure(size: tuple[float, float]) -> Figure:
    return Figure(figsize=size, facecolor="white")


def render(draw: Callable[[Figure], None], size: tuple[float, float]) -> str:
    """Draw on a private Figure and return it as a base64 PNG."""
    with _render_slots:
        fig = _new_figure(size)
        try:
            draw(fig)
            buf = io.BytesIO()
            fig.savefig(buf, format="png", dpi=DPI, bbox_inches="tight", facecolor="white")
            return base64.b64encode(buf.getvalue()).decode("ascii")
        finally:
            fig.clear()


class ChartCache:
    """Thread-safe TTL + LRU cache of rendered images."""

    def __init__(self, ttl: float = CACHE_TTL_SECONDS, max_entries: int = CACHE_MAX_ENTRIES):
        self._ttl = ttl
        self._max = max_entries
        self._items: OrderedDict = OrderedDict()
        self._lock = threading.Lock()
        self._clock = time.monotonic

    def get_or_render(self, key, produce: Callable[[], str]) -> str:
        now = self._clock()
        with self._lock:
            hit = self._items.get(key)
            if hit and hit[0] > now:
                self._items.move_to_end(key)
                return hit[1]
        image = produce()
        with self._lock:
            self._items[key] = (self._clock() + self._ttl, image)
            self._items.move_to_end(key)
            while len(self._items) > self._max:
                self._items.popitem(last=False)
        return image

    def clear(self):
        with self._lock:
            self._items.clear()


chart_cache = ChartCache()


def _data_version(data) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


def _cached_chart(user_id, endpoint, range_key, name, data, produce: Callable[[], str]) -> dict:
    key = (user_id, endpoint, str(range_key), name, _data_version(data))
    return {"image": chart_cache.get_or_render(key, produce), "data": data}


# ------------------------------------------------------------------ #
#  Focus score gauge
# ------------------------------------------------------------------ #

def _draw_gauge(score: float, title: str):
    def draw(fig: Figure):
        ax = fig.add_subplot(projection="polar")
        theta = np.linspace(np.pi, 0, 100)
        ax.plot(theta, [1] * 100, color=COLORS["track"], linewidth=18, solid_capstyle="round")
        color = COLORS["secondary"] if score >= 70 else COLORS["accent"] if score >= 40 else COLORS["danger"]
        filled = np.linspace(np.pi, np.pi - (score / 100 * np.pi), max(int(score), 1))
        ax.plot(filled, [1] * len(filled), color=color, linewidth=18, solid_capstyle="round")
        ax.set_ylim(0, 1.5)
        ax.set_yticklabels([])
        ax.set_xticklabels([])
        ax.spines["polar"].set_visible(False)
        ax.grid(False)
        ax.text(np.pi / 2, 0.4, f"{score:g}", ha="center", va="center", fontsize=36, fontweight="bold", color=color)
        ax.text(np.pi / 2, -0.1, title, ha="center", va="center", fontsize=12, color=COLORS["muted"])
        fig.tight_layout()
    return draw


def gauge_chart(user_id, endpoint, range_key, score: float | None, title: str = "Focus Score") -> dict:
    data = {"score": score}
    if score is None:
        return {"image": "", "data": data}
    return _cached_chart(user_id, endpoint, range_key, "focus_gauge", data,
                         lambda: render(_draw_gauge(score, title), (5, 3.5)))


# ------------------------------------------------------------------ #
#  Category distribution (donut)
# ------------------------------------------------------------------ #

def _draw_category(points: list[dict], title: str):
    def draw(fig: Figure):
        ax = fig.add_subplot()
        labels = [p["label"] for p in points]
        sizes = [p["value"] for p in points]
        _, _, autotexts = ax.pie(
            sizes, labels=labels, colors=[COLORS.get(lbl, "#9CA3AF") for lbl in labels],
            autopct="%1.1f%%", startangle=90, pctdistance=0.75,
            wedgeprops=dict(width=0.4, edgecolor="white"),
        )
        for t in autotexts:
            t.set_fontsize(10)
            t.set_fontweight("bold")
        ax.set_title(title, fontsize=14, fontweight="bold", pad=16)
        fig.tight_layout()
    return draw


def category_chart(user_id, endpoint, range_key, points: list[dict],
                   title: str = "Time distribution by category") -> dict:
    """points: [{"label": category, "value": hours}]"""
    if not points:
        return {"image": "", "data": points}
    return _cached_chart(user_id, endpoint, range_key, "category_distribution", points,
                         lambda: render(_draw_category(points, title), (6, 6)))


# ------------------------------------------------------------------ #
#  Daily series (distraction trend)
# ------------------------------------------------------------------ #

def _draw_trend(points: list[dict], title: str, ylabel: str):
    def draw(fig: Figure):
        ax = fig.add_subplot()
        shown = [p for p in points if p["value"] is not None]
        labels = [p["label"] for p in shown]
        values = [p["value"] for p in shown]
        ax.plot(labels, values, color=COLORS["danger"], linewidth=2, marker="o", markersize=4)
        ax.fill_between(labels, values, alpha=0.1, color=COLORS["danger"])
        ax.set_title(title, fontsize=14, fontweight="bold", pad=12)
        ax.set_ylabel(ylabel)
        ax.set_ylim(bottom=0)
        ax.tick_params(axis="x", rotation=45)
        if len(labels) > 14:
            step = len(labels) // 7
            for i, label in enumerate(ax.xaxis.get_ticklabels()):
                label.set_visible(i % step == 0)
        fig.tight_layout()
    return draw


def trend_chart(user_id, endpoint, range_key, points: list[dict], title: str = "Distraction trend",
                ylabel: str = "Distractions per deep-work hour") -> dict:
    """points: [{"label": date, "value": number | None}]"""
    if not any(p["value"] is not None for p in points):
        return {"image": "", "data": points}
    return _cached_chart(user_id, endpoint, range_key, "distraction_trend", points,
                         lambda: render(_draw_trend(points, title, ylabel), (10, 4)))


# ------------------------------------------------------------------ #
#  Focus heatmap
# ------------------------------------------------------------------ #

def _draw_heatmap(heatmap: dict, title: str):
    def draw(fig: Figure):
        ax = fig.add_subplot()
        matrix = np.array(heatmap["values"], dtype=float)
        mesh = ax.pcolormesh(matrix, cmap="YlOrRd", edgecolors="white", linewidth=0.5)
        fig.colorbar(mesh, ax=ax, label="Deep work hours", shrink=0.8)
        for (r, c), v in np.ndenumerate(matrix):
            ax.text(c + 0.5, r + 0.5, f"{v:.1f}", ha="center", va="center", fontsize=8)
        ax.set_xticks(np.arange(len(heatmap["hours"])) + 0.5,
                      [f"{h}:00" for h in heatmap["hours"]], rotation=45)
        ax.set_yticks(np.arange(len(heatmap["weekdays"])) + 0.5, heatmap["weekdays"])
        ax.invert_yaxis()
        ax.set_title(title, fontsize=14, fontweight="bold", pad=14)
        ax.set_xlabel("Hour of day")
        fig.tight_layout()
    return draw


def heatmap_chart(user_id, endpoint, range_key, heatmap: dict,
                  title: str = "Focus heatmap — deep work by hour & day") -> dict:
    """heatmap: {"weekdays": [...], "hours": [...], "values": rows x hours}"""
    return _cached_chart(user_id, endpoint, range_key, "focus_heatmap", heatmap,
                         lambda: render(_draw_heatmap(heatmap, title), (14, 4)))
