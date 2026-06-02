import os
import shlex
import calendar
from collections import Counter, defaultdict
from datetime import datetime, timedelta, time
from typing import List, Dict, Tuple
from termstory.models import Session, Project, Command, format_duration
from termstory.date_utils import get_current_time, format_date_range
from termstory.project import disambiguate_project_names

DISPLAY_NAMES = {
    "git": "Git",
    "docker": "Docker",
    "npm": "NPM/Yarn/PNPM",
    "python": "Python",
    "maven": "Maven",
    "vim": "Editor (Vim/Nano/etc)",
}

def classify_command(cmd_text: str) -> str:
    """Classify the command type based on the executable name"""
    tokens = cmd_text.strip().split()
    if not tokens:
        return "other"
        
    first_token = tokens[0].lower()
    
    if len(tokens) > 1 and first_token == "docker" and tokens[1].lower() == "compose":
        return "docker"
        
    classifications = {
        "git": ["git", "gh"],
        "docker": ["docker", "docker-compose"],
        "npm": ["npm", "yarn", "pnpm", "npx"],
        "python": ["python", "python3", "pip", "pip3", "pytest", "poetry"],
        "maven": ["mvn", "maven"],
        "vim": ["vim", "vi", "nano", "emacs"],
    }
    
    for category, triggers in classifications.items():
        if first_token in triggers:
            return category
            
    return first_token

def format_time(timestamp: int) -> str:
    """Format Unix timestamp to 12-hour local time format without leading zeroes, e.g. '9:00 AM'"""
    dt = datetime.fromtimestamp(timestamp)
    time_str = dt.strftime("%I:%M %p")
    if time_str.startswith("0"):
        time_str = time_str[1:]
    return time_str

def extract_files_from_commands(commands: List[Command]) -> Dict[str, int]:
    """Helper to extract edited files from command line arguments of editors (vim, nano, code, etc.)"""
    file_counts = Counter()
    editor_executables = {"vim", "vi", "nano", "emacs", "code"}
    
    for cmd in commands:
        try:
            tokens = shlex.split(cmd.command)
        except Exception:
            tokens = cmd.command.split()
            
        if not tokens:
            continue
            
        exec_name = os.path.basename(tokens[0].lower())
        if exec_name in editor_executables:
            # Arguments are likely file paths. Skip flags
            files = [t for t in tokens[1:] if not t.startswith('-')]
            for f in files:
                base = os.path.basename(f)
                if base:
                    file_counts[base] += 1
    return dict(file_counts)

def format_today_output(sessions: List[Session], projects: List[Project], compare_sessions: List[Session] = None) -> str:
    """Format today's sessions, command aggregates, and project details as a clean UI card"""
    is_override = "TERMSTORY_DATE_OVERRIDE" in os.environ
    
    if not sessions:
        if is_override:
            date_str = get_current_time().strftime("%A, %B %d, %Y")
            return f"No sessions recorded on {date_str}."
        return "No sessions recorded today."
        
    today_str = get_current_time().strftime("%A, %B %d, %Y")
    
    display_names = disambiguate_project_names(projects)
    project_map = {p.id: p for p in projects if p.id is not None}
    
    sessions_by_project = defaultdict(list)
    for s in sessions:
        sessions_by_project[s.project_id].append(s)
        
    if is_override:
        header_title = f"📋 Report for {today_str}"
    else:
        header_title = f"📋 Today ({today_str})"
    border = "─" * (len(header_title) + 2)
    output = []
    output.append(f"╭{border}╮")
    output.append(f"│ {header_title} │")
    output.append(f"╰{border}╯\n")
    
    project_ids = list(sessions_by_project.keys())
    
    def project_sort_key(p_id):
        if p_id is None:
            return (1, "")
        p = project_map.get(p_id)
        name = p.name if p else ""
        return (0, name)
        
    project_ids.sort(key=project_sort_key)
    
    for p_id in project_ids:
        proj_sessions = sessions_by_project[p_id]
        proj_sessions.sort(key=lambda s: s.start_time)
        
        proj_name = "General / No Project"
        if p_id is not None and p_id in display_names:
            proj_name = display_names[p_id]
            
        session_word = "session" if len(proj_sessions) == 1 else "sessions"
        output.append(f"📁 Project: {proj_name} ({len(proj_sessions)} {session_word})")
        
        total_time_seconds = sum(s.duration_seconds for s in proj_sessions)
        
        compare_str = ""
        if compare_sessions is not None:
            yesterday_seconds = sum(s.duration_seconds for s in compare_sessions if s.project_id == p_id)
            diff = total_time_seconds - yesterday_seconds
            sign = "+" if diff >= 0 else "-"
            compare_str = f" ({sign}{format_duration(abs(diff))} vs yesterday)"
            
        output.append(f"⏱️  Total Time: {format_duration(total_time_seconds)}{compare_str}")
        
        cmd_counts = Counter()
        for s in proj_sessions:
            for cmd in s.commands:
                category = classify_command(cmd.command)
                cmd_counts[category] += 1
                
        if cmd_counts:
            output.append("\n📝 Commands:")
            for category, count in cmd_counts.most_common(5):
                display_cat = DISPLAY_NAMES.get(category, category)
                output.append(f"  {display_cat:<20} {count} times")
                
        output.append("\n📅 Sessions:")
        for s in proj_sessions:
            start_str = format_time(s.start_time)
            end_str = format_time(s.end_time)
            dur_str = format_duration(s.duration_seconds)
            output.append(f"  {start_str} - {end_str} ({dur_str})")
            
        output.append("\n" + "─" * 40 + "\n")
        
    if output and output[-1] == "\n" + "─" * 40 + "\n":
        output.pop()
        
    return "\n".join(output).strip()

