import os
import sys

# Setup path to import termstory
sys.path.insert(0, "/Users/himanshuverma/Projects/termstory")

from termstory.database import Database
from termstory.formatter import format_search_results, highlight_query

db = Database(os.path.expanduser("~/.termstory/termstory.db"))
results = db.search_sessions("docker")

# Let's inspect what format_search_results does by building a mini version of it
from rich.table import Table
from rich.console import Console

table = Table(box=None, show_header=False, padding=(0, 1))
table.add_column("date", style="dim", width=6, no_wrap=True)
table.add_column("time", style="dim", width=5, no_wrap=True)
table.add_column("duration", style="green", width=7, no_wrap=True)
table.add_column("project", style="cyan bold", width=16, no_wrap=True)
table.add_column("match", no_wrap=True, overflow="ellipsis")

from datetime import datetime
from termstory.models import format_duration

r = results[0]
dt = datetime.fromtimestamp(r["start_time"])
date_str = dt.strftime("%b %d")
time_str = dt.strftime("%H:%M")
dur_str = f"({format_duration(r['duration_seconds'])})"
proj_name = r["project_name"] or "General"
if len(proj_name) > 16:
    proj_name = proj_name[:15] + "…"

match_text = r["matching_commands"][0]

print("Cell values to be added:")
print(f"  date: '{date_str}'")
print(f"  time: '{time_str}'")
print(f"  duration: '{dur_str}'")
print(f"  project: '{proj_name}'")
print(f"  match: '{match_text}'")

table.add_row(
    date_str,
    time_str,
    dur_str,
    proj_name,
    highlight_query(match_text, "docker")
)

console = Console(width=80)
with console.capture() as capture:
    console.print(table)
    
rendered = capture.get()
print("\nRendered single row:")
print(repr(rendered))
