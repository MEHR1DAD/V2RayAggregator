import os
import asyncio
import socket
from datetime import datetime
from utils import extract_ip_from_connection, resolve_to_ip
from database import initialize_db, bulk_update_configs, get_country_code, clear_configs_table
import geoip2.database

# --- Constants ---
INPUT_DIR = "protocol_configs"
# A short timeout for a simple socket connection
CONNECTION_TIMEOUT = 5 
# We need the GeoIP database to determine the country
GEOIP_DB_PATH = "GeoLite2-City.mmdb" 

async def check_port_open(host, port):
    """
    Asynchronously checks if a TCP port is open on a given host.
    Returns True if open, False otherwise.
    """
    try:
        # Create a socket and try to connect with a timeout
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), 
            timeout=CONNECTION_TIMEOUT
        )
        writer.close()
        await writer.wait_closed()
        return True
    except (socket.gaierror, asyncio.TimeoutError, ConnectionRefusedError, OSError):
        # Any connection error means the port is likely closed or unreachable
        return False

async def process_config_file(file_path, geoip_reader):
    """
    Reads a single config file, performs liveness checks, 
    and returns a list of live configs.
    """
    live_configs = []
    now = datetime.utcnow().isoformat()

    with open(file_path, 'r', encoding='utf-8') as f:
        configs = f.read().strip().splitlines()

    for config in configs:
        # We need a more robust way to get host and port, but for now this works for many cases
        host_and_port = extract_ip_from_connection(config) 
        if not host_and_port or ':' not in host_and_port:
            continue
        
        host, port_str = host_and_port.rsplit(':', 1)
        try:
            port = int(port_str)
        except ValueError:
            continue
            
        is_live = await check_port_open(host, port)
        if is_live:
            ip = resolve_to_ip(host)
            country = get_country_code(ip, geoip_reader)
            if country:
                # Save with a symbolic speed of 1.0 to mark as live
                live_configs.append((config, 'unknown', country, 1.0, now))
                print(f"✅ Live | {country} | {config[:50]}...")
    
    return live_configs

async def main():
    """Main function to run the liveness check process."""
    initialize_db()
    # Clear previous results before starting a new cycle
    clear_configs_table() 
    
    if not os.path.exists(GEOIP_DB_PATH):
        print(f"GeoIP database not found at {GEOIP_DB_PATH}. Cannot proceed.")
        return
        
    geoip_reader = geoip2.database.Reader(GEOIP_DB_PATH)
    all_live_configs = []
    
    if not os.path.exists(INPUT_DIR):
        print(f"Input directory '{INPUT_DIR}' not found. Exiting.")
        return
        
    # Create a list of tasks for each config file
    tasks = []
    for filename in os.listdir(INPUT_DIR):
        if filename.endswith("_configs.txt"):
            file_path = os.path.join(INPUT_DIR, filename)
            tasks.append(process_config_file(file_path, geoip_reader))
            
    # Run all file processing concurrently
    results = await asyncio.gather(*tasks)
    
    for result_list in results:
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