def format_week_output(sessions: List[Session], projects: List[Project], start_ts: int, end_ts: int) -> str:
    """Format weekly summary report, grouping project hours by days of the week"""
    range_str = format_date_range(start_ts, end_ts)
    
    header_title = f"📊 This Week ({range_str})"
    border = "─" * (len(header_title) + 2)
    output = []
    output.append(f"╭{border}╮")
    output.append(f"│ {header_title} │")
    output.append(f"╰{border}╯\n")
    
    if not sessions:
        output.append("No sessions recorded this week.")
        return "\n".join(output)
        
    display_names = disambiguate_project_names(projects)
    project_map = {p.id: p for p in projects if p.id is not None}
    
    sessions_by_project = defaultdict(list)
    for s in sessions:
        sessions_by_project[s.project_id].append(s)
        
    project_ids = list(sessions_by_project.keys())
    
    def project_sort_key(p_id):
        if p_id is None:
            return (1, "")
        p = project_map.get(p_id)
        name = p.name if p else ""
        return (0, name)
        
    project_ids.sort(key=project_sort_key)
    
    total_week_time = 0
    total_week_sessions = len(sessions)
    
    for p_id in project_ids:
        proj_sessions = sessions_by_project[p_id]
        proj_name = "General / No Project"
        if p_id is not None and p_id in display_names:
            proj_name = display_names[p_id]
            
        session_word = "session" if len(proj_sessions) == 1 else "sessions"
        output.append(f"📁 {proj_name} ({len(proj_sessions)} {session_word})")
        
        proj_total_time = sum(s.duration_seconds for s in proj_sessions)
        total_week_time += proj_total_time
        output.append(f"⏱️  Total Time: {format_duration(proj_total_time)}")
        
        # Calculate day-by-day breakdown
        day_times = defaultdict(int)
        for s in proj_sessions:
            day_name = datetime.fromtimestamp(s.start_time).strftime('%A')
            day_times[day_name] += s.duration_seconds
            
        days_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        for day in days_order:
            if day_times[day] > 0:
                output.append(f"  {day:<10} {format_duration(day_times[day])}")
                
        # Command counts
        cmd_counts = Counter()
        for s in proj_sessions:
            for cmd in s.commands:
                category = classify_command(cmd.command)
                cmd_counts[category] += 1
                
        if cmd_counts:
            cmd_strs = []
            for category, count in cmd_counts.most_common(5):
                display_cat = DISPLAY_NAMES.get(category, category)
                cmd_strs.append(f"{display_cat} ({count})")
            output.append("\nCommands:")
            output.append("  " + " • ".join(cmd_strs))
            
        output.append("\n" + "─" * 40 + "\n")
        
    if output and output[-1] == "\n" + "─" * 40 + "\n":
        output.pop()
        
    output.append("─" * 49)
    output.append(f"📈 Total Work Time This Week: {format_duration(total_week_time)}")
    output.append(f"📝 Projects: {len(project_ids)} • Sessions: {total_week_sessions}")
    
    return "\n".join(output).strip()

