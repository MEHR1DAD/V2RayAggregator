import os
import asyncio
import subprocess
from datetime import datetime
from utils import extract_ip_from_connection, resolve_to_ip, get_country_code
from database import initialize_db, bulk_update_configs, clear_configs_table
import geoip2.database
import yaml

# --- Load Configuration ---
with open("config.yml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)
    
# --- Constants ---
INPUT_DIR = "protocol_configs"
CONNECTION_TIMEOUT = config['settings']['request_timeout']
GEOIP_DB_PATH = "GeoLite2-City.mmdb"

async def check_port_open_curl(host, port):
    """
    Asynchronously checks if a TCP port is open using curl.
    This is more robust in restricted network environments like GitHub Actions.
    """
    command = [
        'curl',
        '--connect-timeout', str(CONNECTION_TIMEOUT),
        '-v',  # Verbose to get connection details
        f'telnet://{host}:{port}'
    ]
    
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    await process.wait()
    return process.returncode == 0

async def process_config_file(file_path, geoip_reader):
    """Reads a single config file, performs liveness checks, and returns a list of live configs."""
    live_configs = []
    now = datetime.utcnow().isoformat()

    with open(file_path, 'r', encoding='utf-8') as f:
        configs = f.read().strip().splitlines()

    valid_targets = []
    for config in configs:
        host_port_str = extract_ip_from_connection(config)
        if host_port_str and ':' in host_port_str:
            host, port_str = host_port_str.rsplit(':', 1)
            try:
                port = int(port_str)
                valid_targets.append({'config': config, 'host': host, 'port': port})
            except ValueError:
                continue
    
    if not valid_targets:
        return []

    tasks = [check_port_open_curl(target['host'], target['port']) for target in valid_targets]
    results = await asyncio.gather(*tasks)

    for target, is_live in zip(valid_targets, results):
        if is_live:
            ip = resolve_to_ip(target['host'])
            country = get_country_code(ip, geoip_reader)
            if country:
                live_configs.append((target['config'], 'unknown', country, 1.0, now))
                print(f"✅ Live | {country} | {target['config'][:50]}...")
    
    return live_configs

async def main():
    """Main function to run the liveness check process."""
    initialize_db()
    clear_configs_table()
    
    if not os.path.exists(GEOIP_DB_PATH):
        print(f"GeoIP database not found at {GEOIP_DB_PATH}. Cannot proceed.")
        return
        
    geoip_reader = geoip2.database.Reader(GEOIP_DB_PATH)
    all_live_configs = []
    
    if not os.path.exists(INPUT_DIR):
        print(f"Input directory '{INPUT_DIR}' not found. Exiting.")
        return
        
    file_paths = [os.path.join(INPUT_DIR, f) for f in os.listdir(INPUT_DIR) if f.endswith("_configs.txt")]
    
    tasks = [process_config_file(file_path, geoip_reader) for file_path in file_paths]
    
    list_of_results = await asyncio.gather(*tasks)
    
    for result_list in list_of_results:
        all_live_configs.extend(result_list)
        
    if all_live_configs:
        print(f"\nFound {len(all_live_configs)} live configurations in total.")
        print("Saving live configs to the database...")
        bulk_update_configs(all_live_configs)
    else:
        print("\nNo live configurations found.")
        
    geoip_reader.close()
    print("Liveness check process finished successfully.")

if __name__ == "__main__":
    asyncio.run(main())