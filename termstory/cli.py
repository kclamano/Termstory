import os
import typer
from typing import Optional
from dateutil import parser as date_parser

from termstory.config import get_history_files, get_db_path
from termstory.parser import parse_all_histories
from termstory.session import create_sessions
from termstory.project import detect_projects
from termstory.database import Database
from termstory.date_utils import get_current_time, get_today_range
from termstory.formatter import format_search_results, format_today_output, format_project_output, format_insights_output
import sqlite3

from rich.console import Console
from rich.table import Table

import sys
import re

# Initialize rich console
console = Console()

def safe_init_db(db: Database) -> None:
    try:
        db.init_db()
    except sqlite3.DatabaseError as e:
        import time
        db_path = db.db_path
        if os.path.exists(db_path):
            backup_path = f"{db_path}.corrupt.{int(time.time())}.bak"
            os.rename(db_path, backup_path)
            Console(stderr=True).print(
                f"\n[bold yellow]Database Corrupted[/bold yellow]\n"
                f"Your TermStory database was corrupted. It has been moved to {backup_path}.\n"
                "Initializing a fresh database..."
            )
            db.init_db()
        else:
            Console(stderr=True).print(
                "\n[bold red]Database Error[/bold red]\n"
                f"Could not initialize database: {e}"
            )
            sys.exit(1)

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
        # Case A — no history files found at all (truly fresh setup)
        Console(stderr=True).print(
            "\n[bold yellow]⚠️  No shell history files found.[/bold yellow]\n"
            "It looks like this might be a fresh setup. Open your terminal and run a few\n"
            "commands first, then re-run `termstory ui` to see your history.\n"
            "Tip: Add `setopt EXTENDED_HISTORY` to ~/.zshrc now so timestamps are recorded from the start.\n"
        )
        return
        
    # Case B — history file(s) exist but every one is empty (terminal opened,
    # but no commands ever typed)
    if all(os.path.getsize(path) == 0 for path in history_files):
        Console(stderr=True).print(
            "\n[bold yellow]⚠️  Your shell history file exists but is empty.[/bold yellow]\n"
            "Run some commands in your terminal first, then re-run `termstory ui`.\n"
        )
        return
        
    def discover_project_paths():
        import glob
        paths = []
        for root_dir in ["~/Projects", "~/src", "~/Developer", "~/Code", "~/Work", "~"]:
            expanded = os.path.expanduser(root_dir)
            if os.path.isdir(expanded):
                for git_dir in glob.glob(os.path.join(expanded, "*", ".git")):
                    paths.append(os.path.dirname(git_dir))
                if root_dir != "~":
                    for git_dir in glob.glob(os.path.join(expanded, "*", "*", ".git")):
                        paths.append(os.path.dirname(git_dir))
        return sorted(set(paths))

    commands = parse_all_histories(history_files, db=db, project_paths=discover_project_paths)
    if len(commands) == 0:
        Console(stderr=True).print(
            "\n[bold yellow]⚠️  Warning: Shell history parser returned 0 commands.[/bold yellow]\n"
            "Your history file might be empty, unreadable, or permission denied.\n"
            "If you are on macOS, please check and grant Full Disk Access to your Terminal app.\n"
        )
        
    sessions = create_sessions(commands)
    projects = detect_projects(sessions)
    db.save_data(projects, sessions, commands)
    
    # Ingest commits for each project: dynamically adjust search window based on the oldest command parsed
    from termstory.git_integration import get_project_commits
    if commands:
        oldest_ts = commands[0].timestamp
        since_ts = min(oldest_ts - 24 * 3600, int(get_current_time().timestamp()) - 90 * 24 * 3600)
    else:
        since_ts = int(get_current_time().timestamp()) - 90 * 24 * 3600
        
    is_deep_history = since_ts < int(get_current_time().timestamp()) - 90 * 24 * 3600
    git_timeout = 30 if is_deep_history else 10
        
    for p in projects:
        if p.id is not None and p.path:
            commits = get_project_commits(p.path, since_ts, timeout=git_timeout)
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
    safe_init_db(db)
    
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
    from rich.text import Text
    console.print(Text.from_ansi(output))

