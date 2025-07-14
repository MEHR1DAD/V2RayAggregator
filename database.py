import sqlite3
from datetime import datetime

DB_FILE = "aggregator_data.db"

def get_connection():
    return sqlite3.connect(DB_FILE)

def initialize_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sources (
            url TEXT PRIMARY KEY,
            status TEXT NOT NULL CHECK(status IN ('active', 'dead', 'new')),
            last_checked TEXT NOT NULL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS configs (
            config TEXT PRIMARY KEY,
            source_url TEXT,
            country_code TEXT,
            speed_kbps REAL,
            last_tested TEXT
        )
    ''')
    conn.commit()
    conn.close()

def get_all_sources_to_check():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT url FROM sources")
    urls = [row[0] for row in cursor.fetchall()]
    conn.close()
    return urls

def get_active_sources():
    """Returns a list of all URLs with 'active' status."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT url FROM sources WHERE status = 'active'")
    urls = [row[0] for row in cursor.fetchall()]
    conn.close()
    return urls

def update_source_status(url: str, status: str):
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.utcnow().isoformat()
    cursor.execute('''
        INSERT INTO sources (url, status, last_checked) VALUES (?, ?, ?)
        ON CONFLICT(url) DO UPDATE SET
            status = excluded.status,
            last_checked = excluded.last_checked
    ''', (url, status, now))
    conn.commit()
    conn.close()

def bulk_update_configs(configs_data: list):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.executemany('''
        INSERT INTO configs (config, source_url, country_code, speed_kbps, last_tested) VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(config) DO UPDATE SET
            source_url = excluded.source_url,
            country_code = excluded.country_code,
            speed_kbps = excluded.speed_kbps,
            last_tested = excluded.last_tested
    ''', configs_data)
    conn.commit()
    conn.close()
    print(f"Successfully upserted {len(configs_data)} configs into the database.")

def get_configs_by_country(country_code: str, limit: int = None):
    conn = get_connection()
    cursor = conn.cursor()
    query = "SELECT config FROM configs WHERE country_code = ? ORDER BY speed_kbps DESC"
    if limit:
        query += f" LIMIT {limit}"
    cursor.execute(query, (country_code,))
    configs = [row[0] for row in cursor.fetchall()]
    conn.close()
    return configs
