"""Integration: the MCP server (Claude custom connector).

Two layers are covered:

* **Exposure** — where the server mounts and who may reach it. These are the
  security properties of Fase 3, so they are asserted rather than assumed.
* **Tools** — the payloads Claude actually receives, driven against a real
  database through ``FastMCP.call_tool``.
"""

from __future__ import annotations

import asyncio
import importlib
from datetime import date, timedelta
from typing import Any

import pytest

from app.schemas import AthleteProfile, Goal, RunSummary
from app.services import save_profile
from app.services.ingest import upsert_activity

TOKEN = "test-secret-path-token"


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _call(mcp, name: str, **kwargs: Any) -> Any:
    """Invoke a tool and return its structured payload (the dict Claude sees)."""
    result = asyncio.run(mcp.call_tool(name, kwargs))
    # call_tool returns (content_blocks, structured_output).
    return result[1] if isinstance(result, tuple) else result


def _server(monkeypatch, **env: str):
    """Build a fresh MCP server with the given environment."""
    from app.config import get_settings

    for key, value in env.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    from app.mcp_server import build_mcp_server

    return build_mcp_server()


def _seed_runs(session, days_back: list[int], km: float = 10.0) -> None:
    """Runs at fixed offsets from today, so the tests never expire."""
    today = date.today()
    for offset in days_back:
        upsert_activity(
            session,
            RunSummary(
                date=(today - timedelta(days=offset)).isoformat(),
                activity_type="easy",
                distance_km=km,
                duration_min=km * 6,
                avg_pace="6:00/km",
                avg_hr=140,
            ),
        )
    session.flush()


@pytest.fixture
def mcp(db_env, monkeypatch):
    """An MCP server bound to the temporary test database."""
    return _server(monkeypatch, MCP_DEV_UNPROTECTED="true")


@pytest.fixture
def mcp_client(db_env, monkeypatch):
    """A TestClient whose app has the MCP server mounted at the secret path.

    ``app.main`` decides the mount at import time, so it must be reloaded
    after the environment changes.
    """
    from fastapi.testclient import TestClient

    from app.config import get_settings

    monkeypatch.setenv("MCP_PATH_TOKEN", TOKEN)
    get_settings.cache_clear()
    import app.main as main_module

    importlib.reload(main_module)
    try:
        with TestClient(main_module.app) as c:
            yield c
    finally:
        # Restore the unmounted app for every other test in the session.
        monkeypatch.delenv("MCP_PATH_TOKEN", raising=False)
        get_settings.cache_clear()
        importlib.reload(main_module)


def _rpc(client, path: str, method: str, params: dict | None = None, _id: int = 1):
    body: dict[str, Any] = {"jsonrpc": "2.0", "id": _id, "method": method}
    if params is not None:
        body["params"] = params
    return client.post(
        path,
        json=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
    )


# --------------------------------------------------------------------------
# exposure / security
# --------------------------------------------------------------------------
def test_mcp_notConfigured_isNotMounted(db_env, monkeypatch):
    """Fail closed: no token and no dev opt-in means no endpoint at all."""
    from app.config import get_settings

    monkeypatch.delenv("MCP_PATH_TOKEN", raising=False)
    monkeypatch.delenv("MCP_DEV_UNPROTECTED", raising=False)
    get_settings.cache_clear()
    settings = get_settings()

    assert settings.mcp_mount_path is None
    assert settings.mcp_enabled is False


def test_mcp_devFlagInProduction_isRefused(db_env, monkeypatch):
    """The unprotected dev mount must never activate in production."""
    from app.config import get_settings

    monkeypatch.setenv("MCP_DEV_UNPROTECTED", "true")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("MCP_PATH_TOKEN", raising=False)
    get_settings.cache_clear()

    assert get_settings().mcp_mount_path is None


