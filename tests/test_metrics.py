"""
F-07: hand-computed fixtures for the single metrics module.

For day D, a block is due once its end time has passed (end <= now).
  completion   = completed minutes of due blocks / planned minutes of due blocks
  deep         = min(1, completed deep-work minutes / 180)
  distraction  = max(0, 1 - distractions per completed deep-work hour / 4); 0 without deep work
  focus_score  = round_half_up(100 * (0.5*completion + 0.3*deep + 0.2*distraction)); None if nothing due
Planned/Done cover all of D's blocks; deep/distraction use every completed deep-work block of D.
"""

from datetime import date, datetime

import pytest

from app.metrics import (
    DAILY_DEEP_WORK_TARGET_MIN,
    Block,
    day_metrics,
    mean_score,
)

PAST = date(2026, 10, 20)
TODAY = date(2026, 10, 29)


def at(hh, mm=0, day=TODAY):
    return datetime(day.year, day.month, day.day, hh, mm)


def block(start, end, category="deep-work", status="completed", distractions=0, day=PAST):
    return Block(day=day, start=start, end=end, category=category, status=status, distractions=distractions)


def test_target_constant():
    assert DAILY_DEEP_WORK_TARGET_MIN == 180


def test_empty_day_has_no_score():
    m = day_metrics(PAST, [], now=at(12))
    assert m.focus_score is None
    assert m.completion is None
    assert m.planned_minutes == 0 and m.completed_minutes == 0
    assert m.deep == 0 and m.distraction == 0


def test_all_pending_scores_zero_with_no_free_points():
    m = day_metrics(PAST, [
        block("09:00", "10:00", status="pending"),
        block("10:00", "11:00", category="study", status="pending"),
    ], now=at(12))
    assert m.completion == 0
    assert m.deep == 0
    assert m.distraction == 0          # no deep work completed -> 0, not a free 1.0
    assert m.focus_score == 0
    assert m.planned_minutes == 120 and m.completed_minutes == 0


def test_finished_day_hand_computed():
    # completion 180/240 = 0.75; deep 120/180; 2 distractions over 2 deep hours = 1/h -> 1 - 1/4 = 0.75
    # 100 * (0.375 + 0.2 + 0.15) = 72.5 -> rounds half up to 73
    m = day_metrics(PAST, [
        block("09:00", "11:00", distractions=2),
        block("11:00", "12:00", category="study"),
        block("13:00", "14:00", category="admin", status="skipped"),
    ], now=at(12))
    assert (m.planned_minutes, m.completed_minutes) == (240, 180)
    assert (m.due_planned_minutes, m.due_completed_minutes) == (240, 180)
    assert m.completion == pytest.approx(0.75)
    assert m.deep == pytest.approx(120 / 180)
    assert m.distraction == pytest.approx(0.75)
    assert m.deep_work_minutes == 120 and m.distractions == 2
    assert m.focus_score == 73


def test_day_in_progress_only_due_blocks_count_for_completion():
    blocks = [
        block("09:00", "10:00", day=TODAY),                                     # due, done
        block("10:00", "12:00", category="study", status="pending", day=TODAY),  # not due at 11:00
        block("14:00", "15:00", distractions=1, day=TODAY),                      # finished early
    ]
    m = day_metrics(TODAY, blocks, now=at(11))
    # completion 60/60 = 1; deep 120/180; 1 distraction / 2h = 0.5/h -> 0.875
    # 100 * (0.5 + 0.2 + 0.175) = 87.5 -> 88
    assert (m.planned_minutes, m.completed_minutes) == (240, 120)
    assert (m.due_planned_minutes, m.due_completed_minutes) == (60, 60)
    assert m.completion == 1
    assert m.distraction == pytest.approx(0.875)
    assert m.focus_score == 88
    assert (m.blocks_total, m.blocks_due, m.blocks_completed) == (3, 1, 2)


