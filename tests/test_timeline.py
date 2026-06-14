# tests/test_timeline.py
"""Tests for the new `timeline` CLI command and render_timeline function."""

import os
from datetime import datetime, timedelta
from typer.testing import CliRunner

from termstory.cli import app
from termstory.database import Database
from termstory.models import Project, Session, Command


def test_cli_timeline_command(tmp_path, monkeypatch):
    # Prepare temporary database path
    db_file = tmp_path / "test_timeline.db"
    monkeypatch.setattr("termstory.cli.get_db_path", lambda: str(db_file))
    monkeypatch.setattr("termstory.config.get_db_path", lambda: str(db_file))
    # Disable history ingestion (no files)
    monkeypatch.setattr("termstory.cli.get_history_files", lambda: [])
    monkeypatch.setattr("termstory.cli.run_ingestion", lambda db: None)

    # Initialise DB and insert data for three consecutive days
    db = Database(str(db_file))
    db.init_db()
    now = datetime(2026, 6, 3, 12, 0, 0)
    base_ts = int(now.timestamp())
    # Project
    project = Project(id=1, name="DemoProject", path="~/demo", first_seen=base_ts, last_seen=base_ts, session_count=2, total_time=300)
    # Sessions on day 0 and day -2
    session_today = Session(id=1, start_time=base_ts, end_time=base_ts + 100, duration_seconds=100, project_id=1, commands=[])
    two_days_ago_ts = int((now - timedelta(days=2)).timestamp())
    session_older = Session(id=2, start_time=two_days_ago_ts, end_time=two_days_ago_ts + 200, duration_seconds=200, project_id=1, commands=[])
    # Commands for each session (required for foreign key integrity)
    cmd_today = Command(timestamp=base_ts, command="echo today", session_id=1, project_id=1)
    cmd_older = Command(timestamp=two_days_ago_ts, command="echo older", session_id=2, project_id=1)
    # Save data
    db.save_data([project], [session_today, session_older], [cmd_today, cmd_older])

    runner = CliRunner()
    result = runner.invoke(app, ["timeline", "--days", "3"]).stdout
    # Verify header and dates appear in output
    assert "Date" in result
    assert "Activity" in result
    # Expect three dates: two days ago, yesterday, today
    dates = [(now - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(2, -1, -1)]
    for d in dates:
        assert d in result
    # Ensure non‑zero bars are present for days with sessions
    assert "█" in result
