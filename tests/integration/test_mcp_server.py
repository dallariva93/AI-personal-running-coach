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
        # Fase 2 — reading the athlete's state
        "get_athlete_overview",
        "get_training_metrics",
        "list_activities",
        "get_activity_detail",
        "get_current_training_plan",
        "get_plan_week",
        "get_race_prediction",
        "compare_periods",
        # Fase 2.5 — what a plan actually needs to be individual
        "get_athlete_physiology",
        "generate_plan_draft",
        "get_training_history_summary",
        "get_personal_records",
        "get_cross_training",
        "get_readiness_history",
        # Nutrizione (Yazio)
        "get_nutrition",
    }
    # Nothing that writes: a leaked URL must not be able to change state.
    # `generate_plan_draft` computes in memory and persists nothing — asserted
    # by test_generatePlanDraft_isMarkedAsDraftAndNotPersisted.
    # Whole words only: "physiology" contains "log" but writes nothing.
    write_verbs = {"create", "update", "delete", "save", "log", "set", "add", "remove"}
    for name in names:
        assert not (set(name.split("_")) & write_verbs), f"tool sospetto: {name}"
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


# --------------------------------------------------------------------------
# Fase 2.5 — i tool che ancorano il coaching alla fisiologia e al motore
# --------------------------------------------------------------------------
def _profile_with_goal(session, days_to_race: int = 120, **kwargs) -> None:
    save_profile(
        session,
        AthleteProfile(
            age=32,
            level="intermediate",
            goal=Goal(
                goal_type="marathon",
                target_date=(date.today() + timedelta(days=days_to_race)).isoformat(),
                target_time="03:30:00",
            ),
            **kwargs,
        ),
    )


def test_getAthletePhysiology_noData_saysSoInsteadOfGuessing(mcp):
    """Without an anchor the coach must be told, not handed a plausible null."""
    out = _call(mcp, "get_athlete_physiology")

    assert out["thresholds"]["lt2_pace"] is None
    assert out["thresholds"]["source"] == "non disponibile"
    assert "non prescrivere ritmi precisi" in out["thresholds"]["hint"]


def test_getAthletePhysiology_profileThreshold_winsOverEstimate(mcp, session):
    from app.schemas import AthletePhysiology

    save_profile(
        session,
        AthleteProfile(physiology=AthletePhysiology(lt2_pace="4:15", lactate_threshold_hr=172)),
    )
    session.commit()

    out = _call(mcp, "get_athlete_physiology")

    assert out["thresholds"]["lt2_pace"] == "4:15"
    assert out["thresholds"]["source"] == "profilo"
    assert out["thresholds"]["lactate_threshold_hr"] == 172
    assert out["thresholds"]["hint"] is None


def test_getAthletePhysiology_exposesCalendarConstraintsAndRaces(mcp, session):
    from app.schemas import Race

    save_profile(
        session,
        AthleteProfile(
            weekly_runs=5,
            risk_tolerance="conservative",
            available_days=["mon", "wed", "fri", "sun"],
            races=[
                Race(name="Mezza di prova", race_type="half",
                     date=(date.today() + timedelta(days=45)).isoformat(), priority="B"),
            ],
        ),
    )
    session.commit()

    out = _call(mcp, "get_athlete_physiology")

    assert out["availability"]["available_days"] == ["mon", "wed", "fri", "sun"]
    assert out["availability"]["weekly_runs"] == 5
    assert out["availability"]["risk_tolerance"] == "conservative"
    assert len(out["races"]) == 1
    assert out["races"][0]["priority"] == "B"


def test_getAthletePhysiology_digitalTwin_carriesConfidenceAndLearningFlag(mcp, session):
    _seed_runs(session, days_back=list(range(1, 40, 2)), km=12.0)
    session.commit()

    twin = _call(mcp, "get_athlete_physiology")["digital_twin"]

    for key in ("ramp_tolerance_pct", "recovery_halflife_days", "heat_sensitivity_s_per_c"):
        assert twin[key] is not None
        assert "value" in twin[key]
        # Confidence and the learning flag are what stop the coach from
        # treating a provisional estimate as established fact.
        assert "confidence" in twin[key]
        assert "learning" in twin[key]


