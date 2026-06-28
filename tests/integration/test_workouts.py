"""Integration tests for the workout builder feature."""

from __future__ import annotations

from app.schemas import WorkoutSegmentIn, WorkoutSuggestRequest, WorkoutTemplateIn

_SIMPLE_PAYLOAD = {
    "name": "Test Ripetute",
    "description": "Sessione test",
    "type": "interval",
    "segments": [
        {
            "position": 0,
            "segment_type": "warmup",
            "repetitions": 1,
            "work_duration_sec": 600.0,
            "work_pace": "6:00/km",
            "notes": "Riscaldamento 10 min",
        },
        {
            "position": 1,
            "segment_type": "interval_block",
            "repetitions": 5,
            "work_distance_km": 1.0,
            "work_pace": "4:15/km",
            "rest_duration_sec": 90.0,
            "rest_type": "jog",
            "notes": "5×1 km",
        },
        {
            "position": 2,
            "segment_type": "cooldown",
            "repetitions": 1,
            "work_duration_sec": 600.0,
            "work_pace": "6:00/km",
            "notes": "Defaticamento 10 min",
        },
    ],
}


def test_create_workout_returns_201(client):
    resp = client.post("/api/workouts", json=_SIMPLE_PAYLOAD)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "Test Ripetute"
    assert body["type"] == "interval"
    assert len(body["segments"]) == 3
    assert body["id"] > 0


def test_create_workout_segments_have_ids(client):
    resp = client.post("/api/workouts", json=_SIMPLE_PAYLOAD)
    assert resp.status_code == 201
    for seg in resp.json()["segments"]:
        assert "id" in seg
        assert seg["id"] > 0


def test_create_workout_segments_ordered_by_position(client):
    resp = client.post("/api/workouts", json=_SIMPLE_PAYLOAD)
    assert resp.status_code == 201
    positions = [s["position"] for s in resp.json()["segments"]]
    assert positions == sorted(positions)


def test_create_workout_computes_estimated_distance(client):
    resp = client.post("/api/workouts", json=_SIMPLE_PAYLOAD)
    assert resp.status_code == 201
    body = resp.json()
    # Warmup: 600s / (6 min/km) = 1.667 km
    # Intervals: 5 × 1.0 km = 5.0 km  + rest has no distance
    # Cooldown: 600s / (6 min/km) = 1.667 km
    # Total ~ 8.33 km
    assert body["estimated_distance_km"] is not None
    assert body["estimated_distance_km"] > 7.0
    assert body["estimated_distance_km"] < 10.0


def test_create_workout_computes_estimated_duration(client):
    resp = client.post("/api/workouts", json=_SIMPLE_PAYLOAD)
    assert resp.status_code == 201
    body = resp.json()
    # Warmup: 10 min
    # Intervals: 5 × (1 km @ 4:15 = 4.25 min) + 5 × 90s rest = 21.25 + 7.5 = 28.75 min
    # Cooldown: 10 min
    # Total ~ 48.75 min
    assert body["estimated_duration_min"] is not None
    assert body["estimated_duration_min"] > 40.0
    assert body["estimated_duration_min"] < 60.0


def test_list_workouts_empty(client):
    resp = client.get("/api/workouts")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_workouts_after_creation(client):
    client.post("/api/workouts", json=_SIMPLE_PAYLOAD)
    resp = client.get("/api/workouts")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["name"] == "Test Ripetute"


def test_list_workouts_newest_first(client):
    payload1 = dict(_SIMPLE_PAYLOAD, name="Primo")
    payload2 = dict(_SIMPLE_PAYLOAD, name="Secondo")
    client.post("/api/workouts", json=payload1)
    client.post("/api/workouts", json=payload2)
    resp = client.get("/api/workouts")
    assert resp.status_code == 200
    names = [w["name"] for w in resp.json()]
    assert names[0] == "Secondo"


