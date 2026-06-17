import sqlite3
import traceback

def test_db():
    try:
        conn = sqlite3.connect("test_corrupt.db")
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE test (id INTEGER)")
        conn.commit()
        
        # Corrupt the file
        with open("test_corrupt.db", "wb") as f:
            f.write(b"NOT A SQLITE DATABASE FILE" + b"\x00" * 1000)
            
        from termstory.database import Database
        from termstory.cli import safe_init_db
        db = Database("test_corrupt.db")
        safe_init_db(db)
        print("No crash!")
    except Exception as e:
        print("CRASH DETECTED!")
        traceback.print_exc()

if __name__ == "__main__":
    test_db()
