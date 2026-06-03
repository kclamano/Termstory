import os
import time
from datetime import datetime
from typer.testing import CliRunner
from termstory.cli import app
from termstory.database import Database
from termstory.models import Project, Session, Command

def test_cli_search_command(tmp_path, monkeypatch):
    monkeypatch.setenv("TERMSTORY_DATE_OVERRIDE", "2026-06-03 12:00:00")
    db_file = tmp_path / "test_cli_search.db"
    monkeypatch.setattr("termstory.cli.get_db_path", lambda: str(db_file))
    monkeypatch.setattr("termstory.config.get_db_path", lambda: str(db_file))
    monkeypatch.setattr("termstory.cli.get_history_files", lambda: [])
    
    db = Database(str(db_file))
    db.init_db()
    
    from datetime import datetime
    now = int(datetime(2026, 6, 3, 11, 0, 0).timestamp())
    p = Project(id=1, name="Apache HugeGraph", path="~/projects/incubator-hugegraph", first_seen=now, last_seen=now, session_count=1, total_time=100)
    cmd = Command(timestamp=now, command="docker run nginx", session_id=1, project_id=1)
    s = Session(id=1, start_time=now, end_time=now + 100, duration_seconds=100, project_id=1, commands=[cmd])
    db.save_data([p], [s], [cmd])
    
    # Save a commit
    commits = [
        {"hash": "1111111111111111111111111111111111111111", "timestamp": now, "message": "feat: Add docker health check", "cleaned_message": "Add docker health check"}
    ]
    db.save_commits(p.id, commits)
    
    runner = CliRunner()
    
    # Test search command
    result = runner.invoke(app, ["search", "health"])
    assert result.exit_code == 0
    assert "health" in result.stdout.lower()
    assert "Apache HugeGraph" in result.stdout
    assert "health" in result.stdout

def test_cli_config_commands(tmp_path, monkeypatch):
    # Mock config path to use tmp_path
    config_file = tmp_path / "config.json"
    monkeypatch.setattr("termstory.config.get_config_path", lambda: str(config_file))
    
    runner = CliRunner()
    
    # 1. Verify default/initial state
    result = runner.invoke(app, ["config", "get", "ai_enabled"])
    assert result.exit_code == 0
    assert "False" in result.stdout
    
    # 2. Test setting a key (supports legacy mapping)
    result = runner.invoke(app, ["config", "set", "groq_api_key", "test-groq-key-123"])
    assert result.exit_code == 0
    assert "Set config key 'groq_api_key'" in result.stdout
    
    # 3. Test getting the key
    result = runner.invoke(app, ["config", "get", "groq_api_key"])
    assert result.exit_code == 0
    assert "test-groq-key-123" in result.stdout
    
    # 4. Test setting nested config path directly
    result = runner.invoke(app, ["config", "set", "providers.openai.api_key", "sk-proj-test-openai-key-abc-123"])
    assert result.exit_code == 0
    assert "Set config key 'providers.openai.api_key'" in result.stdout
    
    result = runner.invoke(app, ["config", "get", "providers.openai.api_key"])
    assert result.exit_code == 0
    assert "sk-proj-test-openai-key-abc-123" in result.stdout
    
    # 5. Test setting boolean config
    result = runner.invoke(app, ["config", "set", "ai_enabled", "true"])
    assert result.exit_code == 0
    result = runner.invoke(app, ["config", "get", "ai_enabled"])
    assert result.exit_code == 0
    assert "True" in result.stdout
    
    # 6. Test config list with redacting
    result = runner.invoke(app, ["config", "list"])
    assert result.exit_code == 0
    assert "providers.groq.api_key" in result.stdout
    assert "test-g...-123" in result.stdout # Redacted key should be printed in redacted format
    assert "providers.openai.api_key" in result.stdout
    assert "sk-pro...-123" in result.stdout
    assert "ai_enabled" in result.stdout


