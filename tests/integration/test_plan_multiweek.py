"""Integration tests for the multi-week training plan feature."""

from __future__ import annotations

_GOAL_DATE = "2027-04-18"  # far enough in the future for a full plan
_GENERATE_PAYLOAD = {
    "goal_type": "marathon",
    "goal_date": _GOAL_DATE,
    "goal_time": "3:45:00",
    "level": "intermediate",
    "days_per_week": 4,
    "long_run_day": 6,
}


def test_generate_plan_creates_active_plan(client):
    resp = client.post("/api/plan/generate", json=_GENERATE_PAYLOAD)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["goal_type"] == "marathon"
    assert body["goal_date"] == _GOAL_DATE
    assert body["status"] == "active"
    assert body["weeks_total"] > 0
    assert len(body["weeks"]) == body["weeks_total"]


def test_generate_plan_has_correct_week_structure(client):
    resp = client.post("/api/plan/generate", json=_GENERATE_PAYLOAD)
    assert resp.status_code == 201
    body = resp.json()
    for week in body["weeks"]:
        assert "week_number" in week
        assert "phase" in week
        assert "target_km" in week
        assert "sessions" in week
        # Each week must have exactly 7 sessions
        assert len(week["sessions"]) == 7, (
            f"Week {week['week_number']} has {len(week['sessions'])} sessions, expected 7"
        )
        days = [s["day_of_week"] for s in week["sessions"]]
        assert sorted(days) == list(range(7)), (
            f"Week {week['week_number']} days: {days}"
        )


def test_get_current_plan_returns_active(client):
    client.post("/api/plan/generate", json=_GENERATE_PAYLOAD)
    resp = client.get("/api/plan/current")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "active"
    assert body["current_week_number"] >= 1
    assert "current_week" in body
    assert "weeks_remaining" in body
    assert "overall_completion_pct" in body


def test_get_current_plan_404_when_none(client):
    resp = client.get("/api/plan/current")
    assert resp.status_code == 404


