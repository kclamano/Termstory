import os
import shlex
import calendar
from collections import Counter, defaultdict
from datetime import datetime, timedelta, time
from typing import List, Dict, Tuple, Optional, Any

from termstory.models import Session, Project, Command, format_duration
from termstory.date_utils import get_current_time, format_date_range
from termstory.project import disambiguate_project_names

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.align import Align
from rich.rule import Rule
from rich.text import Text
from rich.box import ROUNDED, MINIMAL, SIMPLE

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

def render_to_string(renderable: Any) -> str:
    """Helper to capture Rich console output as a string"""
    console = Console(width=80)
    with console.capture() as capture:
        console.print(renderable)
    return capture.get().strip()

def make_visual_bar(value: int, max_value: int, width: int = 15) -> str:
    """Generate a colorized visual progress bar using block characters"""
    if max_value <= 0:
        return "[grey37]" + "░" * width + "[/]"
    filled_len = int((value / max_value) * width)
    filled_len = max(0, min(width, filled_len))
    empty_len = width - filled_len
    return f"[bold green]{'█' * filled_len}[/][grey37]{'░' * empty_len}[/]"

def format_today_output(sessions: List[Session], projects: List[Project], compare_sessions: List[Session] = None) -> str:
    """Format today's sessions, command aggregates, and project details as a clean UI card"""
    is_override = "TERMSTORY_DATE_OVERRIDE" in os.environ
    today_str = get_current_time().strftime("%A, %B %d, %Y")
    
    if is_override:
        header_title = f"📋 Report for {today_str}"
    else:
        header_title = f"📋 Today ({today_str})"
        
    if not sessions:
        if is_override:
            return render_to_string(Panel(f"No sessions recorded on {today_str}.", title=header_title, border_style="yellow", box=ROUNDED))
        return render_to_string(Panel("No sessions recorded today.", title=header_title, border_style="yellow", box=ROUNDED))
        
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
    
    elements = []
    
    for idx, p_id in enumerate(project_ids):
        proj_sessions = sessions_by_project[p_id]
        proj_sessions.sort(key=lambda s: s.start_time)
        
        proj_name = "General / No Project"
        if p_id is not None and p_id in display_names:
            proj_name = display_names[p_id]
            
        session_word = "session" if len(proj_sessions) == 1 else "sessions"
        
        total_time_seconds = sum(s.duration_seconds for s in proj_sessions)
        
        compare_str = ""
        if compare_sessions is not None:
            yesterday_seconds = sum(s.duration_seconds for s in compare_sessions if s.project_id == p_id)
            diff = total_time_seconds - yesterday_seconds
            sign = "+" if diff >= 0 else "-"
            diff_color = "green" if diff >= 0 else "red"
            compare_str = f" ([{diff_color}]{sign}{format_duration(abs(diff))}[/] vs yesterday)"
            
        proj_header = [
            f"📁 Project: [bold cyan]{proj_name}[/] ([dim]{len(proj_sessions)} {session_word}[/])",
            f"⏱️  Total Time: [bold green]{format_duration(total_time_seconds)}[/]{compare_str}"
        ]
        
        project_group_items = [Text.from_markup("\n".join(proj_header))]
        
        # Commands Breakdown
        cmd_counts = Counter()
        for s in proj_sessions:
            for cmd in s.commands:
                category = classify_command(cmd.command)
                cmd_counts[category] += 1
                
        if cmd_counts:
            cmd_table = Table(box=None, show_header=False, padding=(0, 2))
            max_count = max(cmd_counts.values()) if cmd_counts else 0
            for category, count in cmd_counts.most_common(5):
                display_cat = DISPLAY_NAMES.get(category, category)
                bar = make_visual_bar(count, max_count, width=15)
                cmd_table.add_row(f"  {display_cat}", bar, f"[bold]{count}[/] times")
                
            project_group_items.append(Text("\n📝 Commands:"))
            project_group_items.append(cmd_table)
            
        # Commits
        proj_commits = []
        seen_hashes = set()
        for s in proj_sessions:
            for commit in s.commits:
                if commit["hash"] not in seen_hashes:
                    seen_hashes.add(commit["hash"])
                    proj_commits.append(commit)
                    
        if proj_commits:
            commit_lines = ["\n💬 Commits:"]
            for c in proj_commits:
                short_hash = c["hash"][:7]
                msg = c["cleaned_message"] or c["message"]
                commit_lines.append(f"  [bold yellow]•[/] [cyan]{short_hash}[/] {msg}")
            project_group_items.append(Text.from_markup("\n".join(commit_lines)))
            
        # Sessions list
        session_lines = ["\n📅 Sessions:"]
        for s in proj_sessions:
            start_str = format_time(s.start_time)
            end_str = format_time(s.end_time)
            dur_str = format_duration(s.duration_seconds)
            session_lines.append(f"  [bold blue]•[/] {start_str} - {end_str} ([dim]{dur_str}[/])")
            
        project_group_items.append(Text.from_markup("\n".join(session_lines)))
        
        # Add to outer element list with rounded panel
        elements.append(Panel(Group(*project_group_items), box=ROUNDED, border_style="blue"))
        
    outer_group = Group(
        Panel(Align.center(f"[bold green]{header_title}[/]"), border_style="green", box=ROUNDED),
        *elements
    )
    
    return render_to_string(outer_group)

