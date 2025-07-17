import os
import asyncio
import subprocess
from datetime import datetime
import random
from utils import extract_ip_from_connection, resolve_to_ip, get_country_code
from database import initialize_db, bulk_update_configs, clear_configs_table
import geoip2.database
import yaml

# --- Load Configuration ---
with open("config.yml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)
    
# --- Constants ---
INPUT_DIR = "protocol_configs"
# Use a shorter timeout for development runs
CONNECTION_TIMEOUT = 5 
GEOIP_DB_PATH = "GeoLite2-City.mmdb"
# Use a smaller sample size for development runs
LIVENESS_SAMPLE_SIZE = 5000 
BATCH_SIZE = 500

async def check_port_open_curl(host, port):
    """Asynchronously checks if a TCP port is open using curl."""
    command = ['curl', '--connect-timeout', str(CONNECTION_TIMEOUT), '-v', f'telnet://{host}:{port}']
    process = await asyncio.create_subprocess_exec(
        *command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    await process.wait()
    return process.returncode == 0

async def process_batch(batch_of_targets, geoip_reader):
    """Processes a single batch of configs for liveness."""
    live_configs_in_batch = []
    now = datetime.utcnow().isoformat()

    tasks = [check_port_open_curl(target['host'], target['port']) for target in batch_of_targets]
    results = await asyncio.gather(*tasks)

    for target, is_live in zip(batch_of_targets, results):
        if is_live:
            ip = resolve_to_ip(target['host'])
            country = get_country_code(ip, geoip_reader)
            if country:
                live_configs_in_batch.append((target['config'], 'unknown', country, 1.0, now))
                print(f"✅ Live | {country} | {target['config'][:50]}...")
    
    return live_configs_in_batch

async def main():
    """Main function to run the liveness check process."""
    initialize_db()
    clear_configs_table()
    
    if not os.path.exists(GEOIP_DB_PATH):
        print(f"GeoIP database not found at {GEOIP_DB_PATH}. Cannot proceed.")
        return
        
    geoip_reader = geoip2.database.Reader(GEOIP_DB_PATH)
    
    if not os.path.exists(INPUT_DIR):
        print(f"Input directory '{INPUT_DIR}' not found. Exiting.")
        return
    
    all_configs = []
    for filename in os.listdir(INPUT_DIR):
        if filename.endswith("_configs.txt"):
            file_path = os.path.join(INPUT_DIR, filename)
            with open(file_path, 'r', encoding='utf-8') as f:
                all_configs.extend(f.read().strip().splitlines())

    if not all_configs:
        print("No configs found to test. Exiting.")
        return

    print(f"Loaded {len(all_configs)} total configs.")
    
    if len(all_configs) > LIVENESS_SAMPLE_SIZE:
        print(f"Taking a random sample of {LIVENESS_SAMPLE_SIZE} configs to test.")
        configs_to_test = random.sample(all_configs, LIVENESS_SAMPLE_SIZE)
    else:
        configs_to_test = all_configs

    valid_targets = []
    for config in configs_to_test:
        host_port_str = extract_ip_from_connection(config)
        if host_port_str and ':' in host_port_str:
            host, port_str = host_port_str.rsplit(':', 1)
            try:
                port = int(port_str)
                valid_targets.append({'config': config, 'host': host, 'port': port})
            except ValueError:
                continue

    all_live_configs = []
    for i in range(0, len(valid_targets), BATCH_SIZE):
        batch = valid_targets[i:i+BATCH_SIZE]
        print(f"--- Processing batch {i//BATCH_SIZE + 1} of {len(valid_targets)//BATCH_SIZE + 1} ---")
        live_in_batch = await process_batch(batch, geoip_reader)
        all_live_configs.extend(live_in_batch)
        
    if all_live_configs:
        print(f"\nFound {len(all_live_configs)} live configurations in total.")
        print("Saving live configs to the database...")
        bulk_update_configs(all_live_configs)
    else:
        print("\nNo new working configurations found.")
        
    geoip_reader.close()
    print("Liveness check process finished successfully.")

if __name__ == "__main__":
    asyncio.run(main())