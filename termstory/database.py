import sqlite3
from datetime import datetime, time
from typing import List, Dict, Optional, Set, Tuple
from termstory.models import Command, Session, Project

class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        
    def get_connection(self) -> sqlite3.Connection:
        """Create and return a database connection with foreign key support enabled"""
        conn = sqlite3.connect(self.db_path)
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
            name TEXT NOT NULL UNIQUE,
            path TEXT,
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
        
        # Indexes for fast querying
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_commands_timestamp ON commands(timestamp);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_commands_session_id ON commands(session_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_start_time ON sessions(start_time);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_project_id ON sessions(project_id);")
        
        conn.commit()
        conn.close()

    def save_data(self, projects: List[Project], sessions: List[Session], commands: List[Command]) -> None:
        """Optimized bulk insertion and updating of projects, sessions, and commands in a single transaction"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            # --- 1. Save Projects ---
            # Capture the temporary python project IDs first
            name_to_old_id = {p.name: p.id for p in projects if p.id is not None}
            
            cursor.execute("SELECT id, name, path, first_seen, last_seen FROM projects")
            db_projects = {row[1]: {"id": row[0], "path": row[2], "first_seen": row[3], "last_seen": row[4]} for row in cursor.fetchall()}
            
            project_id_map = {} # old_python_id -> db_id
            
            new_projects_to_insert = []
            projects_to_update = []
            inserted_names = set()
            
            for project in projects:
                if project.name in db_projects:
                    db_p = db_projects[project.name]
                    db_id = db_p["id"]
                    project.id = db_id
                    
                    # Update first_seen/last_seen ranges if they expanded
                    new_first = min(db_p["first_seen"], project.first_seen)
                    new_last = max(db_p["last_seen"], project.last_seen)
                    if new_first != db_p["first_seen"] or new_last != db_p["last_seen"] or project.path != db_p["path"]:
                        projects_to_update.append((project.path, new_first, new_last, db_id))
                else:
                    if project.name not in inserted_names:
                        new_projects_to_insert.append((project.name, project.path, project.first_seen, project.last_seen))
                        inserted_names.add(project.name)
                    
            if new_projects_to_insert:
                cursor.executemany("""
                    INSERT INTO projects (name, path, first_seen, last_seen)
                    VALUES (?, ?, ?, ?)
                """, new_projects_to_insert)
                
            if projects_to_update:
                cursor.executemany("""
                    UPDATE projects SET path = ?, first_seen = ?, last_seen = ? WHERE id = ?
                """, projects_to_update)
                
            # Re-read projects map to update project_id_map
            cursor.execute("SELECT id, name FROM projects")
            refreshed_projects = {row[1]: row[0] for row in cursor.fetchall()}
            
            for project in projects:
                project.id = refreshed_projects[project.name]
                
            # Build the ID mapping: old_python_id -> db_id
            for name, old_id in name_to_old_id.items():
                if name in refreshed_projects:
                    project_id_map[old_id] = refreshed_projects[name]
                
            # Re-map project_ids in sessions and commands
            for session in sessions:
                if session.project_id in project_id_map:
                    session.project_id = project_id_map[session.project_id]
            for cmd in commands:
                if cmd.project_id in project_id_map:
                    cmd.project_id = project_id_map[cmd.project_id]
                    
            # --- 2. Save Sessions ---
            cursor.execute("SELECT id, start_time, end_time, duration_seconds, project_id FROM sessions")
            db_sessions = {(row[1], row[2]): {"id": row[0], "duration": row[3], "project_id": row[4]} for row in cursor.fetchall()}
            
            session_id_map = {}
            
            for session in sessions:
                temp_id = session.id
                key = (session.start_time, session.end_time)
                if key in db_sessions:
                    db_id = db_sessions[key]["id"]
                    # Update if changed
                    if db_sessions[key]["duration"] != session.duration_seconds or db_sessions[key]["project_id"] != session.project_id:
                        cursor.execute("""
                            UPDATE sessions SET duration_seconds = ?, project_id = ? WHERE id = ?
                        """, (session.duration_seconds, session.project_id, db_id))
                    session.id = db_id
                else:
                    cursor.execute("""
                        INSERT INTO sessions (start_time, end_time, duration_seconds, project_id)
                        VALUES (?, ?, ?, ?)
                    """, (session.start_time, session.end_time, session.duration_seconds, session.project_id))
                    db_id = cursor.lastrowid
                    session.id = db_id
                    
                if temp_id is not None:
                    session_id_map[temp_id] = db_id
                    
            # Re-map session_ids in commands
            for cmd in commands:
                if cmd.session_id in session_id_map:
                    cmd.session_id = session_id_map[cmd.session_id]
                    
            # --- 3. Save Commands ---
            if commands:
                min_ts = min(cmd.timestamp for cmd in commands)
                max_ts = max(cmd.timestamp for cmd in commands)
                cursor.execute("""
                    SELECT timestamp, command, id, exit_code, session_id, project_id
                    FROM commands
                    WHERE timestamp >= ? AND timestamp <= ?
                """, (min_ts, max_ts))
                db_cmds = {(row[0], row[1]): {"id": row[2], "exit_code": row[3], "session_id": row[4], "project_id": row[5]} for row in cursor.fetchall()}
            else:
                db_cmds = {}
                
            new_commands_to_insert = []
            commands_to_update = []
            
            for cmd in commands:
                key = (cmd.timestamp, cmd.command)
                if key in db_cmds:
                    db_c = db_cmds[key]
                    cmd.id = db_c["id"]
                    # Update details if they mismatch
                    if db_c["exit_code"] != cmd.exit_code or db_c["session_id"] != cmd.session_id or db_c["project_id"] != cmd.project_id:
                        commands_to_update.append((cmd.exit_code, cmd.session_id, cmd.project_id, db_c["id"]))
                else:
                    new_commands_to_insert.append((cmd.timestamp, cmd.command, cmd.exit_code, cmd.session_id, cmd.project_id))
                    
            if new_commands_to_insert:
                cursor.executemany("""
                    INSERT INTO commands (timestamp, command, exit_code, session_id, project_id)
                    VALUES (?, ?, ?, ?, ?)
                """, new_commands_to_insert)
                
            if commands_to_update:
                cursor.executemany("""
                    UPDATE commands SET exit_code = ?, session_id = ?, project_id = ? WHERE id = ?
                """, commands_to_update)
                
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def get_today_sessions(self) -> List[Session]:
        """Query and return today's sessions, commands, and project attributes"""
        now = datetime.now()
        start_of_today = datetime.combine(now.date(), time.min)
        today_timestamp = int(start_of_today.timestamp())
        
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # 1. Fetch sessions starting today
        cursor.execute("""
            SELECT id, start_time, end_time, duration_seconds, project_id
            FROM sessions
            WHERE start_time >= ?
            ORDER BY start_time ASC
        """, (today_timestamp,))
        session_rows = cursor.fetchall()
        
        sessions = []
        for row in session_rows:
            s_id, start, end, duration, p_id = row
            
            # 2. Fetch all commands for this session
            cursor.execute("""
                SELECT id, timestamp, command, exit_code, session_id, project_id
                FROM commands
                WHERE session_id = ?
                ORDER BY timestamp ASC
            """, (s_id,))
            cmd_rows = cursor.fetchall()
            
            commands = []
            for c_row in cmd_rows:
                c_id, timestamp, command_text, exit_code, _, cmd_p_id = c_row
                commands.append(Command(
                    id=c_id,
                    timestamp=timestamp,
                    command=command_text,
                    exit_code=exit_code,
                    session_id=s_id,
                    project_id=cmd_p_id
                ))
                
            sessions.append(Session(
                id=s_id,
                start_time=start,
                end_time=end,
                duration_seconds=duration,
                project_id=p_id,
                commands=commands
            ))
            
        conn.close()
        return sessions

    def get_projects_by_ids(self, project_ids: List[int]) -> List[Project]:
        """Retrieve Project entities from database for a given list of IDs"""
        if not project_ids:
            return []
            
        conn = self.get_connection()
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
            
        conn.close()
        return projects