@app.command("today")
def show_today(
    compare: bool = typer.Option(True, "--compare/--no-compare", help="Compare with yesterday's metrics")
):
    """Show today's work summary"""
    db_path = get_db_path()
    db = Database(db_path)
    safe_init_db(db)
    
    run_ingestion(db)
    
    sessions = db.get_today_sessions()
    projects = db.get_all_projects_with_stats()
    
    compare_sessions = None
    if compare:
        start_ts, end_ts = get_today_range()
        yesterday_start = start_ts - 24 * 3600
        yesterday_end = end_ts - 24 * 3600
        compare_sessions = db.get_range_sessions(yesterday_start, yesterday_end)
        
    output = format_today_output(sessions, projects, compare_sessions=compare_sessions)
    from rich.text import Text
    console.print(Text.from_ansi(output))

@app.command("project")
def show_project(
    name: str = typer.Argument(..., help="Name or path of the project")
):
    """Show detailed history for a specific project"""
    db_path = get_db_path()
    db = Database(db_path)
    safe_init_db(db)
    
    run_ingestion(db)
    
    projects = db.get_all_projects_with_stats()
    
    target = None
    for p in projects:
        if name.lower() in p.name.lower() or (p.path and name.lower() in p.path.lower()):
            target = p
            break
            
    if not target:
        Console(stderr=True).print(f"[bold red]Error: Could not find project matching '{name}'[/]")
        raise typer.Exit(code=1)
        
    sessions = db.get_project_sessions(target.id, start_ts=0)
    
    output = format_project_output(sessions, target)
    from rich.text import Text
    console.print(Text.from_ansi(output))

@app.command("insights")
def show_insights(
    days: int = typer.Option(30, "--days", help="Number of days to analyze")
):
    """Show executive highlights and work patterns"""
    db_path = get_db_path()
    db = Database(db_path)
    safe_init_db(db)
    
    run_ingestion(db)
    
    insights = {"days": days}
    output = format_insights_output(insights)
    from rich.text import Text
    console.print(Text.from_ansi(output))

def cleanup_shell_marker():
    """Remove TermStory injection block and old injections from shell rc files"""
    rc_files = ["~/.zshrc", "~/.bashrc", "~/.bash_profile"]
    
    block_pattern = re.compile(
        r'\n?# >>> TermStory Shell History Timestamp Support >>>.*?'
        r'# <<< TermStory Shell History Timestamp Support <<<\n?',
        re.DOTALL
    )
    
    old_block_pattern_zsh = re.compile(r'\n?# TermStory Timekeeping\nsetopt EXTENDED_HISTORY\n?')
    old_block_pattern_bash = re.compile(r'\n?# TermStory Timekeeping\nexport HISTTIMEFORMAT="%F %T "\n?')
    
    for rc in rc_files:
        path = os.path.expanduser(rc)
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    content = f.read()
                
                new_content = block_pattern.sub('\n', content)
                new_content = old_block_pattern_zsh.sub('\n', new_content)
                new_content = old_block_pattern_bash.sub('\n', new_content)
                
                if new_content != content:
                    with open(path, "w") as f:
                        f.write(new_content.rstrip() + '\n')
            except Exception:
                pass

