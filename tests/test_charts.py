"""
F-13: charts use the object-oriented matplotlib API only, never touch global state,
render at most 2 at a time, are cached for 5 minutes per (user, endpoint, range,
chart, data), clean up their figure even on errors, and ship their data with the image.
"""

import base64
import subprocess
import sys
import threading
import time

import matplotlib
import pytest

from app import charts


@pytest.fixture(autouse=True)
def fresh_cache():
    charts.chart_cache.clear()
    yield
    charts.chart_cache.clear()


def is_png(b64: str) -> bool:
    return base64.b64decode(b64)[:8] == b"\x89PNG\r\n\x1a\n"


SAMPLE = [{"label": "deep-work", "value": 2.0}, {"label": "study", "value": 1.0}]


def test_app_never_imports_pyplot():
    code = "import sys; import main; from app import charts; print('matplotlib.pyplot' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=".")
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "False"


def test_rendering_does_not_change_global_rcparams():
    before = dict(matplotlib.rcParams)
    charts.category_chart(1, "weekly", "week", SAMPLE)
    charts.gauge_chart(1, "weekly", "week", 72.5)
    charts.trend_chart(1, "focus-patterns", 30, [{"label": "2026-10-28", "value": 1.5}])
    assert dict(matplotlib.rcParams) == before


def test_chart_payload_has_image_and_data():
    c = charts.category_chart(1, "weekly", "week", SAMPLE)
    assert is_png(c["image"])
    assert c["data"] == SAMPLE


def test_cache_hits_for_same_user_endpoint_range_and_data(monkeypatch):
    calls = []
    real = charts.render
    monkeypatch.setattr(charts, "render", lambda draw, size: calls.append(1) or real(draw, size))

    charts.category_chart(1, "weekly", "week", SAMPLE)
    charts.category_chart(1, "weekly", "week", SAMPLE)
    assert len(calls) == 1, "same key must be served from cache"

    charts.category_chart(2, "weekly", "week", SAMPLE)                              # other user
    charts.category_chart(1, "monthly", "month", SAMPLE)                            # other endpoint/range
    charts.category_chart(1, "weekly", "week", [{"label": "study", "value": 3.0}])  # data changed
    assert len(calls) == 4


def test_cache_entries_expire_after_5_minutes(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(charts.chart_cache, "_clock", lambda: now[0])
    calls = []
    real = charts.render
    monkeypatch.setattr(charts, "render", lambda draw, size: calls.append(1) or real(draw, size))

    charts.category_chart(1, "weekly", "week", SAMPLE)
    now[0] += 299
    charts.category_chart(1, "weekly", "week", SAMPLE)
    assert len(calls) == 1
    now[0] += 2
    charts.category_chart(1, "weekly", "week", SAMPLE)
    assert len(calls) == 2


def test_at_most_two_renders_run_concurrently(monkeypatch):
    active, peak, lock = [0], [0], threading.Lock()

    def slow_draw(fig):
        with lock:
            active[0] += 1
            peak[0] = max(peak[0], active[0])
        time.sleep(0.05)
        with lock:
            active[0] -= 1
        fig.add_subplot().plot([0, 1])

    threads = [threading.Thread(target=charts.render, args=(slow_draw, (2, 2))) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert peak[0] <= 2, f"{peak[0]} renders ran at once"


def test_figure_is_cleaned_up_even_when_drawing_fails(monkeypatch):
    cleared = []
    real_new = charts._new_figure

    def tracking_new(size):
        fig = real_new(size)
        orig = fig.clear
        fig.clear = lambda *a, **k: (cleared.append(1), orig(*a, **k))[1]
        return fig

    monkeypatch.setattr(charts, "_new_figure", tracking_new)

    def broken(fig):
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        charts.render(broken, (2, 2))
    assert cleared == [1]
