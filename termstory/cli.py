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
    extract_files_from_commands,
    classify_command,
    DISPLAY_NAMES,
)

import sys
import re

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

@app.command("today")
def show_today(
    detailed: bool = typer.Option(False, "--detailed", help="Show all commands in sessions"),
    compare: bool = typer.Option(False, "--compare", help="Compare with yesterday's work"),
    stats: bool = typer.Option(False, "--stats", help="Show detailed command breakdown stats"),
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
    
    if detailed:
        output = format_detailed_sessions(today_sessions)
        typer.echo(output)
        return
        
    if stats:
        # Show detailed command breakdown stats
        all_commands = [c for s in today_sessions for c in s.commands]
        cmd_counts = {}
        for c in all_commands:
            cat = classify_command(c.command)
            cmd_counts[cat] = cmd_counts.get(cat, 0) + 1
            
        typer.echo("📋 Today's Command Stats:")
        for category, count in sorted(cmd_counts.items(), key=lambda x: x[1], reverse=True):
            display_cat = DISPLAY_NAMES.get(category, category)
            typer.echo(f"  {display_cat:<20} {count} commands")
        return
        
    compare_sessions = None
    if compare:
        # Query yesterday's sessions
        today_start, today_end = get_today_range()
        yesterday_start = today_start - 86400
        yesterday_end = today_end - 86400
        compare_sessions = db.get_range_sessions(yesterday_start, yesterday_end)
        
    output = format_today_output(today_sessions, today_projects, compare_sessions=compare_sessions)
    typer.echo(output)

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
        
    typer.echo(output)

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
            typer.echo(f"Error: Could not parse month '{month_arg}'", err=True)
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
        
    typer.echo(output)

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
        typer.echo(f"Error: No project found matching '{name}'", err=True)
        raise typer.Exit(code=1)
        
    # Take the first (most relevant) matched project
    project = projects[0]
    
    # Calculate timeframe
    if since:
        try:
            start_ts = int(date_parser.parse(since).timestamp())
            end_ts = int(get_current_time().timestamp())
        except Exception:
            typer.echo(f"Error: Could not parse date '{since}'", err=True)
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
        typer.echo(f"📁 Files modified in '{project.name}':")
        for fname, count in sorted(file_counts.items(), key=lambda x: x[1], reverse=True):
            times_word = "time" if count == 1 else "times"
            typer.echo(f"  {fname:<30} edited {count} {times_word}")
        return
        
    if stats:
        cmd_counts = {}
        for s in sessions:
            for c in s.commands:
                cat = classify_command(c.command)
                cmd_counts[cat] = cmd_counts.get(cat, 0) + 1
        typer.echo(f"📊 Command Stats for project '{project.name}':")
        for category, count in sorted(cmd_counts.items(), key=lambda x: x[1], reverse=True):
            display_cat = DISPLAY_NAMES.get(category, category)
            typer.echo(f"  {display_cat:<20} {count} times")
        return
        
    output = format_project_output(sessions, project)
    typer.echo(output)

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
    typer.echo(output)

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
            typer.echo(f"Error: Invalid date format '{date}'", err=True)
            raise typer.Exit(code=1)
            
    if ctx.invoked_subcommand is None:
        # No subcommand, fallback to today's report
        show_today(detailed=False, compare=False, stats=False)

if __name__ == "__main__":
    app()
