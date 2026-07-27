"""Integration: the same run arriving from two sources must be one activity.

Garmin and Health Connect both observe the phone/watch's run but share no
identifier, so an id-only upsert stored it twice. That is not a cosmetic bug:
every load metric (CTL/ATL/TSB, ACWR, weekly volume) sums distances, so a
duplicate silently inflates the athlete's training load.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.db.models import Activity
from app.processing import compute_metrics
from app.schemas import RunSummary
from app.services.ingest import (
    _all_summaries,
    find_duplicate,
    merge_duplicates,
    upsert_activity,
)

TODAY = date.today().isoformat()


def _garmin(day: str = TODAY, km: float = 10.0, minutes: float = 55.0, **kw) -> RunSummary:
    return RunSummary(
        garmin_activity_id=kw.pop("gid", "g-1"),
        date=day, activity_type="easy", distance_km=km, duration_min=minutes,
        avg_pace="5:30/km", avg_hr=145, rpe=2, splits_km=["5:28", "5:31"], **kw,
    )


def _health_connect(day: str = TODAY, km: float = 10.0, minutes: float = 55.0, **kw) -> RunSummary:
    """Health Connect v0: derived pace, no splits, no RPE."""
    return RunSummary(
        health_connect_id=kw.pop("hcid", "hc-1"),
        date=day, activity_type="easy", distance_km=km, duration_min=minutes,
        avg_pace="5:30/km", **kw,
    )


# --------------------------------------------------------------------------
# prevention: the same run never lands twice
# --------------------------------------------------------------------------
def test_healthConnectAfterGarmin_mergesInsteadOfDuplicating(session):
    upsert_activity(session, _garmin())
    upsert_activity(session, _health_connect())
    session.flush()

    rows = session.query(Activity).all()
    assert len(rows) == 1
    assert rows[0].garmin_activity_id == "g-1"
    assert rows[0].health_connect_id == "hc-1"  # both ids now point at one row


def test_healthConnect_doesNotDegradeGarminData(session):
    """The exact symptom that started this: RPE disappearing from a run."""
    upsert_activity(session, _garmin())
    session.flush()

    # Health Connect carries no RPE and no splits. It must not blank them.
    upsert_activity(session, _health_connect())
    session.flush()

    row = session.query(Activity).one()
    assert row.rpe == 2
    assert row.splits_km == ["5:28", "5:31"]
    assert row.avg_hr == 145


def test_garminAfterHealthConnect_upgradesTheRow(session):
    """Arrival order must not matter — but Garmin's richer data should win."""
    upsert_activity(session, _health_connect())
    session.flush()
    upsert_activity(session, _garmin())
    session.flush()

    rows = session.query(Activity).all()
    assert len(rows) == 1
    assert rows[0].garmin_activity_id == "g-1"
    assert rows[0].health_connect_id == "hc-1"
    assert rows[0].rpe == 2  # the richer source filled it in


def test_repeatedSync_isStillIdempotent(session):
    for _ in range(3):
        upsert_activity(session, _garmin())
        upsert_activity(session, _health_connect())
        session.flush()

    assert session.query(Activity).count() == 1


def test_twoGenuineRunsOnSameDay_areNotMerged(session):
    """A double session is two runs, not a duplicate."""
    upsert_activity(session, _garmin(gid="g-morning", km=10.0, minutes=55.0))
    upsert_activity(session, _garmin(gid="g-evening", km=6.0, minutes=32.0))
    session.flush()

    assert session.query(Activity).count() == 2


def test_sameSourceTwice_isNeverMerged(session):
    """Two Garmin activities of similar length on one day are both real."""
    upsert_activity(session, _garmin(gid="g-a", km=10.0, minutes=55.0))
    upsert_activity(session, _garmin(gid="g-b", km=10.1, minutes=55.5))
    session.flush()

    assert session.query(Activity).count() == 2


def test_differentDays_areNotMerged(session):
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    upsert_activity(session, _garmin())
    upsert_activity(session, _health_connect(day=yesterday))
    session.flush()

    assert session.query(Activity).count() == 2


