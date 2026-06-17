import os
import sys
import tempfile
import traceback

from termstory.parser import parse_zsh_history, parse_all_histories
from termstory.session import create_sessions
from termstory.project import detect_projects
from termstory.database import Database

def test_overflow():
    # Large timestamp that fits in Python int but NOT in SQLite INTEGER (max is 9223372036854775807)
    content = b"""
: 9999999999999999999:0;echo "Huge timestamp"
"""
    
    with tempfile.NamedTemporaryFile(mode='wb', delete=False) as f:
        f.write(content)
        temp_path = f.name
        
    try:
        db_path = tempfile.mktemp(suffix='.db')
        db = Database(db_path)
        db.init_db()
        
        commands = parse_all_histories([temp_path], db=db)
        sessions = create_sessions(commands)
        projects = detect_projects(sessions)
        
        print(f"Commands parsed: {len(commands)}")
        for c in commands: print(c.timestamp)
        db.save_data(projects, sessions, commands)
        print("Success! No crashes.")
        
    except Exception as e:
        print("CRASH DETECTED!")
        traceback.print_exc()
    finally:
        os.remove(temp_path)
        if os.path.exists(db_path):
            os.remove(db_path)

if __name__ == "__main__":
    test_overflow()