def perform_reset():
    """Reset all TermStory state, configuration, and database files on disk"""
    import shutil
    import os
    from termstory.config import get_app_dir

    dirs_to_clean = set()

    # 1. Legacy directory
    dirs_to_clean.add(os.path.expanduser("~/.termstory"))

    # 2. Currently resolved app directories
    dirs_to_clean.add(get_app_dir("config"))
    dirs_to_clean.add(get_app_dir("data"))

    # 3. All potential XDG Base directories
    if os.name != "nt":
        if os.environ.get("XDG_CONFIG_HOME"):
            dirs_to_clean.add(os.path.join(os.environ["XDG_CONFIG_HOME"], "termstory"))
        dirs_to_clean.add(os.path.expanduser("~/.config/termstory"))
        
        if os.environ.get("XDG_DATA_HOME"):
            dirs_to_clean.add(os.path.join(os.environ["XDG_DATA_HOME"], "termstory"))
        dirs_to_clean.add(os.path.expanduser("~/.local/share/termstory"))

    for db_dir in dirs_to_clean:
        if os.path.exists(db_dir):
            try:
                if os.path.islink(db_dir) or os.path.isfile(db_dir):
                    os.unlink(db_dir)
                elif os.path.isdir(db_dir):
                    shutil.rmtree(db_dir)
            except Exception:
                pass
                
    # 4. Remove global ignore file
    ignore_file = os.path.expanduser("~/.termstoryignore")
    if os.path.exists(ignore_file):
        try:
            os.unlink(ignore_file)
        except Exception:
            pass

    cleanup_shell_marker()
    console.print("\n[bold green]✨ TermStory state, configuration, and database have been successfully reset![/]")

@app.command("ui")
def show_ui(
    days: int = typer.Option(90, "--days", help="Number of days of history to display"),
    all_history: bool = typer.Option(False, "--all", help="Display all recorded history"),
):
    """Launch the interactive terminal dashboard user interface"""
    db_path = get_db_path()
    db = Database(db_path)
    safe_init_db(db)
    
    run_ingestion(db)
    
    # White-Glove Onboarding Prompt:
    # If the parser flags that shell history timestamps are missing, pause the standard
    # boot sequence to offer automatic configuration injection into the user's shell
    # config file. We detect the user's default shell (bash vs zsh) and write the
    # appropriate timekeeping directive. Never perform this without explicit user consent ('Y').
    missing_ts = os.environ.get("TERMSTORY_MISSING_TIMESTAMPS") == "1"
    _cfg = {}
    if missing_ts:
        from termstory.config import load_config, save_config
        _cfg = load_config()
    if missing_ts and not _cfg.get("has_seen_timestamp_prompt", False):
        # Detect default shell from $SHELL (e.g. /bin/bash, /usr/bin/zsh)
        shell_path = os.environ.get("SHELL", "")
        is_bash = "bash" in os.path.basename(shell_path).lower()
        
        if is_bash:
            # On macOS bash login shells read ~/.bash_profile; elsewhere ~/.bashrc
            if sys.platform == "darwin" and os.path.exists(os.path.expanduser("~/.bash_profile")):
                config_path = os.path.expanduser("~/.bash_profile")
            else:
                config_path = os.path.expanduser("~/.bashrc")
            config_directive = '\n# >>> TermStory Shell History Timestamp Support >>>\nexport HISTTIMEFORMAT="%F %T "\n# <<< TermStory Shell History Timestamp Support <<<\n'
        else:
            config_path = os.path.expanduser("~/.zshrc")
            config_directive = "\n# >>> TermStory Shell History Timestamp Support >>>\nsetopt EXTENDED_HISTORY\n# <<< TermStory Shell History Timestamp Support <<<\n"
        config_display = config_path.replace(os.path.expanduser("~"), "~", 1)
        
        console.print("\n[bold yellow]⚠️  TermStory needs your shell to record timestamps to build your timeline accurately.[/bold yellow]")
        try:
            response = input(
                "Would you like TermStory to automatically enable history timestamps in your shell config file (`~/.zshrc` or `~/.bashrc`)? [Y/n] "
            ).strip().lower()
            if response == "":
                response = "y"
        except (KeyboardInterrupt, EOFError):
            console.print()
            response = "n"
            
        if response in ("y", "yes"):
            try:
                already_exists = False
                if os.path.exists(config_path):
                    with open(config_path, "r") as f:
                        content = f.read()
                    if (is_bash and "HISTTIMEFORMAT" in content) or (not is_bash and "EXTENDED_HISTORY" in content):
                        already_exists = True

                if not already_exists:
                    with open(config_path, "a") as f:
                        f.write(config_directive)
                
                _cfg["has_seen_timestamp_prompt"] = True
                save_config(_cfg)
                
                if not already_exists:
                    console.print(
                        f"\n[bold green]✅ Done! Please restart your terminal or run `source {config_display}` "
                        f"for the changes to take effect, then run `termstory ui` again.[/bold green]\n"
                    )
                    sys.exit(0)
                else:
                    console.print(
                        f"\n[yellow]⚡ Shell configuration already has timestamps enabled! Proceeding to TUI...[/yellow]\n"
                    )
            except Exception as e:
                console.print(f"[bold red]Error modifying {config_display}: {e}[/bold red]")
                console.print("Continuing with legacy history fallback...")
        elif response in ("n", "no"):
            _cfg["has_seen_timestamp_prompt"] = True
            save_config(_cfg)
            console.print("Continuing with legacy history fallback...")
        else:
            console.print("Invalid response. Continuing with legacy history fallback...")
            
    from termstory.tui import TermStoryWorkspace
    app_tui = TermStoryWorkspace(db, days_limit=None if all_history else days)
    app_tui.run()
    
    if getattr(app_tui, "was_reset", False):
        perform_reset()
    else:
        try:
            from termstory.config import load_config, save_config
            _cfg = load_config()
            if (
                not _cfg.get("has_seen_onboarding_reminder", False)
                and not _cfg.get("has_seen_onboarding", False)
                and _cfg.get("active_provider", "disabled") == "disabled"
            ):
                console.print("\n[bold yellow]💡 Hint: TermStory works best with AI summaries enabled![/bold yellow]")
                console.print("To configure a local or cloud AI provider (Groq, OpenAI, Ollama), run:")
                console.print("  [cyan]termstory config set active_provider groq[/cyan] (or [cyan]openai[/cyan] / [cyan]ollama[/cyan])")
                console.print("  [cyan]termstory config set providers.groq.api_key <your_api_key>[/cyan]")
                console.print("Alternatively, press [bold]? [/bold]inside the TUI to open the onboarding settings anytime.\n")
                _cfg["has_seen_onboarding_reminder"] = True
                save_config(_cfg)
        except Exception as e:
            Console(stderr=True).print(f"[dim]Note: failed to persist onboarding reminder flag: {e}[/dim]")

