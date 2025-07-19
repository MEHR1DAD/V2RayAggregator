import os
import asyncio
from datetime import datetime
import yaml

# Import testing logic from exp_country (we can refactor this later to a shared module)
from exp_country import test_proxy_speed, BATCH_SIZE
# Import database functions
from database import initialize_db, get_all_db_configs, bulk_update_configs, bulk_delete_configs, get_country_code
from utils import extract_ip_from_connection, resolve_to_ip
import geoip2.database

# --- Load Configuration ---
with open("config.yml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

# --- Constants ---
GEOIP_DB = "GeoLite2-City.mmdb"

async def main():
    print("--- Starting Database Maintenance Process ---")
    initialize_db()

    # 1. Get all configs that are currently in our final list
    configs_to_retest = get_all_db_configs()

    if not configs_to_retest:
        print("No configs in the database to maintain. Exiting.")
        return
    
    print(f"Found {len(configs_to_retest)} configs in the database to re-test.")

    if not os.path.exists(GEOIP_DB):
        print(f"GeoIP database not found at {GEOIP_DB}. Cannot proceed.")
        return
        
    try:
        reader = geoip2.database.Reader(GEOIP_DB)
    except Exception as e:
        print(f"Error loading GeoIP database: {e}")
        return

    # 2. Re-test all of them for speed
    all_retested_configs = []
    dead_configs = []
    start_port = 11000 # Use a different port range

    for i in range(0, len(configs_to_retest), BATCH_SIZE):
        batch = configs_to_retest[i:i+BATCH_SIZE]
        print(f"--- Re-testing batch {i//BATCH_SIZE + 1} of {len(configs_to_retest)//BATCH_SIZE + 1} ---")
        
        tasks = [test_proxy_speed(conn, start_port + j) for j, conn in enumerate(batch)]
        results = await asyncio.gather(*tasks)

        now = datetime.utcnow().isoformat()
        for conn, speed_kbps in zip(batch, results):
            if speed_kbps > 1:
                # Config is still alive, prepare its data for update
                host = extract_ip_from_connection(conn)
                ip = resolve_to_ip(host)
                country_code = get_country_code(ip, reader)
                if country_code:
                    all_retested_configs.append((conn, 're-tested', country_code, round(speed_kbps, 2), now))
            else:
                # Config is dead, add it to the deletion list
                print(f"❌ Dead | Config marked for deletion: {conn[:60]}...")
                dead_configs.append(conn)

    # 3. Update the still-living configs and delete the dead ones
    if all_retested_configs:
        print(f"\nUpdating {len(all_retested_configs)} still-live configs...")
        bulk_update_configs(all_retested_configs)
    
    if dead_configs:
        print(f"\nDeleting {len(dead_configs)} dead configs...")
        bulk_delete_configs(dead_configs)
        
    reader.close()
    print("\n--- Database Maintenance Process Finished ---")

if __name__ == "__main__":
    asyncio.run(main())