def format_week_output(sessions: List[Session], projects: List[Project], start_ts: int, end_ts: int) -> str:
    """Format weekly summary report, grouping project hours by days of the week"""
    range_str = format_date_range(start_ts, end_ts)
    header_title = f"📊 This Week ({range_str})"
    
    if not sessions:
        return render_to_string(Panel("No sessions recorded this week.", title=header_title, border_style="yellow", box=ROUNDED))
        
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
    elements = []
    
    for p_id in project_ids:
        proj_sessions = sessions_by_project[p_id]
        proj_name = "General / No Project"
        if p_id is not None and p_id in display_names:
            proj_name = display_names[p_id]
            
        session_word = "session" if len(proj_sessions) == 1 else "sessions"
        proj_total_time = sum(s.duration_seconds for s in proj_sessions)
        total_week_time += proj_total_time
        
        proj_group_items = [
            Text.from_markup(f"📁 [bold cyan]{proj_name}[/] ([dim]{len(proj_sessions)} {session_word}[/])"),
            Text.from_markup(f"⏱️  Total Time: [bold green]{format_duration(proj_total_time)}[/]\n")
        ]
        
        # Calculate day-by-day breakdown
        day_times = defaultdict(int)
        for s in proj_sessions:
            day_name = datetime.fromtimestamp(s.start_time).strftime('%A')
            day_times[day_name] += s.duration_seconds
            
        days_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        max_day_time = max(day_times.values()) if day_times else 0
        
        day_table = Table(box=None, show_header=False, padding=(0, 2))
        for day in days_order:
            if day_times[day] > 0:
                bar = make_visual_bar(day_times[day], max_day_time, width=15)
                day_table.add_row(f"  {day:<10}", bar, f"[dim]{format_duration(day_times[day])}[/]")
                
        proj_group_items.append(day_table)
        
        # Commands
        cmd_counts = Counter()
        for s in proj_sessions:
            for cmd in s.commands:
                category = classify_command(cmd.command)
                cmd_counts[category] += 1
                
        if cmd_counts:
            cmd_strs = []
            for category, count in cmd_counts.most_common(5):
                display_cat = DISPLAY_NAMES.get(category, category)
                cmd_strs.append(f"[bold]{display_cat}[/] ({count})")
            proj_group_items.append(Text.from_markup("\n[bold]Commands:[/]\n  " + " • ".join(cmd_strs)))
            
        # Commits during this week
        proj_commits = []
        seen_hashes = set()
        for s in proj_sessions:
            for commit in s.commits:
                if commit["hash"] not in seen_hashes:
                    seen_hashes.add(commit["hash"])
                    proj_commits.append(commit)
                    
        if proj_commits:
            commit_lines = ["\n[bold]Commits This Week:[/]"]
            for c in proj_commits[:10]:
                short_hash = c["hash"][:7]
                msg = c["cleaned_message"] or c["message"]
                commit_lines.append(f"  [bold yellow]•[/] [cyan]{short_hash}[/] {msg}")
            if len(proj_commits) > 10:
                commit_lines.append(f"  [dim]... and {len(proj_commits) - 10} more commits[/]")
            proj_group_items.append(Text.from_markup("\n".join(commit_lines)))
            
        elements.append(Panel(Group(*proj_group_items), box=ROUNDED, border_style="blue"))
        
    footer_text = [
        f"📈 Total Work Time This Week: [bold green]{format_duration(total_week_time)}[/]",
        f"📝 Projects: [bold]{len(project_ids)}[/] • Sessions: [bold]{total_week_sessions}[/]"
    ]
    
    outer_group = Group(
        Panel(Align.center(f"[bold green]{header_title}[/]"), border_style="green", box=ROUNDED),
        *elements,
        Panel(Text.from_markup("\n".join(footer_text)), border_style="green")
    )
    
    return render_to_string(outer_group)

