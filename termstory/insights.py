from datetime import datetime
from collections import defaultdict
from typing import List, Tuple
from termstory.models import Session, Project, format_duration
from termstory.formatter import classify_command, DISPLAY_NAMES

def calculate_time_distribution(sessions: List[Session], projects: List[Project]) -> List[Tuple[str, float, int]]:
    """Calculate the percentage of total hours and absolute time spent on each project.
    Returns: [(project_name, percentage, duration_seconds), ...] sorted by duration DESC
    """
    total_time = sum(s.duration_seconds for s in sessions)
    if total_time == 0:
        return []
        
    project_map = {p.id: p.name for p in projects if p.id is not None}
    time_by_project = defaultdict(int)
    
    for s in sessions:
        p_name = project_map.get(s.project_id, "General / No Project")
        time_by_project[p_name] += s.duration_seconds
        
    sorted_time = sorted(time_by_project.items(), key=lambda x: x[1], reverse=True)
    
    distribution = []
    for p_name, duration in sorted_time:
        pct = (duration / total_time) * 100
        distribution.append((p_name, pct, duration))
        
    return distribution

def calculate_time_of_day_distribution(sessions: List[Session]) -> Dict[str, int]:
    """Calculate total seconds spent in Morning (6-12), Afternoon (12-18), and Evening (18-6)"""
    distribution = {"morning": 0, "afternoon": 0, "evening": 0}
    
    for session in sessions:
        # Determine time-of-day category by the midpoint of the session
        mid_ts = (session.start_time + session.end_time) // 2
        dt = datetime.fromtimestamp(mid_ts)
        hour = dt.hour
        
        if 6 <= hour < 12:
            distribution["morning"] += session.duration_seconds
        elif 12 <= hour < 18:
            distribution["afternoon"] += session.duration_seconds
        else:
            distribution["evening"] += session.duration_seconds
            
    return distribution

def calculate_day_distribution(sessions: List[Session]) -> Dict[str, int]:
    """Group session durations by day of week"""
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    distribution = {d: 0 for d in days}
    
    for session in sessions:
        dt = datetime.fromtimestamp(session.start_time)
        day_name = dt.strftime("%A")
        if day_name in distribution:
            distribution[day_name] += session.duration_seconds
            
    return distribution

def calculate_focus_score(sessions: List[Session]) -> float:
    """Calculate a focus score out of 10.0 based on context switching and session lengths.
    - Base score: 5.0
    - Context switches per day: penalty of up to 3.0 (switches = unique projects per active day minus 1)
    - Session duration: bonus of up to 5.0 (longer average sessions reflect deeper focus)
    """
    if not sessions:
        return 0.0
        
    # Group sessions by calendar day to find unique projects worked on per day
    projects_by_day = defaultdict(set)
    total_duration = 0
    
    for s in sessions:
        day_str = datetime.fromtimestamp(s.start_time).strftime("%Y-%m-%d")
        projects_by_day[day_str].add(s.project_id)
        total_duration += s.duration_seconds
        
    # Calculate average projects per active day
    active_days = len(projects_by_day)
    if active_days == 0:
        return 0.0
        
    avg_projects = sum(len(p_set) for p_set in projects_by_day.values()) / active_days
    
    # Calculate average session length in minutes
    avg_session_mins = (total_duration / len(sessions)) / 60
    
    # Base score
    score = 6.0
    
    # Penalty: subtract 1.5 points for every project above 1.0 worked on average per day
    switches_penalty = max(0.0, (avg_projects - 1.0) * 1.5)
    score -= switches_penalty
    
    # Bonus: add points for average session length (up to 45 mins = +2.0, up to 90 mins = +4.0)
    duration_bonus = min(4.0, (avg_session_mins / 20.0))
    score += duration_bonus
    
    # Bounded between 0.0 and 10.0, rounded to 1 decimal place
    return round(max(0.0, min(10.0, score)), 1)

def detect_patterns_and_anomalies(sessions: List[Session], projects: List[Project]) -> List[str]:
    """Analyze sessions and commands to generate rule-based developer insights"""
    insights = []
    if not sessions:
        return ["No work data available yet. Start running commands to generate insights!"]
        
    # 1. Busiest and least active days
    day_dist = calculate_day_distribution(sessions)
    active_days = {day: duration for day, duration in day_dist.items() if duration > 0}
    
    if active_days:
        busiest_day = max(active_days.items(), key=lambda x: x[1])
        least_day = min(active_days.items(), key=lambda x: x[1])
        
        busiest_duration = format_duration(busiest_day[1])
        least_duration = format_duration(least_day[1])
        
        insights.append(f"Most productive day: {busiest_day[0]} ({busiest_duration})")
        if busiest_day[0] != least_day[0]:
            insights.append(f"Least active day: {least_day[0]} ({least_duration})")
            
    # 2. Average session duration
    total_seconds = sum(s.duration_seconds for s in sessions)
    avg_session_seconds = int(total_seconds / len(sessions))
    insights.append(f"Your average session duration is {format_duration(avg_session_seconds)} (very consistent)")
    
    # 3. Project focus insights
    time_dist = calculate_time_distribution(sessions, projects)
    if time_dist:
        top_project = time_dist[0]
        insights.append(f"Your longest project focus is on '{top_project[0]}' ({format_duration(top_project[2])})")
        
    # 4. Command patterns
    all_commands = [c for s in sessions for c in s.commands]
    cmd_counts = defaultdict(int)
    for c in all_commands:
        cat = classify_command(c.command)
        cmd_counts[cat] += 1
        
    if cmd_counts:
        sorted_cmds = sorted(cmd_counts.items(), key=lambda x: x[1], reverse=True)
        top_cmd_name = DISPLAY_NAMES.get(sorted_cmds[0][0], sorted_cmds[0][0].capitalize())
        insights.append(f"{top_cmd_name} is your #1 tool ({sorted_cmds[0][1]} executions)")
        
        # Git vs Docker ratio if both exist
        git_count = cmd_counts.get("git", 0)
        docker_count = cmd_counts.get("docker", 0)
        if git_count > 0 and docker_count > 0:
            ratio = round(git_count / docker_count, 1)
            if ratio >= 1.5:
                insights.append(f"You run git {ratio}x more than Docker")
            elif ratio <= 0.7:
                docker_ratio = round(docker_count / git_count, 1)
                insights.append(f"You run docker {docker_ratio}x more than Git")
                
    # 5. Day-of-week context switching anomaly
    # Group sessions by day of week
    switches_by_day = defaultdict(set)
    for s in sessions:
        dt = datetime.fromtimestamp(s.start_time)
        day_name = dt.strftime("%A")
        switches_by_day[day_name].add(s.project_id)
        
    if switches_by_day:
        avg_switches = sum(len(p_set) for p_set in switches_by_day.values()) / len(switches_by_day)
        
        # Check if Friday is particularly focused
        friday_projects = len(switches_by_day.get("Friday", set()))
        if "Friday" in switches_by_day and friday_projects > 0 and friday_projects < avg_switches:
            insights.append("You switch projects less on Fridays compared to other days")
            
    return insights
