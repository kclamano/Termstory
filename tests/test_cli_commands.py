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

    # 5b. Test setting numeric config
    result = runner.invoke(app, ["config", "set", "request_timeout_seconds", "45"])
    assert result.exit_code == 0
    import json
    with open(config_file, "r") as f:
        data = json.load(f)
    assert data["request_timeout_seconds"] == 45

    result = runner.invoke(app, ["config", "get", "request_timeout_seconds"])
    assert result.exit_code == 0
    assert "45" in result.stdout
    
    # 6. Test config list with redacting
    result = runner.invoke(app, ["config", "list"])
    assert result.exit_code == 0
    assert "providers.groq.api_key" in result.stdout
    assert "test-g...-123" in result.stdout # Redacted key should be printed in redacted format
    assert "providers.openai.api_key" in result.stdout
    assert "sk-pro...-123" in result.stdout
    assert "ai_enabled" in result.stdout

def test_cli_reset_commands(monkeypatch):
    called = []
    def mock_perform_reset():
        called.append(True)
        
    monkeypatch.setattr("termstory.cli.perform_reset", mock_perform_reset)
    
    runner = CliRunner()
    
    # Test --reset option
    result = runner.invoke(app, ["--reset"])
    assert result.exit_code == 0
    assert len(called) == 1
    
    called.clear()
    # Test reset subcommand
    result_sub = runner.invoke(app, ["reset"])
    assert result_sub.exit_code == 0
    assert len(called) == 1
    
    # Test -reset arg rewritten to --reset via intercept_sys_argv
    import sys
    sys_argv_orig = sys.argv
    try:
        sys.argv = ["termstory", "-reset"]
        from termstory.cli import intercept_sys_argv
        intercept_sys_argv()
        assert sys.argv[1] == "--reset"
    finally:
        sys.argv = sys_argv_orig

def test_cli_ui_onboarding_missing_timestamps_yes(tmp_path, monkeypatch):
    db_file = tmp_path / "test_cli_ui.db"
    monkeypatch.setattr("termstory.cli.get_db_path", lambda: str(db_file))
    monkeypatch.setattr("termstory.config.get_db_path", lambda: str(db_file))
    config_file = tmp_path / "config.json"
    monkeypatch.setattr("termstory.config.get_config_path", lambda: str(config_file))
    
    # Mock run_ingestion to do nothing
    monkeypatch.setattr("termstory.cli.run_ingestion", lambda db: None)
    
    # Flag missing timestamps manually
    monkeypatch.setenv("TERMSTORY_MISSING_TIMESTAMPS", "1")
    # Exercise the zsh branch of the shell-aware onboarding flow
    monkeypatch.setenv("SHELL", "/bin/zsh")
    
    # Mock open for ~/.zshrc appending
    zshrc_file = tmp_path / ".zshrc"
    monkeypatch.setattr("os.path.expanduser", lambda p: str(zshrc_file) if p == "~/.zshrc" else p)
    
    runner = CliRunner()
    result = runner.invoke(app, ["ui"], input="y\n")
    
    assert result.exit_code == 0
    assert "Done! Please restart your terminal" in result.stdout
    # Verify file was appended correctly
    assert zshrc_file.exists()
    content = zshrc_file.read_text()
    assert "setopt EXTENDED_HISTORY" in content

    # Verify config flag was saved
    import json
    assert config_file.exists()
    with open(config_file, "r") as f:
        cfg = json.load(f)
    assert cfg.get("has_seen_timestamp_prompt") is True

def test_cli_ui_onboarding_missing_timestamps_no(tmp_path, monkeypatch):
    db_file = tmp_path / "test_cli_ui.db"
    monkeypatch.setattr("termstory.cli.get_db_path", lambda: str(db_file))
    monkeypatch.setattr("termstory.config.get_db_path", lambda: str(db_file))
    config_file = tmp_path / "config.json"
    monkeypatch.setattr("termstory.config.get_config_path", lambda: str(config_file))
    
    # Mock run_ingestion
    monkeypatch.setattr("termstory.cli.run_ingestion", lambda db: None)
    
    # Flag missing timestamps manually
    monkeypatch.setenv("TERMSTORY_MISSING_TIMESTAMPS", "1")
    
    # Mock TermStoryWorkspace.run to exit instead of running actual Textual TUI
    workspace_runs = []
    def mock_run(self):
        workspace_runs.append(True)
    monkeypatch.setattr("termstory.tui.TermStoryWorkspace.run", mock_run)
    
    runner = CliRunner()
    result = runner.invoke(app, ["ui"], input="n\n")
    
    assert "Continuing with legacy history fallback" in result.stdout
    assert len(workspace_runs) == 1

    # Verify config flag was saved
    import json
    assert config_file.exists()
    with open(config_file, "r") as f:
        cfg = json.load(f)
    assert cfg.get("has_seen_timestamp_prompt") is True

    # Second run should not re-prompt once flag is set
    result2 = runner.invoke(app, ["ui"])
    assert result2.exit_code == 0
    assert "automatically enable history timestamps" not in result2.stdout
    assert len(workspace_runs) == 2


