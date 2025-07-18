import sqlite3
from datetime import datetime

DB_FILE = "aggregator_data.db"

def get_connection():
    """A helper function to get a database connection."""
    return sqlite3.connect(DB_FILE)

def initialize_db():
    """Creates the necessary tables if they don't already exist."""
    conn = get_connection()
    cursor = conn.cursor()
    # Your existing table creation logic...
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

def clear_configs_table():
    """Deletes all records from the configs table."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM configs")
        conn.commit()
        conn.close()
        print("🧹 Cleared all previous records from the configs table.")
    except Exception as e:
        print(f"Error clearing configs table: {e}")

def get_active_sources():
    """Gets all sources with 'active' status."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT url FROM sources WHERE status = 'active'")
    urls = [row[0] for row in cursor.fetchall()]
    conn.close()
    return urls

def update_source_status(url: str, status: str):
    """Inserts or updates a source's status in the database."""
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
    """Efficiently inserts or updates a list of configuration data."""
    if not configs_data:
        return
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
    """Gets configs for a specific country, sorted by speed."""
    conn = get_connection()
    cursor = conn.cursor()
    query = "SELECT config FROM configs WHERE country_code = ? ORDER BY speed_kbps DESC"
    if limit:
        query += f" LIMIT {limit}"
    cursor.execute(query, (country_code,))
    configs = [row[0] for row in cursor.fetchall()]
    conn.close()
    return configs

def get_countries_with_config_counts():
    """Gets a list of countries and their active config counts."""
    conn = get_connection()
    cursor = conn.cursor()
    query = """
        SELECT country_code, COUNT(config)
        FROM configs
        WHERE country_code IS NOT NULL AND country_code != ''
        GROUP BY country_code
        ORDER BY COUNT(config) DESC
    """
    cursor.execute(query)
    countries = cursor.fetchall()
    conn.close()
    return countries

# --- NEW FUNCTIONS FOR MAINTENANCE ---
def get_all_db_configs():
    """Gets all configs currently stored in the database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT config FROM configs")
    configs = [row[0] for row in cursor.fetchall()]
    conn.close()
    return configs

def bulk_delete_configs(configs_to_delete: list):
    """Efficiently deletes a list of configs from the database."""
    if not configs_to_delete:
        return
    conn = get_connection()
    cursor = conn.cursor()
    # Need to wrap each config in a tuple for executemany
    cursor.executemany("DELETE FROM configs WHERE config = ?", [(c,) for c in configs_to_delete])
    conn.commit()
    conn.close()
    print(f"Successfully deleted {len(configs_to_delete)} dead configs from the database.")