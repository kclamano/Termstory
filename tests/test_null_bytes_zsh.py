import os
import tempfile
import sqlite3
from termstory.parser import parse_all_histories
from termstory.database import Database

def test_null():
    content = b': 1672531200:0;echo "Hello \x00 World"\n'
    with tempfile.NamedTemporaryFile(mode='wb', suffix='.zsh_history', delete=False) as f:
        f.write(content)
        temp_path = f.name
    try:
        db_path = tempfile.mktemp(suffix='.db')
        db = Database(db_path)
        db.init_db()
        commands = parse_all_histories([temp_path], db=db)
        print("Parsed:", repr(commands[0].command) if commands else "None")
        
        # Now try to save it to DB
        from termstory.session import create_sessions
        from termstory.project import detect_projects
        sessions = create_sessions(commands)
        projects = detect_projects(sessions)
        db.save_data(projects, sessions, commands)
        print("Saved successfully!")
        
        # Read back
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("SELECT command FROM commands")
        print("Read from DB:", repr(c.fetchone()[0]))
    finally:
        os.remove(temp_path)
        if os.path.exists(db_path):
            os.remove(db_path)

test_null()
