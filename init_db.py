import sqlite3

conn = sqlite3.connect("movies.db")
conn.execute("""
CREATE TABLE IF NOT EXISTS movies (
    code TEXT PRIMARY KEY,
    title TEXT,
    file_id TEXT,
    views INTEGER DEFAULT 0,
    downloads INTEGER DEFAULT 0
)
""")

conn.execute("""
CREATE TABLE IF NOT EXISTS downloads (
    user_id INTEGER,
    code TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")
conn.commit()
conn.close()
print("✅ DB tayyor")
