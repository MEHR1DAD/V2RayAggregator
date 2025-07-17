import os
import asyncio
import subprocess
from datetime import datetime
import random
import time
from utils import extract_ip_from_connection, resolve_to_ip, get_country_code
from database import initialize_db, bulk_update_configs, clear_configs_table
import geoip2.database
import yaml

# --- Load Configuration ---
with open("config.yml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)
    
# --- Constants ---
INPUT_DIR = "protocol_configs"
CONNECTION_TIMEOUT = 5 
GEOIP_DB_PATH = "GeoLite2-City.mmdb"
BATCH_SIZE = 500
# Set timeout to 14 minutes
TOTAL_TIMEOUT_SECONDS = 14 * 60 
START_TIME = time.time()

def is_timeout():
    """Checks if the global script timeout has been reached."""
    if (time.time() - START_TIME) > TOTAL_TIMEOUT_SECONDS:
        print("⏰ Global timeout reached. Finalizing...")
        return True
    return False

async def check_port_open_curl(host, port):
    # ... (This function is unchanged)
    pass

async def process_batch(batch_of_targets, geoip_reader):
    # ... (This function is unchanged)
    pass

async def main():
    """Main function to run the liveness check process."""
    initialize_db()
    clear_configs_table()
    
    if not os.path.exists(GEOIP_DB_PATH):
        print(f"GeoIP database not found at {GEOIP_DB_PATH}. Cannot proceed.")
        return
        
    geoip_reader = geoip2.database.Reader(GEOIP_DB_PATH)
    all_live_configs = []
    
    try:
        if not os.path.exists(INPUT_DIR):
            print(f"Input directory '{INPUT_DIR}' not found. Exiting.")
            return
        
        # --- NEW LOGIC: Process files one by one ---
        for filename in sorted(os.listdir(INPUT_DIR)):
            if is_timeout():
                break # Check timeout before starting a new file

            if not filename.endswith("_configs.txt"):
                continue

            file_path = os.path.join(INPUT_DIR, filename)
            print(f"\n--- Processing file: {filename} ---")
            
            with open(file_path, 'r', encoding='utf-8') as f:
                configs_to_test = f.read().strip().splitlines()
            
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

            for i in range(0, len(valid_targets), BATCH_SIZE):
                if is_timeout():
                    break # Check timeout between batches

                batch = valid_targets[i:i+BATCH_SIZE]
                print(f"  - Processing batch {i//BATCH_SIZE + 1} of {len(valid_targets)//BATCH_SIZE + 1}...")
                
                remaining_time = TOTAL_TIMEOUT_SECONDS - (time.time() - START_TIME)
                if remaining_time <= 0:
                    break
                
                try:
                    live_in_batch = await asyncio.wait_for(
                        process_batch(batch, geoip_reader),
                        timeout=remaining_time
                    )
                    all_live_configs.extend(live_in_batch)
                except asyncio.TimeoutError:
                    print("  - Batch timed out. Moving to next file...")
                    break
            
    finally:
        if all_live_configs:
            print(f"\nFound {len(all_live_configs)} live configurations in total.")
            print("Saving live configs to the database before exiting...")
            bulk_update_configs(all_live_configs)
        else:
            print("\nNo live configurations found.")
            
        geoip_reader.close()
        print("Liveness check process finished.")

if __name__ == "__main__":
    asyncio.run(main())