def test_get_workout_by_id(client):
    created = client.post("/api/workouts", json=_SIMPLE_PAYLOAD).json()
    wid = created["id"]
    resp = client.get(f"/api/workouts/{wid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == wid
    assert len(body["segments"]) == 3


def test_get_workout_404_unknown(client):
    resp = client.get("/api/workouts/99999")
    assert resp.status_code == 404


def test_delete_workout(client):
    created = client.post("/api/workouts", json=_SIMPLE_PAYLOAD).json()
    wid = created["id"]
    resp = client.delete(f"/api/workouts/{wid}")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    assert client.get(f"/api/workouts/{wid}").status_code == 404


def test_delete_workout_404_unknown(client):
    resp = client.delete("/api/workouts/99999")
    assert resp.status_code == 404


def test_suggest_workout_uses_offline_coach(client):
    """POST /api/workouts/suggest returns a valid template using OfflineCoach."""
    payload = {"session_type": "intervals"}
    resp = client.post("/api/workouts/suggest", json=payload)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["id"] > 0
    assert body["name"]
    assert len(body["segments"]) > 0


def test_suggest_workout_tempo(client):
    resp = client.post("/api/workouts/suggest", json={"session_type": "tempo"})
    assert resp.status_code == 201
    body = resp.json()
    seg_types = [s["segment_type"] for s in body["segments"]]
    assert "threshold" in seg_types


def test_suggest_workout_strides(client):
    resp = client.post("/api/workouts/suggest", json={"session_type": "strides"})
    assert resp.status_code == 201
    body = resp.json()
    seg_types = [s["segment_type"] for s in body["segments"]]
    assert "strides" in seg_types


def test_suggest_workout_easy(client):
    resp = client.post("/api/workouts/suggest", json={"session_type": "easy"})
    assert resp.status_code == 201
    body = resp.json()
    assert len(body["segments"]) >= 1


def test_suggest_workout_saved_in_library(client):
    client.post("/api/workouts/suggest", json={"session_type": "intervals"})
    resp = client.get("/api/workouts")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


def test_estimated_distance_easy_segment():
    """Unit test: _compute_estimates works for a duration-only easy segment."""
    from app.services.workout_service import _compute_estimates

    segs = [
        WorkoutSegmentIn(
            position=0,
            segment_type="easy",
            repetitions=1,
            work_duration_sec=1800.0,  # 30 min
            work_pace="6:00/km",       # 6 min/km → 5 km
        )
    ]
    dist, dur = _compute_estimates(segs)
    assert dist is not None
    assert abs(dist - 5.0) < 0.1
    assert dur is not None
    assert abs(dur - 30.0) < 0.5


def test_estimated_distance_interval_block():
    """Unit test: repetitions are correctly multiplied in estimate."""
    from app.services.workout_service import _compute_estimates

    segs = [
        WorkoutSegmentIn(
            position=0,
            segment_type="interval_block",
            repetitions=4,
            work_distance_km=1.0,
            work_pace="4:00/km",
            rest_duration_sec=120.0,
            rest_type="jog",
        )
    ]
    dist, dur = _compute_estimates(segs)
    assert dist is not None
    assert abs(dist - 4.0) < 0.1  # 4 × 1 km
    # duration: 4 × (1 km @ 4 min/km + 2 min rest) = 4 × 6 = 24 min
    assert dur is not None
    assert abs(dur - 24.0) < 0.5


def test_offline_coach_suggest_workout_intervals():
    """Unit test: OfflineCoach.suggest_workout returns valid intervals template."""
    from app.coaching.coach import OfflineCoach

    coach = OfflineCoach()
    req = WorkoutSuggestRequest(session_type="intervals")
    result = coach.suggest_workout(req, metrics=None, profile=None)

    assert isinstance(result, WorkoutTemplateIn)
    assert result.type == "interval"
    assert len(result.segments) == 3
    positions = [s.position for s in result.segments]
    assert positions == sorted(positions)
    interval = next(s for s in result.segments if s.segment_type == "interval_block")
    assert interval.repetitions == 5
    assert interval.work_distance_km == 1.0


def test_offline_coach_suggest_workout_tempo():
    from app.coaching.coach import OfflineCoach

    coach = OfflineCoach()
    req = WorkoutSuggestRequest(session_type="tempo")
    result = coach.suggest_workout(req, metrics=None, profile=None)

    assert result.type == "threshold"
    seg_types = [s.segment_type for s in result.segments]
    assert "threshold" in seg_types


def test_mobile_overview_includes_saved_workout_count(client):
    resp = client.get("/api/mobile/overview")
    assert resp.status_code == 200
    body = resp.json()
    assert "saved_workout_count" in body
    assert body["saved_workout_count"] == 0

    client.post("/api/workouts", json=_SIMPLE_PAYLOAD)
    resp2 = client.get("/api/mobile/overview")
    assert resp2.json()["saved_workout_count"] == 1