def test_get_plan_by_id(client):
    gen = client.post("/api/plan/generate", json=_GENERATE_PAYLOAD)
    plan_id = gen.json()["id"]
    resp = client.get(f"/api/plan/{plan_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == plan_id


def test_toggle_session_complete(client):
    gen = client.post("/api/plan/generate", json=_GENERATE_PAYLOAD)
    body = gen.json()
    # Find a non-rest session in the first week
    first_week = body["weeks"][0]
    non_rest = [s for s in first_week["sessions"] if s["session_type"] != "rest"]
    assert non_rest, "No non-rest sessions in first week"
    session_id = non_rest[0]["id"]

    # Toggle to complete
    resp = client.patch(f"/api/plan/sessions/{session_id}/complete")
    assert resp.status_code == 200
    assert resp.json()["completed"] is True
    assert resp.json()["completed_at"] is not None

    # Toggle back to incomplete
    resp2 = client.patch(f"/api/plan/sessions/{session_id}/complete")
    assert resp2.status_code == 200
    assert resp2.json()["completed"] is False
    assert resp2.json()["completed_at"] is None


def test_completion_pct_computed_correctly(client):
    gen = client.post("/api/plan/generate", json=_GENERATE_PAYLOAD)
    body = gen.json()
    # Initially all zero
    assert body["overall_completion_pct"] == 0.0
    first_week = body["weeks"][0]
    assert first_week["completion_pct"] == 0.0

    # Complete one non-rest session
    non_rest = [s for s in first_week["sessions"] if s["session_type"] != "rest"]
    session_id = non_rest[0]["id"]
    client.patch(f"/api/plan/sessions/{session_id}/complete")

    # Re-fetch
    updated = client.get("/api/plan/current").json()
    assert updated["overall_completion_pct"] > 0.0
    updated_week = next(
        w for w in updated["weeks"] if w["week_number"] == first_week["week_number"]
    )
    assert updated_week["completion_pct"] > 0.0


def test_delete_plan_archives_it(client):
    gen = client.post("/api/plan/generate", json=_GENERATE_PAYLOAD)
    plan_id = gen.json()["id"]

    # Delete
    resp = client.delete(f"/api/plan/{plan_id}")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    # Current plan should now be 404
    resp2 = client.get("/api/plan/current")
    assert resp2.status_code == 404

    # But the plan still exists by ID (archived)
    resp3 = client.get(f"/api/plan/{plan_id}")
    assert resp3.status_code == 200
    assert resp3.json()["status"] == "archived"


def test_generate_new_plan_archives_previous(client):
    gen1 = client.post("/api/plan/generate", json=_GENERATE_PAYLOAD)
    plan1_id = gen1.json()["id"]

    # Generate a second plan
    payload2 = dict(_GENERATE_PAYLOAD, goal_type="half", goal_date="2027-01-15")
    gen2 = client.post("/api/plan/generate", json=payload2)
    assert gen2.status_code == 201
    plan2_id = gen2.json()["id"]

    # First plan should be archived
    old = client.get(f"/api/plan/{plan1_id}").json()
    assert old["status"] == "archived"

    # Second plan should be active
    current = client.get("/api/plan/current").json()
    assert current["id"] == plan2_id
    assert current["goal_type"] == "half"


def test_plan_week_count_for_marathon(client):
    gen = client.post("/api/plan/generate", json=_GENERATE_PAYLOAD)
    body = gen.json()
    # For a race ~40 weeks away, expect a plan of reasonable length
    assert body["weeks_total"] >= 4
    assert body["weeks_total"] <= 24


def test_offline_coach_generates_valid_plan():
    """Unit test: OfflineCoach.plan_multiweek produces a valid structure."""
    from app.coaching.coach import OfflineCoach
    from app.schemas import PlanGenerateRequest

    coach = OfflineCoach()
    req = PlanGenerateRequest(
        goal_type="marathon",
        goal_date="2027-04-18",
        goal_time="3:45:00",
        level="intermediate",
        days_per_week=4,
        long_run_day=6,
    )
    result = coach.plan_multiweek(req, profile=None, metrics=None)

    assert "weeks" in result
    assert "start_date" in result
    assert len(result["weeks"]) > 0

    for week in result["weeks"]:
        assert "week_number" in week
        assert "phase" in week
        assert "sessions" in week
        # Every week has exactly 7 sessions
        assert len(week["sessions"]) == 7
        days = sorted(s["day_of_week"] for s in week["sessions"])
        assert days == list(range(7))
        # Each session has required fields
        for s in week["sessions"]:
            assert "session_type" in s
            assert "title" in s
            assert "day_of_week" in s


def test_mobile_overview_includes_active_plan(client):
    """The mobile overview endpoint should include active_plan when a plan exists."""
    # Before generation: active_plan is null
    resp = client.get("/api/mobile/overview")
    assert resp.status_code == 200
    assert resp.json().get("active_plan") is None

    # Generate a plan
    client.post("/api/plan/generate", json=_GENERATE_PAYLOAD)

    # Now active_plan should be present
    resp2 = client.get("/api/mobile/overview")
    assert resp2.status_code == 200
    body = resp2.json()
    assert body["active_plan"] is not None
    assert body["active_plan"]["status"] == "active"
    assert body["active_plan"]["goal_type"] == "marathon"


def test_session_complete_toggle_404_on_bad_id(client):
    resp = client.patch("/api/plan/sessions/99999/complete")
    assert resp.status_code == 404


def test_delete_plan_404_on_bad_id(client):
    resp = client.delete("/api/plan/99999")
    assert resp.status_code == 404


def test_plan_sessions_expose_structured_segments(client):
    """Fase E: quality sessions carry Workout-Builder segments in the API."""
    resp = client.post("/api/plan/generate", json=_GENERATE_PAYLOAD)
    assert resp.status_code == 201, resp.text
    body = resp.json()

    structured = 0
    for week in body["weeks"]:
        for s in week["sessions"]:
            if s["session_type"] in ("tempo", "intervals"):
                seg_types = [seg["segment_type"] for seg in s["segments"]]
                assert "warmup" in seg_types and "cooldown" in seg_types
                structured += 1
            elif s["session_type"] == "rest":
                assert s["segments"] == []
    assert structured > 0, "a marathon block must contain quality sessions"


def test_plan_weeks_have_rationale_and_long_runs_have_fueling(client):
    """Fase F: every week explains itself; long runs/races carry fueling."""
    resp = client.post("/api/plan/generate", json=_GENERATE_PAYLOAD)
    assert resp.status_code == 201, resp.text
    body = resp.json()

    assert all(w["rationale"] for w in body["weeks"])  # explainability everywhere

    fuelled = 0
    for week in body["weeks"]:
        for s in week["sessions"]:
            if s["session_type"] == "easy":
                assert s["fueling"] is None
            if s["fueling"]:
                assert "carboidrati" in s["fueling"]
                fuelled += 1
    assert fuelled > 0, "long runs in a marathon block should carry fueling"


def test_generate_plan_honors_chat_agreed_week_structure(client):
    """The app plan must match the week agreed in the pre-plan chat.

    In tests the coach is the offline fallback, which ignores the runner
    context entirely — exactly the worst case. The deterministic enforcement
    pass must still reshape the plan to the agreed structure.
    """
    import json as _json

    runner_context = _json.dumps(
        {
            "weekly_km": 45,
            "threshold_pace": "4:30/km",
            "week_structure": [
                {"day": "mar", "type": "intervals", "note": "Ripetute col gruppo"},
                {"day": "gio", "type": "tempo", "pace": "4:30/km"},
                {"day": "dom", "type": "long"},
                {"day": "lun", "type": "rest"},
            ],
        }
    )
    payload = dict(_GENERATE_PAYLOAD, runner_context=runner_context)
    resp = client.post("/api/plan/generate", json=payload)
    assert resp.status_code == 201, resp.text
    body = resp.json()

    checked = 0
    for week in body["weeks"]:
        by_day = {s["day_of_week"]: s for s in week["sessions"]}
        # The goal-race week keeps its own structure.
        if any(s["session_type"] == "race" for s in week["sessions"]):
            continue
        assert by_day[1]["session_type"] == "intervals", f"week {week['week_number']}"
        assert by_day[3]["session_type"] == "tempo", f"week {week['week_number']}"
        assert by_day[3]["target_pace"] == "4:30/km"
        assert by_day[6]["session_type"] == "long", f"week {week['week_number']}"
        assert by_day[0]["session_type"] == "rest", f"week {week['week_number']}"
        checked += 1
    assert checked > 0
