import os
import time
from datetime import datetime
from typer.testing import CliRunner
from termstory.cli import app
from termstory.database import Database
from termstory.models import Project, Session, Command

def test_cli_week_and_month_commands(tmp_path, monkeypatch):
    db_file = tmp_path / "test_cli.db"
    monkeypatch.setattr("termstory.cli.get_db_path", lambda: str(db_file))
    
    # Bypass ingestion
    monkeypatch.setattr("termstory.cli.get_history_files", lambda: [])
    
    db = Database(str(db_file))
    db.init_db()
    
    # Tuesday, June 2nd, 2026
    now_dt = datetime(2026, 6, 2, 12, 0)
    now = int(now_dt.timestamp())
    
    # Set date override (use 13:00:00 to include the 12:00:00 mock session)
    monkeypatch.setenv("TERMSTORY_DATE_OVERRIDE", "2026-06-02 13:00:00")
    
    p = Project(id=1, name="Apache HugeGraph", path="~/projects/incubator-hugegraph", first_seen=now, last_seen=now, session_count=1, total_time=100)
    cmd = Command(timestamp=now, command="vim pom.xml", session_id=1, project_id=1)
    s = Session(id=1, start_time=now, end_time=now + 100, duration_seconds=100, project_id=1, commands=[cmd])
    
    db.save_data([p], [s], [cmd])
    
    runner = CliRunner()
    
    # 1. Test week command
    result = runner.invoke(app, ["week"])
    assert result.exit_code == 0
    assert "This Week" in result.stdout
    assert "Apache HugeGraph" in result.stdout
    assert "Tuesday" in result.stdout
    
    # 2. Test month command
    result = runner.invoke(app, ["month"])
    assert result.exit_code == 0
    assert "June 2026" in result.stdout
    assert "Apache HugeGraph" in result.stdout
    
    # 3. Test projects command
    result = runner.invoke(app, ["projects"])
    assert result.exit_code == 0
    assert "Your Projects" in result.stdout
    assert "Apache HugeGraph" in result.stdout
    
    # 4. Test project command
    result = runner.invoke(app, ["project", "huge"])
    assert result.exit_code == 0
    assert "Apache HugeGraph" in result.stdout
    assert "pom.xml" in result.stdout
    
    # Test --files option
    result = runner.invoke(app, ["project", "huge", "--files"])
    assert result.exit_code == 0
    assert "pom.xml" in result.stdout
    
    # Test --stats option
    result = runner.invoke(app, ["project", "huge", "--stats"])
    assert result.exit_code == 0
    assert "Editor" in result.stdout
    
    # 5. Test date override option
    result = runner.invoke(app, ["--date", "2026-06-02"])
    assert result.exit_code == 0
    assert "Report for" in result.stdout
    assert "June 02, 2026" in result.stdout
    assert "Apache HugeGraph" in result.stdout

    # 6. Test a different date override (May 2nd, 2026) where no sessions exist
    result = runner.invoke(app, ["--date", "2026-05-02"])
    assert result.exit_code == 0
    assert "No sessions recorded on Saturday, May 02, 2026" in result.stdout
    assert "Apache HugeGraph" not in result.stdout  # Since the session is in June, not May

    # 7. Add a session in May 2nd, 2026 and verify it's queried only for May 2nd
    may_now = int(datetime(2026, 5, 2, 10, 0).timestamp())
    p_may = Project(id=3, name="May Project", path="~/projects/may-proj", first_seen=may_now, last_seen=may_now, session_count=1, total_time=50)
    cmd_may = Command(timestamp=may_now, command="git log", session_id=3, project_id=3)
    s_may = Session(id=3, start_time=may_now, end_time=may_now + 50, duration_seconds=50, project_id=3, commands=[cmd_may])
    db.save_data([p_may], [s_may], [cmd_may])

    result = runner.invoke(app, ["--date", "2026-05-02"])
    assert result.exit_code == 0
    assert "May 02, 2026" in result.stdout
    assert "May Project" in result.stdout
    assert "Apache HugeGraph" not in result.stdout  # June session shouldn't show up!
    
    # 8. Test positional date argument override (intercepted sys.argv)
    import sys
    orig_argv = sys.argv
    try:
        sys.argv = ["termstory", "2026-05-02"]
        from termstory.cli import intercept_sys_argv
        intercept_sys_argv()
        
        result = runner.invoke(app, ["today"])
        assert result.exit_code == 0
        assert "May 02, 2026" in result.stdout
        assert "May Project" in result.stdout
        assert "Apache HugeGraph" not in result.stdout
    finally:
        sys.argv = orig_argv
        os.environ.pop("TERMSTORY_DATE_OVERRIDE", None)

def test_cli_search_and_insights_commands(tmp_path, monkeypatch):
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

    # Test insights command
    result = runner.invoke(app, ["insights"])
    assert result.exit_code == 0
    assert "Highlights" in result.stdout
    assert "Apache HugeGraph" in result.stdout

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


def test_cli_today_story(tmp_path, monkeypatch):
    # Set mock time
    monkeypatch.setenv("TERMSTORY_DATE_OVERRIDE", "2026-06-03 12:00:00")
    
    db_file = tmp_path / "test_cli_story.db"
    monkeypatch.setattr("termstory.cli.get_db_path", lambda: str(db_file))
    monkeypatch.setattr("termstory.config.get_db_path", lambda: str(db_file))
    monkeypatch.setattr("termstory.cli.get_history_files", lambda: [])
    
    config_file = tmp_path / "config.json"
    monkeypatch.setattr("termstory.config.get_config_path", lambda: str(config_file))
    
    db = Database(str(db_file))
    db.init_db()
    
    from datetime import datetime
    now = int(datetime(2026, 6, 3, 11, 0, 0).timestamp())
    p = Project(id=1, name="Apache HugeGraph", path="~/projects/incubator-hugegraph", first_seen=now, last_seen=now, session_count=1, total_time=100)
    cmd = Command(timestamp=now, command="docker run nginx", session_id=1, project_id=1)
    s = Session(id=1, start_time=now, end_time=now + 100, duration_seconds=100, project_id=1, commands=[cmd])
    db.save_data([p], [s], [cmd])
    
    runner = CliRunner()
    
    # Test --story with AI disabled (local/offline)
    result = runner.invoke(app, ["today", "--story"])
    assert result.exit_code == 0
    assert "THE DAILY CHRONICLE" in result.stdout
    assert "TODAY'S ACTIVITY PUNCH-CARD" in result.stdout
    assert "Offline / Local Only" in result.stdout
    
    # Test --story with AI enabled
    # Write config file enabling AI
    config_data = {
        "ai_enabled": True,
        "active_provider": "ollama",
        "providers": {
            "ollama": {
                "api_key": "",
                "api_base_url": "http://localhost:11434/v1",
                "model_name": "llama3"
            }
        }
    }
    with open(config_file, "w") as f:
        import json
        json.dump(config_data, f)
        
    called_ai = []
    def mock_generate_daily_chronicle(*args, **kwargs):
        called_ai.append(args)
        return "✨ ACT I: THE MORNING SPRINT\nYou woke up and immediately chose violence."
        
    monkeypatch.setattr("termstory.ai.generate_daily_chronicle", mock_generate_daily_chronicle)
    
    result = runner.invoke(app, ["today", "--story"])
    assert result.exit_code == 0
    assert "THE DAILY CHRONICLE" in result.stdout
    assert "Narrative Concluded" in result.stdout
    assert "THE MORNING SPRINT" in result.stdout
    assert len(called_ai) == 1



