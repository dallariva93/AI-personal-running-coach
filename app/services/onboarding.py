"""Onboarding checklist status (Roadmap #4).

Determines which onboarding steps the athlete has completed so the app can
guide them from zero to their first coaching recommendation. Each step is
a simple boolean check against the database state.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Activity, CoachDecisionRow, DailyCheckinRow, TrainingPlan
from app.services.profile import get_profile

STEPS = (
    "connect_data",
    "set_goal",
    "first_checkin",
    "generate_plan",
    "first_recommendation",
)


def get_onboarding_status(session: Session) -> dict:
    """Return the completion state of each onboarding step.

    The response is a dict with boolean fields per step, a ``complete`` flag
    (all steps done), and a ``next_step`` string indicating the first pending
    step (or None when all are done).
    """
    has_activities = session.scalar(
        select(Activity.id).where(Activity.sport == "run").limit(1)
    ) is not None

    profile = get_profile(session)
    has_goal = bool(
        profile
        and profile.goal
        and profile.goal.goal_type
        and profile.goal.goal_type != "general"
        and profile.goal.target_date
    )

    has_checkin = session.scalar(
        select(DailyCheckinRow.id).limit(1)
    ) is not None

    has_plan = session.scalar(
        select(TrainingPlan.id).where(TrainingPlan.status == "active").limit(1)
    ) is not None

    has_decision = session.scalar(
        select(CoachDecisionRow.id).limit(1)
    ) is not None

    status = {
        "connect_data": has_activities,
        "set_goal": has_goal,
        "first_checkin": has_checkin,
        "generate_plan": has_plan,
        "first_recommendation": has_decision,
    }
    status["complete"] = all(status.values())

    next_step = next(
        (step for step in STEPS if not status[step]),
        None,
    )
    status["next_step"] = next_step
    return status
