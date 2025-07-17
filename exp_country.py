import os
import json
import tarfile
import random
import asyncio
import subprocess
from datetime import datetime
import geoip2.database
import httpx
import yaml
from urllib.parse import urlparse, parse_qs, unquote
import base64
from utils import extract_ip_from_connection, resolve_to_ip
from database import initialize_db, bulk_update_configs, clear_configs_table

# --- Load Configuration ---
with open("config.yml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

# --- Constants ---
GEOIP_DB = config['paths']['geoip_database']
GEOIP_URL = config['urls']['geoip_download']
MAXMIND_LICENSE_KEY = os.getenv("MAXMIND_LICENSE_KEY")
# --- DELETED LINE: COUNTRIES = config['countries'] ---
REQUEST_TIMEOUT = config['settings']['request_timeout']
XRAY_PATH = './xray'
SAMPLE_SIZE = 5000
LIVENESS_TEST_URL = "http://www.google.com/generate_204"

# --- Define which protocols to test and where to find them ---
PROTOCOLS_TO_TEST = ["vless", "trojan", "ss", "vmess"]
INPUT_DIR = "protocol_configs"

def download_geoip_database():
    if not MAXMIND_LICENSE_KEY: print("Error: MAXMIND_LICENSE_KEY not set."); return False
    try:
        url = GEOIP_URL.format(MAXMIND_LICENSE_KEY)
        print("Downloading fresh GeoIP database from MaxMind...")
        with httpx.stream("GET", url, timeout=60) as response:
            response.raise_for_status()
            with open("GeoLite2-City.tar.gz", "wb") as f:
                for chunk in response.iter_bytes():
                    f.write(chunk)
        with tarfile.open("GeoLite2-City.tar.gz", "r:gz") as tar:
            db_member = next((m for m in tar.getmembers() if m.name.endswith(GEOIP_DB)), None)
            if db_member is None: return False
            db_member.name = os.path.basename(db_member.name); tar.extract(db_member, path=".")
            os.rename(db_member.name, GEOIP_DB)
        os.remove("GeoLite2-City.tar.gz"); print(f"✅ GeoIP database successfully downloaded.")
        return True
    except Exception as e: print(f"An error occurred during GeoIP download: {e}"); return False

def get_country_code(ip, reader):
    try:
        if not ip: return None
        return reader.city(ip).country.iso_code
    except geoip2.errors.AddressNotFoundError:
        return None
    except Exception:
        return None

def parse_proxy_uri(uri: str):
    # ... (parser logic remains the same) ...
    # ... (I have omitted it here for brevity, but it should be in your file) ...
    pass # Placeholder for the full parser function

async def test_proxy_speed(proxy_config: str, port: int) -> float:
    # ... (tester logic remains the same) ...
    pass # Placeholder for the full tester function

async def process_batch(batch, reader, start_port):
    # ... (batch logic remains the same) ...
    pass # Placeholder for the full batch function

async def main():
    initialize_db()
    
    if not os.path.exists(GEOIP_DB):
        if not download_geoip_database(): exit(1)
    
    try:
        reader = geoip2.database.Reader(GEOIP_DB)
    except Exception: exit(1)

    print(f"--- Loading configs from '{INPUT_DIR}' directory ---")
    connections = []
    if not os.path.exists(INPUT_DIR):
        print(f"Input directory '{INPUT_DIR}' not found. Exiting.")
        return

    for protocol in PROTOCOLS_TO_TEST:
        file_path = os.path.join(INPUT_DIR, f"{protocol}_configs.txt")
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                configs = f.read().strip().splitlines()
                connections.extend(configs)
                print(f"Loaded {len(configs)} configs from {file_path}")
    
    if not connections:
        print("No configs found to test. Exiting.")
        return
        
    random.shuffle(connections)
    
    if len(connections) > SAMPLE_SIZE:
        print(f"Original list has {len(connections)} configs. Taking a random sample of {SAMPLE_SIZE}.")
        connections_to_test = random.sample(connections, SAMPLE_SIZE)
    else:
        connections_to_test = connections

    all_successful_configs = []
    
    batch_size = 100
    start_port = 10809
    
    for i in range(0, len(connections_to_test), batch_size):
        batch = connections_to_test[i:i+batch_size]
        print(f"--- Processing batch {i//batch_size + 1} of {len(connections_to_test)//batch_size + 1} ---")
        
        successful_in_batch = await process_batch(batch, reader, start_port)
        all_successful_configs.extend(successful_in_batch)
        
    if all_successful_configs:
        print(f"\nSaving {len(all_successful_configs)} tested configs to database...")
        bulk_update_configs(all_successful_configs)
    else:
        print("\nNo new working configs found to save.")
    
    reader.close()
    print("\nProcess finished successfully.")

if __name__ == "__main__":
    if not os.path.exists('config.yml'):
        print("FATAL: config.yml not found.")
    else:
        asyncio.run(main())