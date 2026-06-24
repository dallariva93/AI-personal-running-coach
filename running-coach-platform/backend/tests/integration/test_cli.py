"""Integration tests for the command-line interface."""

from __future__ import annotations

from app.cli import main


def test_cli_ingest_then_metrics(db_env, capsys):
    assert main(["ingest"]) == 0
    out = capsys.readouterr().out
    assert "corse" in out

    assert main(["metrics"]) == 0
    out = capsys.readouterr().out
    assert "form_state" in out


def test_cli_analyze_and_save(db_env, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    # Re-point DB under the new cwd is unnecessary: DATABASE_URL is absolute.
    assert main(["ingest"]) == 0
    capsys.readouterr()
    assert main(["analyze", "--save"]) == 0
    out = capsys.readouterr().out
    assert "## Analisi" in out
    assert "Prossimo allenamento" in out
    # a report markdown file was written under data/reports
    reports = list((tmp_path / "data" / "reports").glob("single-*.md"))
    assert len(reports) == 1


def test_cli_weekly(db_env, capsys):
    main(["ingest"])
    capsys.readouterr()
    assert main(["weekly"]) == 0
    out = capsys.readouterr().out
    assert "Prossimo allenamento" in out