def test_differentSport_isNotMerged(session):
    upsert_activity(session, _garmin())
    upsert_activity(session, _health_connect(hcid="hc-bike", sport="bike"))
    session.flush()

    assert session.query(Activity).count() == 2


def test_smallMeasurementDrift_stillCountsAsTheSameRun(session):
    """Two apps reading one GPS track disagree slightly; that is not two runs."""
    upsert_activity(session, _garmin(km=10.0, minutes=55.0))
    upsert_activity(session, _health_connect(km=10.2, minutes=55.6))
    session.flush()

    assert session.query(Activity).count() == 1


def test_findDuplicate_returnsNoneWhenNothingMatches(session):
    upsert_activity(session, _garmin())
    session.flush()

    assert find_duplicate(session, _health_connect(km=25.0, minutes=140.0)) is None


# --------------------------------------------------------------------------
# cleanup: duplicates already stored
# --------------------------------------------------------------------------
def _seed_legacy_duplicate(session) -> None:
    """Two rows for one run, as the id-only upsert used to leave them."""
    session.add(Activity(
        garmin_activity_id="g-1", date=TODAY, sport="run", activity_type="easy",
        distance_km=10.0, duration_min=55.0, avg_pace="5:30/km", avg_hr=145, rpe=2,
    ))
    session.add(Activity(
        health_connect_id="hc-1", date=TODAY, sport="run", activity_type="easy",
        distance_km=10.0, duration_min=55.0, avg_pace="5:30/km",
    ))
    session.flush()


def test_mergeDuplicates_dryRunReportsWithoutChanging(session):
    _seed_legacy_duplicate(session)

    report = merge_duplicates(session, dry_run=True)

    assert len(report) == 1
    assert report[0]["kept"]["source"] == "garmin"
    assert report[0]["dropped"]["source"] == "health_connect"
    assert session.query(Activity).count() == 2  # untouched


def test_mergeDuplicates_applyKeepsTheRicherSource(session):
    _seed_legacy_duplicate(session)

    merge_duplicates(session, dry_run=False)

    row = session.query(Activity).one()
    assert row.garmin_activity_id == "g-1"
    assert row.health_connect_id == "hc-1"
    assert row.rpe == 2


def test_mergeDuplicates_fillsGapsFromTheDroppedRow(session):
    session.add(Activity(
        garmin_activity_id="g-1", date=TODAY, sport="run", activity_type="easy",
        distance_km=10.0, duration_min=55.0,  # no HR recorded by the watch
    ))
    session.add(Activity(
        health_connect_id="hc-1", date=TODAY, sport="run", activity_type="easy",
        distance_km=10.0, duration_min=55.0, avg_hr=142,
    ))
    session.flush()

    merge_duplicates(session, dry_run=False)

    row = session.query(Activity).one()
    assert row.garmin_activity_id == "g-1"
    assert row.avg_hr == 142  # gap filled rather than lost


def test_mergeDuplicates_isIdempotent(session):
    _seed_legacy_duplicate(session)
    merge_duplicates(session, dry_run=False)

    assert merge_duplicates(session, dry_run=False) == []
    assert session.query(Activity).count() == 1


def test_mergeDuplicates_noDuplicates_reportsNothing(session):
    upsert_activity(session, _garmin())
    session.flush()

    assert merge_duplicates(session, dry_run=True) == []


# --------------------------------------------------------------------------
# why it matters
# --------------------------------------------------------------------------
def test_duplicatesInflateTrainingLoad_andMergingRestoresIt(session):
    """The reason this is a correctness bug, not a tidiness one."""
    _seed_legacy_duplicate(session)
    inflated = compute_metrics(_all_summaries(session))

    merge_duplicates(session, dry_run=False)
    corrected = compute_metrics(_all_summaries(session))

    assert inflated.total_distance_km == 20.0   # one 10 km run counted twice
    assert corrected.total_distance_km == 10.0
    assert corrected.runs_count == 1
