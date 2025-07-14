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

def ensure_initial_sources_exist():
    """
    Ensures that all sources from the initial_seed_sources list in config.yml
    exist in the database. This allows for easy manual addition of sources.
    """
    print("Ensuring all initial seed sources exist in the database...")
    all_db_sources = set(get_all_sources_to_check())
    
    new_manual_sources = 0
    for url in INITIAL_SEED_SOURCES:
        if url not in all_db_sources:
            update_source_status(url, 'active')
            new_manual_sources += 1
            
    if new_manual_sources > 0:
        print(f"Added {new_manual_sources} new manually configured sources to the database.")

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
    ensure_initial_sources_exist()

    discovered_urls = read_urls_from_txt(DISCOVERED_SOURCES_FILE)
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