def format_month_output(sessions: List[Session], projects: List[Project], year: int, month: int) -> str:
    """Format monthly summary report, listing total times and days worked for each project"""
    month_name = calendar.month_name[month]
    total_days = calendar.monthrange(year, month)[1]
    
    logged_dates = set(datetime.fromtimestamp(s.start_time).date() for s in sessions)
    days_logged = len(logged_dates)
    header_title = f"📊 {month_name} {year} ({days_logged} of {total_days} days logged)"
    
    if not sessions:
        return render_to_string(Panel("No sessions recorded this month.", title=header_title, border_style="yellow", box=ROUNDED))
        
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
    elements = []
    
    for p_id in project_ids:
        proj_sessions = sessions_by_project[p_id]
        proj_name = "General / No Project"
        if p_id is not None and p_id in display_names:
            proj_name = display_names[p_id]
            
        proj_total_time = sum(s.duration_seconds for s in proj_sessions)
        total_month_time += proj_total_time
        
        proj_logged_dates = set(datetime.fromtimestamp(s.start_time).date() for s in proj_sessions)
        days_worked = len(proj_logged_dates)
        day_word = "day" if days_worked == 1 else "days"
        
        sorted_dates = sorted(list(proj_logged_dates))
        days_str = ", ".join(d.strftime("%b %-d") for d in sorted_dates)
        
        proj_group_items = [
            Text.from_markup(f"📁 [bold cyan]{proj_name}[/]"),
            Text.from_markup(f"⏱️  Total: [bold green]{format_duration(proj_total_time)}[/] ({days_worked} {day_word} worked)"),
            Text.from_markup(f"  Days: [dim]{days_str}[/]")
        ]
        
        elements.append(Panel(Group(*proj_group_items), box=ROUNDED, border_style="blue"))
        
    footer_text = [
        f"Total Work Days: [bold]{total_work_days}[/]",
        f"Total Work Time: [bold green]{format_duration(total_month_time)}[/]"
    ]
    if total_work_days > 0:
        avg_per_day = int(total_month_time / total_work_days)
        footer_text.append(f"Average Per Day: [bold yellow]{format_duration(avg_per_day)}[/]")
        
    outer_group = Group(
        Panel(Align.center(f"[bold green]{header_title}[/]"), border_style="green", box=ROUNDED),
        *elements,
        Panel(Text.from_markup("\n".join(footer_text)), border_style="green")
    )
    
    return render_to_string(outer_group)

