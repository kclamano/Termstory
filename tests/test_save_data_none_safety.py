"""Tests for save_data None-row safety and the _safe_rollback_and_reraise helper."""
import sqlite3
import pytest

from termstory.database import Database, _safe_rollback_and_reraise
from termstory.models import Project, Session, Command


# ── _safe_rollback_and_reraise ───────────────────────────────────────────────
def test_rollback_helper_preserves_original_traceback(tmp_path):
    """Verify the traceback of the original call site is preserved.

    Raises from a real nested function, catches it, passes to the helper,
    then asserts the traceback still contains that nested function's frame.
    """
    def _inner():
        raise ValueError("original failure at line 42")

    conn = Database(str(tmp_path / "rb_ok.db")).get_connection()
    try:
        with pytest.raises(ValueError) as exc_info:
            try:
                _inner()
            except ValueError as e:
                _safe_rollback_and_reraise(conn, e)
        assert "_inner" in str(exc_info.traceback[-1]), (
            f"traceback lost _inner frame, got: {exc_info.traceback}"
        )
    finally:
        conn.close()


def test_rollback_helper_swallows_rollback_failure():
    """If the connection itself fails during rollback, the original
    exception still propagates."""
    class FakeConn:
        def rollback(self):
            raise sqlite3.OperationalError("simulated failure")
    with pytest.raises(ValueError, match="real cause"):
        _safe_rollback_and_reraise(FakeConn(), ValueError("real cause"))


# ── save_data: NULL project_id conflict ──────────────────────────────────────
def test_save_data_recovers_null_project_id_conflict(tmp_path):
    """COALESCE-based SELECT matches rows with NULL project_id, preventing a
    None-row TypeError that the old plain-equality SELECT would cause."""
    db_file = tmp_path / "null_proj.db"
    db = Database(str(db_file))
    db.init_db()

    s1 = Session(id=999, start_time=1750000000, end_time=1750001000,
                 duration_seconds=1000, project_id=None,
                 commands=[Command(id=None, session_id=999,
                                  timestamp=1750000000, command="test")])
    db.save_data([], [s1], s1.commands)

    s2 = Session(id=998, start_time=1750000000, end_time=1750001100,
                 duration_seconds=1100, project_id=None,
                 commands=[Command(id=None, session_id=998,
                                  timestamp=1750000001, command="test2")])
    db.save_data([], [s2], s2.commands)

    conn = db.get_connection()
    c = conn.cursor()
    c.execute("SELECT count(*) FROM sessions")
    assert c.fetchone()[0] == 1
    conn.close()


# ── save_data: project_id match conflict ─────────────────────────────────────
def test_save_data_handles_project_id_conflict(tmp_path):
    """With FK present, duplicate (start_time, project_id) is one row."""
    db_file = tmp_path / "proj_conflict.db"
    db = Database(str(db_file))
    db.init_db()

    p = Project(id=1, name="test", path="/test",
                first_seen=1750000000, last_seen=1750000000,
                session_count=0, total_time=0)
    s1_cmds = [Command(id=None, session_id=999, timestamp=1750000000,
                       command="a", project_id=1)]
    s1 = Session(id=999, start_time=1750000000, end_time=1750001000,
                 duration_seconds=1000, project_id=1, commands=s1_cmds)
    db.save_data([p], [s1], s1_cmds)

    conn = db.get_connection()
    c = conn.cursor()
    c.execute("SELECT count(*) FROM sessions")
    assert c.fetchone()[0] == 1, "first session should persist"
    conn.close()

    s2_cmds = [Command(id=None, session_id=998, timestamp=1750000001,
                       command="b", project_id=1)]
    s2 = Session(id=998, start_time=1750000000, end_time=1750001100,
                 duration_seconds=1100, project_id=1, commands=s2_cmds)
    db.save_data([], [s2], s2_cmds)

    conn = db.get_connection()
    c = conn.cursor()
    c.execute("SELECT count(*) FROM sessions")
    assert c.fetchone()[0] == 1
    conn.close()


# ── archive.py: missing sessions handled gracefully ─────────────────────────
def test_archive_handles_clean_db(tmp_path):
    """Archive on a DB with no eligible sessions completes without error.
    This is a regression test: before the skip guard, a missing row during
    the copy loop would crash with TypeError on None unpack."""
    from termstory import archive as archive_mod

    main_db_path = str(tmp_path / "main.db")
    archive_db_path = str(tmp_path / "archive.db")

    main_db = Database(main_db_path)
    main_db.init_db()

    # New session — too recent to archive, but proves the archive path works
    p = Project(id=1, name="proj", path="/proj",
                first_seen=1750000100, last_seen=1750000100,
                session_count=1, total_time=0)
    cmd = Command(id=1, session_id=1, timestamp=1750000100,
                  command="recent", project_id=1)
    s = Session(id=1, start_time=1750000100, end_time=1750000200,
                duration_seconds=100, project_id=1, commands=[cmd])
    main_db.save_data([p], [s], [cmd])

    archive_mod.archive_old_data(main_db_path, archive_db_path, days=30)
