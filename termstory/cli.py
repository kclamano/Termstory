import os
import typer
from typing import Optional
from dateutil import parser as date_parser
from datetime import timedelta

from termstory.config import get_history_files, get_db_path
from termstory.parser import parse_all_histories
from termstory.session import create_sessions
from termstory.project import detect_projects
from termstory.database import Database
from termstory.date_utils import (
    get_current_time,
    get_today_range,
    get_week_range,
    get_month_range,
)
from termstory.formatter import (
    format_today_output,
    format_week_output,
    format_month_output,
    format_project_output,
    format_projects_list,
    format_detailed_sessions,
    format_search_results,
    format_insights_output,
    extract_files_from_commands,
    classify_command,
    DISPLAY_NAMES,
)

from rich.console import Console
from rich.table import Table

import sys
import re

# Initialize rich console
console = Console()

def intercept_sys_argv():
    """Intercept positional date arguments (e.g. termstory 2026-06-02) and rewrite them
    to option flags so they do not conflict with subcommands in click/typer"""
    if len(sys.argv) > 1:
        date_pattern = re.compile(r'^\d{4}-\d{2}-\d{2}$')
        first_arg = sys.argv[1]
        if date_pattern.match(first_arg):
            os.environ["TERMSTORY_DATE_OVERRIDE"] = first_arg
            if len(sys.argv) == 2:
                sys.argv[1] = "today"
            else:
                sys.argv.pop(1)

# Execute immediately to intercept arguments before click/typer processes them
intercept_sys_argv()

app = typer.Typer(
    help="TermStory CLI - Parse local shell history and explore your work patterns",
    no_args_is_help=False,
)

def run_ingestion(db: Database) -> None:
    """Helper to parse active history files and store them in the database"""
    history_files = get_history_files()
    if not history_files:
        return
        
    commands = parse_all_histories(history_files)
    sessions = create_sessions(commands)
    projects = detect_projects(sessions)
    db.save_data(projects, sessions, commands)
    
    # Ingest commits from last 90 days for each project
    from termstory.git_integration import get_project_commits
    since_ts = int(get_current_time().timestamp()) - 90 * 24 * 3600
    for p in projects:
        if p.id is not None and p.path:
            commits = get_project_commits(p.path, since_ts)
            if commits:
                db.save_commits(p.id, commits)

