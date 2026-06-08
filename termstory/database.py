import sqlite3
from datetime import datetime, time
from typing import List, Dict, Optional, Set, Tuple
from termstory.models import Command, Session, Project

class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        
    def get_connection(self) -> sqlite3.Connection:
        """Create and return a database connection with foreign key support enabled"""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn
        
    def init_db(self) -> None:
        """Initialize the database schema and indexes if they do not exist"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Enable WAL mode for better concurrency and speed
        cursor.execute("PRAGMA journal_mode = WAL;")
        
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            path TEXT UNIQUE,
            first_seen INTEGER,
            last_seen INTEGER,
            created_at INTEGER DEFAULT (strftime('%s', 'now'))
        );
        """)
        
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start_time INTEGER NOT NULL,
            end_time INTEGER NOT NULL,
            duration_seconds INTEGER,
            project_id INTEGER,
            created_at INTEGER DEFAULT (strftime('%s', 'now')),
            FOREIGN KEY(project_id) REFERENCES projects(id)
        );
        """)
        
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS commands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp INTEGER NOT NULL,
            command TEXT NOT NULL,
            exit_code INTEGER,
            session_id INTEGER,
            project_id INTEGER,
            created_at INTEGER DEFAULT (strftime('%s', 'now')),
            FOREIGN KEY(session_id) REFERENCES sessions(id),
            FOREIGN KEY(project_id) REFERENCES projects(id)
        );
        """)
        
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS commits (
            hash TEXT PRIMARY KEY,
            timestamp INTEGER NOT NULL,
            message TEXT NOT NULL,
            cleaned_message TEXT NOT NULL,
            project_id INTEGER,
            created_at INTEGER DEFAULT (strftime('%s', 'now')),
            FOREIGN KEY(project_id) REFERENCES projects(id)
        );
        """)
        
        # Indexes for fast querying
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_commands_timestamp ON commands(timestamp);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_commands_session_id ON commands(session_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_start_time ON sessions(start_time);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_project_id ON sessions(project_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_date_range ON sessions(start_time DESC);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_commands_date_range ON commands(timestamp DESC);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_project_date ON sessions(project_id, start_time);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_commits_timestamp ON commits(timestamp DESC);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_commits_project_id ON commits(project_id);")
        
        # Add ai_summary column to sessions if not exists
        try:
            cursor.execute("ALTER TABLE sessions ADD COLUMN ai_summary TEXT;")
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                raise

        # v0.2.9: Add recovery_source column to commands so the Timestamp Detective's
        # Chain of Custody attribution survives the DB round-trip and appears in the TUI.
        # NULL for all commands with real EXTENDED_HISTORY timestamps.
        try:
            cursor.execute("ALTER TABLE commands ADD COLUMN recovery_source TEXT;")
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                raise
            
        # Create macro_summaries table if not exists
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS macro_summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timeframe_id TEXT NOT NULL UNIQUE,
            type TEXT NOT NULL,
            summary TEXT NOT NULL,
            created_at INTEGER DEFAULT (strftime('%s', 'now'))
        );
        """)
        
        # One-time migration: change projects unique constraint
        self._migrate_projects_unique_path(cursor)
        
        # One-time migration: clean up duplicate sessions/commands and create unique indexes
        self._migrate_deduplicate_sessions(cursor)
            
        conn.commit()
        conn.close()

    def _migrate_projects_unique_path(self, cursor) -> None:
        """One-time migration: change projects table to have UNIQUE on path instead of name"""
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='projects'")
        create_sql = cursor.fetchone()
        if create_sql and "name TEXT NOT NULL UNIQUE" in create_sql[0]:
            # Must commit any pending transaction before changing PRAGMA foreign_keys
            cursor.connection.commit()
            cursor.execute("PRAGMA foreign_keys = OFF;")
            
            # First deduplicate projects by path before adding UNIQUE path constraint
            cursor.execute("SELECT path, COUNT(*), MIN(id) FROM projects WHERE path IS NOT NULL GROUP BY path HAVING COUNT(*) > 1")
            for row in cursor.fetchall():
                path, count, min_id = row
                # Reassign foreign keys to the kept project (min_id)
                cursor.execute("SELECT id FROM projects WHERE path = ? AND id != ?", (path, min_id))
                dup_ids = [r[0] for r in cursor.fetchall()]
                for dup_id in dup_ids:
                    cursor.execute("UPDATE sessions SET project_id = ? WHERE project_id = ?", (min_id, dup_id))
                    cursor.execute("UPDATE commands SET project_id = ? WHERE project_id = ?", (min_id, dup_id))
                    cursor.execute("UPDATE commits SET project_id = ? WHERE project_id = ?", (min_id, dup_id))
                    cursor.execute("DELETE FROM projects WHERE id = ?", (dup_id,))
            
            cursor.execute("ALTER TABLE projects RENAME TO projects_old;")
            cursor.execute("""
            CREATE TABLE projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                path TEXT UNIQUE,
                first_seen INTEGER,
                last_seen INTEGER,
                created_at INTEGER DEFAULT (strftime('%s', 'now'))
            );
            """)
            cursor.execute("""
            INSERT INTO projects (id, name, path, first_seen, last_seen, created_at)
            SELECT id, name, path, first_seen, last_seen, created_at FROM projects_old;
            """)
            cursor.execute("DROP TABLE projects_old;")
            
            cursor.connection.commit()
            cursor.execute("PRAGMA foreign_keys = ON;")

    def _migrate_deduplicate_sessions(self, cursor) -> None:
        """One-time migration: remove duplicate sessions and commands that share the same keys,
        and create unique constraints to prevent future duplicates."""
        # Find start_times that have duplicates
        cursor.execute("""
            SELECT start_time, COUNT(*) as cnt
            FROM sessions
            GROUP BY start_time
            HAVING cnt > 1
        """)
        dup_start_times = cursor.fetchall()
        
        for (start_time, _count) in dup_start_times:
            # Get all sessions with this start_time
            cursor.execute("""
                SELECT s.id, s.ai_summary,
                       (SELECT COUNT(*) FROM commands WHERE session_id = s.id) as cmd_count
                FROM sessions s
                WHERE s.start_time = ?
                ORDER BY cmd_count DESC, s.ai_summary IS NOT NULL DESC, s.id ASC
            """, (start_time,))
            rows = cursor.fetchall()
            
            if len(rows) <= 1:
                continue
                
            # Keep the best one (most commands, or has ai_summary)
            keeper_id = rows[0][0]
            
            # Reassign orphaned commands from duplicates to the keeper
            for row in rows[1:]:
                dup_id = row[0]
                cursor.execute("UPDATE commands SET session_id = ? WHERE session_id = ?", (keeper_id, dup_id))
                cursor.execute("DELETE FROM sessions WHERE id = ?", (dup_id,))
        
        # Deduplicate legacy commands on (timestamp, command)
        cursor.execute("""
            SELECT timestamp, command, COUNT(*) as cnt
            FROM commands
            GROUP BY timestamp, command
            HAVING cnt > 1
        """)
        dup_commands = cursor.fetchall()
        for ts, cmd_str, _cnt in dup_commands:
            cursor.execute("""
                SELECT id FROM commands
                WHERE timestamp = ? AND command = ?
                ORDER BY id ASC
            """, (ts, cmd_str))
            cmd_rows = cursor.fetchall()
            if len(cmd_rows) > 1:
                # Keep the first one, delete the rest
                for row in cmd_rows[1:]:
                    cursor.execute("DELETE FROM commands WHERE id = ?", (row[0],))
        
        # Create UNIQUE indexes
        import sqlite3
        try:
            cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_sessions_start_time_unique ON sessions(start_time);")
        except sqlite3.IntegrityError:
            pass  # Edge case: if migration didn't fully clean up, index creation will be retried next run
            
        try:
            cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_commands_ts_cmd_unique ON commands(timestamp, command);")
        except sqlite3.IntegrityError:
            pass



    def save_data(self, projects: List[Project], sessions: List[Session], commands: List[Command]) -> None:
        """Optimized bulk insertion and updating of projects, sessions, and commands in a single transaction"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            # --- 1. Save Projects ---
            # Capture the temporary python project IDs first (grouping by path)
            path_to_old_ids = {}
            for p in projects:
                if p.id is not None:
                    if p.path not in path_to_old_ids:
                        path_to_old_ids[p.path] = []
                    path_to_old_ids[p.path].append(p.id)
            
            cursor.execute("SELECT id, name, path, first_seen, last_seen FROM projects")
            db_projects = {row[2]: {"id": row[0], "name": row[1], "first_seen": row[3], "last_seen": row[4]} for row in cursor.fetchall()}
            
            project_id_map = {} # old_python_id -> db_id
            
            new_projects_to_insert = []
            projects_to_update = []
            inserted_paths = set()
            
            for project in projects:
                if project.path in db_projects:
                    db_p = db_projects[project.path]
                    db_id = db_p["id"]
                    project.id = db_id
                    
                    # Update first_seen/last_seen ranges if they expanded
                    new_first = min(db_p["first_seen"], project.first_seen)
                    new_last = max(db_p["last_seen"], project.last_seen)
                    if new_first != db_p["first_seen"] or new_last != db_p["last_seen"] or project.name != db_p["name"]:
                        projects_to_update.append((project.name, new_first, new_last, db_id))
                else:
                    if project.path not in inserted_paths:
                        new_projects_to_insert.append((project.name, project.path, project.first_seen, project.last_seen))
                        inserted_paths.add(project.path)
                    
            if new_projects_to_insert:
                cursor.executemany("""
                    INSERT INTO projects (name, path, first_seen, last_seen)
                    VALUES (?, ?, ?, ?)
                """, new_projects_to_insert)
                
            if projects_to_update:
                cursor.executemany("""
                    UPDATE projects SET name = ?, first_seen = ?, last_seen = ? WHERE id = ?
                """, projects_to_update)
                
            # Re-read projects map to update project_id_map
            cursor.execute("SELECT id, path FROM projects")
            refreshed_projects = {row[1]: row[0] for row in cursor.fetchall()}
            
            for project in projects:
                project.id = refreshed_projects.get(project.path, project.id)
                
            # Build the ID mapping: old_python_id -> db_id
            for path, old_ids in path_to_old_ids.items():
                if path in refreshed_projects:
                    db_id = refreshed_projects[path]
                    for old_id in old_ids:
                        project_id_map[old_id] = db_id
                
            # Re-map project_ids in sessions and commands
            for session in sessions:
                if session.project_id in project_id_map:
                    session.project_id = project_id_map[session.project_id]
            for cmd in commands:
                if cmd.project_id in project_id_map:
                    cmd.project_id = project_id_map[cmd.project_id]
                    
            # --- 2. Save Sessions ---
            # Dedup key is start_time ONLY (stable across runs regardless of project_id changes)
            cursor.execute("SELECT id, start_time, end_time, duration_seconds, project_id, ai_summary FROM sessions")
            db_sessions = {}
            for row in cursor.fetchall():
                key = row[1]  # start_time only
                # If there are duplicate legacy sessions, prefer the one with the latest end_time
                if key not in db_sessions or row[2] > db_sessions[key]["end_time"]:
                    db_sessions[key] = {"id": row[0], "end_time": row[2], "duration": row[3], "ai_summary": row[5]}
            
            session_id_map = {}
            
            for session in sessions:
                temp_id = session.id
                key = session.start_time  # start_time only
                if key in db_sessions:
                    db_id = db_sessions[key]["id"]
                    existing_summary = db_sessions[key]["ai_summary"]
                    # Update end_time, duration, and project_id — but preserve existing ai_summary
                    cursor.execute("""
                        UPDATE sessions SET end_time = ?, duration_seconds = ?, project_id = ? WHERE id = ?
                    """, (session.end_time, session.duration_seconds, session.project_id, db_id))
                    session.id = db_id
                    session.ai_summary = existing_summary  # preserve cached AI work
                else:
                    cursor.execute("""
                        INSERT OR IGNORE INTO sessions (start_time, end_time, duration_seconds, project_id)
                        VALUES (?, ?, ?, ?)
                    """, (session.start_time, session.end_time, session.duration_seconds, session.project_id))
                    db_id = cursor.lastrowid
                    if db_id == 0:
                        # INSERT OR IGNORE hit a conflict — fetch the existing row
                        cursor.execute("SELECT id FROM sessions WHERE start_time = ?", (session.start_time,))
                        db_id = cursor.fetchone()[0]
                    session.id = db_id
                    
                if temp_id is not None:
                    session_id_map[temp_id] = db_id
                    
            # Re-map session_ids in commands
            for cmd in commands:
                if cmd.session_id in session_id_map:
                    cmd.session_id = session_id_map[cmd.session_id]
                    
            # --- 3. Save Commands ---
            # Fetch existing commands in the same timestamp range so we can diff.
            # We now also select recovery_source so we can update it if the Detective
            # ran again with new information.
            if commands:
                min_ts = min(cmd.timestamp for cmd in commands)
                max_ts = max(cmd.timestamp for cmd in commands)
                cursor.execute("""
                    SELECT timestamp, command, id, exit_code, session_id, project_id, recovery_source
                    FROM commands
                    WHERE timestamp >= ? AND timestamp <= ?
                """, (min_ts, max_ts))
                db_cmds = {
                    (row[0], row[1]): {
                        "id": row[2],
                        "exit_code": row[3],
                        "session_id": row[4],
                        "project_id": row[5],
                        "recovery_source": row[6]
                    } for row in cursor.fetchall()
                }
            else:
                db_cmds = {}
                
            new_commands_to_insert = []
            commands_to_update = []

            for cmd in commands:
                key = (cmd.timestamp, cmd.command)
                recovery_src = getattr(cmd, "recovery_source", None)
                if key in db_cmds:
                    db_c = db_cmds[key]
                    cmd.id = db_c["id"]
                    # Update if any column changed, including recovery_source
                    # (a subsequent parse run may have resolved a better source).
                    if (
                        db_c["exit_code"] != cmd.exit_code
                        or db_c["session_id"] != cmd.session_id
                        or db_c["project_id"] != cmd.project_id
                        or (recovery_src and db_c["recovery_source"] != recovery_src)
                    ):
                        commands_to_update.append(
                            (cmd.exit_code, cmd.session_id, cmd.project_id, recovery_src, db_c["id"])
                        )
                else:
                    # New command — include recovery_source from the Detective
                    new_commands_to_insert.append(
                        (cmd.timestamp, cmd.command, cmd.exit_code,
                         cmd.session_id, cmd.project_id, recovery_src)
                    )

            if new_commands_to_insert:
                cursor.executemany("""
                    INSERT OR IGNORE INTO commands (timestamp, command, exit_code, session_id, project_id, recovery_source)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, new_commands_to_insert)

            if commands_to_update:
                cursor.executemany("""
                    UPDATE commands SET exit_code = ?, session_id = ?, project_id = ?, recovery_source = ? WHERE id = ?
                """, commands_to_update)
                
            # Prune legacy duplicate sessions that became orphaned (have no commands)
            cursor.execute("""
                DELETE FROM sessions 
                WHERE id NOT IN (SELECT DISTINCT session_id FROM commands WHERE session_id IS NOT NULL);
            """)
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def get_today_sessions(self) -> List[Session]:
        """Query and return today's sessions, commands, and project attributes"""
        from termstory.date_utils import get_today_range
        start_ts, end_ts = get_today_range()
        
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            # 1. Fetch sessions starting today
            cursor.execute("""
                SELECT id, start_time, end_time, duration_seconds, project_id, ai_summary
                FROM sessions
                WHERE start_time >= ? AND start_time <= ?
                ORDER BY start_time ASC
            """, (start_ts, end_ts))
            session_rows = cursor.fetchall()
            
            sessions = []
            for row in session_rows:
                s_id, start, end, duration, p_id, ai_sum = row
    
                
                # 2. Fetch all commands for this session, including recovery_source
                # so the Chain of Custody tooltip can be displayed in the TUI.
                cursor.execute("""
                    SELECT id, timestamp, command, exit_code, session_id, project_id, recovery_source
                    FROM commands
                    WHERE session_id = ?
                    ORDER BY timestamp ASC
                """, (s_id,))
                cmd_rows = cursor.fetchall()

                commands = []
                for c_row in cmd_rows:
                    c_id, timestamp, command_text, exit_code, _, cmd_p_id, rec_src = c_row
                    commands.append(Command(
                        id=c_id,
                        timestamp=timestamp,
                        command=command_text,
                        exit_code=exit_code,
                        session_id=s_id,
                        project_id=cmd_p_id,
                        recovery_source=rec_src
                    ))
                    
                # 3. Fetch all commits for this session (5m pre, 10m post buffers)
                commits = []
                if p_id is not None:
                    cursor.execute("""
                        SELECT hash, timestamp, message, cleaned_message
                        FROM commits
                        WHERE project_id = ? AND timestamp >= ? AND timestamp <= ?
                        ORDER BY timestamp ASC
                    """, (p_id, start - 300, end + 600))
                    for c_row in cursor.fetchall():
                        commits.append({
                            "hash": c_row[0],
                            "timestamp": c_row[1],
                            "message": c_row[2],
                            "cleaned_message": c_row[3]
                        })
                        
                sessions.append(Session(
                    id=s_id,
                    start_time=start,
                    end_time=end,
                    duration_seconds=duration,
                    project_id=p_id,
                    commands=commands,
                    commits=commits,
                    ai_summary=ai_sum
                ))
        finally:
            conn.close()
        return sessions

    def get_projects_by_ids(self, project_ids: List[int]) -> List[Project]:
        """Retrieve Project entities from database for a given list of IDs"""
        if not project_ids:
            return []
            
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            placeholders = ",".join("?" for _ in project_ids)
            cursor.execute(f"""
                SELECT id, name, path, first_seen, last_seen
                FROM projects
                WHERE id IN ({placeholders})
            """, project_ids)
            
            rows = cursor.fetchall()
            projects = []
            for row in rows:
                p_id, name, path, first, last = row
                # Calculate counts dynamically based on all sessions
                cursor.execute("""
                    SELECT COUNT(*), SUM(duration_seconds)
                    FROM sessions
                    WHERE project_id = ?
                """, (p_id,))
                s_count, t_time = cursor.fetchone()
                
                projects.append(Project(
                    id=p_id,
                    name=name,
                    path=path,
                    first_seen=first,
                    last_seen=last,
                    session_count=s_count or 0,
                    total_time=t_time or 0
                ))
        finally:
            conn.close()
        return projects

    def get_sessions_by_ids(self, session_ids: List[int]) -> List[Session]:
        """Retrieve Session entities (with commands and commits) for a given list of IDs"""
        if not session_ids:
            return []
            
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            placeholders = ",".join("?" for _ in session_ids)
            cursor.execute(f"""
                SELECT id, start_time, end_time, duration_seconds, project_id, ai_summary
                FROM sessions
                WHERE id IN ({placeholders})
                ORDER BY start_time ASC
            """, session_ids)
            session_rows = cursor.fetchall()
            
            sessions = []
            for row in session_rows:
                s_id, start, end, duration, p_id, ai_sum = row
                
                # Fetch commands including recovery_source for Chain of Custody
                cursor.execute("""
                    SELECT id, timestamp, command, exit_code, session_id, project_id, recovery_source
                    FROM commands
                    WHERE session_id = ?
                    ORDER BY timestamp ASC
                """, (s_id,))
                cmd_rows = cursor.fetchall()

                commands = []
                for c_row in cmd_rows:
                    c_id, timestamp, command_text, exit_code, _, cmd_p_id, rec_src = c_row
                    commands.append(Command(
                        id=c_id,
                        timestamp=timestamp,
                        command=command_text,
                        exit_code=exit_code,
                        session_id=s_id,
                        project_id=cmd_p_id,
                        recovery_source=rec_src
                    ))
                    
                # Fetch commits (with buffers)
                commits = []
                if p_id is not None:
                    cursor.execute("""
                        SELECT hash, timestamp, message, cleaned_message
                        FROM commits
                        WHERE project_id = ? AND timestamp >= ? AND timestamp <= ?
                        ORDER BY timestamp ASC
                    """, (p_id, start - 300, end + 600))
                    for c_row in cursor.fetchall():
                        commits.append({
                            "hash": c_row[0],
                            "timestamp": c_row[1],
                            "message": c_row[2],
                            "cleaned_message": c_row[3]
                        })
                        
                sessions.append(Session(
                    id=s_id,
                    start_time=start,
                    end_time=end,
                    duration_seconds=duration,
                    project_id=p_id,
                    commands=commands,
                    commits=commits,
                    ai_summary=ai_sum
                ))
        finally:
            conn.close()
        return sessions

    def get_range_sessions(self, start_ts: int, end_ts: int) -> List[Session]:
        """Get sessions starting in the given Unix timestamp range"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id, start_time, end_time, duration_seconds, project_id, ai_summary
                FROM sessions
                WHERE start_time >= ? AND start_time <= ?
                ORDER BY start_time ASC
            """, (start_ts, end_ts))
            session_rows = cursor.fetchall()
            
            sessions = []
            for row in session_rows:
                s_id, start, end, duration, p_id, ai_sum = row
    
                
                cursor.execute("""
                    SELECT id, timestamp, command, exit_code, session_id, project_id, recovery_source
                    FROM commands
                    WHERE session_id = ?
                    ORDER BY timestamp ASC
                """, (s_id,))
                cmd_rows = cursor.fetchall()

                commands = []
                for c_row in cmd_rows:
                    c_id, timestamp, command_text, exit_code, _, cmd_p_id, rec_src = c_row
                    commands.append(Command(
                        id=c_id,
                        timestamp=timestamp,
                        command=command_text,
                        exit_code=exit_code,
                        session_id=s_id,
                        project_id=cmd_p_id,
                        recovery_source=rec_src
                    ))
                    
                # 3. Fetch all commits for this session (5m pre, 10m post buffers)
                commits = []
                if p_id is not None:
                    cursor.execute("""
                        SELECT hash, timestamp, message, cleaned_message
                        FROM commits
                        WHERE project_id = ? AND timestamp >= ? AND timestamp <= ?
                        ORDER BY timestamp ASC
                    """, (p_id, start - 300, end + 600))
                    for c_row in cursor.fetchall():
                        commits.append({
                            "hash": c_row[0],
                            "timestamp": c_row[1],
                            "message": c_row[2],
                            "cleaned_message": c_row[3]
                        })
                        
                sessions.append(Session(
                    id=s_id,
                    start_time=start,
                    end_time=end,
                    duration_seconds=duration,
                    project_id=p_id,
                    commands=commands,
                    commits=commits,
                    ai_summary=ai_sum
                ))
        finally:
            conn.close()
        return sessions

    def get_project_sessions(self, project_id: int, start_ts: int) -> List[Session]:
        """Get sessions for a specific project starting after the start_ts timestamp"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id, start_time, end_time, duration_seconds, project_id, ai_summary
                FROM sessions
                WHERE project_id = ? AND start_time >= ?
                ORDER BY start_time ASC
            """, (project_id, start_ts))
            session_rows = cursor.fetchall()
            
            sessions = []
            for row in session_rows:
                s_id, start, end, duration, p_id, ai_sum = row
    
                
                cursor.execute("""
                    SELECT id, timestamp, command, exit_code, session_id, project_id, recovery_source
                    FROM commands
                    WHERE session_id = ?
                    ORDER BY timestamp ASC
                """, (s_id,))
                cmd_rows = cursor.fetchall()

                commands = []
                for c_row in cmd_rows:
                    c_id, timestamp, command_text, exit_code, _, cmd_p_id, rec_src = c_row
                    commands.append(Command(
                        id=c_id,
                        timestamp=timestamp,
                        command=command_text,
                        exit_code=exit_code,
                        session_id=s_id,
                        project_id=cmd_p_id,
                        recovery_source=rec_src
                    ))
                    
                # 3. Fetch all commits for this session (5m pre, 10m post buffers)
                commits = []
                if p_id is not None:
                    cursor.execute("""
                        SELECT hash, timestamp, message, cleaned_message
                        FROM commits
                        WHERE project_id = ? AND timestamp >= ? AND timestamp <= ?
                        ORDER BY timestamp ASC
                    """, (p_id, start - 300, end + 600))
                    for c_row in cursor.fetchall():
                        commits.append({
                            "hash": c_row[0],
                            "timestamp": c_row[1],
                            "message": c_row[2],
                            "cleaned_message": c_row[3]
                        })
                        
                sessions.append(Session(
                    id=s_id,
                    start_time=start,
                    end_time=end,
                    duration_seconds=duration,
                    project_id=p_id,
                    commands=commands,
                    commits=commits,
                    ai_summary=ai_sum
                ))
        finally:
            conn.close()
        return sessions

    def save_session_ai_summary(self, session_id: int, ai_summary: str) -> None:
        """Update a session's AI-generated summary in the database"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE sessions SET ai_summary = ? WHERE id = ?
            """, (ai_summary, session_id))
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def get_macro_summary(self, timeframe_id: str) -> Optional[str]:
        """Fetch cached macro summary (executive review) for a given timeframe"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT summary FROM macro_summaries WHERE timeframe_id = ?
            """, (timeframe_id,))
            row = cursor.fetchone()
        finally:
            conn.close()
        return row[0] if row else None

    def save_macro_summary(self, timeframe_id: str, type_str: str, summary: str) -> None:
        """Cache macro summary (executive review) in the database"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            # Delete first to ensure SQLite version compatibility without UPSERT (ON CONFLICT)
            cursor.execute("DELETE FROM macro_summaries WHERE timeframe_id = ?", (timeframe_id,))
            cursor.execute("""
                INSERT INTO macro_summaries (timeframe_id, type, summary)
                VALUES (?, ?, ?)
            """, (timeframe_id, type_str, summary))
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()


    def get_all_projects_with_stats(self) -> List[Project]:
        """Get all projects from database, joining with sessions to aggregate statistics"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT p.id, p.name, p.path, p.first_seen, p.last_seen,
                       COUNT(s.id) AS session_count,
                       SUM(s.duration_seconds) AS total_time
                FROM projects p
                LEFT JOIN sessions s ON p.id = s.project_id
                GROUP BY p.id
            """)
            
            rows = cursor.fetchall()
            projects = []
            for row in rows:
                p_id, name, path, first, last, s_count, t_time = row
                projects.append(Project(
                    id=p_id,
                    name=name,
                    path=path,
                    first_seen=first,
                    last_seen=last,
                    session_count=s_count or 0,
                    total_time=t_time or 0
                ))
        finally:
            conn.close()
        return projects

    def search_projects(self, query: str) -> List[Project]:
        """Fuzzy search projects by name or path using case-insensitive LIKE matches"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT p.id, p.name, p.path, p.first_seen, p.last_seen,
                       COUNT(s.id) AS session_count,
                       SUM(s.duration_seconds) AS total_time
                FROM projects p
                LEFT JOIN sessions s ON p.id = s.project_id
                WHERE p.name LIKE ? OR p.path LIKE ?
                GROUP BY p.id
            """, (f"%{query}%", f"%{query}%"))
            
            rows = cursor.fetchall()
            projects = []
            for row in rows:
                p_id, name, path, first, last, s_count, t_time = row
                projects.append(Project(
                    id=p_id,
                    name=name,
                    path=path,
                    first_seen=first,
                    last_seen=last,
                    session_count=s_count or 0,
                    total_time=t_time or 0
                ))
            
            # Sort results: exact name matches first, then prefix matches, then substring matches, then path matches
            def sort_key(p):
                name_lower = p.name.lower()
                query_lower = query.lower()
                if name_lower == query_lower:
                    return (0, name_lower)
                if name_lower.startswith(query_lower):
                    return (1, name_lower)
                if query_lower in name_lower:
                    return (2, name_lower)
                return (3, name_lower)
                
            projects.sort(key=sort_key)
        finally:
            conn.close()
        return projects

    def save_commits(self, project_id: int, commits: List[Dict]) -> None:
        """Upsert commits for a project using INSERT OR IGNORE"""
        if not commits:
            return
            
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            commit_rows = [
                (c["hash"], c["timestamp"], c["message"], c["cleaned_message"], project_id)
                for c in commits
            ]
            
            cursor.executemany("""
                INSERT OR IGNORE INTO commits (hash, timestamp, message, cleaned_message, project_id)
                VALUES (?, ?, ?, ?, ?)
            """, commit_rows)
            
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def get_session_commits(self, project_id: int, start_time: int, end_time: int) -> List[Dict]:
        """Fetch commits made during a session's time window (with pre and post buffers)"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            # 5 minutes pre-buffer, 10 minutes post-buffer
            cursor.execute("""
                SELECT hash, timestamp, message, cleaned_message
                FROM commits
                WHERE project_id = ? AND timestamp >= ? AND timestamp <= ?
                ORDER BY timestamp ASC
            """, (project_id, start_time - 300, end_time + 600))
            
            rows = cursor.fetchall()
            commits = []
            for r in rows:
                commits.append({
                    "hash": r[0],
                    "timestamp": r[1],
                    "message": r[2],
                    "cleaned_message": r[3]
                })
        finally:
            conn.close()
        return commits

    def get_all_commands_lookup(self) -> Dict[str, List[int]]:
        """Return a mapping of command string to list of its stored timestamps (sorted)"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT command, timestamp FROM commands ORDER BY timestamp ASC")
            lookup = {}
            for cmd, ts in cursor.fetchall():
                if cmd not in lookup:
                    lookup[cmd] = []
                lookup[cmd].append(ts)
            return lookup
        finally:
            conn.close()

    def search_sessions(self, query: str, project_filter: Optional[str] = None, since_ts: Optional[int] = None) -> List[Dict]:
        """Query sessions containing matching commands, matching project names, or matching commits"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            query_val = f"%{query}%"
            
            sql = """
                SELECT DISTINCT s.id, s.start_time, s.end_time, s.duration_seconds, s.project_id, p.name, p.path, s.ai_summary
                FROM sessions s
                LEFT JOIN projects p ON s.project_id = p.id
                LEFT JOIN commands c ON s.id = c.session_id
                LEFT JOIN commits co ON s.project_id = co.project_id 
                    AND co.timestamp >= s.start_time - 300 
                    AND co.timestamp <= s.end_time + 600
                WHERE (
                    p.name LIKE ?
                    OR c.command LIKE ?
                    OR co.message LIKE ?
                    OR co.cleaned_message LIKE ?
                    OR s.ai_summary LIKE ?
                )
            """
            params = [query_val, query_val, query_val, query_val, query_val]
            
            if project_filter:
                sql += " AND p.name LIKE ?"
                params.append(f"%{project_filter}%")
                
            if since_ts:
                sql += " AND s.start_time >= ?"
                params.append(since_ts)
                
            sql += " ORDER BY s.start_time DESC"
            
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            
            results = []
            for row in rows:
                s_id, start_time, end_time, duration, p_id, p_name, p_path, ai_sum = row
                
                # Fetch all commands in this session
                cursor.execute("""
                    SELECT command FROM commands WHERE session_id = ? ORDER BY timestamp ASC
                """, (s_id,))
                all_cmds = [r[0] for r in cursor.fetchall()]
                
                # Fetch matching commands in this session
                cursor.execute("""
                    SELECT command FROM commands WHERE session_id = ? AND command LIKE ? ORDER BY timestamp ASC
                """, (s_id, query_val))
                matching_cmds = [r[0] for r in cursor.fetchall()]
                
                # Fetch all commits in this session (using buffer)
                all_commits = []
                matching_commits = []
                if p_id is not None:
                    cursor.execute("""
                        SELECT hash, timestamp, message, cleaned_message 
                        FROM commits 
                        WHERE project_id = ? AND timestamp >= ? AND timestamp <= ?
                        ORDER BY timestamp ASC
                    """, (p_id, start_time - 300, end_time + 600))
                    for c_row in cursor.fetchall():
                        c_dict = {
                            "hash": c_row[0],
                            "timestamp": c_row[1],
                            "message": c_row[2],
                            "cleaned_message": c_row[3]
                        }
                        all_commits.append(c_dict)
                        # Check if commit matches query
                        if query.lower() in c_row[2].lower() or query.lower() in c_row[3].lower():
                            matching_commits.append(c_dict)
                            
                results.append({
                    "session_id": s_id,
                    "start_time": start_time,
                    "end_time": end_time,
                    "duration_seconds": duration,
                    "project_id": p_id,
                    "project_name": p_name or "General / No Project",
                    "project_path": p_path or "",
                    "ai_summary": ai_sum,
                    "all_commands": all_cmds,
                    "matching_commands": matching_cmds,
                    "all_commits": all_commits,
                    "matching_commits": matching_commits
                })
        finally:
            conn.close()
        return results

    def optimize(self) -> None:
        """Run VACUUM on the database to defragment it and reclaim disk space."""
        conn = self.get_connection()
        try:
            conn.execute("VACUUM;")
        finally:
            conn.close()
