"""Unit tests for onboarding status (Roadmap #4)."""

from app.services.onboarding import get_onboarding_status
from app.db.models import Activity, CoachDecisionRow, DailyCheckinRow, TrainingPlan


def test_onboarding_all_empty(session):
    """When no data exists, all steps are incomplete."""
    status = get_onboarding_status(session)
    assert status["connect_data"] is False
    assert status["set_goal"] is False
    assert status["first_checkin"] is False
    assert status["generate_plan"] is False
    assert status["first_recommendation"] is False
    assert status["complete"] is False
    assert status["next_step"] == "connect_data"


def test_onboarding_connect_data(session):
    """When a running activity exists, connect_data is complete."""
    activity = Activity(
        date="2026-07-01",
        sport="run",
        activity_type="easy",
        duration_min=30.0,
        distance_km=5.0,
    )
    session.add(activity)
    session.flush()

    status = get_onboarding_status(session)
    assert status["connect_data"] is True
    assert status["next_step"] == "set_goal"


def test_onboarding_set_goal(session):
    """When a profile with a goal exists, set_goal is complete."""
    activity = Activity(
        date="2026-07-01",
        sport="run",
        activity_type="easy",
        duration_min=30.0,
        distance_km=5.0,
    )
    session.add(activity)

    from app.services.profile import save_profile
    from app.schemas import AthleteProfile, Goal

    profile = AthleteProfile(
        goal=Goal(goal_type="marathon", target_date="2026-12-01", target_time="3:30:00")
    )
    save_profile(session, profile)
    session.flush()

    status = get_onboarding_status(session)
    assert status["connect_data"] is True
    assert status["set_goal"] is True
    assert status["next_step"] == "first_checkin"


def test_onboarding_first_checkin(session):
    """When a checkin exists, first_checkin is complete."""
    activity = Activity(
        date="2026-07-01",
        sport="run",
        activity_type="easy",
        duration_min=30.0,
        distance_km=5.0,
    )
    session.add(activity)

    from app.services.profile import save_profile
    from app.schemas import AthleteProfile, Goal

    profile = AthleteProfile(
        goal=Goal(goal_type="marathon", target_date="2026-12-01", target_time="3:30:00")
    )
    save_profile(session, profile)

    checkin = DailyCheckinRow(date="2026-07-01", sleep_h=7.5, fatigue=3)
    session.add(checkin)
    session.flush()

    status = get_onboarding_status(session)
    assert status["connect_data"] is True
    assert status["set_goal"] is True
    assert status["first_checkin"] is True
    assert status["next_step"] == "generate_plan"


def test_onboarding_generate_plan(session):
    """When an active plan exists, generate_plan is complete."""
    activity = Activity(
        date="2026-07-01",
        sport="run",
        activity_type="easy",
        duration_min=30.0,
        distance_km=5.0,
    )
    session.add(activity)

    from app.services.profile import save_profile
    from app.schemas import AthleteProfile, Goal

    profile = AthleteProfile(
        goal=Goal(goal_type="marathon", target_date="2026-12-01", target_time="3:30:00")
    )
    save_profile(session, profile)

    checkin = DailyCheckinRow(date="2026-07-01", sleep_h=7.5, fatigue=3)
    session.add(checkin)

    plan = TrainingPlan(
        goal_type="marathon",
        goal_date="2026-12-01",
        level="intermediate",
        weeks_total=12,
        start_date="2026-09-15",
        status="active",
    )
    session.add(plan)
    session.flush()

    status = get_onboarding_status(session)
    assert status["connect_data"] is True
    assert status["set_goal"] is True
    assert status["first_checkin"] is True
    assert status["generate_plan"] is True
    assert status["next_step"] == "first_recommendation"


def test_onboarding_first_recommendation(session):
    """When a coach decision exists, first_recommendation is complete."""
    activity = Activity(
        date="2026-07-01",
        sport="run",
        activity_type="easy",
        duration_min=30.0,
        distance_km=5.0,
    )
    session.add(activity)

    from app.services.profile import save_profile
    from app.schemas import AthleteProfile, Goal

    profile = AthleteProfile(
        goal=Goal(goal_type="marathon", target_date="2026-12-01", target_time="3:30:00")
    )
    save_profile(session, profile)

    checkin = DailyCheckinRow(date="2026-07-01", sleep_h=7.5, fatigue=3)
    session.add(checkin)

    plan = TrainingPlan(
        goal_type="marathon",
        goal_date="2026-12-01",
        level="intermediate",
        weeks_total=12,
        start_date="2026-09-15",
        status="active",
    )
    session.add(plan)

    decision = CoachDecisionRow(
        date="2026-07-01",
        decision="easy",
        headline="Easy run",
        prescription="5km easy",
        rationale="Recovery",
    )
    session.add(decision)
    session.flush()

    status = get_onboarding_status(session)
    assert status["connect_data"] is True
    assert status["set_goal"] is True
    assert status["first_checkin"] is True
    assert status["generate_plan"] is True
    assert status["first_recommendation"] is True
    assert status["complete"] is True
    assert status["next_step"] is None


def test_onboarding_complete_flow(session):
    """When all steps are done, onboarding is complete."""
    activity = Activity(
        date="2026-07-01",
        sport="run",
        activity_type="easy",
        duration_min=30.0,
        distance_km=5.0,
    )
    session.add(activity)

    from app.services.profile import save_profile
    from app.schemas import AthleteProfile, Goal

    profile = AthleteProfile(
        goal=Goal(goal_type="marathon", target_date="2026-12-01", target_time="3:30:00")
    )
    save_profile(session, profile)

    checkin = DailyCheckinRow(date="2026-07-01", sleep_h=7.5, fatigue=3)
    session.add(checkin)

    plan = TrainingPlan(
        goal_type="marathon",
        goal_date="2026-12-01",
        level="intermediate",
        weeks_total=12,
        start_date="2026-09-15",
        status="active",
    )
    session.add(plan)

    decision = CoachDecisionRow(
        date="2026-07-01",
        decision="easy",
        headline="Easy run",
        prescription="5km easy",
        rationale="Recovery",
    )
    session.add(decision)
    session.flush()

    status = get_onboarding_status(session)
    assert status["complete"] is True
    assert status["next_step"] is None
