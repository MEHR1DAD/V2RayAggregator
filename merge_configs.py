import httpx
import asyncio
import os
import time
import argparse # ماژول برای خواندن آرگومان‌های خط فرمان اضافه شد
from database import get_active_sources
from collections import defaultdict

# --- Constants ---
REQUEST_TIMEOUT = 10
KNOWN_PROTOCOLS = {"vmess", "vless", "ss", "ssr", "trojan", "hysteria", "hysteria2", "tuic", "socks", "wireguard"}

# --- Batch Processing Settings ---
BATCH_SIZE = 100
DELAY_BETWEEN_BATCHES = 5  # seconds

async def fetch_one(client, url):
    """Fetches configs from a single URL."""
    try:
        response = await client.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.text.splitlines()
    except (httpx.RequestError, httpx.HTTPStatusError) as e:
        print(f"Error fetching {url}: {e}")
        return []

def process_results(results, configs_by_protocol):
    """Processes fetched results and separates them by protocol."""
    for result in results:
        if isinstance(result, list):
            for config in result:
                clean_config = config.strip().split('#')[0]
                if '://' in clean_config:
                    protocol = clean_config.split('://')[0].lower()
                    if protocol in KNOWN_PROTOCOLS:
                        configs_by_protocol[protocol].add(clean_config)

def save_separated_configs(configs_by_protocol, output_dir): # آرگومان output_dir اضافه شد
    """Saves the separated configs into different files in the specified directory."""
    # به جای ثابت، از مسیر ورودی استفاده می‌کنیم
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"\n--- Saving configs into separate files in '{output_dir}' directory ---")
    
    for protocol, configs in sorted(configs_by_protocol.items()):
        if not configs:
            continue
            
        # مسیر فایل خروجی با استفاده از output_dir ساخته می‌شود
        filename = os.path.join(output_dir, f"{protocol}_configs.txt")
        try:
            with open(filename, "w", encoding="utf-8") as f:
                for config in sorted(list(configs)):
                    f.write(config + "\n")
            print(f"✅ Saved {len(configs)} configs to {filename}")
        except Exception as e:
            print(f"❌ Error saving file {filename}: {e}")

async def main(output_dir): # آرگومان output_dir به تابع اصلی اضافه شد
    """Main function to run the process."""
    urls = get_active_sources()
    
    if not urls:
        print("No active sources found in database. Exiting.")
        return

    print(f"Loaded {len(urls)} active sources from database.")
    print(f"Fetching and separating sources in batches of {BATCH_SIZE}...")
    
    configs_by_protocol = defaultdict(set)
    
    for i in range(0, len(urls), BATCH_SIZE):
        batch_urls = urls[i:i + BATCH_SIZE]
        print(f"\n--- Processing batch {i // BATCH_SIZE + 1} of {len(urls) // BATCH_SIZE + 1} ({len(batch_urls)} URLs) ---")

        async with httpx.AsyncClient() as client:
            tasks = [fetch_one(client, url) for url in batch_urls]
            results = await asyncio.gather(*tasks, return_exceptions=True)
        
        process_results(results, configs_by_protocol)
        
        total_fetched = sum(len(s) for s in configs_by_protocol.values())
        print(f"Batch finished. Total unique configs fetched so far: {total_fetched}")

        if i + BATCH_SIZE < len(urls):
            print(f"Waiting for {DELAY_BETWEEN_BATCHES} seconds before next batch...")
            await asyncio.sleep(DELAY_BETWEEN_BATCHES)

    total_fetched = sum(len(s) for s in configs_by_protocol.values())
    print(f"\nFinished fetching all batches. Fetched a total of {total_fetched} unique configurations for {len(configs_by_protocol)} protocols.")
    
    # پاس دادن مسیر خروجی به تابع ذخیره‌سازی
    save_separated_configs(configs_by_protocol, output_dir)
    
    print("\nSeparation process finished successfully.")

if __name__ == "__main__":
    # بخش خواندن آرگومان‌های خط فرمان
    parser = argparse.ArgumentParser(description="Fetch, merge, and separate proxy configs by protocol.")
    parser.add_argument(
        '--output-dir',
        required=True,
        help="The directory where separated protocol configs will be saved."
    )
    args = parser.parse_args()
    
    # اجرای تابع اصلی با مسیر خروجی مشخص شده
    asyncio.run(main(args.output_dir))