@app.command("today")
def show_today(
    detailed: bool = typer.Option(False, "--detailed", help="Show all commands in sessions"),
    compare: bool = typer.Option(False, "--compare", help="Compare with yesterday's work"),
    stats: bool = typer.Option(False, "--stats", help="Show detailed command breakdown stats"),
    story: bool = typer.Option(False, "--story", help="Generate daily AI chronicle narrative story"),
):
    """Display today's sessions, projects, and command statistics"""
    db_path = get_db_path()
    db = Database(db_path)
    db.init_db()
    
    # Ingest newest history entries first
    run_ingestion(db)
    
    # Query today's sessions
    today_sessions = db.get_today_sessions()
    project_ids = list(set(s.project_id for s in today_sessions if s.project_id is not None))
    today_projects = db.get_projects_by_ids(project_ids)
    
    if story:
        from termstory.config import load_config
        from termstory.formatter import generate_daily_activity_punch_card, get_operator_handle
        from termstory.insights import calculate_focus_score, calculate_time_of_day_distribution
        import re
        
        operator = get_operator_handle()
        date_str = get_current_time().strftime("%B %d, %Y")
        
        if not today_sessions:
            console.print("====================================================================")
            console.print("📖 termstory // THE DAILY CHRONICLE")
            console.print("====================================================================")
            console.print(f"OPERATOR: {operator:<20} |  DATE: {date_str}")
            console.print("STATUS: No Activity            |  FOCUS SCORE: 0/100")
            console.print("====================================================================")
            console.print("\nNo terminal activity was logged today. Choose violence against technical debt tomorrow!")
            return
            
        fs = int(calculate_focus_score(today_sessions) * 10)
        tod = calculate_time_of_day_distribution(today_sessions)
        peak_velocity = "morning grinds"
        if tod.get("afternoon", 0) >= tod.get("morning", 0) and tod.get("afternoon", 0) >= tod.get("evening", 0):
            peak_velocity = "afternoon compilation grinds"
        elif tod.get("evening", 0) >= tod.get("morning", 0) and tod.get("evening", 0) >= tod.get("afternoon", 0):
            peak_velocity = "late night grinds"
            
        punch_card = generate_daily_activity_punch_card(today_sessions)
        
        console.print("====================================================================")
        console.print("📖 termstory // THE DAILY CHRONICLE")
        console.print("====================================================================")
        console.print(f"OPERATOR: {operator:<20} |  DATE: {date_str}")
        
        config = load_config()
        ai_enabled = config.get("ai_enabled", False)
        provider = config.get("active_provider", "disabled")
        
        if ai_enabled and provider != "disabled":
            console.print(f"STATUS: Narrative Concluded     |  FOCUS SCORE: {fs}/100")
            console.print("====================================================================")
            console.print("\n📊 TODAY'S ACTIVITY PUNCH-CARD")
            console.print(punch_card)
            console.print(f"(Peak velocity detected during {peak_velocity})\n")
            
            prov_config = config.get("providers", {}).get(provider, {})
            api_key = prov_config.get("api_key", "")
            api_base_url = prov_config.get("api_base_url", "")
            model_name = prov_config.get("model_name", "")
            
            from termstory.ai import generate_daily_chronicle
            story_text = generate_daily_chronicle(
                github_username=operator,
                session_date=date_str,
                sessions=today_sessions,
                projects=today_projects,
                api_key=api_key,
                api_base_url=api_base_url,
                model_name=model_name,
                provider=provider
            )
            if story_text:
                console.print(story_text)
            else:
                console.print("[Failed to generate AI story. Returning local summary.]\n")
                output = format_today_output(today_sessions, today_projects)
                console.print(output)
        else:
            console.print(f"STATUS: Offline / Local Only    |  FOCUS SCORE: {fs}/100")
            console.print("====================================================================")
            console.print("\n📊 TODAY'S ACTIVITY PUNCH-CARD")
            console.print(punch_card)
            console.print(f"(Peak velocity detected during {peak_velocity})\n")
            
            console.print("[AI Narrative disabled. Run 'termstory config set active_provider' to configure Groq/OpenAI/Ollama.]\n")
            output = format_today_output(today_sessions, today_projects)
            console.print(output)
        return

    if detailed:
        output = format_detailed_sessions(today_sessions)
        console.print(output)
        return
        
    if stats:
        # Show detailed command breakdown stats
        all_commands = [c for s in today_sessions for c in s.commands]
        cmd_counts = {}
        for c in all_commands:
            cat = classify_command(c.command)
            cmd_counts[cat] = cmd_counts.get(cat, 0) + 1
            
        from rich.box import ROUNDED
        table = Table(title="📋 Today's Command Stats", box=ROUNDED, border_style="green")
        table.add_column("Command Category", style="cyan bold")
        table.add_column("Count", justify="right", style="green")
        
        for category, count in sorted(cmd_counts.items(), key=lambda x: x[1], reverse=True):
            display_cat = DISPLAY_NAMES.get(category, category)
            table.add_row(display_cat, f"{count} commands")
        console.print(table)
        return
        
    compare_sessions = None
    if compare:
        # Query yesterday's sessions
        today_start, today_end = get_today_range()
        yesterday_start = today_start - 86400
        yesterday_end = today_end - 86400
        compare_sessions = db.get_range_sessions(yesterday_start, yesterday_end)
        
    output = format_today_output(today_sessions, today_projects, compare_sessions=compare_sessions)
    console.print(output)

