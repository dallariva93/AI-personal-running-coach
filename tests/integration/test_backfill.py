"""Integration: historical backfill of the Garmin history.

The three properties that matter are asserted directly, because each one only
shows up in conditions that are painful to reproduce by hand: idempotence
(re-running), resumability (a failure mid-history) and the cutoff (not pulling
ten years when you asked for one).
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.db.models import Activity
from app.exceptions import CollectionError
from app.services.backfill import (
    backfill_activities,
    enrich_missing,
    months_ago,
    read_checkpoint,
    reset_checkpoint,
)


class FakeGarmin:
    """A Garmin source that pages through a canned history.

    Mirrors the real contract: newest first, `get_activities_page(start, limit)`
    returns a slice, and an exhausted history returns a short/empty page.
    """

    def __init__(self, activities: list[dict], fail_at_offset: int | None = None) -> None:
        self.activities = activities
        self.fail_at_offset = fail_at_offset
        self.pages_requested: list[tuple[int, int]] = []
        self.enrichment_calls: list[str] = []

    def get_activities_page(self, start: int, limit: int) -> list[dict]:
        self.pages_requested.append((start, limit))
        if self.fail_at_offset is not None and start >= self.fail_at_offset:
            raise CollectionError("connessione persa")
        return self.activities[start : start + limit]

    def get_activity_enrichment(self, activity_id) -> dict:
        self.enrichment_calls.append(str(activity_id))
        return {"splits_km": ["5:00", "4:58"], "hr_zones": {"z2": 30.0}}


def _activity(days_ago: int, activity_id: int, running: bool = True) -> dict:
    """A raw Garmin-shaped activity payload."""
    day = date.today() - timedelta(days=days_ago)
    return {
        "activityId": activity_id,
        "activityName": "Corsa",
        "startTimeLocal": f"{day.isoformat()} 07:30:00",
        "activityType": {"typeKey": "running" if running else "cycling"},
        "distance": 10000.0,
        "duration": 3000.0,
        "averageHR": 145,
    }


def _history(count: int, step_days: int = 3) -> list[dict]:
    """`count` activities going back in time, newest first."""
    return [_activity(days_ago=i * step_days, activity_id=1000 + i) for i in range(count)]


# --------------------------------------------------------------------------
# cutoff
# --------------------------------------------------------------------------
def test_monthsAgo_walksCalendarMonthsBack():
    assert months_ago(12, ref=date(2026, 7, 25)) == date(2025, 7, 25)
    assert months_ago(3, ref=date(2026, 1, 15)) == date(2025, 10, 15)
    # Day clamped into a shorter month rather than crashing.
    assert months_ago(1, ref=date(2026, 3, 31)) == date(2026, 2, 28)


def test_backfill_stopsAtCutoff_doesNotPullWholeHistory(session):
    # Two years of history, but we only asked for six months.
    source = FakeGarmin(_history(count=200, step_days=5))

    result = backfill_activities(session, source, months=6, page_size=50, throttle_s=0)

    assert result.completed
    cutoff = months_ago(6)
    stored = session.query(Activity).all()
    assert stored
    assert all(date.fromisoformat(a.date) >= cutoff for a in stored)
    # It stopped paging instead of walking all 200.
    assert result.activities_seen < 200


def test_backfill_importsRunsAndCrossTraining(session):
    source = FakeGarmin(
        [
            _activity(days_ago=1, activity_id=1, running=True),
            _activity(days_ago=2, activity_id=2, running=False),
            _activity(days_ago=3, activity_id=3, running=True),
        ]
    )

    result = backfill_activities(session, source, months=12, page_size=10, throttle_s=0)

    assert result.runs_imported == 2
    assert result.cross_training_imported == 1
    assert session.query(Activity).filter_by(sport="run").count() == 2
    assert session.query(Activity).filter(Activity.sport != "run").count() == 1


# --------------------------------------------------------------------------
# idempotence
# --------------------------------------------------------------------------
def test_backfill_rerun_importsNothingNew(session):
    source = FakeGarmin(_history(count=12))

    first = backfill_activities(session, source, months=12, page_size=5, throttle_s=0)
    count_after_first = session.query(Activity).count()

    second = backfill_activities(session, source, months=12, page_size=5, throttle_s=0)

    assert first.runs_imported == 12
    assert second.runs_imported == 0
    assert second.skipped_existing == 12
    assert session.query(Activity).count() == count_after_first  # no duplicates


def test_backfill_completedRun_clearsCheckpoint(session):
    source = FakeGarmin(_history(count=6))

    backfill_activities(session, source, months=12, page_size=5, throttle_s=0)

    assert read_checkpoint(session) == (0, None)


# --------------------------------------------------------------------------
# resumability
# --------------------------------------------------------------------------
def test_backfill_interrupted_keepsCheckpointAndPartialData(session):
    # Fails once past the first page: the first page must survive.
    source = FakeGarmin(_history(count=30), fail_at_offset=10)

    result = backfill_activities(session, source, months=12, page_size=10, throttle_s=0)

    assert not result.completed
    assert result.errors
    assert session.query(Activity).count() == 10  # page 1 persisted
    offset, cutoff = read_checkpoint(session)
    assert offset == 10
    assert cutoff == months_ago(12).isoformat()


def test_backfill_resumesFromCheckpoint_insteadOfRestarting(session):
    history = _history(count=30)
    failing = FakeGarmin(history, fail_at_offset=10)
    backfill_activities(session, failing, months=12, page_size=10, throttle_s=0)
    assert session.query(Activity).count() == 10

    # Network is back: the same command picks up where it stopped.
    healthy = FakeGarmin(history)
    result = backfill_activities(session, healthy, months=12, page_size=10, throttle_s=0)

    assert healthy.pages_requested[0][0] == 10  # did not re-read page 1
    assert result.completed
    assert session.query(Activity).count() == 30


def test_backfill_restartFlag_ignoresCheckpoint(session):
    history = _history(count=30)
    backfill_activities(session, FakeGarmin(history, fail_at_offset=10),
                        months=12, page_size=10, throttle_s=0)

    fresh = FakeGarmin(history)
    backfill_activities(session, fresh, months=12, page_size=10, throttle_s=0, resume=False)

    assert fresh.pages_requested[0][0] == 0  # started from the top


def test_backfill_changedCutoff_restartsInsteadOfResuming(session):
    """A different window is a different job — resuming into it would skip data."""
    history = _history(count=30, step_days=20)
    backfill_activities(session, FakeGarmin(history, fail_at_offset=10),
                        months=24, page_size=10, throttle_s=0)

    fresh = FakeGarmin(history)
    backfill_activities(session, fresh, months=6, page_size=10, throttle_s=0)

    assert fresh.pages_requested[0][0] == 0


def test_resetCheckpoint_clearsStoredProgress(session):
    backfill_activities(session, FakeGarmin(_history(30), fail_at_offset=10),
                        months=12, page_size=10, throttle_s=0)
    assert read_checkpoint(session)[0] == 10

    reset_checkpoint(session)

    assert read_checkpoint(session) == (0, None)


# --------------------------------------------------------------------------
# robustness
# --------------------------------------------------------------------------
def test_backfill_emptyHistory_completesCleanly(session):
    result = backfill_activities(session, FakeGarmin([]), months=12, throttle_s=0)

    assert result.completed
    assert result.runs_imported == 0
    assert session.query(Activity).count() == 0


def test_backfill_malformedActivity_doesNotAbortTheRun(session):
    source = FakeGarmin(
        [
            _activity(days_ago=1, activity_id=1),
            {"activityId": 2, "startTimeLocal": "non-una-data", "activityType": {}},
            _activity(days_ago=3, activity_id=3),
        ]
    )

    result = backfill_activities(session, source, months=12, page_size=10, throttle_s=0)

    assert result.runs_imported == 2  # the good ones still landed
    assert result.completed


# --------------------------------------------------------------------------
# enrichment pass
# --------------------------------------------------------------------------
def test_enrichMissing_fillsSplitsAndSkipsAlreadyEnriched(session):
    source = FakeGarmin(_history(count=3))
    backfill_activities(session, source, months=12, page_size=10, throttle_s=0)
    assert all(a.splits_km is None for a in session.query(Activity).all())

    result = enrich_missing(session, source, throttle_s=0)

    assert result.enriched == 3
    assert all(a.splits_km == ["5:00", "4:58"] for a in session.query(Activity).all())

    # A second pass has nothing left to do — no wasted API calls.
    source.enrichment_calls.clear()
    again = enrich_missing(session, source, throttle_s=0)
    assert again.enriched == 0
    assert source.enrichment_calls == []


def test_enrichMissing_respectsBatchLimit(session):
    source = FakeGarmin(_history(count=10))
    backfill_activities(session, source, months=12, page_size=20, throttle_s=0)

    result = enrich_missing(session, source, limit=4, throttle_s=0)

    assert result.enriched == 4
    assert len(source.enrichment_calls) == 4


def test_enrichMissing_failureOnOneActivity_continuesWithTheRest(session):
    source = FakeGarmin(_history(count=3))
    backfill_activities(session, source, months=12, page_size=10, throttle_s=0)

    calls: list[str] = []
    original = source.get_activity_enrichment

    def flaky(activity_id):
        calls.append(str(activity_id))
        if len(calls) == 1:
            raise RuntimeError("429 Too Many Requests")
        return original(activity_id)

    source.get_activity_enrichment = flaky
    result = enrich_missing(session, source, throttle_s=0)

    assert len(calls) == 3  # it kept going
    assert result.enriched == 2
    assert result.errors


@pytest.mark.parametrize("months,expected_years", [(12, 1), (24, 2)])
def test_backfill_monthsParameter_setsTheWindow(session, months, expected_years):
    source = FakeGarmin(_history(count=400, step_days=5))

    backfill_activities(session, source, months=months, page_size=100, throttle_s=0)

    oldest = min(date.fromisoformat(a.date) for a in session.query(Activity).all())
    assert oldest >= date.today() - timedelta(days=expected_years * 366)
