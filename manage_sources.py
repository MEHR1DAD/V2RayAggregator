import httpx
import asyncio
import os
import time
import yaml
from database import initialize_db, get_all_sources_to_check, update_source_status

# --- Load Configuration ---
with open("config.yml", "r") as f:
    config = yaml.safe_load(f)

# --- Constants from Config File ---
DISCOVERED_SOURCES_FILE = config['paths']['discovered_sources']
REQUEST_TIMEOUT = config['settings']['request_timeout']
SEED_SOURCES_FILE = "seed_sources.txt"
VALID_PROTOCOLS = ('vmess://', 'vless://', 'ss://', 'ssr://', 'trojan://',
                   'hysteria://', 'hysteria2://', 'tuic://', 'brook://',
                   'socks://', 'wireguard://')

# --- Batch Processing Settings ---
BATCH_SIZE = 100  # تعداد URL برای بررسی در هر دسته
DELAY_BETWEEN_BATCHES = 5  # ثانیه تأخیر بین هر دسته

def ensure_initial_sources_exist():
    """Ensures that all sources from the seed_sources.txt file exist in the database."""
    print("Ensuring all initial seed sources exist in the database...")

    if not os.path.exists(SEED_SOURCES_FILE):
        print(f"Warning: '{SEED_SOURCES_FILE}' not found. Skipping initial seed.")
        return

    with open(SEED_SOURCES_FILE, 'r', encoding='utf-8') as f:
        seed_urls = {line.strip() for line in f if line.strip()}

    all_db_sources = set(get_all_sources_to_check())

    new_manual_sources = 0
    for url in seed_urls:
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

async def is_source_valid(client, url):
    """Checks a single source asynchronously."""
    try:
        response = await client.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        content = response.text
        if any(line.strip().startswith(VALID_PROTOCOLS) for line in content.splitlines()):
            return url, 'active'
        return url, 'dead'  # Valid content but no configs
    except (httpx.RequestError, httpx.HTTPStatusError):
        return url, 'dead'

async def main():
    print("--- Source Management Process Started ---")
    
    initialize_db()
    ensure_initial_sources_exist()

    discovered_urls = read_urls_from_txt(DISCOVERED_SOURCES_FILE)
    for url in discovered_urls:
        update_source_status(url, 'active') # Add new discovered sources for checking

    all_potential_urls = list(set(get_all_sources_to_check()))

    if not all_potential_urls:
        print("No sources found to check. Exiting.")
        return

    print(f"Checking {len(all_potential_urls)} potential sources in batches of {BATCH_SIZE}...")
    
    active_count = 0
    dead_count = 0
    
    # --- New Batch Processing Loop ---
    for i in range(0, len(all_potential_urls), BATCH_SIZE):
        batch_urls = all_potential_urls[i:i + BATCH_SIZE]
        print(f"\n--- Processing batch {i // BATCH_SIZE + 1} of {len(all_potential_urls) // BATCH_SIZE + 1} ({len(batch_urls)} URLs) ---")

        tasks = []
        async with httpx.AsyncClient(follow_redirects=True) as client:
            for url in batch_urls:
                tasks.append(is_source_valid(client, url))
            
            results = await asyncio.gather(*tasks)

        for url, status in results:
            update_source_status(url, status)
            if status == 'active':
                active_count += 1
            else:
                dead_count += 1
        
        print(f"Batch finished. Current totals - Active: {active_count}, Dead: {dead_count}")

        # Add delay between batches to avoid rate limiting
        if i + BATCH_SIZE < len(all_potential_urls):
            print(f"Waiting for {DELAY_BETWEEN_BATCHES} seconds before next batch...")
            await asyncio.sleep(DELAY_BETWEEN_BATCHES)

    print(f"\nFinished checking all batches. Final counts - Active: {active_count}, Dead: {dead_count}")

    if os.path.exists(DISCOVERED_SOURCES_FILE):
        open(DISCOVERED_SOURCES_FILE, 'w').close()
        print(f"\nCleared '{DISCOVERED_SOURCES_FILE}'.")

    print("\n--- Source Management Process Finished ---")

if __name__ == "__main__":
    if not os.path.exists('config.yml'):
        print("FATAL: config.yml not found. Please create it first.")
    else:
        asyncio.run(main())