def test_generatePlanDraft_usesTheEngine_volumesAddUp(mcp, session):
    """The property freehand plan-writing gets wrong: the arithmetic."""
    _profile_with_goal(session, days_to_race=120)
    _seed_runs(session, days_back=list(range(1, 40, 2)), km=12.0)
    session.commit()

    out = _call(mcp, "generate_plan_draft")

    assert out["weeks_total"] > 10
    assert out["baseline_km"] > 0
    for week in out["weeks"]:
        # Rest days are collapsed into their own list, but the week must still
        # account for all seven days — that invariant is the engine's contract.
        assert len(week["sessions"]) + len(week["rest_days"]) == 7
        assert all(s["type"] != "rest" for s in week["sessions"])
        total = sum(s["km"] or 0 for s in week["sessions"])
        assert total == pytest.approx(week["target_km"], abs=0.15)


def test_generatePlanDraft_restDaysCollapsed_withoutLosingInformation(mcp, session):
    """Rest days were 35% of this payload while carrying no information.

    Collapsing them must stay lossless: every day of every week is still
    accounted for, and every rest day is named.
    """
    _profile_with_goal(session, days_to_race=120)
    _seed_runs(session, days_back=list(range(1, 40, 2)), km=12.0)
    session.commit()
    valid_days = {"lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"}

    weeks = _call(mcp, "generate_plan_draft")["weeks"]

    assert weeks, "il piano deve essere completo, non troncato"
    for week in weeks:
        named = [s["day"] for s in week["sessions"]] + week["rest_days"]
        assert set(named) <= valid_days
        assert len(set(named)) == 7, f"settimana {week['week_number']}: giorni mancanti o doppi"
        assert week["rest_days"], "una settimana senza riposi è sospetta"


def test_generatePlanDraft_returnsTheWholeBlockNotAWindow(mcp, session):
    """The full plan is the deliverable: weeks must run start to race."""
    _profile_with_goal(session, days_to_race=120)
    session.commit()

    out = _call(mcp, "generate_plan_draft")

    numbers = [w["week_number"] for w in out["weeks"]]
    assert numbers == list(range(1, out["weeks_total"] + 1))
    assert all("sessions" in w for w in out["weeks"])


def test_generatePlanDraft_isMarkedAsDraftAndNotPersisted(mcp, session):
    _profile_with_goal(session)
    session.commit()

    out = _call(mcp, "generate_plan_draft")

    assert out["is_draft"] is True
    assert out["saved"] is False
    assert "non è il piano" in out["note"].lower()
    # And it really did not touch the app's plan.
    assert _call(mcp, "get_current_training_plan")["active_plan"] is None


def test_generatePlanDraft_progressionRampsThenTapers(mcp, session):
    _profile_with_goal(session, days_to_race=120)
    _seed_runs(session, days_back=list(range(1, 40, 2)), km=12.0)
    session.commit()

    weeks = _call(mcp, "generate_plan_draft")["weeks"]
    volumes = [w["target_km"] for w in weeks]
    peak = max(volumes)
    peak_index = volumes.index(peak)

    assert peak > volumes[0]                       # it builds to a peak
    assert volumes[-1] < peak * 0.6                # and tapers hard into the race
    assert weeks[-1]["phase"].lower() in ("taper", "race", "gara")
    # Deload weeks: the build is a sawtooth, not a ramp. A plan that only ever
    # goes up is the classic freehand mistake this engine exists to prevent.
    assert any(
        volumes[i] < volumes[i - 1] for i in range(1, peak_index)
    ), f"nessuna settimana di scarico prima del picco: {volumes}"


def test_generatePlanDraft_fallsBackToStoredGoal(mcp, session):
    _profile_with_goal(session, days_to_race=90)
    session.commit()

    out = _call(mcp, "generate_plan_draft")

    assert out["goal"]["type"] == "marathon"
    assert out["goal"]["target_time"] == "03:30:00"


def test_generatePlanDraft_noGoalAnywhere_explainsWhatIsMissing(mcp):
    with pytest.raises(Exception, match="goal_type"):
        _call(mcp, "generate_plan_draft")


def test_generatePlanDraft_rejectsImpossibleSchedule(mcp, session):
    _profile_with_goal(session)
    session.commit()

    with pytest.raises(Exception, match="days_per_week"):
        _call(mcp, "generate_plan_draft", days_per_week=9)
    with pytest.raises(Exception, match="long_run_day"):
        _call(mcp, "generate_plan_draft", long_run_day=7)


