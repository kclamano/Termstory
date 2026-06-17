import os
import sys
import tempfile
import traceback

from termstory.parser import parse_zsh_history, parse_all_histories
from termstory.session import create_sessions
from termstory.project import detect_projects
from termstory.database import Database

def test_parser():
    # Generate corrupted history
    content = b"""
# Normal entry
: 1672531200:0;echo "Hello World"
# Negative timestamp
: -100:0;echo "Negative"
# Future timestamp (year 3000)
: 32503680000:0;echo "Future"
# Null byte in command
: 1672531205:0;echo "Null \x00 Byte"
# 10k character command
: 1672531210:0;""" + b"A" * 10000 + b"""
# Invalid format
: abc:def;bad format
# Multi-line with null byte
: 1672531220:0;echo "multi \\
line \\
\x00 \\
done"
# Missing semicolon
: 1672531230:0echo "missing semi"
# Non-ascii bytes
: 1672531240:0;echo "\xff\xfe\xfd"
# Missing command
: 1672531250:0;
# Huge timestamp
: 9999999999999999999999999999999999999999:0;echo "huge ts"
# Negative duration
: 1672531260:-10;echo "neg duration"
"""
    
    with tempfile.NamedTemporaryFile(mode='wb', delete=False) as f:
        f.write(content)
        temp_path = f.name
        
    print(f"Created temp file: {temp_path}")
    
    try:
        # DB setup
        db_path = tempfile.mktemp(suffix='.db')
        db = Database(db_path)
        db.init_db()
        
        print("Running parser...")
        commands = parse_all_histories([temp_path], db=db)
        print(f"Parsed {len(commands)} commands.")
        
        print("Creating sessions...")
        sessions = create_sessions(commands)
        print(f"Created {len(sessions)} sessions.")
        
        print("Detecting projects...")
        projects = detect_projects(sessions)
        
        print("Saving data to DB...")
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
    test_parser()
