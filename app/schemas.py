"""
Response models for every analytics endpoint. The frontend's contract
(discipline/contracts/analytics.schema.json) is checked against these responses.
"""

from typing import Literal, Union

from pydantic import BaseModel


class DayMetricsModel(BaseModel):
    date: str
    planned_minutes: int
    completed_minutes: int
    due_planned_minutes: int
    due_completed_minutes: int
    deep_work_minutes: int
    distractions: int
    blocks_total: int
    blocks_due: int
    blocks_completed: int
    completion: float | None
    deep: float
    distraction: float
    focus_score: int | None


class TodayResponse(DayMetricsModel):
    daily_deep_work_target_minutes: int


class CategoryMinutes(BaseModel):
    category: str
    minutes: int


class Comparison(BaseModel):
    previous_focus_score: float | None
    change: float | None


class InsufficientData(BaseModel):
    insufficient_data: Literal[True]
    days_needed: int
    days_with_data: int
    window_days: int


class Patterns(BaseModel):
    insufficient_data: Literal[False]
    days_with_data: int
    window_days: int
    best_weekday: str | None
    peak_hour: int | None
    trend: Literal["improving", "stable", "declining"]
    consistency_score: int
    insights: list[str]


class SeriesPoint(BaseModel):
    label: str
    value: float | None


class GaugeData(BaseModel):
    score: float | None


class GaugeChart(BaseModel):
    image: str  # base64 PNG (a "No data yet" placeholder when there is nothing to draw)
    data: GaugeData


class SeriesChart(BaseModel):
    image: str
    data: list[SeriesPoint]


class PeriodCharts(BaseModel):
    focus_gauge: GaugeChart
    category_distribution: SeriesChart


class PeriodReport(BaseModel):
    range: Literal["week", "month"]
    start_date: str
    end_date: str
    period_end_date: str
    focus_score: float | None
    planned_minutes: int
    completed_minutes: int
    deep_work_minutes: int
    days: list[DayMetricsModel]
    category_minutes: list[CategoryMinutes]
    streak: int
    comparison: Comparison
    patterns: Union[InsufficientData, Patterns]
    charts: PeriodCharts


class HeatmapData(BaseModel):
    weekdays: list[str]
    hours: list[int]
    values: list[list[float]]


class WeekdayScore(BaseModel):
    day: str
    focus_score: float | None


class SlotMinutes(BaseModel):
    label: str
    minutes: int


class DistractionPoint(BaseModel):
    date: str
    distractions_per_hour: float | None


class HeatmapChart(BaseModel):
    image: str
    data: HeatmapData


class FocusCharts(BaseModel):
    focus_heatmap: HeatmapChart
    distraction_trend: SeriesChart


class FocusPatternsResponse(BaseModel):
    start_date: str
    end_date: str
    days: int
    heatmap: HeatmapData
    productivity_by_weekday: list[WeekdayScore]
    deep_work_by_slot: list[SlotMinutes]
    distraction_trend: list[DistractionPoint]
    charts: FocusCharts


class ServiceInfo(BaseModel):
    service: str
    status: str
    version: str


class Health(BaseModel):
    status: str  # "ok" or "unavailable"
    checks: dict[str, str]  # dependency -> "ok" / "unavailable"
