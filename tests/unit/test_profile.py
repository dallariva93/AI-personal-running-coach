"""Unit tests for athlete profile persistence and goal-aware coaching."""

from __future__ import annotations

from datetime import date

from app.coaching import prompts
from app.coaching.coach import OfflineCoach
from app.processing import compute_metrics
from app.schemas import AthletePhysiology, AthleteProfile, Goal, HRZones, RunSummary
from app.services import get_profile, save_profile


def test_profile_absent_returns_none(session):
    assert get_profile(session) is None


def test_profile_round_trip(session):
    profile = AthleteProfile(
        age=35,
        sex="M",
        max_hr=188,
        resting_hr=48,
        weekly_runs=5,
        zones=HRZones(z2_hr=(141, 155)),
        physiology=AthletePhysiology(lt2_pace="4:25"),
        goal=Goal(goal_type="marathon", target_date="2027-04-11", priority="A"),
    )
    save_profile(session, profile)
    session.commit()

    loaded = get_profile(session)
    assert loaded is not None
    assert loaded.age == 35
    assert loaded.max_hr == 188
    assert loaded.zones is not None and loaded.zones.z2_hr == (141, 155)
    assert loaded.physiology is not None and loaded.physiology.lt2_pace == "4:25"
    assert loaded.goal is not None and loaded.goal.goal_type == "marathon"


def test_profile_is_singleton(session):
    save_profile(session, AthleteProfile(age=30))
    save_profile(session, AthleteProfile(age=40))
    session.commit()
    loaded = get_profile(session)
    assert loaded is not None and loaded.age == 40


def test_clearing_goal_persists(session):
    save_profile(session, AthleteProfile(goal=Goal(goal_type="10k", target_date="2026-09-01")))
    session.commit()
    save_profile(session, AthleteProfile(age=30))  # no goal
    session.commit()
    loaded = get_profile(session)
    assert loaded is not None and loaded.goal is None


def test_days_to_go():
    g = Goal(goal_type="marathon", target_date="2026-07-01")
    assert g.days_to_go(ref=date(2026, 6, 24)) == 7
    assert Goal().days_to_go() is None


def test_goal_context_in_prompt():
    profile = AthleteProfile(
        goal=Goal(goal_type="marathon", target_date="2099-01-01", target_time="03:15:00"),
        available_days=["Tuesday", "Saturday"],
    )
    ctx = prompts.goal_context(profile)
    assert "marathon" in ctx
    assert "03:15:00" in ctx
    assert "Tuesday" in ctx


def test_goal_context_empty_without_goal():
    assert prompts.goal_context(None) == ""
    assert prompts.goal_context(AthleteProfile(age=30)) == ""


def test_offline_week_mentions_goal(session):
    runs = [RunSummary(date="2026-06-20", distance_km=10, activity_type="easy", duration_min=60)]
    profile = AthleteProfile(goal=Goal(goal_type="half", target_date="2099-01-01"))
    m = compute_metrics(runs, ref=date(2026, 6, 22), profile=profile)
    result = OfflineCoach().plan_week(runs, m, [], profile)
    assert "half" in result.analysis


def test_profile_api_round_trip(client):
    payload = {
        "age": 40,
        "max_hr": 185,
        "goal": {"goal_type": "marathon", "target_date": "2027-04-11", "priority": "A"},
    }
    resp = client.put("/api/profile", json=payload)
    assert resp.status_code == 200
    assert resp.json()["age"] == 40

    resp = client.get("/api/profile")
    assert resp.status_code == 200
    body = resp.json()
    assert body["max_hr"] == 185
    assert body["goal"]["goal_type"] == "marathon"


def test_ui_profile_form_saves(client):
    resp = client.post(
        "/ui/profile",
        data={
            "age": "35",
            "sex": "M",
            "max_hr": "188",
            "goal_type": "marathon",
            "goal_target_date": "2027-04-11",
            "goal_priority": "A",
        },
    )
    assert resp.status_code == 200
    assert "Profilo aggiornato" in resp.text
    # Zones should have been derived from max HR.
    profile = client.get("/api/profile").json()
    assert profile["zones"] is not None
