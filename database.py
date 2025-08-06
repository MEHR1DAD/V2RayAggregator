import sqlite3
from datetime import datetime

DB_FILE = "aggregator_data.db"

def get_connection():
    """A helper function to get a database connection."""
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
    """Gets all unique source URLs from the database to be checked."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT url FROM sources")
    urls = [row[0] for row in cursor.fetchall()]
    conn.close()
    return urls

def get_active_sources():
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

def get_all_db_configs():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT config FROM configs")
    configs = [row[0] for row in cursor.fetchall()]
    conn.close()
    return configs

# *** تابع جدید برای پیشنهاد شما ***
def get_top_configs(limit: int):
    """۱۰۰ کانفیگ برتر را، صرف نظر از کشور، بر اساس سرعت برمی‌گرداند."""
    conn = get_connection()
    cursor = conn.cursor()
    query = "SELECT config FROM configs ORDER BY speed_kbps DESC LIMIT ?"
    cursor.execute(query, (limit,))
    configs = [row[0] for row in cursor.fetchall()]
    conn.close()
    return configs

def bulk_delete_configs(configs_to_delete: list):
    if not configs_to_delete:
        return
    conn = get_connection()
    cursor = conn.cursor()
    cursor.executemany("DELETE FROM configs WHERE config = ?", [(c,) for c in configs_to_delete])
    conn.commit()
    conn.close()
    print(f"Successfully deleted {len(configs_to_delete)} dead configs from the database.")

def get_average_speed(country_code: str) -> float:
    """Calculates the average speed for a given country."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT AVG(speed_kbps) FROM configs WHERE country_code = ? AND speed_kbps > 0", (country_code,))
    result = cursor.fetchone()[0]
    conn.close()
    return result if result else 0.0

def get_configs_above_speed(country_code: str, speed_kbps: float) -> list:
    """Gets all configs for a country above a certain speed, sorted from fastest to slowest."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT config FROM configs WHERE country_code = ? AND speed_kbps >= ? ORDER BY speed_kbps DESC",
        (country_code, speed_kbps)
    )
    configs = [row[0] for row in cursor.fetchall()]
    conn.close()
    return configs

def get_live_configs_no_speed(country_code: str) -> list:
    """Gets live configs that have not been speed-tested (speed is NULL or 0)."""
    conn = get_connection()
    cursor = conn.cursor()
    # Assuming configs with no speed test have speed_kbps as NULL or 0
    cursor.execute(
        "SELECT config FROM configs WHERE country_code = ? AND (speed_kbps IS NULL OR speed_kbps <= 1)",
        (country_code,)
    )
    configs = [row[0] for row in cursor.fetchall()]
    conn.close()
    return configs
