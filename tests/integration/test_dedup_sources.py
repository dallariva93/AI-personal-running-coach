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


def test_tripleSource_collapsesToTheRichestRow(session):
    """A run seen by Garmin, Strava AND Health Connect is still one run.

    Observed in real data: three rows for the same activity, so the merge has
    to fold two of them into the survivor rather than handling a single pair.
    """
    session.add(Activity(
        garmin_activity_id="g-1", date=TODAY, sport="run", activity_type="easy",
        distance_km=6.1, duration_min=36.0, rpe=3,
    ))
    session.add(Activity(
        strava_activity_id="s-1", date=TODAY, sport="run", activity_type="easy",
        distance_km=6.1, duration_min=36.0,
    ))
    session.add(Activity(
        health_connect_id="hc-1", date=TODAY, sport="run", activity_type="easy",
        distance_km=6.1, duration_min=36.2, avg_hr=141,
    ))
    session.flush()

    report = merge_duplicates(session, dry_run=False)

    assert len(report) == 2  # two rows folded into one survivor
    row = session.query(Activity).one()
    assert row.garmin_activity_id == "g-1"
    assert row.strava_activity_id == "s-1"
    assert row.health_connect_id == "hc-1"
    assert row.rpe == 3          # richest source kept
    assert row.avg_hr == 141     # gap filled from a dropped row


def test_stravaDuplicate_isMergedIntoGarmin(session):
    """Strava duplicates the same way Health Connect does, and ranks below Garmin."""
    upsert_activity(session, _garmin())
    upsert_activity(session, RunSummary(
        strava_activity_id="s-1", date=TODAY, activity_type="easy",
        distance_km=10.0, duration_min=55.0, avg_pace="5:30/km",
    ))
    session.flush()

    row = session.query(Activity).one()
    assert row.garmin_activity_id == "g-1"
    assert row.strava_activity_id == "s-1"
    assert row.rpe == 2  # Strava must not blank Garmin's RPE


# --------------------------------------------------------------------------
# cross-training nel sync normale
# --------------------------------------------------------------------------
class _SourceWithCrossTraining:
    """A source that returns both runs and cross-training, like Garmin does."""

    def __init__(self, fail_cross: bool = False) -> None:
        self.fail_cross = fail_cross
        self.cross_calls = 0

    def get_recent_runs(self, limit: int = 10, skip_gps_for=None) -> list[RunSummary]:
        return [RunSummary(
            garmin_activity_id="g-run", date=TODAY, activity_type="easy",
            distance_km=10.0, duration_min=55.0,
        )]

    def get_recent_cross_training(self, limit: int = 20) -> list[RunSummary]:
        self.cross_calls += 1
        if self.fail_cross:
            raise RuntimeError("endpoint cross-training non disponibile")
        return [
            RunSummary(garmin_activity_id="g-bike", date=TODAY, sport="bike",
                       activity_type="easy", distance_km=40.0, duration_min=80.0),
            RunSummary(garmin_activity_id="g-gym", date=TODAY, sport="strength",
                       activity_type="easy", distance_km=0.0, duration_min=45.0),
        ]


def test_ingestRuns_alsoPullsCrossTraining(session):
    """Bike and gym are load too — they used to need a separate manual call."""
    from app.services.ingest import ingest_runs

    ingest_runs(session, source=_SourceWithCrossTraining())
    session.flush()

    sports = {row.sport for row in session.query(Activity).all()}
    assert sports == {"run", "bike", "strength"}


def test_crossTrainingFailure_doesNotBreakTheRunSync(session):
    """A secondary signal must never cost you the primary one."""
    from app.services.ingest import ingest_runs

    saved = ingest_runs(session, source=_SourceWithCrossTraining(fail_cross=True))
    session.flush()

    assert len(saved) == 1
    assert session.query(Activity).filter_by(sport="run").count() == 1


def test_crossTraining_staysOutOfRunningMetrics(session):
    """The whole reason it is stored separately: it must not inflate CTL/ACWR."""
    from app.services.ingest import ingest_runs

    ingest_runs(session, source=_SourceWithCrossTraining())
    session.flush()

    metrics = compute_metrics(_all_summaries(session))
    assert metrics.runs_count == 1
    assert metrics.total_distance_km == 10.0  # the 40 km bike ride is excluded
