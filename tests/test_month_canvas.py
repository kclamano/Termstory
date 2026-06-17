import asyncio
from datetime import datetime
from termstory.tui import TermStoryWorkspace, DetailsCanvas
from termstory.models import Session, Command
from termstory.database import Database

c1 = Command(timestamp=1777574510, command='git push -u origin main', exit_code=0, session_id=1)
s1 = Session(
    id=1,
    start_time=1777574510,
    end_time=1777574510,
    duration_seconds=0,
    project_id=None,
    commands=[c1],
    commits=[],
    ai_summary=None,
    is_generating_story=False,
    recent_generation=None,
    is_legacy=False
)
s1._cached_date_str = "2026-05-01"

db = Database(":memory:")
app = TermStoryWorkspace(db)
app.sessions = [s1]
app.projects = []

canvas = DetailsCanvas()
# Patch app so canvas can access it
canvas._app = app

try:
    canvas.render_wrapped_view('May 2026', '2026-05', [s1], [])
    print("Success render_wrapped_view")
except Exception as e:
    import traceback
    traceback.print_exc()
