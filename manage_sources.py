import requests
import os
import yaml
from database import initialize_db, get_all_sources_to_check, update_source_status, get_connection

# --- Load Configuration ---
with open("config.yml", "r") as f:
    config = yaml.safe_load(f)

# --- Constants from Config File ---
DISCOVERED_SOURCES_FILE = config['paths']['discovered_sources']
REQUEST_TIMEOUT = config['settings']['request_timeout']
INITIAL_SEED_SOURCES = config.get('initial_seed_sources', [])
VALID_PROTOCOLS = ('vmess://', 'vless://', 'ss://', 'ssr://', 'trojan://',
                   'hysteria://', 'hysteria2://', 'tuic://', 'brook://',
                   'socks://', 'wireguard://')

def seed_database_if_empty():
    """Checks if the sources table is empty and seeds it from config if it is."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM sources")
    count = cursor.fetchone()[0]
    conn.close()
    
    if count == 0 and INITIAL_SEED_SOURCES:
        print("Database is empty. Seeding with initial sources from config.yml...")
        for url in INITIAL_SEED_SOURCES:
            # اصلاح کلیدی: منابع اولیه را با وضعیت 'active' اضافه می‌کنیم
            update_source_status(url, 'active')
        print(f"Seeded {len(INITIAL_SEED_SOURCES)} initial sources.")

def read_urls_from_txt(file_path):
    if not os.path.exists(file_path):
        return set()
    with open(file_path, 'r', encoding='utf-8') as f:
        return {line.strip() for line in f if line.strip()}

def is_source_valid(url):
    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        content = response.text
        return any(line.strip().startswith(VALID_PROTOCOLS) for line in content.splitlines())
    except requests.RequestException:
        return False

def main():
    print("--- Source Management Process Started ---")
    
    initialize_db()
    seed_database_if_empty()

    sources_from_db = set(get_all_sources_to_check())
    discovered_urls = read_urls_from_txt(DISCOVERED_SOURCES_FILE)
    
    # منابع جدید کشف شده را با وضعیت 'active' اضافه می‌کنیم تا بلافاصله تست شوند
    for url in discovered_urls:
        update_source_status(url, 'active')

    all_potential_urls = set(get_all_sources_to_check())

    if not all_potential_urls:
        print("No sources found to check. Exiting.")
        return

    print(f"Checking a total of {len(all_potential_urls)} potential sources...")

    for i, url in enumerate(all_potential_urls):
        print(f"  ({i+1}/{len(all_potential_urls)}) Checking: {url[:80]}...")
        if is_source_valid(url):
            update_source_status(url, 'active')
            print("   -> ✅ Valid, status set to 'active'")
        else:
            update_source_status(url, 'dead')
            print("   -> ❌ Invalid, status set to 'dead'")

    if os.path.exists(DISCOVERED_SOURCES_FILE):
        open(DISCOVERED_SOURCES_FILE, 'w').close()
        print(f"\nCleared '{DISCOVERED_SOURCES_FILE}'.")

    print("\n--- Source Management Process Finished ---")

if __name__ == "__main__":
    if not os.path.exists('config.yml'):
        print("FATAL: config.yml not found. Please create it first.")
    else:
        main()