def test_cli_ui_onboarding_bash_shell(tmp_path, monkeypatch):
    """On a bash shell, onboarding should write HISTTIMEFORMAT to ~/.bashrc."""
    db_file = tmp_path / "test_cli_ui.db"
    monkeypatch.setattr("termstory.cli.get_db_path", lambda: str(db_file))
    monkeypatch.setattr("termstory.config.get_db_path", lambda: str(db_file))
    config_file = tmp_path / "config.json"
    monkeypatch.setattr("termstory.config.get_config_path", lambda: str(config_file))
    monkeypatch.setattr("termstory.cli.run_ingestion", lambda db: None)
    monkeypatch.setenv("TERMSTORY_MISSING_TIMESTAMPS", "1")
    monkeypatch.setenv("SHELL", "/bin/bash")
    
    bashrc_file = tmp_path / ".bashrc"

    def fake_expand(p):
        if p in ("~/.bashrc", "~/.bash_profile"):
            return str(bashrc_file)
        if p == "~":
            return str(tmp_path)
        return p
    monkeypatch.setattr("os.path.expanduser", fake_expand)
    
    runner = CliRunner()
    result = runner.invoke(app, ["ui"], input="y\n")
    
    assert result.exit_code == 0
    assert "Done! Please restart your terminal" in result.stdout
    assert bashrc_file.exists()
    content = bashrc_file.read_text()
    assert 'HISTTIMEFORMAT="%F %T "' in content
    assert "setopt EXTENDED_HISTORY" not in content

    # Verify config flag was saved
    import json
    assert config_file.exists()
    with open(config_file, "r") as f:
        cfg = json.load(f)
    assert cfg.get("has_seen_timestamp_prompt") is True


def test_run_ingestion_no_history_files(tmp_path, monkeypatch, capsys):
    """Case A — no history files found at all (fresh setup)."""
    from termstory.cli import run_ingestion
    monkeypatch.setattr("termstory.cli.get_history_files", lambda: [])
    db = Database(str(tmp_path / "t.db"))
    db.init_db()
    
    run_ingestion(db)
    err = capsys.readouterr().err
    assert "No shell history files found" in err
    assert "fresh setup" in err


def test_run_ingestion_empty_history_file(tmp_path, monkeypatch, capsys):
    """Case B — a history file exists but is empty."""
    from termstory.cli import run_ingestion
    empty = tmp_path / ".zsh_history"
    empty.write_text("")
    monkeypatch.setattr("termstory.cli.get_history_files", lambda: [str(empty)])
    db = Database(str(tmp_path / "t.db"))
    db.init_db()
    
    run_ingestion(db)
    err = capsys.readouterr().err
    assert "exists but is empty" in err


def test_cli_ui_onboarding_reminder_printed(tmp_path, monkeypatch):
    db_file = tmp_path / "test_cli_ui.db"
    monkeypatch.setattr("termstory.cli.get_db_path", lambda: str(db_file))
    monkeypatch.setattr("termstory.config.get_db_path", lambda: str(db_file))
    config_file = tmp_path / "config.json"
    monkeypatch.setattr("termstory.config.get_config_path", lambda: str(config_file))
    
    # Mock run_ingestion
    monkeypatch.setattr("termstory.cli.run_ingestion", lambda db: None)
    
    # Mock TermStoryWorkspace.run to do nothing
    monkeypatch.setattr("termstory.tui.TermStoryWorkspace.run", lambda self: None)
    
    runner = CliRunner()
    result = runner.invoke(app, ["ui"])
    assert result.exit_code == 0
    assert "Hint: TermStory works best with AI summaries enabled!" in result.stdout
    
    # Verify config flag was saved
    import json
    assert config_file.exists()
    with open(config_file, "r") as f:
        cfg = json.load(f)
    assert cfg.get("has_seen_onboarding_reminder") is True
    
    # Second run should not print the reminder
    result2 = runner.invoke(app, ["ui"])
    assert result2.exit_code == 0
    assert "Hint: TermStory works best with AI summaries enabled!" not in result2.stdout