@app.command("week")
def show_week(
    last: bool = typer.Option(False, "--last", help="Show last week's summary"),
    project: Optional[str] = typer.Option(None, "--project", help="Filter summary by project name"),
    detailed: bool = typer.Option(False, "--detailed", help="Show all commands in sessions"),
):
    """Show weekly work report detailing projects, hours, and days worked"""
    db_path = get_db_path()
    db = Database(db_path)
    db.init_db()
    
    run_ingestion(db)
    
    start_ts, end_ts = get_week_range(last=last)
    sessions = db.get_range_sessions(start_ts, end_ts)
    
    # Filter by project if name was specified
    if project:
        matched_projects = db.search_projects(project)
        matched_ids = {p.id for p in matched_projects if p.id is not None}
        sessions = [s for s in sessions if s.project_id in matched_ids]
        
    # Get associated projects for the sessions
    project_ids = list(set(s.project_id for s in sessions if s.project_id is not None))
    projects = db.get_projects_by_ids(project_ids)
    
    if detailed:
        output = format_detailed_sessions(sessions)
    else:
        output = format_week_output(sessions, projects, start_ts, end_ts)
        
    console.print(output)

@app.command("month")
def show_month(
    month_arg: Optional[str] = typer.Argument(None, help="Specific month/year (e.g. 'June 2026')"),
    last: bool = typer.Option(False, "--last", help="Show last month's summary"),
    detailed: bool = typer.Option(False, "--detailed", help="Show all commands in sessions"),
):
    """Show monthly summary detailing logged days, project time, and averages"""
    db_path = get_db_path()
    db = Database(db_path)
    db.init_db()
    
    run_ingestion(db)
    
    now = get_current_time()
    
    if month_arg:
        try:
            dt = date_parser.parse(month_arg)
            year = dt.year
            month_num = dt.month
        except Exception:
            Console(stderr=True).print(f"[bold red]Error: Could not parse month '{month_arg}'[/]")
            raise typer.Exit(code=1)
    elif last:
        # Go to first of this month and subtract a day
        first_of_month = now.replace(day=1)
        last_month = first_of_month - timedelta(days=1)
        year = last_month.year
        month_num = last_month.month
    else:
        year = now.year
        month_num = now.month
        
    start_ts, end_ts = get_month_range(year, month_num)
    sessions = db.get_range_sessions(start_ts, end_ts)
    
    project_ids = list(set(s.project_id for s in sessions if s.project_id is not None))
    projects = db.get_projects_by_ids(project_ids)
    
    if detailed:
        output = format_detailed_sessions(sessions)
    else:
        output = format_month_output(sessions, projects, year, month_num)
        
    console.print(output)

@app.command("project")
def show_project(
    name: str = typer.Argument(..., help="Fuzzy name matching a project directory"),
    last_week: bool = typer.Option(False, "--last-week", help="Show summary for last week"),
    since: Optional[str] = typer.Option(None, "--since", help="Show summary since YYYY-MM-DD"),
    files: bool = typer.Option(False, "--files", help="Show only the list of related files modified"),
    stats: bool = typer.Option(False, "--stats", help="Show only top command statistics"),
):
    """Show project-specific summary of total time, weekly breakdowns, and edited files"""
    db_path = get_db_path()
    db = Database(db_path)
    db.init_db()
    
    run_ingestion(db)
    
    projects = db.search_projects(name)
    if not projects:
        Console(stderr=True).print(f"[bold red]Error: No project found matching '{name}'[/]")
        raise typer.Exit(code=1)
        
    # Take the first (most relevant) matched project
    project = projects[0]
    
    # Calculate timeframe
    if since:
        try:
            start_ts = int(date_parser.parse(since).timestamp())
            end_ts = int(get_current_time().timestamp())
        except Exception:
            Console(stderr=True).print(f"[bold red]Error: Could not parse date '{since}'[/]")
            raise typer.Exit(code=1)
    elif last_week:
        start_ts, end_ts = get_week_range(last=True)
    else:
        # Default: last 30 days
        start_ts = int((get_current_time() - timedelta(days=30)).timestamp())
        end_ts = int(get_current_time().timestamp())
        
    sessions = db.get_project_sessions(project.id, start_ts)
    sessions = [s for s in sessions if s.start_time <= end_ts]
    
    if files:
        all_commands = [c for s in sessions for c in s.commands]
        file_counts = extract_files_from_commands(all_commands)
        
        from rich.box import ROUNDED
        table = Table(title=f"📁 Files modified in '{project.name}'", box=ROUNDED, border_style="cyan")
        table.add_column("File Name", style="cyan bold")
        table.add_column("Edit Count", justify="right", style="green")
        
        for fname, count in sorted(file_counts.items(), key=lambda x: x[1], reverse=True):
            times_word = "time" if count == 1 else "times"
            table.add_row(fname, f"{count} {times_word}")
        console.print(table)
        return
        
    if stats:
        cmd_counts = {}
        for s in sessions:
            for c in s.commands:
                cat = classify_command(c.command)
                cmd_counts[cat] = cmd_counts.get(cat, 0) + 1
                
        from rich.box import ROUNDED
        table = Table(title=f"📊 Command Stats for project '{project.name}'", box=ROUNDED, border_style="cyan")
        table.add_column("Command Category", style="cyan bold")
        table.add_column("Count", justify="right", style="green")
        
        for category, count in sorted(cmd_counts.items(), key=lambda x: x[1], reverse=True):
            display_cat = DISPLAY_NAMES.get(category, category)
            table.add_row(display_cat, f"{count} times")
        console.print(table)
        return
        
    output = format_project_output(sessions, project)
    console.print(output)

