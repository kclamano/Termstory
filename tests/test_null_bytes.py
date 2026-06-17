import os
import tempfile
from termstory.parser import parse_all_histories
from termstory.database import Database
def test_null():
    content = b': 1672531200:0;echo "Hello \x00 World"\n'
    with tempfile.NamedTemporaryFile(mode='wb', delete=False) as f:
        f.write(content)
        temp_path = f.name
    try:
        db_path = tempfile.mktemp(suffix='.db')
        db = Database(db_path)
        db.init_db()
        commands = parse_all_histories([temp_path], db=db)
        print("Parsed:", repr(commands[0].command) if commands else "None")
    finally:
        os.remove(temp_path)
        if os.path.exists(db_path):
            os.remove(db_path)
test_null()
