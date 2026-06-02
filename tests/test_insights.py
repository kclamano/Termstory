import time
from termstory.models import Session, Project, Command
from termstory.insights import (
    calculate_time_distribution,
    calculate_time_of_day_distribution,
    calculate_day_distribution,
    calculate_focus_score,
    detect_patterns_and_anomalies
)

def test_insights_calculations():
    now = int(time.time())
    
    # Create projects
    p1 = Project(id=1, name="Project Alpha", path="~/alpha", first_seen=0, last_seen=0, session_count=1, total_time=1)
    p2 = Project(id=2, name="Project Beta", path="~/beta", first_seen=0, last_seen=0, session_count=1, total_time=1)
    
    # Create sessions
    # Monday starts
    s1 = Session(id=1, start_time=now, end_time=now + 3600, duration_seconds=3600, project_id=1, commands=[
        Command(timestamp=now, command="git commit -m 'feat: first commit'")
    ]) # 1 hour
    
    s2 = Session(id=2, start_time=now + 7200, end_time=now + 9000, duration_seconds=1800, project_id=2, commands=[
        Command(timestamp=now+7200, command="docker run nginx")
    ]) # 30 mins
    
    # Test Time Distribution
    dist = calculate_time_distribution([s1, s2], [p1, p2])
    assert len(dist) == 2
    assert dist[0][0] == "Project Alpha"
    assert dist[0][1] == 66.66666666666666  # 3600 / 5400 * 100
    assert dist[0][2] == 3600
    
    # Test Time of Day (depends on local timezone, so we can mock/assert categorization)
    # Check that it returns counts matching total time
    tod = calculate_time_of_day_distribution([s1, s2])
    assert sum(tod.values()) == 5400
    
    # Test Day of Week
    day_dist = calculate_day_distribution([s1, s2])
    assert sum(day_dist.values()) == 5400
    
    # Test Focus Score
    # 2 sessions, 2 unique projects on 1 day. 
    # Mins active = 90 mins. Mins per session = 45 mins.
    # Switches = 2 unique projects - 1 = 1 switch.
    # Penalty = 1 * 1.5 = 1.5.
    # Bonus = 45 / 20 = 2.25.
    # Score = 6.0 - 1.5 + 2.25 = 6.75 -> 6.8
    score = calculate_focus_score([s1, s2])
    assert score == 6.8
    
    # Test Patterns and Anomalies
    patterns = detect_patterns_and_anomalies([s1, s2], [p1, p2])
    assert len(patterns) > 0
    assert any("Project Alpha" in p for p in patterns)
    assert any("git" in p.lower() for p in patterns)