def format_month_output(sessions: List[Session], projects: List[Project], year: int, month: int) -> str:
    """Format monthly summary report, listing total times and days worked for each project"""
    month_name = calendar.month_name[month]
    total_days = calendar.monthrange(year, month)[1]
    
    logged_dates = set(datetime.fromtimestamp(s.start_time).date() for s in sessions)
    days_logged = len(logged_dates)
    
    header_title = f"📊 {month_name} {year} ({days_logged} of {total_days} days logged)"
    border = "─" * (len(header_title) + 2)
    output = []
    output.append(f"╭{border}╮")
    output.append(f"│ {header_title} │")
    output.append(f"╰{border}╯\n")
    
    if not sessions:
        output.append("No sessions recorded this month.")
        return "\n".join(output)
        
    display_names = disambiguate_project_names(projects)
    project_map = {p.id: p for p in projects if p.id is not None}
    
    sessions_by_project = defaultdict(list)
    for s in sessions:
        sessions_by_project[s.project_id].append(s)
        
    project_ids = list(sessions_by_project.keys())
    
    def project_sort_key(p_id):
        if p_id is None:
            return (1, "")
        p = project_map.get(p_id)
        name = p.name if p else ""
        return (0, name)
        
    project_ids.sort(key=project_sort_key)
    
    total_month_time = 0
    total_work_days = len(logged_dates)
    
    for p_id in project_ids:
        proj_sessions = sessions_by_project[p_id]
        proj_name = "General / No Project"
        if p_id is not None and p_id in display_names:
            proj_name = display_names[p_id]
            
        output.append(f"📁 {proj_name}")
        
        proj_total_time = sum(s.duration_seconds for s in proj_sessions)
        total_month_time += proj_total_time
        
        proj_logged_dates = set(datetime.fromtimestamp(s.start_time).date() for s in proj_sessions)
        days_worked = len(proj_logged_dates)
        day_word = "day" if days_worked == 1 else "days"
        
        output.append(f"⏱️  Total: {format_duration(proj_total_time)} ({days_worked} {day_word} worked)")
        
        # Format the list of unique days worked, e.g. "Jun 2, Jun 3"
        sorted_dates = sorted(list(proj_logged_dates))
        days_str = ", ".join(d.strftime("%b %-d") for d in sorted_dates)
        output.append(f"  Days: {days_str}")
        
        output.append("\n" + "─" * 40 + "\n")
        
    if output and output[-1] == "\n" + "─" * 40 + "\n":
        output.pop()
        
    # Stats footer
    output.append("─" * 49)
    output.append(f"Total Work Days: {total_work_days}")
    output.append(f"Total Work Time: {format_duration(total_month_time)}")
    if total_work_days > 0:
        avg_per_day = int(total_month_time / total_work_days)
        output.append(f"Average Per Day: {format_duration(avg_per_day)}")
        
    return "\n".join(output).strip()

