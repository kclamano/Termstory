import sqlite3
import time
from termstory.database import Database
import os

db_path = os.path.expanduser('~/.termstory/termstory.db')

def setup_fts(conn):
    cursor = conn.cursor()
    # Check if fts5 is available
    cursor.execute("PRAGMA compile_options;")
    options = [row[0] for row in cursor.fetchall()]
    if not any('FTS5' in opt for opt in options):
        print("FTS5 is not supported in this SQLite build.")
        return False

    print("FTS5 is supported. Creating virtual table...")
    cursor.execute("DROP TABLE IF EXISTS search_index;")
    cursor.execute("""
        CREATE VIRTUAL TABLE search_index USING fts5(
            content,
            type UNINDEXED,
            ref_id UNINDEXED,
            project_id UNINDEXED,
            timestamp UNINDEXED
        );
    """)
    conn.commit()
    return True

def populate_fts(conn):
    cursor = conn.cursor()
    print("Populating FTS5 index...")
    
    start_time = time.time()
    
    # Insert commands
    cursor.execute("""
        INSERT INTO search_index (content, type, ref_id, project_id, timestamp)
        SELECT command, 'command', session_id, project_id, timestamp FROM commands WHERE session_id IS NOT NULL;
    """)
    
    # Insert commits
    cursor.execute("""
        INSERT INTO search_index (content, type, ref_id, project_id, timestamp)
        SELECT cleaned_message, 'commit', hash, project_id, timestamp FROM commits;
    """)
    
    # Insert session AI summaries
    cursor.execute("""
        INSERT INTO search_index (content, type, ref_id, project_id, timestamp)
        SELECT ai_summary, 'session_summary', id, project_id, start_time FROM sessions WHERE ai_summary IS NOT NULL;
    """)
    
    conn.commit()
    print(f"Populated in {time.time() - start_time:.4f}s")

def search_fts(conn, query):
    cursor = conn.cursor()
    start_time = time.time()
    
    # Match using MATCH
    cursor.execute("""
        SELECT ref_id, type, content, timestamp
        FROM search_index
        WHERE search_index MATCH ?
        ORDER BY rank
        LIMIT 50;
    """, (query,))
    
    results = cursor.fetchall()
    duration = time.time() - start_time
    print(f"FTS5 Search for '{query}' found {len(results)} results in {duration:.4f}s")
    return duration

def search_traditional(conn, query):
    cursor = conn.cursor()
    start_time = time.time()
    
    # Traditional LIKE search across multiple tables
    query_val = f"%{query}%"
    
    sql = """
        SELECT s.id
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
        ORDER BY s.start_time DESC
        LIMIT 50;
    """
    cursor.execute(sql, (query_val, query_val, query_val, query_val, query_val))
    results = cursor.fetchall()
    duration = time.time() - start_time
    print(f"Traditional Search for '{query}' found {len(results)} results in {duration:.4f}s")
    return duration

if __name__ == "__main__":
    if not os.path.exists(db_path):
        print(f"Database {db_path} not found.")
        exit(1)
        
    conn = sqlite3.connect(db_path)
    
    if setup_fts(conn):
        populate_fts(conn)
        
        # Test queries
        queries = ["docker", "git", "python", "test", "build"]
        
        fts_times = []
        trad_times = []
        
        for q in queries:
            print(f"\n--- Testing query: {q} ---")
            fts_times.append(search_fts(conn, q))
            trad_times.append(search_traditional(conn, q))
            
        print("\n--- Summary ---")
        avg_fts = sum(fts_times)/len(fts_times)
        avg_trad = sum(trad_times)/len(trad_times)
        print(f"Average FTS5 Time: {avg_fts:.4f}s")
        print(f"Average Traditional Time: {avg_trad:.4f}s")
        if avg_trad > 0:
            print(f"Speedup: {avg_trad / avg_fts:.2f}x")
            
    conn.close()