@app.command("projects")
def list_projects(
    sort: str = typer.Option("time", "--sort", help="Sort by: 'time' (total hours), 'recent' (last activity), or 'name' (alphabetically)"),
):
    """List all tracked projects with summaries and lifetimes"""
    db_path = get_db_path()
    db = Database(db_path)
    db.init_db()
    
    run_ingestion(db)
    
    projects = db.get_all_projects_with_stats()
    
    # Filter projects to only those with sessions recorded (to avoid listing empty ones)
    projects = [p for p in projects if p.session_count > 0]
    
    if sort == "recent":
        projects.sort(key=lambda p: p.last_seen, reverse=True)
    elif sort == "name":
        projects.sort(key=lambda p: p.name.lower())
    else:
        # Default: time desc
        projects.sort(key=lambda p: p.total_time, reverse=True)
        
    output = format_projects_list(projects)
    console.print(output)

@app.command("search")
def search_history(
    query: str = typer.Argument(..., help="Search term/query across commits, commands, and project names"),
    project: Optional[str] = typer.Option(None, "--project", help="Filter matches by project name"),
    since: Optional[str] = typer.Option(None, "--since", help="Filter matches since date YYYY-MM-DD"),
    limit: int = typer.Option(50, "--limit", help="Maximum number of search results to return"),
    detailed: bool = typer.Option(False, "--detailed", help="Show all commands and commits in matched sessions"),
):
    """Search across your work history (commits, commands, and projects)"""
    db_path = get_db_path()
    db = Database(db_path)
    db.init_db()
    
    run_ingestion(db)
    
    since_ts = None
    if since:
        try:
            since_ts = int(date_parser.parse(since).timestamp())
        except Exception:
            Console(stderr=True).print(f"[bold red]Error: Could not parse date '{since}'[/]")
            raise typer.Exit(code=1)
            
    results = db.search_sessions(query, project_filter=project, since_ts=since_ts)
    
    # Limit results
    results = results[:limit]
    
    output = format_search_results(query, results, detailed=detailed)
    console.print(output)

@app.command("insights")
def show_insights(
    days: int = typer.Option(30, "--days", help="Number of days to analyze history for insights"),
):
    """Analyze your history and surface focus scores, work patterns, and tool breakdown"""
    db_path = get_db_path()
    db = Database(db_path)
    db.init_db()
    
    run_ingestion(db)
    
    # Calculate timeframe (last N days)
    start_ts = int((get_current_time() - timedelta(days=days)).timestamp())
    
    # Retrieve all sessions in the range
    sessions = db.get_range_sessions(start_ts, int(get_current_time().timestamp()))
    
    # Get associated projects for the sessions
    project_ids = list(set(s.project_id for s in sessions if s.project_id is not None))
    projects = db.get_projects_by_ids(project_ids)
    
    from termstory.insights import (
        calculate_time_distribution,
        calculate_time_of_day_distribution,
        calculate_day_distribution,
        calculate_focus_score,
        detect_patterns_and_anomalies
    )
    
    time_dist = calculate_time_distribution(sessions, projects)
    tod_dist = calculate_time_of_day_distribution(sessions)
    day_dist = calculate_day_distribution(sessions)
    focus_score = calculate_focus_score(sessions)
    patterns = detect_patterns_and_anomalies(sessions, projects)
    
    insights_data = {
        "days": days,
        "focus_score": focus_score,
        "time_dist": time_dist,
        "tod_dist": tod_dist,
        "day_dist": day_dist,
        "patterns": patterns
    }
    
    output = format_insights_output(insights_data)
    console.print(output)

