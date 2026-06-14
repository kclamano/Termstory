import os
import time
from termstory.parser import parse_zsh_history
from termstory.session import create_sessions
from termstory.database import Database
from termstory.project import find_project_root, Project

def test_end_to_end_integration(tmp_path):
    # 1. Create a mock Zsh history file
    hist_file = tmp_path / "zsh_history"
    
    # We will write some timestamped commands.
    # Note: 1717675200 is June 6, 2026 12:00:00 UTC.
    now = 1717675200
    lines = [
        f": {now}:0;cd {tmp_path}\n",
        f": {now + 10}:0;pytest --verbose\n",
        f": {now + 50}:0;git commit -m \"feat: initial commit\"\n"
    ]
    hist_file.write_text("".join(lines), encoding="utf-8")
    
    # 2. Parse the history file
    commands = parse_zsh_history(str(hist_file))
    assert len(commands) == 3
    assert commands[0].command == f"cd {tmp_path}"
    assert commands[1].command == "pytest --verbose"
    assert commands[2].command == "git commit -m \"feat: initial commit\""
    
    # Associate commands with project_id
    project_root = find_project_root(str(tmp_path))
    p1 = Project(id=1, name="Integration Project", path=project_root, first_seen=now, last_seen=now + 50, session_count=1, total_time=50)
    
    for cmd in commands:
        cmd.project_id = p1.id
        
    # 3. Build sessions
    sessions = create_sessions(commands)
    assert len(sessions) == 1
    session = sessions[0]
    session.id = 1
    session.project_id = p1.id
    for cmd in commands:
        cmd.session_id = session.id
        
    # 4. Initialize Database
    db_file = tmp_path / "integration.db"
    db = Database(str(db_file))
    db.init_db()
    
    # Save projects, sessions, commands
    db.save_data([p1], [session], commands)
    
    # 5. Search sessions
    results = db.search_sessions("verbose")
    assert len(results) == 1
    assert results[0]["session_id"] == 1
    assert "pytest --verbose" in results[0]["matching_commands"]


def test_e2e_search_by_project_name(tmp_path):
    """E2E: ingest history, save to DB, and search by project name."""
    hist_file = tmp_path / "zsh_history"
    now = 1717675200
    lines = [
        f": {now}:0;npm install\n",
        f": {now + 60}:0;npm run build\n",
    ]
    hist_file.write_text("".join(lines), encoding="utf-8")

    commands = parse_zsh_history(str(hist_file))
    assert len(commands) == 2

    project_root = find_project_root(str(tmp_path))
    p1 = Project(id=1, name="MyWebApp", path=project_root, first_seen=now, last_seen=now + 60, session_count=1, total_time=60)

    for cmd in commands:
        cmd.project_id = p1.id

    sessions = create_sessions(commands)
    assert len(sessions) == 1
    sessions[0].id = 1
    sessions[0].project_id = p1.id
    for cmd in commands:
        cmd.session_id = sessions[0].id

    db_file = tmp_path / "e2e_web.db"
    db = Database(str(db_file))
    db.init_db()
    db.save_data([p1], sessions, commands)

    # Search by command fragment
    results = db.search_sessions("npm run build")
    assert len(results) >= 1
    assert any("npm run build" in r["matching_commands"] for r in results)


def test_e2e_multiple_sessions(tmp_path):
    """E2E: history with a long idle gap should produce 2 separate sessions."""
    hist_file = tmp_path / "zsh_history"
    now = 1717675200
    gap = 35 * 60  # 35 minutes → exceeds 30-minute session threshold
    lines = [
        f": {now}:0;git status\n",
        f": {now + 10}:0;git diff\n",
        f": {now + gap}:0;python3 manage.py runserver\n",
        f": {now + gap + 30}:0;python3 manage.py migrate\n",
    ]
    hist_file.write_text("".join(lines), encoding="utf-8")

    commands = parse_zsh_history(str(hist_file))
    assert len(commands) == 4

    sessions = create_sessions(commands)
    assert len(sessions) == 2, f"Expected 2 sessions, got {len(sessions)}"

    db_file = tmp_path / "e2e_multi.db"
    db = Database(str(db_file))
    db.init_db()

    project_root = find_project_root(str(tmp_path))
    p1 = Project(id=1, name="Django App", path=project_root,
                 first_seen=now, last_seen=now + gap + 30, session_count=2, total_time=gap + 30)

    # Assign project_id and session_id before calling save_data so that the DB
    # correctly links commands → sessions → projects for search indexing.
    for i, sess in enumerate(sessions):
        sess.id = i + 1
        sess.project_id = p1.id

    sess_boundary = sessions[0].end_time
    for cmd in commands:
        cmd.project_id = p1.id
        if cmd.timestamp <= sess_boundary:
            cmd.session_id = sessions[0].id
        else:
            cmd.session_id = sessions[1].id

    db.save_data([p1], sessions, commands)

    results = db.search_sessions("runserver")
    assert len(results) >= 1, f"Expected search results for 'runserver', got 0. Sessions in DB: {len(sessions)}"
    # Check that the result contains 'runserver' in any command field
    found = any(
        "runserver" in r["matching_commands"] or
        any("runserver" in cmd for cmd in r.get("all_commands", []))
        for r in results
    )
    assert found, f"'runserver' not found in any result. Got: {[r['all_commands'] for r in results]}"