@app.command("reset")
def reset_cmd():
    """Reset all TermStory state, configuration, and database"""
    perform_reset()


@app.command("optimize")
def optimize_cmd():
    """Run VACUUM on the database to defragment it and reclaim disk space"""
    db_path = get_db_path()
    db = Database(db_path)
    safe_init_db(db)
    
    console.print("Running database optimization (VACUUM)...")
    db.optimize()
    console.print("[bold green]✅ Database optimized successfully![/]")


# ==========================================
# CONFIG SUBCOMMANDS
# ==========================================

config_app = typer.Typer(help="Manage TermStory configuration settings")

@config_app.command("set")
def config_set(key: str, value: str):
    """Set a configuration value (supports nested dot notation, e.g. providers.openai.api_key)"""
    from termstory.config import load_config, save_config, set_config_value, get_config_value
    config = load_config()
    
    current_val = get_config_value(config, key)
    if isinstance(current_val, bool):
        converted_value = value.lower() in ("true", "1", "yes")
    elif isinstance(current_val, int):
        try:
            converted_value = int(value)
        except ValueError:
            converted_value = value
    elif isinstance(current_val, float):
        try:
            converted_value = float(value)
        except ValueError:
            converted_value = value
    else:
        if key in ("ai_enabled", "has_seen_onboarding") or key.endswith(".ai_enabled") or key.endswith(".has_seen_onboarding"):
            converted_value = value.lower() in ("true", "1", "yes")
        elif "api_key" in key or "token" in key or "password" in key:
            converted_value = value
        else:
            try:
                if "." in value:
                    converted_value = float(value)
                elif value.isdigit() and value.startswith("0") and len(value) > 1:
                    converted_value = value
                else:
                    converted_value = int(value)
            except ValueError:
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
    
    from rich.box import SIMPLE
    table = Table(title="🔧 TermStory Configuration", box=SIMPLE, border_style="cyan")
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
