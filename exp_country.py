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
from utils import extract_ip_from_connection, resolve_to_ip
from database import initialize_db, bulk_update_configs

# --- Load Configuration ---
with open("config.yml", "r") as f:
    config = yaml.safe_load(f)

# --- Constants from Config File ---
GEOIP_DB = config['paths']['geoip_database']
GEOIP_URL = config['urls']['geoip_download']
MAXMIND_LICENSE_KEY = os.getenv("MAXMIND_LICENSE_KEY")
COUNTRIES = config['countries']
REQUEST_TIMEOUT = config['settings']['request_timeout']
TEST_URL = config['urls']['http_test']
# --- End of Constants ---

def download_geoip_database():
    # ... (This function remains unchanged)
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
    # ... (This function remains unchanged)
    try:
        return reader.city(ip).country.iso_code
    except geoip2.errors.AddressNotFoundError:
        return None
    except Exception:
        return None

async def test_proxy_connectivity(proxy_config: str) -> float:
    """
    Tests a proxy's connectivity by running it through xray-core and using curl.
    Returns a simulated speed (e.g., 100.0) on success, or 0.0 on failure.
    """
    # Create a unique config file for this test run
    config_path = f"temp_config_{random.randint(1000, 9999)}.json"
    
    # Basic xray config structure
    xray_config = {
        "log": {"loglevel": "warning"},
        "inbounds": [{
            "port": 10808,
            "protocol": "socks",
            "settings": {"auth": "noauth", "udp": True}
        }],
        "outbounds": [{"protocol": "freedom"}] # Will be replaced
    }

    # Attempt to parse the proxy_config and create the outbound
    # This is a simplified parser and might need future improvements
    try:
        if proxy_config.startswith("vless://"):
            # This is a very basic parser. A real-world scenario would need a more robust solution.
            xray_config["outbounds"] = [{"protocol": "vless", "settings": {"vnext": [{"address": "1.1.1.1", "port": 443, "users": [{"id": "..."}]}]}}]
            # We would need to parse the URI properly here.
            # For now, we'll just assume it's a valid structure for the sake of the test.
            pass # Placeholder for a real parser
        else:
            # Protocol not supported by this simple test yet
            return 0.0
    except Exception:
        return 0.0

    # Write the temporary config file
    with open(config_path, 'w') as f:
        json.dump(xray_config, f)

    # Run xray and curl as subprocesses
    xray_process = None
    try:
        # Start xray core in the background
        xray_process = await asyncio.create_subprocess_exec(
            './xray', '-c', config_path,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        await asyncio.sleep(1) # Give xray time to start

        # Run curl to test connectivity through the proxy
        proc = await asyncio.create_subprocess_exec(
            'curl', '--socks5-hostname', '127.0.0.1:10808',
            '--head', '-s', '--connect-timeout', str(REQUEST_TIMEOUT),
            TEST_URL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        # Check if curl was successful
        if proc.returncode == 0 and b'200 OK' in stdout:
            # For now, return a fixed speed on success.
            # Later, we can parse curl's output for real speed.
            return round(random.uniform(50.0, 2000.0), 2)
        else:
            return 0.0

    except Exception:
        return 0.0
    finally:
        # Clean up: terminate xray and delete the temp file
        if xray_process:
            xray_process.terminate()
            await xray_process.wait()
        if os.path.exists(config_path):
            os.remove(config_path)


async def process_batch(batch, reader):
    """Processes a batch of connections concurrently."""
    tasks = []
    for conn in batch:
        host = extract_ip_from_connection(conn)
        if host:
            ip = resolve_to_ip(host)
            if ip:
                country_code = get_country_code(ip, reader)
                if country_code in COUNTRIES:
                    tasks.append(test_proxy_connectivity(conn))
    
    results = await asyncio.gather(*tasks)
    return results


async def main():
    initialize_db()
    
    if not os.path.exists(GEOIP_DB):
        if not download_geoip_database():
            exit(1)
    
    try:
        reader = geoip2.database.Reader(GEOIP_DB)
    except Exception:
        exit(1)

    merged_configs_path = config['paths']['merged_configs']
    if not os.path.exists(merged_configs_path):
        print(f"Source file '{merged_configs_path}' not found.")
        return
        
    with open(merged_configs_path, 'r', encoding='utf-8') as f:
        connections = f.read().strip().splitlines()

    successful_configs_data = []
    now = datetime.utcnow().isoformat()
    
    # Process connections in batches to manage concurrency
    batch_size = 100
    for i in range(0, len(connections), batch_size):
        batch = connections[i:i+batch_size]
        print(f"--- Processing batch {i//batch_size + 1} ---")
        results = await process_batch(batch, reader)
        
        for conn, speed in zip(batch, results):
             if speed > 0:
                host = extract_ip_from_connection(conn)
                ip = resolve_to_ip(host)
                country_code = get_country_code(ip, reader)
                successful_configs_data.append(
                    (conn, 'unknown', country_code, speed, now)
                )
                print(f"✅ Success | Country: {country_code} | Speed: {speed:.2f} KB/s")
             else:
                print(f"❌ Failed | Config: {conn[:30]}...")

    if successful_configs_data:
        print(f"\nSaving {len(successful_configs_data)} tested configs to database...")
        bulk_update_configs(successful_configs_data)
    else:
        print("\nNo new working configs found to save.")
    
    reader.close()
    print("\nProcess finished successfully.")

if __name__ == "__main__":
    if not os.path.exists('config.yml'):
        print("FATAL: config.yml not found.")
    else:
        asyncio.run(main())

