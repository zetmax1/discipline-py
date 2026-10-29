"""
F-12: the heatmap's color scale starts at 0 (vmin=0, vmax=max(1, data max)), so an
empty week is drawn in the lowest color, and blocks are bucketed by their minute
overlap with each hour [h, h+1) across 00–23.
"""

from datetime import date

import numpy as np
import pytest
from matplotlib.figure import Figure

from app import charts, reports
from app.metrics import Block


def deep(day, start, end, status="completed", category="deep-work"):
    return Block(day=date.fromisoformat(day), start=start, end=end, category=category, status=status)


# 2026-10-26 is a Monday.
BLOCKS = [
    deep("2026-10-26", "09:30", "10:15"),
    deep("2026-10-27", "09:00", "10:00"),
    deep("2026-10-28", "01:00", "02:00"),
    deep("2026-10-29", "23:00", "24:00"),
    deep("2026-10-30", "09:00", "10:00", status="pending"),
    deep("2026-10-30", "11:00", "12:00", category="study"),
]


def test_buckets_by_minute_overlap_over_all_24_hours():
    hm = reports.heatmap_matrix(BLOCKS)
    assert hm["hours"] == list(range(24))
    assert hm["weekdays"] == ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    v = np.array(hm["values"])
    assert v.shape == (7, 24)
    assert v[0, 9] == 0.5 and v[0, 10] == 0.25           # 09:30-10:15
    assert v[1, 9] == 1.0 and v[1, 10] == 0.0            # 09:00-10:00 does not spill into 10:00
    assert v[2, 1] == 1.0                                # early-morning hours are included
    assert v[3, 23] == 1.0                               # block ending at 24:00
    assert v[4].sum() == 0                               # pending and non-deep blocks ignored
    assert v.sum() == pytest.approx(0.75 + 1 + 1 + 1)


def draw(values):
    hm = {"weekdays": ["Mon", "Tue"], "hours": [0, 1], "values": values}
    fig = Figure()
    charts._draw_heatmap(hm, "t")(fig)
    return fig.axes[0].collections[0]


def test_all_zero_heatmap_maps_to_lowest_color():
    mesh = draw([[0.0, 0.0], [0.0, 0.0]])
    assert (mesh.norm.vmin, mesh.norm.vmax) == (0, 1)
    lowest = mesh.cmap(0.0)
    assert all(tuple(c) == tuple(lowest) for c in mesh.to_rgba(np.zeros(4)))


@pytest.mark.parametrize("values,vmax", [
    ([[0.0, 0.5], [0.2, 0.0]], 1),        # small values still on a 0..1 scale
    ([[2.0, 2.0], [2.0, 2.0]], 2.0),      # uniform non-zero data starts at 0, not at 2
    ([[0.0, 3.2], [1.0, 0.0]], 3.2),
])
def test_scale_starts_at_zero(values, vmax):
    mesh = draw(values)
    assert mesh.norm.vmin == 0
    assert mesh.norm.vmax == pytest.approx(vmax)
