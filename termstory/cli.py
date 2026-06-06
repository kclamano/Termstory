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
from termstory.date_utils import get_current_time
from termstory.formatter import format_search_results

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
        # Intercept -reset and rewrite it to --reset
        for i in range(1, len(sys.argv)):
            if sys.argv[i] == "-reset":
                sys.argv[i] = "--reset"

        date_pattern = re.compile(r'^\d{4}-\d{2}-\d{2}$')
        first_arg = sys.argv[1]
        if date_pattern.match(first_arg):
            os.environ["TERMSTORY_DATE_OVERRIDE"] = first_arg
            if len(sys.argv) == 2:
                sys.argv[1] = "today"
            else:
                sys.argv.pop(1)

# Will be executed via main_entry() to intercept arguments before click/typer processes them

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

def perform_reset():
    """Reset all TermStory state, configuration, and database files on disk"""
    import shutil
    from termstory.config import get_app_dir
    dirs_to_clean = {get_app_dir("config"), get_app_dir("data")}
    for db_dir in dirs_to_clean:
        if os.path.exists(db_dir):
            try:
                for filename in os.listdir(db_dir):
                    file_path = os.path.join(db_dir, filename)
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)
            except Exception:
                pass
    console.print("\n[bold green]✨ TermStory state, configuration, and database have been successfully reset![/]")

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
    
    if getattr(app_tui, "was_reset", False):
        perform_reset()

@app.command("reset")
def reset_cmd():
    """Reset all TermStory state, configuration, and database"""
    perform_reset()




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
    reset: bool = typer.Option(False, "--reset", help="Reset all TermStory state, configuration, and database"),
):
    """TermStory - local shell history parsing and session summaries"""
    if reset:
        perform_reset()
        raise typer.Exit()

    if date:
        try:
            date_parser.parse(date)
            os.environ["TERMSTORY_DATE_OVERRIDE"] = date
        except Exception:
            Console(stderr=True).print(f"[bold red]Error: Invalid date format '{date}'[/]")
            raise typer.Exit(code=1)
            
    if ctx.invoked_subcommand is None:
        # No subcommand, fallback to today's report
        show_ui()

def main_entry():
    intercept_sys_argv()
    app()

def cli():
    main_entry()

if __name__ == "__main__":
    main_entry()