@app.command("ui")
def show_ui(
    days: int = typer.Option(90, "--days", help="Number of days of history to display"),
    all_history: bool = typer.Option(False, "--all", help="Display all recorded history"),
):
    """Launch the interactive terminal dashboard user interface"""
    db_path = get_db_path()
    db = Database(db_path)
    db.init_db()
    
    run_ingestion(db)
    
    from termstory.tui import TermStoryWorkspace
    app_tui = TermStoryWorkspace(db, days_limit=None if all_history else days)
    app_tui.run()


# ==========================================
# CONFIG SUBCOMMANDS
# ==========================================

config_app = typer.Typer(help="Manage TermStory configuration settings")

@config_app.command("set")
def config_set(key: str, value: str):
    """Set a configuration value (supports nested dot notation, e.g. providers.openai.api_key)"""
    from termstory.config import load_config, save_config, set_config_value, get_config_value
    config = load_config()
    
    # Type conversion for booleans
    if key in ("ai_enabled", "has_seen_onboarding") or key.endswith(".ai_enabled") or key.endswith(".has_seen_onboarding"):
        converted_value = value.lower() in ("true", "1", "yes")
    else:
        converted_value = value
        
    set_config_value(config, key, converted_value)
    save_config(config)
    
    set_val = get_config_value(config, key)
    console.print(f"[green]Set config key '{key}' to '{set_val}'[/]")

@config_app.command("get")
def config_get(key: str):
    """Get a configuration value (supports nested dot notation)"""
    from termstory.config import load_config, get_config_value
    config = load_config()
    val = get_config_value(config, key)
    if val is not None:
        console.print(f"{val}")
    else:
        Console(stderr=True).print(f"[bold red]Error: Config key '{key}' not found[/]")
        raise typer.Exit(code=1)

@config_app.command("list")
def config_list():
    """List all current configuration values, flattening nested paths"""
    from termstory.config import load_config
    config = load_config()
    
    def flatten_dict(d: dict, prefix: str = "") -> list:
        items = []
        for k, v in d.items():
            new_key = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                items.extend(flatten_dict(v, new_key))
            else:
                items.append((new_key, v))
        return items

    flat_config = flatten_dict(config)
    
    from rich.box import ROUNDED
    table = Table(title="🔧 TermStory Configuration", box=ROUNDED, border_style="cyan")
    table.add_column("Key", style="cyan bold")
    table.add_column("Value", style="green")
    
    for k, v in sorted(flat_config):
        val_str = str(v)
        # Mask keys that represent an API key
        if ("api_key" in k.lower() or "api-key" in k.lower()) and v:
            val_str = v[:6] + "..." + v[-4:] if len(v) > 10 else "[SET]"
        table.add_row(k, val_str)
        
    console.print(table)

app.add_typer(config_app, name="config")


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    date: Optional[str] = typer.Option(None, "--date", help="Date override (YYYY-MM-DD) for commands"),
):
    """TermStory - local shell history parsing and session summaries"""
    if date:
        try:
            date_parser.parse(date)
            os.environ["TERMSTORY_DATE_OVERRIDE"] = date
        except Exception:
            Console(stderr=True).print(f"[bold red]Error: Invalid date format '{date}'[/]")
            raise typer.Exit(code=1)
            
    if ctx.invoked_subcommand is None:
        # No subcommand, fallback to today's report
        show_today(detailed=False, compare=False, stats=False, story=False)

if __name__ == "__main__":
    app()
