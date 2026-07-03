"""Golden structural tests for the LLM plan generation (Roadmap A9 / Passo 9).

These hit the real Anthropic API, so they are marked ``eval_llm`` and skipped
unless ``ANTHROPIC_API_KEY`` is set — they belong to a nightly job, not the PR
CI. When they run, they assert *structural* properties of the generated plan
(not exact wording): weeks are present, every week has sessions, and the
multi-week validator accepts the payload.

Follow-up (documented, not yet done): expand to the 20 recorded pre-plan
conversations the brief calls for, asserting §CTX validity and the <=2
confirmation budget on each.
"""

from __future__ import annotations

import os
from datetime import date, timedelta

import pytest

pytestmark = pytest.mark.eval_llm

_HAS_KEY = bool(os.environ.get("ANTHROPIC_API_KEY"))
skip_no_key = pytest.mark.skipif(not _HAS_KEY, reason="ANTHROPIC_API_KEY not set")


@skip_no_key
def test_llm_plan_multiweek_is_structurally_valid():
    """A generated multi-week plan must pass the structural validator."""
    from app.coaching.coach import AICoach, _validate_plan_structure
    from app.schemas import AthleteProfile, Goal, PlanGenerateRequest

    goal_date = (date.today() + timedelta(weeks=12)).isoformat()
    request = PlanGenerateRequest(
        goal_type="10k", goal_date=goal_date, level="intermediate", days_per_week=4
    )
    profile = AthleteProfile(
        level="intermediate",
        goal=Goal(goal_type="10k", target_date=goal_date, target_time="45:00"),
    )

    plan = AICoach().plan_multiweek(request, profile, None)

    _validate_plan_structure(plan)  # raises on a malformed plan
    assert plan["weeks"], "plan has no weeks"
    for week in plan["weeks"]:
        assert week["sessions"], f"week {week.get('week_number')} has no sessions"
