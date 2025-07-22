import os
import argparse
from datetime import datetime
import time

from database import initialize_db, bulk_update_configs
from utils import extract_ip_from_connection, resolve_to_ip, get_country_code
import geoip2.database

GEOIP_DB = "GeoLite2-City.mmdb"
START_TIME = time.time()
WORKFLOW_TIMEOUT_SECONDS = 170 * 60

def is_approaching_timeout():
    # This function is kept for safety
    return (time.time() - START_TIME) >= WORKFLOW_TIMEOUT_SECONDS

def process_and_save_live_configs(input_path):
    """
    Reads live candidates, enriches them with country data,
    and upserts them to the main database. Includes verbose logging.
    """
    if not os.path.exists(input_path):
        print(f"DEBUG: Candidates file '{input_path}' not found. Exiting.")
        return

    with open(input_path, 'r', encoding='utf-8') as f:
        live_configs = f.read().strip().splitlines()

    if not live_configs:
        print("DEBUG: No live candidates to process.")
        return
        
    print(f"Processing {len(live_configs)} live candidates...")

    try:
        reader = geoip2.database.Reader(GEOIP_DB)
        print("DEBUG: GeoIP database loaded successfully.")
    except Exception as e:
        print(f"DEBUG: FATAL - Error loading GeoIP database: {e}")
        return

    enriched_configs = []
    now = datetime.utcnow().isoformat()
    
    # We will only log the first 10 attempts to avoid spamming the log
    log_counter = 0

    for config in live_configs:
        host = extract_ip_from_connection(config)
        ip = resolve_to_ip(host)
        country_code = get_country_code(ip, reader)

        if country_code:
            enriched_configs.append((config, 'live-tested', country_code, 1.0, now))
        elif log_counter < 10:
            # Log why a config was rejected
            print("--------------------")
            print(f"DEBUG: Failed to enrich config: {config[:70]}...")
            print(f"  -> Host extracted: {host}")
            print(f"  -> IP resolved: {ip}")
            print(f"  -> Country code found: {country_code}")
            print("--------------------")
            log_counter += 1

    if enriched_configs:
        print(f"Upserting {len(enriched_configs)} enriched configs into the database...")
        bulk_update_configs(enriched_configs)
    else:
        print("DEBUG: The enriched_configs list is empty. No data will be saved to the database.")
    
    reader.close()
    print("Finished processing live configs.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Enrich live configs and save to DB.")
    parser.add_argument('--input', required=True, help="Path to the input file containing live candidates.")
    
    args = parser.parse_args()
    
    initialize_db()
    process_and_save_live_configs(args.input)
