"""Tests for save_data None-row safety and the _safe_rollback_and_reraise helper."""
import sqlite3
import pytest

from termstory.database import Database, _safe_rollback_and_reraise
from termstory.models import Project, Session, Command


# ── _safe_rollback_and_reraise ───────────────────────────────────────────────
def test_rollback_helper_preserves_original_traceback(tmp_path):
    conn = Database(str(tmp_path / "rb_ok.db")).get_connection()
    try:
        with pytest.raises(ValueError, match="original"):
            _safe_rollback_and_reraise(conn, ValueError("original failure"))
    finally:
        conn.close()


def test_rollback_helper_swallows_rollback_failure():
    class FakeConn:
        def rollback(self):
            raise sqlite3.OperationalError("simulated failure")
    with pytest.raises(ValueError, match="real cause"):
        _safe_rollback_and_reraise(FakeConn(), ValueError("real cause"))


# ── save_data: NULL project_id conflict ──────────────────────────────────────
def test_save_data_recovers_null_project_id_conflict(tmp_path):
    """Uses COALESCE-based SELECT to match rows with NULL project_id."""
    db_file = tmp_path / "null_proj.db"
    db = Database(str(db_file))
    db.init_db()

    s1 = Session(id=999, start_time=1750000000, end_time=1750001000,
                 duration_seconds=1000, project_id=None,
                 commands=[Command(id=None, session_id=999, timestamp=1750000000, command="test")])
    db.save_data([], [s1], s1.commands)

    s2 = Session(id=998, start_time=1750000000, end_time=1750001100,
                 duration_seconds=1100, project_id=None,
                 commands=[Command(id=None, session_id=998, timestamp=1750000001, command="test2")])
    db.save_data([], [s2], s2.commands)

    conn = db.get_connection()
    c = conn.cursor()
    c.execute("SELECT count(*) FROM sessions")
    assert c.fetchone()[0] == 1
    conn.close()


# ── save_data: project_id match conflict ─────────────────────────────────────
def test_save_data_handles_project_id_conflict(tmp_path):
    """With a project FK present, duplicate (start_time, project_id) = one row."""
    db_file = tmp_path / "proj_conflict.db"
    db = Database(str(db_file))
    db.init_db()

    p = Project(id=1, name="test", path="/test",
                first_seen=1750000000, last_seen=1750000000,
                session_count=0, total_time=0)
    s1 = Session(id=None, start_time=1750000000, end_time=1750001000,
                 duration_seconds=1000, project_id=1)
    s1_cmds = [Command(id=None, session_id=999, timestamp=1750000000, command="a", project_id=1)]
    s1 = Session(id=999, start_time=1750000000, end_time=1750001000,
                 duration_seconds=1000, project_id=1, commands=s1_cmds)

    db.save_data([p], [s1], s1_cmds)
    conn = db.get_connection()
    c = conn.cursor()
    c.execute("SELECT count(*) FROM sessions")
    assert c.fetchone()[0] == 1, "first session should persist"
    conn.close()

    s2_cmds = [Command(id=None, session_id=998, timestamp=1750000001, command="b", project_id=1)]
    s2 = Session(id=998, start_time=1750000000, end_time=1750001100,
                 duration_seconds=1100, project_id=1, commands=s2_cmds)
    db.save_data([], [s2], s2_cmds)

    conn = db.get_connection()
    c = conn.cursor()
    c.execute("SELECT count(*) FROM sessions")
    assert c.fetchone()[0] == 1
    conn.close()


# ── archive.py: skip guard exists in code ───────────────────────────────────
def test_archive_skip_guard_exists():
    """Verify the skip guard was added to archive.py."""
    import inspect
    from termstory import archive as arc_mod
    src = inspect.getsource(arc_mod.archive_old_data)
    assert "session_row is None" in src
    assert "continue" in src