def test_generatePlanDraft_withoutSessions_returnsSkeletonOnly(mcp, session):
    _profile_with_goal(session)
    session.commit()

    out = _call(mcp, "generate_plan_draft", include_sessions=False)

    assert out["weeks"]
    assert "sessions" not in out["weeks"][0]


def test_getTrainingHistorySummary_bucketsByMonth(mcp, session):
    today = date.today()
    _seed_runs(session, days_back=[1, 3, 5], km=10.0)
    _seed_runs(session, days_back=[40, 42], km=10.0)
    session.commit()

    out = _call(mcp, "get_training_history_summary", months=6)

    assert out["months_returned"] >= 2
    months = {m["month"]: m for m in out["months"]}
    assert f"{today.year:04d}-{today.month:02d}" in months
    current = months[f"{today.year:04d}-{today.month:02d}"]
    assert current["runs"] >= 1
    assert current["total_km"] > 0
    assert "hard_sessions" in current and "long_runs_18k_plus" in current


def test_getTrainingHistorySummary_emptyHistory_returnsHint(mcp):
    out = _call(mcp, "get_training_history_summary")

    assert out["months_returned"] == 0
    assert out["hint"]


def test_getPersonalRecords_emptyHistory_returnsHint(mcp):
    out = _call(mcp, "get_personal_records")

    assert out["records"] == []
    assert out["hint"]


def test_getCrossTraining_separatesSportsFromRunning(mcp, session):
    _seed_runs(session, days_back=[1, 2], km=10.0)
    upsert_activity(
        session,
        RunSummary(
            date=date.today().isoformat(), sport="bike",
            activity_type="easy", distance_km=40.0, duration_min=80.0,
        ),
    )
    session.commit()

    out = _call(mcp, "get_cross_training")

    assert out["returned"] == 1  # the two runs are not here
    assert out["by_sport"] == {"bike": 1}
    assert out["sessions"][0]["sport"] == "bike"


def test_getReadinessHistory_returnsEntriesAndAverages(mcp, session):
    from app.schemas import DailyCheckin
    from app.services import save_checkin

    for offset, fatigue in [(1, 7), (2, 6), (3, 8)]:
        save_checkin(
            session,
            DailyCheckin(
                date=(date.today() - timedelta(days=offset)).isoformat(),
                sleep_h=6.5, fatigue=fatigue, soreness=4, motivation=6,
            ),
        )
    session.commit()

    out = _call(mcp, "get_readiness_history", days=30)

    assert out["entries_found"] == 3
    assert out["averages"]["fatigue_1_10"] == pytest.approx(7.0)
    assert out["averages"]["sleep_h"] == pytest.approx(6.5)
    dates = [e["date"] for e in out["entries"]]
    assert dates == sorted(dates, reverse=True)


def test_getReadinessHistory_windowExcludesOlderEntries(mcp, session):
    from app.schemas import DailyCheckin
    from app.services import save_checkin

    recent = (date.today() - timedelta(days=2)).isoformat()
    old = (date.today() - timedelta(days=90)).isoformat()
    save_checkin(session, DailyCheckin(date=recent, fatigue=5))
    save_checkin(session, DailyCheckin(date=old, fatigue=9))
    session.commit()

    out = _call(mcp, "get_readiness_history", days=7)

    assert out["entries_found"] == 1
    assert out["averages"]["fatigue_1_10"] == pytest.approx(5.0)


def test_getReadinessHistory_noCheckins_returnsHint(mcp):
    out = _call(mcp, "get_readiness_history")

    assert out["entries_found"] == 0
    assert out["hint"]


# --------------------------------------------------------------------------
# Livelli 1-2: id delle attività, seduta pianificata, cross-training nel sync
# --------------------------------------------------------------------------
def _plan_with_executed_session(session, activity_id: int, session_type: str = "tempo"):
    """A plan whose session was scored as executed by `activity_id`."""
    from app.db.models import TrainingPlan, TrainingPlanSession, TrainingPlanWeek

    plan = TrainingPlan(
        goal_type="10k", goal_date=(date.today() + timedelta(days=60)).isoformat(),
        level="intermediate", weeks_total=1,
        start_date=(date.today() - timedelta(days=date.today().weekday())).isoformat(),
        status="active",
    )
    session.add(plan)
    session.flush()
    week = TrainingPlanWeek(plan_id=plan.id, week_number=1, phase="Build", target_km=40.0)
    session.add(week)
    session.flush()
    sess = TrainingPlanSession(
        week_id=week.id, day_of_week=1, session_type=session_type,
        title="Medio progressivo", target_distance_km=10.0, target_pace="4:40/km",
        executed_activity_id=activity_id, execution_status="completed_well",
        execution_score=92.0,
    )
    session.add(sess)
    session.flush()
    return sess