def test_nothing_due_yet_means_no_score_even_with_early_completions():
    m = day_metrics(TODAY, [block("14:00", "15:00", day=TODAY)], now=at(9, 30))
    assert m.focus_score is None and m.completion is None
    assert m.completed_minutes == 60          # Done still shows it
    assert m.deep == pytest.approx(60 / 180)


def test_block_is_due_when_its_end_time_is_reached():
    m = day_metrics(TODAY, [block("09:00", "10:00", day=TODAY)], now=at(10))
    assert m.blocks_due == 1 and m.completion == 1


def test_future_day_has_no_score():
    future = date(2026, 11, 2)
    m = day_metrics(future, [block("09:00", "10:00", day=future)], now=at(12))
    assert m.focus_score is None and m.blocks_due == 0


def test_end_of_day_block():
    m = day_metrics(PAST, [block("21:00", "24:00")], now=at(12))
    assert m.planned_minutes == 180 and m.deep == 1


def test_distraction_floor():
    m = day_metrics(PAST, [block("09:00", "10:00", distractions=10)], now=at(12))
    assert m.distraction == 0


def test_completed_zero_duration_block_does_not_divide_by_zero():
    m = day_metrics(PAST, [block("10:00", "10:00")], now=at(12))
    assert m.focus_score is None and m.completion is None
    assert m.deep == 0 and m.distraction == 0


def test_unparseable_or_inverted_legacy_rows_count_as_zero_minutes():
    m = day_metrics(PAST, [block("10:00", "09:00"), block("bad", "11:00")], now=at(12))
    assert m.planned_minutes == 0 and m.focus_score is None


def test_mean_score_excludes_days_without_data():
    assert mean_score([73, None, 88]) == 80.5
    assert mean_score([None, None]) is None
    assert mean_score([]) is None


# ------------------------------------------------------------------ #
#  F1: block lifecycle — actual times, partial, moved
# ------------------------------------------------------------------ #

def lifecycle(start, end, status, actual=None, category="deep-work", distractions=0):
    a_start, a_end = actual if actual else (None, None)
    return Block(day=PAST, start=start, end=end, category=category, status=status, distractions=distractions,
                 actual_start_min=a_start, actual_end_min=a_end)


def test_done_counts_its_actual_minutes_when_present():
    m = day_metrics(PAST, [lifecycle("09:00", "11:00", "done", actual=(560, 650))], at(23))
    assert (m.planned_minutes, m.completed_minutes, m.deep_work_minutes) == (120, 90, 90)
    assert m.completion == 0.75


def test_done_without_actual_times_counts_planned_minutes():
    m = day_metrics(PAST, [lifecycle("09:00", "10:00", "done")], at(23))
    assert m.completed_minutes == 60 and m.completion == 1


def test_partial_counts_only_its_actual_minutes():
    blocks = [lifecycle("09:00", "11:00", "partial", actual=(540, 570)), lifecycle("13:00", "14:00", "partial")]
    m = day_metrics(PAST, blocks, at(23))
    assert (m.completed_minutes, m.blocks_completed) == (30, 1)
    assert m.completion == pytest.approx(30 / 180)


def test_completion_is_capped_when_actual_time_runs_longer_than_planned():
    m = day_metrics(PAST, [lifecycle("09:00", "10:00", "done", actual=(540, 660))], at(23))
    assert m.completed_minutes == 120 and m.completion == 1


def test_moved_blocks_count_nowhere_and_skipped_stay_planned():
    blocks = [lifecycle("09:00", "10:00", "moved"), lifecycle("10:00", "11:00", "skipped"),
              lifecycle("11:00", "12:00", "done")]
    m = day_metrics(PAST, blocks, at(23))
    assert (m.planned_minutes, m.completed_minutes, m.blocks_total) == (120, 60, 2)
    assert m.completion == 0.5


def test_new_and_legacy_status_names_mean_the_same():
    old = day_metrics(PAST, [lifecycle("09:00", "10:00", "completed"), lifecycle("10:00", "11:00", "pending")], at(23))
    new = day_metrics(PAST, [lifecycle("09:00", "10:00", "done"), lifecycle("10:00", "11:00", "planned")], at(23))
    assert old == new