def test_mcp_tokenConfigured_mountsAtSecretPath(db_env, monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("MCP_PATH_TOKEN", TOKEN)
    get_settings.cache_clear()

    assert get_settings().mcp_mount_path == f"/mcp-{TOKEN}"


def test_mcp_secretPath_answersHandshake(mcp_client):
    r = _rpc(
        mcp_client,
        f"/mcp-{TOKEN}/",
        "initialize",
        {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1"},
        },
    )
    assert r.status_code == 200


def test_mcp_wrongPath_is404(mcp_client):
    """A guessed-but-wrong URL is indistinguishable from a missing route."""
    assert _rpc(mcp_client, "/mcp/", "initialize", {}).status_code == 404
    assert _rpc(mcp_client, "/mcp-wrong-token/", "initialize", {}).status_code == 404


def test_mcp_reachableWithoutBearerToken_whileApiStaysProtected(db_env, monkeypatch):
    """The secret path is the credential — but only for the MCP mount.

    Turning the connector on must not punch a hole in the REST API.
    """
    from fastapi.testclient import TestClient

    from app.config import get_settings

    monkeypatch.setenv("MCP_PATH_TOKEN", TOKEN)
    monkeypatch.setenv("API_TOKEN", "super-secret-api-token")
    get_settings.cache_clear()
    import app.main as main_module

    importlib.reload(main_module)
    try:
        with TestClient(main_module.app) as c:
            # No Authorization header anywhere in this block.
            mcp_resp = _rpc(
                c,
                f"/mcp-{TOKEN}/",
                "initialize",
                {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "t", "version": "1"},
                },
            )
            assert mcp_resp.status_code == 200
            assert c.get("/api/metrics").status_code == 401
    finally:
        monkeypatch.delenv("MCP_PATH_TOKEN", raising=False)
        monkeypatch.delenv("API_TOKEN", raising=False)
        get_settings.cache_clear()
        importlib.reload(main_module)