def format_project_output(sessions: List[Session], project: Project) -> str:
    """Format project-specific detailed history (last 30 days dashboard)"""
    header_title = f"📁 {project.name} (Last 30 Days)"
    border = "─" * (len(header_title) + 2)
    output = []
    output.append(f"╭{border}╮")
    output.append(f"│ {header_title} │")
    output.append(f"╰{border}╯\n")
    
    total_time_seconds = sum(s.duration_seconds for s in sessions)
    session_count = len(sessions)
    unique_days = len(set(datetime.fromtimestamp(s.start_time).date() for s in sessions))
    
    day_word = "day" if unique_days == 1 else "days"
    output.append(f"⏱️  Total Time: {format_duration(total_time_seconds)} • {session_count} sessions • {unique_days} {day_word} worked\n")
    
    # 1. Group by Week (Monday of each week)
    sessions_by_week = defaultdict(list)
    for s in sessions:
        # Find Monday of that week
        dt = datetime.fromtimestamp(s.start_time)
        monday = dt - timedelta(days=dt.weekday())
        monday_start = datetime.combine(monday.date(), time.min)
        sessions_by_week[int(monday_start.timestamp())].append(s)
        
    if sessions_by_week:
        output.append("By Week:")
        sorted_weeks = sorted(list(sessions_by_week.keys()))
        for week_ts in sorted_weeks:
            week_sessions = sessions_by_week[week_ts]
            week_time = sum(s.duration_seconds for s in week_sessions)
            week_start_str = datetime.fromtimestamp(week_ts).strftime("%b %-d")
            s_word = "session" if len(week_sessions) == 1 else "sessions"
            output.append(f"  Week of {week_start_str}: {format_duration(week_time)} ({len(week_sessions)} {s_word})")
        output.append("")
        
    # 2. Top Commands
    cmd_counts = Counter()
    all_commands = []
    for s in sessions:
        for cmd in s.commands:
            category = classify_command(cmd.command)
            cmd_counts[category] += 1
            all_commands.append(cmd)
            
    if cmd_counts:
        output.append("Commands:")
        cmd_strs = []
        for category, count in cmd_counts.most_common(5):
            display_cat = DISPLAY_NAMES.get(category, category)
            cmd_strs.append(f"{display_cat} ({count})")
        output.append("  " + " • ".join(cmd_strs) + "\n")
        
    # 3. Recent Activity (last 5 sessions)
    sorted_sessions = sorted(sessions, key=lambda s: s.start_time, reverse=True)
    recent_sessions = sorted_sessions[:5]
    if recent_sessions:
        output.append("Recent Activity:")
        for s in recent_sessions:
            date_str = datetime.fromtimestamp(s.start_time).strftime("%b %-d")
            start_str = format_time(s.start_time)
            end_str = format_time(s.end_time)
            dur_str = format_duration(s.duration_seconds)
            
            # Get main command types in this session
            types = list(set(classify_command(c.command) for c in s.commands))
            types_str = ", ".join(DISPLAY_NAMES.get(t, t) for t in types[:3])
            
            output.append(f"  {date_str}, {start_str} - {end_str} ({dur_str})")
            if types_str:
                output.append(f"    {types_str}")
        output.append("")
        
    # 4. Related Files
    file_counts = extract_files_from_commands(all_commands)
    if file_counts:
        output.append("Related Files:")
        sorted_files = sorted(file_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        for fname, count in sorted_files:
            times_word = "time" if count == 1 else "times"
            output.append(f"  {fname} (edited {count} {times_word})")
            
    return "\n".join(output).strip()

def format_projects_list(projects: List[Project]) -> str:
    """Format all-time projects list card"""
    header_title = "📚 Your Projects (All Time)"
    border = "─" * (len(header_title) + 2)
    output = []
    output.append(f"╭{border}╮")
    output.append(f"│ {header_title} │")
    output.append(f"╰{border}╯\n")
    
    if not projects:
        output.append("No projects found.")
        return "\n".join(output)
        
    total_time = sum(p.total_time for p in projects)
    total_sessions = sum(p.session_count for p in projects)
    
    # Display projects list
    display_names = disambiguate_project_names(projects)
    for idx, p in enumerate(projects, 1):
        name = display_names.get(p.id, p.name)
        output.append(f"{idx}. {name}")
        output.append(f"   ⏱️  {format_duration(p.total_time)} total • {p.session_count} sessions")
        first_str = datetime.fromtimestamp(p.first_seen).strftime("%b %-d, %Y")
        last_str = datetime.fromtimestamp(p.last_seen).strftime("%b %-d, %Y")
        output.append(f"   📅 {first_str} - {last_str}\n")
        
    if output and output[-1] == "\n":
        output.pop()
        
    output.append("─" * 49)
    output.append(f"Total: {len(projects)} projects, {total_sessions} sessions, {format_duration(total_time)} worked")
    
    return "\n".join(output).strip()

def format_detailed_sessions(sessions: List[Session]) -> str:
    """Detailed formatting showing all commands inside each session"""
    output = []
    for idx, s in enumerate(sessions, 1):
        start_str = format_time(s.start_time)
        end_str = format_time(s.end_time)
        dur_str = format_duration(s.duration_seconds)
        date_str = datetime.fromtimestamp(s.start_time).strftime("%B %d, %Y")
        
        output.append(f"SESSION {idx}: {start_str} - {end_str} ({dur_str}) on {date_str}")
        
        output.append("Commands:")
        for cmd in s.commands:
            t_str = datetime.fromtimestamp(cmd.timestamp).strftime("%H:%M:%S")
            output.append(f"  {t_str} │ {cmd.command}")
        output.append("")
        
    return "\n".join(output).strip()
