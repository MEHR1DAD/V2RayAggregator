import os
import asyncio
from datetime import datetime
import yaml

# *** FIX: Import the complete testing logic from test_worker ***
from test_worker import test_proxy, BATCH_SIZE 
# Import database functions
from database import initialize_db, get_all_db_configs, bulk_update_configs, bulk_delete_configs
from utils import extract_ip_from_connection, resolve_to_ip, get_country_code
import geoip2.database

# --- Load Configuration ---
with open("config.yml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

# --- Constants ---
GEOIP_DB = "GeoLite2-City.mmdb"

async def main():
    print("--- Starting Database Maintenance Process (Full Protocol Support) ---")
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
    start_port = 11000 # Use a different port range to avoid conflicts

    for i in range(0, len(configs_to_retest), BATCH_SIZE):
        batch = configs_to_retest[i:i+BATCH_SIZE]
        print(f"--- Re-testing batch {i//BATCH_SIZE + 1} of {len(configs_to_retest)//BATCH_SIZE + 1} ---")
        
        # *** FIX: Use the comprehensive test_proxy function ***
        tasks = [test_proxy(conn, start_port + j) for j, conn in enumerate(batch)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        now = datetime.utcnow().isoformat()
        for conn, result in zip(batch, results):
            # Check if the result is a valid speed (float and greater than 1 Kbps)
            if isinstance(result, float) and result > 1:
                speed_kbps = result
                # Config is still alive, prepare its data for update
                host_port_str = extract_ip_from_connection(conn)
                if not host_port_str or ':' not in host_port_str: continue
                
                host, _ = host_port_str.rsplit(':', 1)
                ip = await asyncio.to_thread(resolve_to_ip, host)
                if not ip: continue

                country_code = await asyncio.to_thread(get_country_code, ip, reader)
                
                if country_code:
                    all_retested_configs.append((conn, 're-tested', country_code, round(speed_kbps, 2), now))
            else:
                # Config is dead or returned an error, add it to the deletion list
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