def test_mcp_allowedHosts_configuredHostsAreParsed(db_env, monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("MCP_ALLOWED_HOSTS", "ai-running-coach.fly.dev, other.example ")
    get_settings.cache_clear()

    assert get_settings().mcp_transport_hosts == [
        "ai-running-coach.fly.dev",
        "other.example",
    ]


# --------------------------------------------------------------------------
# tool surface
# --------------------------------------------------------------------------
def test_mcp_exposesReadOnlyToolsAndCoachPrompt(mcp):
    names = {t.name for t in asyncio.run(mcp.list_tools())}

    assert names == {
        "get_athlete_overview",
        "get_training_metrics",
        "list_activities",
        "get_activity_detail",
        "get_current_training_plan",
        "get_plan_week",
        "get_race_prediction",
        "compare_periods",
    }
    # Nothing that writes: a leaked URL must not be able to change state.
    assert not any(
        verb in n for n in names for verb in ("create", "update", "delete", "save", "log")
    )
    assert [p.name for p in asyncio.run(mcp.list_prompts())] == ["running_coach"]


def test_getAthleteOverview_emptyDatabase_stillAnswers(mcp):
    """A cold install must not error — Claude needs to hear "no data yet"."""
    out = _call(mcp, "get_athlete_overview")

    assert out["athlete"] is None
    assert out["runs_in_history"] == 0
    assert out["summary"]


def test_getAthleteOverview_withHistory_reportsProfileGoalAndVolume(mcp, session):
    save_profile(
        session,
        AthleteProfile(
            age=32,
            level="advanced",
            goal=Goal(
                goal_type="marathon",
                target_date=(date.today() + timedelta(days=90)).isoformat(),
                target_time="03:30:00",
            ),
        ),
    )
    _seed_runs(session, days_back=[1, 3, 5, 8, 12], km=12.0)
    session.commit()

    out = _call(mcp, "get_athlete_overview")

    assert out["athlete"]["level"] == "advanced"
    assert out["athlete"]["age"] == 32
    assert out["goal"]["type"] == "marathon"
    assert out["goal"]["days_to_go"] == 90
    assert out["runs_in_history"] == 5
    assert out["volume"]["weekly_km"] > 0


def test_getTrainingMetrics_returnsCoachDimensions(mcp, session):
    _seed_runs(session, days_back=[1, 2, 4, 6, 9, 14, 20], km=10.0)
    session.commit()

    out = _call(mcp, "get_training_metrics")

    assert out["as_of"] == date.today().isoformat()
    assert out["runs_counted"] == 7
    for block in ("volume", "form", "risk", "intensity", "readiness", "phase"):
        assert block in out
    assert out["volume"]["weekly_km"] > 0


def test_getTrainingMetrics_refDate_reconstructsPastState(mcp, session):
    # Runs only in the distant past: "today" sees a detrained athlete, while a
    # ref date inside the block must still see the volume that was there.
    _seed_runs(session, days_back=[60, 62, 64, 66], km=15.0)
    session.commit()

    ref = (date.today() - timedelta(days=60)).isoformat()
    past = _call(mcp, "get_training_metrics", ref_date=ref)
    now = _call(mcp, "get_training_metrics")

    assert past["volume"]["weekly_km"] > 0
    assert now["volume"]["weekly_km"] == 0.0


def test_getTrainingMetrics_badDate_raisesActionableError(mcp):
    with pytest.raises(Exception, match="YYYY-MM-DD"):
        _call(mcp, "get_training_metrics", ref_date="25-07-2026")


def test_listActivities_defaultsToMostRecent(mcp, session):
    _seed_runs(session, days_back=[1, 2, 3, 10, 20], km=8.0)
    session.commit()

    out = _call(mcp, "list_activities")

    assert out["returned"] == 5
    assert out["totals"]["runs"] == 5
    assert out["totals"]["total_km"] == pytest.approx(40.0)
    dates = [a["date"] for a in out["activities"]]
    assert dates == sorted(dates, reverse=True)  # newest first


def test_listActivities_dateRange_filtersAndAggregates(mcp, session):
    today = date.today()
    _seed_runs(session, days_back=[1, 2, 30, 40], km=10.0)
    session.commit()

    out = _call(
        mcp,
        "list_activities",
        from_date=(today - timedelta(days=7)).isoformat(),
        to_date=today.isoformat(),
    )

    assert out["returned"] == 2
    assert out["matching_total"] == 2
    assert out["totals"]["total_km"] == pytest.approx(20.0)


def test_listActivities_limitIsCappedAndReportsTotal(mcp, session):
    _seed_runs(session, days_back=list(range(1, 11)), km=5.0)
    session.commit()

    out = _call(mcp, "list_activities", limit=3)

    assert out["returned"] == 3
    assert out["matching_total"] == 10  # the caller can tell it was truncated


def test_getActivityDetail_returnsSplitsAndContext(mcp, session):
    upsert_activity(
        session,
        RunSummary(
            date=date.today().isoformat(),
            activity_type="tempo",
            distance_km=10.0,
            duration_min=45.0,
            avg_pace="4:30/km",
            avg_hr=165,
            max_hr=178,
            splits_km=["4:35", "4:30", "4:28"],
            temperature_c=21.5,
        ),
    )
    session.commit()
    listed = _call(mcp, "list_activities")
    from app.db.models import Activity

    activity_id = session.query(Activity).one().id
    assert listed["returned"] == 1

    out = _call(mcp, "get_activity_detail", activity_id=activity_id)

    assert out["type"] == "tempo"
    assert out["splits_km"] == ["4:35", "4:30", "4:28"]
    assert out["max_hr"] == 178
    assert out["temperature_c"] == 21.5


def test_getActivityDetail_unknownId_raises(mcp):
    with pytest.raises(Exception, match="non trovata"):
        _call(mcp, "get_activity_detail", activity_id=999999)


def test_comparePeriods_reportsBothWindowsAndDelta(mcp, session):
    today = date.today()
    _seed_runs(session, days_back=[1, 3, 5], km=10.0)      # 30 km, recent
    _seed_runs(session, days_back=[40, 42], km=10.0)        # 20 km, earlier
    session.commit()

    out = _call(
        mcp,
        "compare_periods",
        period_a_from=(today - timedelta(days=7)).isoformat(),
        period_a_to=today.isoformat(),
        period_b_from=(today - timedelta(days=45)).isoformat(),
        period_b_to=(today - timedelta(days=35)).isoformat(),
    )

    assert out["period_a"]["total_km"] == pytest.approx(30.0)
    assert out["period_b"]["total_km"] == pytest.approx(20.0)
    assert out["delta"]["total_km"] == pytest.approx(10.0)
    assert out["delta"]["total_km_pct"] == pytest.approx(50.0)
    assert out["delta"]["runs"] == 1


def test_comparePeriods_emptyWindow_doesNotDivideByZero(mcp, session):
    today = date.today()
    _seed_runs(session, days_back=[1, 2], km=10.0)
    session.commit()

    out = _call(
        mcp,
        "compare_periods",
        period_a_from=(today - timedelta(days=7)).isoformat(),
        period_a_to=today.isoformat(),
        period_b_from=(today - timedelta(days=400)).isoformat(),
        period_b_to=(today - timedelta(days=390)).isoformat(),
    )

    assert out["period_b"]["runs"] == 0
    assert out["delta"]["total_km_pct"] is None


def test_getCurrentTrainingPlan_noPlan_returnsHintNotError(mcp):
    out = _call(mcp, "get_current_training_plan")

    assert out["active_plan"] is None
    assert "hint" in out


def test_getPlanWeek_noPlan_raises(mcp):
    with pytest.raises(Exception, match="Nessun piano attivo"):
        _call(mcp, "get_plan_week", week_number=1)


def test_getRacePrediction_withoutGoal_explainsWhy(mcp):
    out = _call(mcp, "get_race_prediction")

    assert out["prediction"] is None
    assert "hint" in out
