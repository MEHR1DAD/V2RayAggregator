import httpx
import asyncio
import json
import os

# --- Constants ---
# این بخش باید وجود داشته باشد تا کد به درستی کار کند
SOURCES_FILE = "active_sources.json"
MERGED_CONFIGS_FILE = "merged_configs.txt"
REQUEST_TIMEOUT = 10
ALLOWED_PROTOCOLS = {
    "vmess://", "vless://", "ss://", "ssr://", "trojan://",
    "hysteria://", "hysteria2://", "brook://", "tuic://",
    "socks://", "wireguard://"
}
# --- End of Constants ---


def load_urls():
    """Loads subscription URLs from the json file."""
    if not os.path.exists(SOURCES_FILE):
        print(f"Error: Source file '{SOURCES_FILE}' not found.")
        return []
    try:
        with open(SOURCES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, TypeError):
        print(f"Error: Could not decode JSON from '{SOURCES_FILE}'.")
        return []

async def fetch_one(client, url):
    """Fetches content from a single URL asynchronously."""
    try:
        response = await client.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.text.splitlines()
    except (httpx.RequestError, httpx.HTTPStatusError) as e:
        print(f"Error fetching {url}: {e}")
        return []

async def fetch_all_configs(urls):
    """Gathers all configs from a list of URLs concurrently."""
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
    """Saves the merged configs to a file."""
    with open(MERGED_CONFIGS_FILE, "w", encoding="utf-8") as f:
        for config in sorted(configs):
            f.write(config + "\n")

async def main():
    """The main async function."""
    urls = load_urls()
    if urls:
        print(f"Loaded {len(urls)} sources from '{SOURCES_FILE}'")
        print("Fetching all sources concurrently...")
        configs = await fetch_all_configs(urls)
        print(f"Fetched {len(configs)} unique configurations.")
        save_configs(configs)
        print(f"Merged configurations into {MERGED_CONFIGS_FILE}")
    else:
        print("No sources to process. Exiting.")

if __name__ == "__main__":
    asyncio.run(main())
