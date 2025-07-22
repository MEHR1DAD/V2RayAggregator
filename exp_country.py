import os
import argparse
from datetime import datetime

# NOTE: This is a simplified version for the 'master' branch.
# It does NOT perform speed tests. It only takes live candidates
# and upserts them into the database.
from database import initialize_db, bulk_update_configs
from utils import extract_ip_from_connection, resolve_to_ip, get_country_code
import geoip2.database

GEOIP_DB = "GeoLite2-City.mmdb"

def process_and_save_live_configs(input_path):
    """
    Reads live candidates, enriches them with country data,
    and upserts them to the main database.
    """
    if not os.path.exists(input_path):
        print(f"Candidates file '{input_path}' not found. No configs to process.")
        return

    with open(input_path, 'r', encoding='utf-8') as f:
        live_configs = f.read().strip().splitlines()

    if not live_configs:
        print("No live candidates to process.")
        return
        
    print(f"Processing {len(live_configs)} live candidates...")

    try:
        reader = geoip2.database.Reader(GEOIP_DB)
    except Exception as e:
        print(f"Error loading GeoIP database: {e}")
        return

    enriched_configs = []
    now = datetime.utcnow().isoformat()

    for config in live_configs:
        host = extract_ip_from_connection(config)
        ip = resolve_to_ip(host)
        country_code = get_country_code(ip, reader)
        
        if country_code:
            # Data format: (config, source_url, country_code, speed_kbps, last_tested)
            # We use a placeholder speed of 1.0 for "live"
            enriched_configs.append((config, 'live-tested', country_code, 1.0, now))

    if enriched_configs:
        print(f"Upserting {len(enriched_configs)} enriched configs into the database...")
        bulk_update_configs(enriched_configs)
    
    reader.close()
    print("Finished processing live configs.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Enrich live configs and save to DB.")
    parser.add_argument('--input', required=True, help="Path to the input file containing live candidates.")
    
    args = parser.parse_args()
    
    initialize_db()
    process_and_save_live_configs(args.input)
