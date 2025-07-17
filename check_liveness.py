import os
import asyncio
import socket
from datetime import datetime
from utils import extract_ip_from_connection, resolve_to_ip, get_country_code
from database import initialize_db, bulk_update_configs, clear_configs_table
import geoip2.database

# --- Constants ---
INPUT_DIR = "protocol_configs"
CONNECTION_TIMEOUT = 5
GEOIP_DB_PATH = "GeoLite2-City.mmdb" 

async def check_port_open(host, port):
    """Asynchronously checks if a TCP port is open."""
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), 
            timeout=CONNECTION_TIMEOUT
        )
        writer.close()
        await writer.wait_closed()
        return True
    except Exception:
        return False

async def process_config_file(file_path, geoip_reader):
    """Reads a single config file and performs liveness checks."""
    live_configs = []
    now = datetime.utcnow().isoformat()

    with open(file_path, 'r', encoding='utf-8') as f:
        configs = f.read().strip().splitlines()

    tasks = []
    for config in configs:
        host_port_str = extract_ip_from_connection(config)
        if not host_port_str or ':' not in host_port_str:
            continue
        
        host, port_str = host_port_str.rsplit(':', 1)
        try:
            port = int(port_str)
            tasks.append(check_port_open(host, port))
        except ValueError:
            continue

    results = await asyncio.gather(*tasks)

    for config, is_live in zip(configs, results):
        if is_live:
            host, _ = extract_ip_from_connection(config).rsplit(':', 1)
            ip = resolve_to_ip(host)
            country = get_country_code(ip, geoip_reader)
            if country:
                live_configs.append((config, 'unknown', country, 1.0, now))
                print(f"✅ Live | {country} | {config[:50]}...")
    
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
    
    for file_path in file_paths:
        live_in_file = await process_config_file(file_path, geoip_reader)
        all_live_configs.extend(live_in_file)
        
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