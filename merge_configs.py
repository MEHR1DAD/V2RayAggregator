import httpx
import asyncio
import os
from database import get_active_sources

# --- Constants ---
MERGED_CONFIGS_FILE = "merged_configs.txt"
REQUEST_TIMEOUT = 10
ALLOWED_PROTOCOLS = {
    "vmess://", "vless://", "ss://", "ssr://", "trojan://",
    "hysteria://", "hysteria2://", "brook://", "tuic://",
    "socks://", "wireguard://"
}
# --- End of Constants ---

async def fetch_one(client, url):
    try:
        response = await client.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.text.splitlines()
    except (httpx.RequestError, httpx.HTTPStatusError) as e:
        print(f"Error fetching {url}: {e}")
        return []

async def fetch_all_configs(urls):
    all_configs = set()
    async with httpx.AsyncClient() as client:
        tasks = [fetch_one(client, url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    for result in results:
        if isinstance(result, list):
            for config in result:
                config = config.strip()
                if config and any(config.startswith(protocol) for protocol in ALLOWED_PROTOCOLS):
                    all_configs.add(config)
    return all_configs

def save_configs(configs):
    with open(MERGED_CONFIGS_FILE, "w", encoding="utf-8") as f:
        for config in sorted(configs):
            f.write(config + "\n")

async def main():
    urls = get_active_sources()
    
    if urls:
        print(f"Loaded {len(urls)} active sources from database.")
        print("Fetching all sources concurrently...")
        configs = await fetch_all_configs(urls)
        print(f"Fetched {len(configs)} unique configurations.")
        save_configs(configs)
        print(f"Merged configurations into {MERGED_CONFIGS_FILE}")
    else:
        print("No active sources found in database. Exiting.")

if __name__ == "__main__":
    asyncio.run(main())
