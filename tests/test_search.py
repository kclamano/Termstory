import time
from termstory.database import Database
from termstory.models import Project, Session, Command

def test_database_commits_and_search(tmp_path):
    db_file = tmp_path / "test_search.db"
    db = Database(str(db_file))
    db.init_db()
    
    now = int(time.time())
    
    # 1. Save projects
    p1 = Project(id=1, name="Apache HugeGraph", path="~/projects/incubator-hugegraph", first_seen=now, last_seen=now, session_count=1, total_time=100)
    p2 = Project(id=2, name="Termstory CLI", path="~/projects/termstory", first_seen=now, last_seen=now, session_count=1, total_time=150)
    
    # 2. Save sessions and commands
    cmd1 = Command(timestamp=now, command="docker ps -a", session_id=1, project_id=1)
    s1 = Session(id=1, start_time=now, end_time=now + 100, duration_seconds=100, project_id=1, commands=[cmd1])
    
    cmd2 = Command(timestamp=now + 5000, command="pytest tests/", session_id=2, project_id=2)
    s2 = Session(id=2, start_time=now + 5000, end_time=now + 5100, duration_seconds=100, project_id=2, commands=[cmd2])
    
    db.save_data([p1, p2], [s1, s2], [cmd1, cmd2])
    
    # 3. Save git commits
    commits_p1 = [
        {"hash": "1111111111111111111111111111111111111111", "timestamp": now + 20, "message": "feat: Add docker health checks", "cleaned_message": "Add docker health checks"},
        {"hash": "2222222222222222222222222222222222222222", "timestamp": now - 3600, "message": "docs: document raft config", "cleaned_message": "Document raft config"}
    ]
    db.save_commits(p1.id, commits_p1)
    
    commits_p2 = [
        {"hash": "3333333333333333333333333333333333333333", "timestamp": now + 5050, "message": "fix: fix tests for cli run", "cleaned_message": "Fix tests for cli run"}
    ]
    db.save_commits(p2.id, commits_p2)
    
    # 4. Verify commits are fetched inside get_today_sessions and get_session_commits
    sessions_today = db.get_today_sessions()
    assert len(sessions_today) >= 2
    
    # Session 1 should have 1 commit mapped (the docker health check commit, which falls in the time range)
    s1_retrieved = next(s for s in sessions_today if s.id == 1)
    assert len(s1_retrieved.commits) == 1
    assert s1_retrieved.commits[0]["hash"] == "1111111111111111111111111111111111111111"
    assert s1_retrieved.commits[0]["cleaned_message"] == "Add docker health checks"
    
    # 5. Test search_sessions matching commit message
    results = db.search_sessions("health")
    assert len(results) == 1
    assert results[0]["session_id"] == 1
    assert results[0]["project_name"] == "Apache HugeGraph"
    assert len(results[0]["matching_commits"]) == 1
    assert results[0]["matching_commits"][0]["hash"] == "1111111111111111111111111111111111111111"
    
    # 6. Test search_sessions matching command text
    results = db.search_sessions("pytest")
    assert len(results) == 1
    assert results[0]["session_id"] == 2
    assert results[0]["project_name"] == "Termstory CLI"
    assert "pytest tests/" in results[0]["matching_commands"]
    
    # 7. Test search_sessions matching project name
    results = db.search_sessions("Termstory")
    assert len(results) == 1
    assert results[0]["session_id"] == 2
    
    # 8. Test filters
    # Filter by project
    results = db.search_sessions("tests", project_filter="Termstory")
    assert len(results) == 1
    
    results = db.search_sessions("tests", project_filter="HugeGraph")
    assert len(results) == 0
