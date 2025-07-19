import os
import json
import asyncio
import subprocess
from datetime import datetime
import geoip2.database
import yaml
import re
import time # Import time module

from utils import extract_ip_from_connection, resolve_to_ip, get_country_code
from database import initialize_db, bulk_update_configs

# --- Load Configuration ---
with open("config.yml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

# --- Constants ---
GEOIP_DB = "GeoLite2-City.mmdb"
CANDIDATES_INPUT_FILE = "candidates.txt"
XRAY_PATH = './xray'
REQUEST_TIMEOUT = config['settings']['exp_country']['request_timeout']
SPEED_TEST_URL = config['settings']['exp_country']['speed_test_url']
SPEED_TEST_TIMEOUT = config['settings']['exp_country']['speed_test_timeout']
BATCH_SIZE = config['settings']['exp_country']['batch_size']
START_TIME = time.time()
WORKFLOW_TIMEOUT_SECONDS = 53 * 60

def is_approaching_timeout():
    """Checks if the script is approaching the GitHub Actions timeout."""
    return (time.time() - START_TIME) >= WORKFLOW_TIMEOUT_SECONDS

# --- The parse_proxy_uri_to_xray_json function remains unchanged ---
def parse_proxy_uri_to_xray_json(uri: str):
    """
    Parses a proxy URI and converts it into a valid Xray outbound configuration JSON object.
    Returns None if the protocol is unsupported or parsing fails.
    """
    try:
        if uri.startswith("vless://"):
            match = re.match(r'vless://([^@]+)@([^:?#]+):(\d+)(?:\?([^#]*))?(?:#.*)?', uri)
            if not match: return None
            uuid, address, port, query = match.groups()
            params = dict(p.split('=') for p in query.split('&')) if query else {}
            
            return {
                "protocol": "vless",
                "settings": {"vnext": [{"address": address, "port": int(port), "users": [{"id": uuid, "flow": params.get("flow", "xtls-rprx-vision")}]}]},
                "streamSettings": {
                    "network": params.get("type", "tcp"),
                    "security": params.get("security", "none"),
                    "tlsSettings": {"serverName": params.get("sni", address)} if params.get("security") == "tls" else None,
                    "wsSettings": {"path": params.get("path", "/")} if params.get("type") == "ws" else None,
                }
            }
        elif uri.startswith("trojan://"):
            match = re.match(r'trojan://([^@]+)@([^:?#]+):(\d+)(?:\?([^#]*))?(?:#.*)?', uri)
            if not match: return None
            password, address, port, query = match.groups()
            params = dict(p.split('=') for p in query.split('&')) if query else {}

            return {
                "protocol": "trojan",
                "settings": {"servers": [{"address": address, "port": int(port), "password": password}]},
                "streamSettings": {
                    "network": params.get("type", "tcp"),
                    "security": params.get("security", "tls"),
                    "tlsSettings": {"serverName": params.get("sni", address)},
                }
            }
        # Add other parsers (VMess, SS) here when ready
    except Exception:
        return None
    return None

# --- The test_proxy_speed function remains unchanged ---
async def test_proxy_speed(proxy_config: str, port: int) -> float:
    config_path = f"temp_config_{port}.json"
    xray_process = None
    
    outbound_config = parse_proxy_uri_to_xray_json(proxy_config)
    if not outbound_config:
        return 0.0

    xray_config = {
        "log": {"loglevel": "warning"},
        "inbounds": [{"port": port, "listen": "127.0.0.1", "protocol": "socks", "settings": {"auth": "noauth", "udp": False}}],
        "outbounds": [outbound_config]
    }

    try:
        with open(config_path, 'w') as f:
            json.dump(xray_config, f)

        xray_process = await asyncio.create_subprocess_exec(
            XRAY_PATH, '-c', config_path,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        await asyncio.sleep(2)

        curl_cmd = [
            'curl', '--socks5-hostname', f'127.0.0.1:{port}',
            '-w', '%{speed_download}', '-o', '/dev/null', '-s',
            '--connect-timeout', str(REQUEST_TIMEOUT),
            '--max-time', str(SPEED_TEST_TIMEOUT),
            SPEED_TEST_URL
        ]
        
        proc = await asyncio.create_subprocess_exec(*curl_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = await proc.communicate()

        if proc.returncode == 0 and stdout:
            try:
                speed_bytes_per_sec = float(stdout.decode('utf-8'))
                return speed_bytes_per_sec / 1024 # Convert to KB/s
            except (ValueError, TypeError):
                return 0.0
        else:
            return 0.0
            
    except Exception as e:
        return 0.0
    finally:
        if xray_process and xray_process.returncode is None:
            try:
                xray_process.terminate()
                await xray_process.wait()
            except ProcessLookupError:
                pass
        if os.path.exists(config_path):
            os.remove(config_path)

# --- The process_batch function remains unchanged ---
async def process_batch(batch, reader, start_port):
    tasks = []
    for i, conn in enumerate(batch):
        tasks.append(test_proxy_speed(conn, start_port + i))
    
    results = await asyncio.gather(*tasks)
    
    successful_in_batch = []
    now = datetime.utcnow().isoformat()
    for conn, speed_kbps in zip(batch, results):
        if speed_kbps > 1:
            host = extract_ip_from_connection(conn)
            ip = resolve_to_ip(host)
            country_code = get_country_code(ip, reader)
            if country_code:
                successful_in_batch.append((conn, 'speed-tested', country_code, round(speed_kbps, 2), now))
                print(f"✅ Success ({round(speed_kbps)} KB/s) | Country: {country_code} | Config: {conn[:40]}...")
    return successful_in_batch

async def main():
    initialize_db()
    
    if not os.path.exists(GEOIP_DB):
        print(f"GeoIP database not found. Cannot proceed.")
        return
    if not os.path.exists(CANDIDATES_INPUT_FILE):
        print(f"Candidates file '{CANDIDATES_INPUT_FILE}' not found. No configs to test.")
        return

    try:
        reader = geoip2.database.Reader(GEOIP_DB)
    except Exception as e:
        print(f"Error loading GeoIP database: {e}")
        return

    with open(CANDIDATES_INPUT_FILE, 'r', encoding='utf-8') as f:
        connections_to_test = f.read().strip().splitlines()
    
    if not connections_to_test:
        print("No configs in candidates file. Exiting.")
        return
        
    print(f"--- Starting Speed Test on {len(connections_to_test)} candidate configs ---")

    all_successful_configs = []
    start_port = 10900
    
    for i in range(0, len(connections_to_test), BATCH_SIZE):
        # The new graceful exit check
        if is_approaching_timeout():
            print("⏰ Approaching workflow timeout. Stopping speed tests to save results.")
            break

        batch = connections_to_test[i:i+BATCH_SIZE]
        print(f"--- Processing speed test batch {i//BATCH_SIZE + 1} ---")
        
        successful_in_batch = await process_batch(batch, reader, start_port)
        if successful_in_batch:
            all_successful_configs.extend(successful_in_batch)
            
    if all_successful_configs:
        print(f"\nUpserting {len(all_successful_configs)} successfully tested configs into the database...")
        bulk_update_configs(all_successful_configs)
    else:
        print("\nNo new working configs were found or tested in this run.")
    
    reader.close()
    print("\nSpeed test process finished.")

if __name__ == "__main__":
    asyncio.run(main())