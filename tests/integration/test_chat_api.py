"""Conversational coach API (Feature 23 / unified in A8).

Regression: ``POST /api/chat/send`` must work when the athlete has activities —
the original route read fields that don't exist on RunSummary and 500'd on
every send once any run was stored.
"""

from __future__ import annotations

from datetime import date

from app.db.models import Activity


def test_chat_send_with_activities_returns_200(client, session):
    session.add(Activity(date=date.today().isoformat(), sport="run",
                         activity_type="easy", distance_km=8.0, duration_min=48.0))
    session.commit()

    resp = client.post("/api/chat/send", json={"message": "Quanti km ho fatto?"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["reply"]  # offline coach reply, no key needed
    assert body["session_id"] > 0


def test_chat_send_without_activities_returns_200(client):
    resp = client.post("/api/chat/send", json={"message": "Ciao coach"})
    assert resp.status_code == 200
    assert resp.json()["reply"]
