import os
import sys

# Setup path to import termstory
sys.path.insert(0, "/Users/himanshuverma/Projects/termstory")

from termstory.database import Database

db = Database(os.path.expanduser("~/.termstory/termstory.db"))
results = db.search_sessions("docker")

from rich.table import Table
from rich.console import Console

# Column match is now flexible
table = Table(box=Table.box.ROUNDED if hasattr(Table, "box") else None, show_header=True)
table.add_column("date", style="dim", width=6, no_wrap=True)
table.add_column("time", style="dim", width=5, no_wrap=True)
table.add_column("duration", style="green", width=7, no_wrap=True)
table.add_column("project", style="cyan bold", width=16, no_wrap=True)
table.add_column("match") # no_wrap=False on column

from termstory.formatter import highlight_query, format_duration
from datetime import datetime

for r in results[:2]:
    dt = datetime.fromtimestamp(r["start_time"])
    date_str = dt.strftime("%b %d")
    time_str = dt.strftime("%H:%M")
    dur_str = f"({format_duration(r['duration_seconds'])})"
    proj_name = r["project_name"] or "General"
    if len(proj_name) > 16:
        proj_name = proj_name[:15] + "…"
        
    match_text = r["all_commands"][0] if r["all_commands"] else ""
    
    t_obj = highlight_query(match_text, "docker")
    t_obj.no_wrap = True
    t_obj.overflow = "ellipsis"
    
    table.add_row(
        date_str,
        time_str,
        dur_str,
        proj_name,
        t_obj
    )

print("Printing with width=80:")
Console(width=80).print(table)