def test_listActivities_exposesTheActivityId(mcp, session):
    """Without ids, opening a detail is guesswork — and picks the wrong run."""
    _seed_runs(session, days_back=[1, 3], km=10.0)
    session.commit()

    out = _call(mcp, "list_activities")

    ids = [a["id"] for a in out["activities"]]
    assert all(isinstance(i, int) for i in ids)
    assert len(set(ids)) == len(ids)
    # And the id actually opens that same activity.
    detail = _call(mcp, "get_activity_detail", activity_id=ids[0])
    assert detail["date"] == out["activities"][0]["date"]


def test_listActivities_dateFilterStillWorksOnRows(mcp, session):
    today = date.today()
    _seed_runs(session, days_back=[1, 2, 30, 40], km=10.0)
    session.commit()

    out = _call(
        mcp, "list_activities",
        from_date=(today - timedelta(days=7)).isoformat(),
        to_date=today.isoformat(),
    )

    assert out["returned"] == 2
    assert out["totals"]["total_km"] == pytest.approx(20.0)


def test_listActivities_excludesCrossTraining(mcp, session):
    _seed_runs(session, days_back=[1], km=10.0)
    upsert_activity(session, RunSummary(
        date=date.today().isoformat(), sport="bike", activity_type="easy",
        distance_km=40.0, duration_min=80.0,
    ))
    session.commit()

    out = _call(mcp, "list_activities")

    assert out["returned"] == 1
    assert out["activities"][0]["distance_km"] == 10.0


def test_listActivities_reportsThePlannedSession(mcp, session):
    """A quality session mislabelled "easy" must not read as easy volume."""
    _seed_runs(session, days_back=[1], km=10.0)
    session.commit()
    activity_id = _call(mcp, "list_activities")["activities"][0]["id"]
    _plan_with_executed_session(session, activity_id, session_type="tempo")
    session.commit()

    out = _call(mcp, "list_activities")["activities"][0]

    assert out["type"] == "easy"                    # what Garmin inferred
    assert out["planned"]["session_type"] == "tempo"  # what was prescribed
    assert out["planned"]["execution_status"] == "completed_well"
    assert out["planned"]["execution_score"] == 92.0


def test_getActivityDetail_reportsThePlannedSession(mcp, session):
    _seed_runs(session, days_back=[1], km=10.0)
    session.commit()
    activity_id = _call(mcp, "list_activities")["activities"][0]["id"]
    _plan_with_executed_session(session, activity_id)
    session.commit()

    detail = _call(mcp, "get_activity_detail", activity_id=activity_id)

    assert detail["planned"]["title"] == "Medio progressivo"
    assert detail["planned"]["target_pace"] == "4:40/km"


def test_unplannedActivity_reportsPlannedAsNone(mcp, session):
    """No plan link is a valid answer — it must not look like a missing field."""
    _seed_runs(session, days_back=[1], km=10.0)
    session.commit()

    out = _call(mcp, "list_activities")["activities"][0]

    assert out["planned"] is None


