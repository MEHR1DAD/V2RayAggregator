import httpx
import asyncio
import os
from database import get_active_sources
from collections import defaultdict

# --- Constants ---
OUTPUT_DIR = "protocol_configs"  # A dedicated directory for separated configs
REQUEST_TIMEOUT = 10
# --- End of Constants ---

async def fetch_one(client, url):
    """Fetches configs from a single URL."""
    try:
        response = await client.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.text.splitlines()
    except (httpx.RequestError, httpx.HTTPStatusError) as e:
        print(f"Error fetching {url}: {e}")
        return []

async def fetch_and_separate_configs(urls):
    """Fetches all configs and separates them by protocol."""
    # Use defaultdict for cleaner code to handle new protocols automatically
    configs_by_protocol = defaultdict(set)
    
    async with httpx.AsyncClient() as client:
        tasks = [fetch_one(client, url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    for result in results:
        if isinstance(result, list):
            for config in result:
                config = config.strip()
                if '://' in config:
                    protocol = config.split('://')[0]
                    configs_by_protocol[protocol].add(config)
                    
    return configs_by_protocol

def save_separated_configs(configs_by_protocol):
    """Saves the separated configs into different files."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    print(f"\n--- Saving configs into separate files in '{OUTPUT_DIR}' directory ---")
    
    for protocol, configs in sorted(configs_by_protocol.items()):
        if not configs:
            continue
            
        filename = os.path.join(OUTPUT_DIR, f"{protocol}_configs.txt")
        try:
            with open(filename, "w", encoding="utf-8") as f:
                for config in sorted(list(configs)):
                    f.write(config + "\n")
            print(f"✅ Saved {len(configs)} configs to {filename}")
        except Exception as e:
            print(f"❌ Error saving file {filename}: {e}")

async def main():
    """Main function to run the process."""
    urls = get_active_sources()
    
    if urls:
        print(f"Loaded {len(urls)} active sources from database.")
        print("Fetching and separating all sources concurrently...")
        
        configs_by_protocol = await fetch_and_separate_configs(urls)
        
        total_fetched = sum(len(s) for s in configs_by_protocol.values())
        print(f"Fetched {total_fetched} unique configurations for {len(configs_by_protocol)} protocols.")
        
        save_separated_configs(configs_by_protocol)
        
        print("\nSeparation process finished successfully.")
    else:
        print("No active sources found in database. Exiting.")

if __name__ == "__main__":
    asyncio.run(main())