def format_project_output(sessions: List[Session], project: Project) -> str:
    """Format project-specific detailed history (last 30 days dashboard)"""
    header_title = f"📁 {project.name} (Last 30 Days)"
    
    total_time_seconds = sum(s.duration_seconds for s in sessions)
    session_count = len(sessions)
    unique_days = len(set(datetime.fromtimestamp(s.start_time).date() for s in sessions))
    day_word = "day" if unique_days == 1 else "days"
    
    stats_text = f"⏱️  Total Time: [bold green]{format_duration(total_time_seconds)}[/] • [bold]{session_count}[/] sessions • [bold]{unique_days}[/] {day_word} worked"
    
    elements = [Text.from_markup(stats_text)]
    
    # 1. Group by Week (Monday of each week)
    sessions_by_week = defaultdict(list)
    for s in sessions:
        dt = datetime.fromtimestamp(s.start_time)
        monday = dt - timedelta(days=dt.weekday())
        monday_start = datetime.combine(monday.date(), time.min)
        sessions_by_week[int(monday_start.timestamp())].append(s)
        
    if sessions_by_week:
        week_table = Table(box=None, show_header=False, padding=(0, 2))
        max_week_time = max(sum(s.duration_seconds for s in ws) for ws in sessions_by_week.values()) if sessions_by_week else 0
        sorted_weeks = sorted(list(sessions_by_week.keys()))
        for week_ts in sorted_weeks:
            week_sessions = sessions_by_week[week_ts]
            week_time = sum(s.duration_seconds for s in week_sessions)
            week_start_str = datetime.fromtimestamp(week_ts).strftime("%b %-d")
            s_word = "session" if len(week_sessions) == 1 else "sessions"
            bar = make_visual_bar(week_time, max_week_time, width=15)
            week_table.add_row(f"  Week of {week_start_str}", bar, f"[dim]{format_duration(week_time)} ({len(week_sessions)} {s_word})[/]")
            
        elements.append(Text.from_markup("\n[bold]By Week:[/]"))
        elements.append(week_table)
        
    # 2. Top Commands
    cmd_counts = Counter()
    all_commands = []
    for s in sessions:
        for cmd in s.commands:
            category = classify_command(cmd.command)
            cmd_counts[category] += 1
            all_commands.append(cmd)
            
    if cmd_counts:
        cmd_strs = []
        for category, count in cmd_counts.most_common(5):
            display_cat = DISPLAY_NAMES.get(category, category)
            cmd_strs.append(f"[bold]{display_cat}[/] ({count})")
        elements.append(Text.from_markup("\n[bold]Commands:[/]\n  " + " • ".join(cmd_strs)))
        
    # 3. Commits
    all_commits = []
    seen_hashes = set()
    for s in sessions:
        for commit in s.commits:
            if commit["hash"] not in seen_hashes:
                seen_hashes.add(commit["hash"])
                all_commits.append(commit)
                
    if all_commits:
        all_commits.sort(key=lambda c: c["timestamp"], reverse=True)
        commit_lines = ["\n[bold]Recent Commits:[/]"]
        for c in all_commits[:5]:
            short_hash = c["hash"][:7]
            msg = c["cleaned_message"] or c["message"]
            commit_lines.append(f"  [bold yellow]•[/] [cyan]{short_hash}[/] {msg}")
        elements.append(Text.from_markup("\n".join(commit_lines)))
        
    # 4. Recent Activity (last 5 sessions)
    sorted_sessions = sorted(sessions, key=lambda s: s.start_time, reverse=True)
    recent_sessions = sorted_sessions[:5]
    if recent_sessions:
        activity_lines = ["\n[bold]Recent Activity:[/]"]
        for s in recent_sessions:
            date_str = datetime.fromtimestamp(s.start_time).strftime("%b %-d")
            start_str = format_time(s.start_time)
            end_str = format_time(s.end_time)
            dur_str = format_duration(s.duration_seconds)
            
            types = list(set(classify_command(c.command) for c in s.commands))
            types_str = ", ".join(DISPLAY_NAMES.get(t, t) for t in types[:3])
            act_info = f"  {date_str}, {start_str} - {end_str} ([bold green]{dur_str}[/])"
            if types_str:
                act_info += f" - [dim]{types_str}[/]"
            activity_lines.append(act_info)
        elements.append(Text.from_markup("\n".join(activity_lines)))
        
    # 5. Related Files
    file_counts = extract_files_from_commands(all_commands)
    if file_counts:
        file_lines = ["\n[bold]Related Files:[/]"]
        sorted_files = sorted(file_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        for fname, count in sorted_files:
            times_word = "time" if count == 1 else "times"
            file_lines.append(f"  [bold cyan]{fname}[/] (edited {count} {times_word})")
        elements.append(Text.from_markup("\n".join(file_lines)))
        
    outer_group = Group(
        Panel(Align.center(f"[bold green]{header_title}[/]"), border_style="green", box=ROUNDED),
        Panel(Group(*elements), box=ROUNDED, border_style="blue")
    )
    
    return render_to_string(outer_group)

def format_projects_list(projects: List[Project]) -> str:
    """Format all-time projects list card"""
    header_title = "📚 Your Projects (All Time)"
    
    if not projects:
        return render_to_string(Panel("No projects found.", title=header_title, border_style="yellow", box=ROUNDED))
        
    total_time = sum(p.total_time for p in projects)
    total_sessions = sum(p.session_count for p in projects)
    
    table = Table(box=ROUNDED, border_style="blue", show_header=True)
    table.add_column("#", justify="right", style="dim")
    table.add_column("Project", style="cyan bold")
    table.add_column("Total Time", style="green")
    table.add_column("Sessions", justify="right")
    table.add_column("Active Range", style="dim")
    
    display_names = disambiguate_project_names(projects)
    for idx, p in enumerate(projects, 1):
        name = display_names.get(p.id, p.name)
        first_str = datetime.fromtimestamp(p.first_seen).strftime("%b %-d, %Y")
        last_str = datetime.fromtimestamp(p.last_seen).strftime("%b %-d, %Y")
        table.add_row(
            str(idx),
            name,
            format_duration(p.total_time),
            str(p.session_count),
            f"{first_str} - {last_str}"
        )
        
    footer_text = f"Total: [bold]{len(projects)}[/] projects, [bold]{total_sessions}[/] sessions, [bold green]{format_duration(total_time)}[/] worked"
    
    outer_group = Group(
        Panel(Align.center(f"[bold green]{header_title}[/]"), border_style="green", box=ROUNDED),
        table,
        Panel(Text.from_markup(footer_text), border_style="green")
    )
    
    return render_to_string(outer_group)

def format_detailed_sessions(sessions: List[Session]) -> str:
    """Detailed formatting showing all commands inside each session"""
    if not sessions:
        return "No sessions found."
        
    group_elements = []
    for idx, s in enumerate(sessions, 1):
        start_str = format_time(s.start_time)
        end_str = format_time(s.end_time)
        dur_str = format_duration(s.duration_seconds)
        date_str = datetime.fromtimestamp(s.start_time).strftime("%B %d, %Y")
        
        session_title = f"SESSION {idx}: [bold]{start_str} - {end_str}[/] ([bold green]{dur_str}[/]) on [bold cyan]{date_str}[/]"
        
        table = Table(box=SIMPLE, show_header=True)
        table.add_column("Time", style="dim", width=10)
        table.add_column("Command", style="bold yellow")
        table.add_column("Exit Code", justify="right", width=10)
        
        for cmd in s.commands:
            t_str = datetime.fromtimestamp(cmd.timestamp).strftime("%H:%M:%S")
            exit_style = "green" if cmd.exit_code == 0 else "bold red"
            table.add_row(t_str, cmd.command, f"[{exit_style}]{cmd.exit_code}[/]")
            
        # If there are commits in this session, show them too!
        commit_group = None
        if s.commits:
            commit_table = Table(box=SIMPLE, show_header=True)
            commit_table.add_column("Hash", style="cyan", width=8)
            commit_table.add_column("Commit Message")
            for c in s.commits:
                commit_table.add_row(c["hash"][:7], c["cleaned_message"] or c["message"])
            commit_group = commit_table
            
        session_group = [Text.from_markup(session_title), table]
        if commit_group:
            session_group.append(Text("\nCommits in Session:"))
            session_group.append(commit_group)
            
        group_elements.append(Panel(Group(*session_group), box=ROUNDED, border_style="blue"))
        
    return render_to_string(Group(*group_elements))

def format_search_results(query: str, results: List[Dict]) -> str:
    """Format matching search sessions and highlight key elements"""
    header_title = f"🔍 Search Results for '{query}'"
    
    if not results:
        return render_to_string(Panel(f"No results found matching '{query}'.", title=header_title, border_style="yellow", box=ROUNDED))
        
    elements = []
    total_matched_time = 0
    
    for idx, r in enumerate(results, 1):
        s_id = r["session_id"]
        start_str = format_time(r["start_time"])
        end_str = format_time(r["end_time"])
        date_str = datetime.fromtimestamp(r["start_time"]).strftime("%B %d, %Y")
        dur_str = format_duration(r["duration_seconds"])
        total_matched_time += r["duration_seconds"]
        
        proj_name = r["project_name"]
        
        session_header = f"MATCH {idx}: Session {s_id} on [bold]{date_str}[/] ({start_str} - {end_str}) [[bold green]{dur_str}[/]]"
        proj_line = f"📁 Project: [bold cyan]{proj_name}[/]"
        
        session_group_items = [
            Text.from_markup(session_header),
            Text.from_markup(proj_line)
        ]
        
        # Highlight matching commands
        import re
        escaped_query = re.escape(query)
        if r["matching_commands"]:
            cmd_lines = ["\n[bold yellow]Matching Commands:[/]"]
            for cmd in r["matching_commands"]:
                highlighted = re.sub(escaped_query, r"[bold red]\g<0>[/]", cmd, flags=re.IGNORECASE)
                cmd_lines.append(f"  • {highlighted}")
            session_group_items.append(Text.from_markup("\n".join(cmd_lines)))
            
        # Highlight matching commits
        if r["matching_commits"]:
            commit_lines = ["\n[bold cyan]Matching Commits:[/]"]
            for c in r["matching_commits"]:
                short_hash = c["hash"][:7]
                msg = c["cleaned_message"] or c["message"]
                highlighted = re.sub(escaped_query, r"[bold red]\g<0>[/]", msg, flags=re.IGNORECASE)
                commit_lines.append(f"  • [cyan]{short_hash}[/] {highlighted}")
            session_group_items.append(Text.from_markup("\n".join(commit_lines)))
            
        elements.append(Panel(Group(*session_group_items), box=ROUNDED, border_style="blue"))
        
    footer_text = [
        f"📈 Total Results: [bold]{len(results)}[/] sessions matched",
        f"⏱️  Total Matched Work Time: [bold green]{format_duration(total_matched_time)}[/]"
    ]
    
    outer_group = Group(
        Panel(Align.center(f"[bold green]{header_title}[/]"), border_style="green", box=ROUNDED),
        *elements,
        Panel(Text.from_markup("\n".join(footer_text)), border_style="green")
    )
    
    return render_to_string(outer_group)

def format_insights_output(insights: Dict) -> str:
    """Format the developer work patterns insights report"""
    days = insights.get("days", 30)
    header_title = f"💡 Developer Insights & Work Patterns (Last {days} Days)"
    
    score = insights.get("focus_score", 0.0)
    # Focus Score Bar
    filled_score = int(score)
    empty_score = 10 - filled_score
    score_bar = f"[bold green]{'█' * filled_score}[/][grey37]{'░' * empty_score}[/]"
    
    score_desc = "Standard focus"
    if score >= 8.5:
        score_desc = "Exceptional deep focus"
    elif score >= 7.0:
        score_desc = "Good focused work"
    elif score < 4.0:
        score_desc = "High context switching"
        
    score_panel_text = f"Focus Score: [bold green]{score} / 10.0[/] ({score_desc})\n{score_bar}"
    
    elements = [
        Panel(Text.from_markup(score_panel_text), title="🎯 Concentration Score", border_style="green", box=ROUNDED),
        Text("")
    ]
    
    # Project Time Distribution
    time_dist = insights.get("time_dist", [])
    if time_dist:
        dist_table = Table(box=None, show_header=True, padding=(0, 2), title="📁 Project Focus Distribution", title_justify="left")
        dist_table.add_column("Project", style="cyan bold")
        dist_table.add_column("Allocation Bar")
        dist_table.add_column("Percentage", justify="right")
        dist_table.add_column("Total Time", justify="right")
        
        max_pct = max(item[1] for item in time_dist) if time_dist else 100
        for proj, pct, dur in time_dist:
            bar = make_visual_bar(int(pct), int(max_pct), width=15)
            dist_table.add_row(proj, bar, f"{pct:.1f}%", format_duration(dur))
            
        elements.append(dist_table)
        elements.append(Text(""))
        
    # Time of Day Allocation
    tod_dist = insights.get("tod_dist", {})
    if tod_dist:
        tod_table = Table(box=None, show_header=True, padding=(0, 2), title="🌅 Hourly Time-of-Day Split", title_justify="left")
        tod_table.add_column("Time Period", style="yellow bold")
        tod_table.add_column("Allocation Bar")
        tod_table.add_column("Total Time", justify="right")
        
        total_tod = sum(tod_dist.values())
        max_tod = max(tod_dist.values()) if tod_dist else 0
        periods = [
            ("Morning (6 AM - 12 PM)", tod_dist.get("morning", 0)),
            ("Afternoon (12 PM - 6 PM)", tod_dist.get("afternoon", 0)),
            ("Evening/Night (6 PM - 6 AM)", tod_dist.get("evening", 0))
        ]
        for name, duration in periods:
            bar = make_visual_bar(duration, max_tod, width=15)
            tod_table.add_row(name, bar, format_duration(duration))
            
        elements.append(tod_table)
        elements.append(Text(""))
        
    # Day of Week Distribution
    day_dist = insights.get("day_dist", {})
    if day_dist:
        day_table = Table(box=None, show_header=True, padding=(0, 2), title="📅 Day-of-Week Work Distribution", title_justify="left")
        day_table.add_column("Day", style="blue bold")
        day_table.add_column("Activity Bar")
        day_table.add_column("Total Time", justify="right")
        
        max_day = max(day_dist.values()) if day_dist else 0
        days_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        for day in days_order:
            duration = day_dist.get(day, 0)
            if duration > 0:
                bar = make_visual_bar(duration, max_day, width=15)
                day_table.add_row(day, bar, format_duration(duration))
                
        elements.append(day_table)
        elements.append(Text(""))
        
    # Patterns and Observations
    patterns = insights.get("patterns", [])
    if patterns:
        pattern_lines = ["[bold]Observed Patterns & Insights:[/]\n"]
        for p in patterns:
            pattern_lines.append(f"  [bold green]✓[/] {p}")
        elements.append(Text.from_markup("\n".join(pattern_lines)))
        
    outer_group = Group(
        Panel(Align.center(f"[bold green]{header_title}[/]"), border_style="green", box=ROUNDED),
        Panel(Group(*elements), box=ROUNDED, border_style="blue")
    )
    
    return render_to_string(outer_group)