def test_getActivityDetail_exposesRealLaps(mcp, session):
    """An interval session must arrive readable: every rep and every recovery."""
    laps = [
        {"index": 1, "distance_m": 2000, "duration_sec": 660, "pace": "5:30/km", "role": "warmup"},
        {"index": 2, "distance_m": 500, "duration_sec": 105, "pace": "3:30/km", "role": "work"},
        {"index": 3, "distance_m": 200, "duration_sec": 90, "pace": "7:30/km", "role": "recovery"},
        {"index": 4, "distance_m": 500, "duration_sec": 108, "pace": "3:36/km", "role": "work"},
    ]
    upsert_activity(session, RunSummary(
        garmin_activity_id="g-intervals", date=date.today().isoformat(),
        activity_type="intervals", distance_km=8.0, duration_min=45.0,
        splits_km=["5:30", "4:10", "5:05"], laps=laps,
    ))
    session.commit()
    activity_id = _call(mcp, "list_activities")["activities"][0]["id"]

    detail = _call(mcp, "get_activity_detail", activity_id=activity_id)

    assert detail["laps"] == laps
    work = [x for x in detail["laps"] if x.get("role") == "work"]
    assert [x["distance_m"] for x in work] == [500, 500]
    # The fade across the series — the thing the per-km view cannot show.
    assert work[0]["pace"] == "3:30/km"
    assert work[1]["pace"] == "3:36/km"


def test_getActivityDetail_withoutLaps_reportsNoneNotAnError(mcp, session):
    _seed_runs(session, days_back=[1], km=10.0)
    session.commit()
    activity_id = _call(mcp, "list_activities")["activities"][0]["id"]

    assert _call(mcp, "get_activity_detail", activity_id=activity_id)["laps"] is None


# --------------------------------------------------------------------------
# get_nutrition (Yazio)
# --------------------------------------------------------------------------
def _connect_yazio(session) -> None:
    from app.services import yazio_sync

    def _fake(method, url, *, data=None, json=None, params=None, token=None):
        return {"access_token": "acc", "refresh_token": "ref", "expires_in": 3600}

    yazio_sync.connect_account(session, "me@example.com", "pw", request=_fake)


def test_getNutrition_withoutYazio_saysSoInsteadOfImplyingZero(mcp, session):
    """No diary is "unknown", not "ate nothing" — the difference matters."""
    out = _call(mcp, "get_nutrition")

    assert out["connected"] is False
    assert out["days"] == []
    assert out["hint"]


def test_getNutrition_returnsDailyTotalsAndAverages(mcp, session):
    from app.services.yazio_sync import upsert_day

    _connect_yazio(session)
    for offset, kcal in [(1, 2400), (2, 2000)]:
        upsert_day(session, {
            "date": (date.today() - timedelta(days=offset)).isoformat(),
            "energy_kcal": kcal, "protein_g": 120, "carbs_g": 300, "fat_g": 70,
        })
    session.commit()

    out = _call(mcp, "get_nutrition", days=7)

    assert out["connected"] is True
    assert out["days_logged"] == 2
    assert out["averages"]["energy_kcal"] == 2200
    assert [d["energy_kcal"] for d in out["days"]] == [2000, 2400]  # oldest first


def test_getNutrition_withPartialDiary_warnsAboutCoverage(mcp, session):
    """A half-logged diary looks like a huge deficit; the coach must be told."""
    from app.services.yazio_sync import upsert_day

    _connect_yazio(session)
    upsert_day(session, {
        "date": (date.today() - timedelta(days=1)).isoformat(), "energy_kcal": 2400,
    })
    session.commit()

    out = _call(mcp, "get_nutrition", days=14)

    assert out["days_logged"] == 1
    assert "parziale" in out["hint"].lower()


def test_getNutrition_reportsTheBalanceNotJustTheIntake(mcp, session):
    """1900 kcal is generous or a deep hole depending on what the day required."""
    from app.services.yazio_sync import upsert_day

    _connect_yazio(session)
    upsert_day(session, {
        "date": (date.today() - timedelta(days=1)).isoformat(),
        "energy_kcal": 1911, "energy_goal_kcal": 2784,
    })
    session.commit()

    out = _call(mcp, "get_nutrition", days=7)

    day = out["days"][0]
    assert day["energy_kcal"] == 1911
    assert day["energy_goal_kcal"] == 2784
    assert day["balance_kcal"] == -873
    assert out["averages"]["balance_kcal"] == -873


def test_getNutrition_withoutAGoal_reportsNoBalance(mcp, session):
    """No target means the deficit is unknown, not zero."""
    from app.services.yazio_sync import upsert_day

    _connect_yazio(session)
    upsert_day(session, {
        "date": (date.today() - timedelta(days=1)).isoformat(), "energy_kcal": 1911,
    })
    session.commit()

    out = _call(mcp, "get_nutrition", days=7)

    assert out["days"][0]["balance_kcal"] is None
    assert out["averages"]["balance_kcal"] is None
