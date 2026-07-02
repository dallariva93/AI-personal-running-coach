"""Tests for the sync_state bookkeeping (FINAL_ROADMAP §5-bis, Passo 2 / Q2)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.services.sync_state import record_ingest, should_skip_ingest


def test_should_skip_ingest_false_without_prior_record(session):
    assert should_skip_ingest(session) is False


def test_should_skip_ingest_true_right_after_record(session):
    now = datetime(2026, 6, 24, 8, 0, tzinfo=UTC)
    record_ingest(session, now=now)
    session.commit()
    assert should_skip_ingest(session, now=now + timedelta(minutes=3)) is True


def test_should_skip_ingest_false_after_window_elapses(session):
    now = datetime(2026, 6, 24, 8, 0, tzinfo=UTC)
    record_ingest(session, now=now)
    session.commit()
    assert should_skip_ingest(session, now=now + timedelta(minutes=11)) is False


def test_record_ingest_updates_existing_row(session):
    t1 = datetime(2026, 6, 24, 8, 0, tzinfo=UTC)
    t2 = datetime(2026, 6, 24, 9, 0, tzinfo=UTC)
    record_ingest(session, now=t1)
    record_ingest(session, now=t2)
    session.commit()
    assert should_skip_ingest(session, now=t2 + timedelta(minutes=1)) is True
    assert should_skip_ingest(session, now=t2 + timedelta(minutes=11)) is False
