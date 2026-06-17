import sqlite3
import threading
import time
import os
import random
from termstory.database import Database

db_path = "stress_test.db"
if os.path.exists(db_path):
    os.remove(db_path)

db = Database(db_path)
db.init_db()

# Insert a project to satisfy foreign keys
conn = db.get_connection()
conn.execute("INSERT INTO projects (name, path) VALUES ('TestProject', '/test')")
conn.commit()
conn.close()

def writer_thread(thread_id, num_writes):
    try:
        for i in range(num_writes):
            # Simulate save_sessions / save_data
            # Uses BEGIN IMMEDIATE explicitly to prevent deadlocks
            conn = db.get_connection()
            try:
                conn.execute("BEGIN IMMEDIATE")
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO sessions (start_time, end_time, duration_seconds, project_id)
                    VALUES (?, ?, ?, ?)
                """, (time.time(), time.time()+100, 100, 1))
                
                # simulate slow write
                time.sleep(random.uniform(0.001, 0.01))
                
                conn.commit()
            except sqlite3.OperationalError as e:
                print(f"Writer {thread_id} failed: {e}")
            finally:
                conn.close()
    except Exception as e:
        print(f"Writer error: {e}")

def reader_thread(thread_id, num_reads):
    try:
        for i in range(num_reads):
            conn = db.get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM sessions")
                count = cursor.fetchone()[0]
                # simulate slow read
                time.sleep(random.uniform(0.001, 0.005))
            except sqlite3.OperationalError as e:
                print(f"Reader {thread_id} failed: {e}")
            finally:
                conn.close()
    except Exception as e:
        print(f"Reader error: {e}")

def run_stress_test():
    print("Starting concurrency stress test...")
    threads = []
    
    # 10 writers, 20 readers
    for i in range(10):
        t = threading.Thread(target=writer_thread, args=(i, 50))
        threads.append(t)
        
    for i in range(20):
        t = threading.Thread(target=reader_thread, args=(i, 100))
        threads.append(t)
        
    start = time.time()
    for t in threads:
        t.start()
        
    for t in threads:
        t.join()
        
    conn = db.get_connection()
    count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    conn.close()
    
    duration = time.time() - start
    print(f"Stress test complete in {duration:.2f}s!")
    print(f"Total sessions inserted: {count} (Expected: 500)")
    if count == 500:
        print("SUCCESS: No deadlocks occurred. The WAL mode and BEGIN IMMEDIATE effectively handled high concurrency.")
    else:
        print("FAILED: Some inserts were lost due to deadlocks.")

if __name__ == "__main__":
    run_stress_test()
    if os.path.exists(db_path):
        os.remove(db_path)
