"""Integration: exporting a planned week to the Garmin calendar.

The tests that matter most here are the refusals. This is the only path in the
app that writes to the outside world, and what it writes gets **run** by a
person — so "nothing was sent" has to be the outcome whenever anything is
unclear, and the confirmation the athlete gives has to be about the week as it
actually is at that moment, not as it was when they last looked.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.db.models import TrainingPlan, TrainingPlanSession, TrainingPlanWeek
from app.exceptions import CollectionError
from app.services import garmin_export


class FakeGarmin:
    """Records what would have reached Garmin."""

    def __init__(self, fail_on: str | None = None) -> None:
        self.uploaded: list = []
        self.scheduled: list = []
        self.deleted: list = []
        self._next_id = 1000
        self._fail_on = fail_on

    def upload_running_workout(self, workout):
        if self._fail_on == "upload":
            raise RuntimeError("Garmin 500")
        self._next_id += 1
        self.uploaded.append(workout.to_dict())
        return {"workoutId": self._next_id}

    def schedule_workout(self, workout_id, date_str):
        self.scheduled.append((str(workout_id), date_str))
        return {"ok": True}

    def delete_workout(self, workout_id):
        self.deleted.append(str(workout_id))
        return {"ok": True}


def _monday() -> date:
    today = date.today()
    return today - timedelta(days=today.weekday())


@pytest.fixture
def plan(session):
    """An active one-week plan: intervals, an easy run, a rest day."""
    p = TrainingPlan(
        goal_type="10k", goal_date=(_monday() + timedelta(days=60)).isoformat(),
        level="intermediate", weeks_total=1, start_date=_monday().isoformat(),
        status="active",
    )
    session.add(p)
    session.flush()
    week = TrainingPlanWeek(plan_id=p.id, week_number=1, phase="Build", target_km=40.0)
    session.add(week)
    session.flush()
    session.add_all([
        TrainingPlanSession(
            week_id=week.id, day_of_week=1, session_type="intervals",
            title="Ripetute", target_distance_km=12.0, target_duration_min=62.0,
            steps=[
                {"kind": "warmup", "distance_km": 2.5, "pace": "5:30/km"},
                {"kind": "repeat", "times": 6, "steps": [
                    {"kind": "interval", "distance_km": 1.0, "pace": "3:45/km"},
                    {"kind": "recovery", "duration_min": 2},
                ]},
                {"kind": "cooldown", "distance_km": 2.0, "pace": "5:30/km"},
            ],
        ),
        TrainingPlanSession(
            week_id=week.id, day_of_week=3, session_type="easy", title="Corsa facile",
            target_distance_km=8.0,
            steps=[{"kind": "interval", "distance_km": 8.0, "pace": "5:30/km"}],
        ),
        TrainingPlanSession(
            week_id=week.id, day_of_week=5, session_type="rest", title="Riposo",
        ),
    ])
    session.commit()
    return p


# ── preview ──────────────────────────────────────────────────────────────────


def test_preview_showsOnlyRunnableSessions(session, plan):
    out = garmin_export.preview_week(session, 1)

    assert [s["title"] for s in out["sessions_to_push"]] == ["Ripetute", "Corsa facile"]
    assert [s["title"] for s in out["not_exported"]] == ["Riposo"]
    assert out["confirm_code"]


def test_preview_datesTheSessionsCorrectly(session, plan):
    out = garmin_export.preview_week(session, 1)
    monday = _monday()

    assert out["sessions_to_push"][0]["date"] == (monday + timedelta(days=1)).isoformat()
    assert out["sessions_to_push"][1]["date"] == (monday + timedelta(days=3)).isoformat()


def test_preview_rendersTheStepsTheAthleteWillRun(session, plan):
    steps = garmin_export.preview_week(session, 1)["sessions_to_push"][0]["steps"]

    assert any("6×" in line for line in steps)
    assert any("riscaldamento" in line for line in steps)


def test_preview_sessionWithoutStructure_isNotExportedAndSaysWhy(session, plan):
    """Sessions from before structured steps must not be silently dropped."""
    row = session.scalars(
        __import__("sqlalchemy").select(TrainingPlanSession).where(
            TrainingPlanSession.session_type == "easy"
        )
    ).first()
    row.steps = None
    session.commit()

    out = garmin_export.preview_week(session, 1)

    skipped = [s for s in out["not_exported"] if s["title"] == "Corsa facile"]
    assert skipped and "struttura" in skipped[0]["reason"]


def test_preview_withoutAnActivePlan_raises(session):
    with pytest.raises(CollectionError):
        garmin_export.preview_week(session, 1)


# ── the confirmation gate ────────────────────────────────────────────────────


def test_push_withoutCode_sendsNothing(session, plan):
    client = FakeGarmin()

    with pytest.raises(CollectionError):
        garmin_export.push_week(session, 1, "", client=client)

    assert client.uploaded == []


def test_push_withWrongCode_sendsNothing(session, plan):
    client = FakeGarmin()

    with pytest.raises(CollectionError):
        garmin_export.push_week(session, 1, "ABC123", client=client)

    assert client.uploaded == []
    assert client.scheduled == []


def test_push_withValidCode_uploadsAndSchedules(session, plan):
    client = FakeGarmin()
    code = garmin_export.preview_week(session, 1)["confirm_code"]

    result = garmin_export.push_week(session, 1, code, client=client)

    assert result.pushed == 2
    assert len(client.uploaded) == 2
    assert len(client.scheduled) == 2
    monday = _monday()
    assert client.scheduled[0][1] == (monday + timedelta(days=1)).isoformat()


def test_push_codeStopsWorkingWhenThePlanChanges(session, plan):
    """The adaptive plan rewrites sessions on its own.

    A code issued for last night's week must not send tonight's — the athlete
    confirmed something they can no longer see.
    """
    code = garmin_export.preview_week(session, 1)["confirm_code"]

    row = session.scalars(
        __import__("sqlalchemy").select(TrainingPlanSession).where(
            TrainingPlanSession.session_type == "intervals"
        )
    ).first()
    row.steps = [{"kind": "interval", "distance_km": 5.0, "pace": "4:30/km"}]
    session.commit()

    client = FakeGarmin()
    with pytest.raises(CollectionError):
        garmin_export.push_week(session, 1, code, client=client)

    assert client.uploaded == []


def test_push_codeIsNotGuessableFromTheWeek(session, plan):
    """The code is derived from key material, not from what the preview shows."""
    out = garmin_export.preview_week(session, 1)

    assert out["confirm_code"] not in str(out["sessions_to_push"])
    assert len(out["confirm_code"]) == 6


# ── re-export and failures ───────────────────────────────────────────────────


def test_push_twice_replacesInsteadOfDuplicating(session, plan):
    """A second export must not stack a second copy in the calendar."""
    client = FakeGarmin()
    code = garmin_export.preview_week(session, 1)["confirm_code"]
    garmin_export.push_week(session, 1, code, client=client)
    first_ids = [str(u) for u in client.scheduled]

    client2 = FakeGarmin()
    code2 = garmin_export.preview_week(session, 1)["confirm_code"]
    result = garmin_export.push_week(session, 1, code2, client=client2)

    assert result.updated == 2
    assert result.pushed == 0
    assert len(client2.deleted) == 2  # the old copies withdrawn
    assert len(client2.scheduled) == 2
    assert first_ids  # sanity: the first run really did schedule something


def test_push_recordsWhatIsOnTheWatch(session, plan):
    client = FakeGarmin()
    code = garmin_export.preview_week(session, 1)["confirm_code"]
    garmin_export.push_week(session, 1, code, client=client)

    rows = session.scalars(
        __import__("sqlalchemy").select(TrainingPlanSession).where(
            TrainingPlanSession.garmin_workout_id.is_not(None)
        )
    ).all()
    assert len(rows) == 2
    assert all(r.garmin_scheduled_date for r in rows)


def test_push_oneFailure_doesNotStopTheWeek(session, plan):
    """A single rejected session must not cost the athlete the other days."""
    client = FakeGarmin(fail_on="upload")
    code = garmin_export.preview_week(session, 1)["confirm_code"]

    result = garmin_export.push_week(session, 1, code, client=client)

    assert result.pushed == 0
    assert len(result.errors) == 2  # both reported, neither silently dropped


def test_previewAgainAfterPush_marksWhatIsAlreadyThere(session, plan):
    client = FakeGarmin()
    code = garmin_export.preview_week(session, 1)["confirm_code"]
    garmin_export.push_week(session, 1, code, client=client)

    out = garmin_export.preview_week(session, 1)

    assert all(s["already_on_garmin"] for s in out["sessions_to_push"])


# ── a week that lives in the conversation, not in the database ───────────────
#
# The plan is kept in the Claude project: this app is the source of truth for
# what was *run*, not for what was prescribed. The engine stops authoring and
# starts checking.


def _week_from_chat(monday: date | None = None) -> list[dict]:
    monday = monday or _monday()
    return [
        {
            "date": (monday + timedelta(days=1)).isoformat(),
            "title": "Ripetute 6×1000",
            "type": "intervals",
            "steps": [
                {"kind": "warmup", "distance_km": 2.5, "pace": "5:30/km",
                 "tolerance_s": 25},
                {"kind": "repeat", "times": 6, "steps": [
                    {"kind": "interval", "distance_km": 1.0, "pace": "4:00/km",
                     "tolerance_s": 6},
                    {"kind": "recovery", "duration_min": 2},
                ]},
                {"kind": "cooldown", "distance_km": 2.0, "pace": "5:30/km",
                 "tolerance_s": 25},
            ],
        },
        {
            "date": (monday + timedelta(days=3)).isoformat(),
            "title": "Corsa facile",
            "type": "easy",
            "steps": [{"kind": "interval", "distance_km": 8.0, "pace": "5:30/km",
                       "tolerance_s": 25}],
        },
    ]


def test_previewSessions_rendersAndReturnsACode(session):
    out = garmin_export.preview_sessions(session, _week_from_chat())

    assert len(out["sessions_to_push"]) == 2
    assert out["confirm_code"]
    assert out["total_km"] == 18.5  # 2.5 + 6×1 + 2 + 8
    assert any("6×" in line for line in out["sessions_to_push"][0]["rendered"])


def test_pushSessions_requiresTheCodeForThoseExactSessions(session):
    client = FakeGarmin()
    week = _week_from_chat()
    code = garmin_export.preview_sessions(session, week)["confirm_code"]

    # One rep more than what was approved.
    changed = [dict(s) for s in week]
    changed[0] = {**changed[0], "title": "Ripetute 8×1000"}

    with pytest.raises(CollectionError):
        garmin_export.push_sessions(session, changed, code, client=client)

    assert client.uploaded == []


def test_pushSessions_withTheRightCode_schedulesEachDay(session):
    client = FakeGarmin()
    week = _week_from_chat()
    code = garmin_export.preview_sessions(session, week)["confirm_code"]

    result = garmin_export.push_sessions(session, week, code, client=client)

    assert result.pushed == 2
    assert [d for _, d in client.scheduled] == [s["date"] for s in week]


# ── the refusals: shape ──────────────────────────────────────────────────────


def test_previewSessions_refusesMoreThanAWeek(session):
    monday = _monday()
    two_weeks = _week_from_chat() + [
        {**_week_from_chat()[0], "date": (monday + timedelta(days=10)).isoformat()}
    ]

    with pytest.raises(CollectionError, match="settimana"):
        garmin_export.preview_sessions(session, two_weeks)


def test_previewSessions_refusesTwoSessionsOnTheSameDay(session):
    week = _week_from_chat()
    clash = [week[0], {**week[1], "date": week[0]["date"]}]

    with pytest.raises(CollectionError, match="stesso giorno"):
        garmin_export.preview_sessions(session, clash)


def test_previewSessions_refusesASessionWithoutSteps(session):
    week = _week_from_chat()
    week[1] = {**week[1], "steps": []}

    with pytest.raises(CollectionError, match="step"):
        garmin_export.preview_sessions(session, week)


def test_previewSessions_refusesABadDate(session):
    week = _week_from_chat()
    week[0] = {**week[0], "date": "martedì"}

    with pytest.raises(CollectionError, match="Data non valida"):
        garmin_export.preview_sessions(session, week)


def test_previewSessions_failsOnAnUnbuildableSessionBeforeAnythingIsSent(session):
    """Better to fail in front of the athlete than halfway through the push."""
    week = _week_from_chat()
    week[0]["steps"] = [{"kind": "repeat", "times": 0, "steps": []}]

    with pytest.raises(CollectionError):
        garmin_export.preview_sessions(session, week)


# ── the engine as a checker ──────────────────────────────────────────────────


def _seed_history(session, weekly_km: float, weeks: int = 4) -> None:
    """Runs at a steady weekly volume, so the ramp check has a baseline."""
    from app.schemas import RunSummary
    from app.services.ingest import upsert_activity

    today = date.today()
    per_run = weekly_km / 4
    for w in range(weeks):
        for d in (0, 2, 4, 6):
            upsert_activity(session, RunSummary(
                date=(today - timedelta(days=w * 7 + d)).isoformat(),
                activity_type="easy", distance_km=per_run,
                duration_min=per_run * 5.5, avg_pace="5:30/km", avg_hr=140,
            ))
    session.commit()


def test_validate_warnsWhenTheWeekRampsTooFast(session):
    """The single most common way a self-written plan hurts someone.

    18.5 km proposed against a 12 km/week base is a +54 % jump.
    """
    _seed_history(session, weekly_km=12.0)

    out = garmin_export.preview_sessions(session, _week_from_chat())

    assert any("Volume in salita" in w for w in out["warnings"])


def test_validate_isQuietOnASensibleWeek(session):
    _seed_history(session, weekly_km=40.0)

    out = garmin_export.preview_sessions(session, _week_from_chat())

    assert not [w for w in out["warnings"] if "Volume in salita" in w]


def test_validate_warnsWhenQualityEatsTheWeek(session):
    """80/20 gone: worth naming before it reaches the watch."""
    _seed_history(session, weekly_km=40.0)
    monday = _monday()
    heavy = [
        {
            "date": (monday + timedelta(days=i)).isoformat(),
            "title": f"Ripetute {i}", "type": "intervals",
            "steps": [{"kind": "interval", "distance_km": 8.0, "pace": "4:00/km",
                       "tolerance_s": 6}],
        }
        for i in range(3)
    ]

    out = garmin_export.preview_sessions(session, heavy)

    assert any("Qualità al" in w for w in out["warnings"])


def test_validate_withoutHistory_saysSoRatherThanApproving(session):
    """No baseline is not the same as a clean bill of health."""
    out = garmin_export.preview_sessions(session, _week_from_chat())

    assert any("Nessuno storico" in w for w in out["warnings"])


def test_validate_warningsNeverBlockThePush(session):
    """The engine advises; the athlete and the coach decide."""
    _seed_history(session, weekly_km=12.0)
    client = FakeGarmin()
    week = _week_from_chat()
    out = garmin_export.preview_sessions(session, week)
    assert out["warnings"]

    result = garmin_export.push_sessions(session, week, out["confirm_code"], client=client)

    assert result.pushed == 2
