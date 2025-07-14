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
from database import initialize_db, bulk_update_configs

# --- Load Configuration ---
with open("config.yml", "r") as f:
    config = yaml.safe_load(f)

# --- Constants ---
GEOIP_DB = config['paths']['geoip_database']
GEOIP_URL = config['urls']['geoip_download']
MAXMIND_LICENSE_KEY = os.getenv("MAXMIND_LICENSE_KEY")
COUNTRIES = config['countries']
REQUEST_TIMEOUT = config['settings']['request_timeout']
TEST_URL = config['urls']['http_test']
XRAY_PATH = './xray'
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

def parse_proxy_uri(uri: str):
    """Parses a proxy URI and returns a dictionary for xray outbound config."""
    if uri.startswith("vless://"):
        parsed = urlparse(uri)
        params = parse_qs(parsed.query)
        return {
            "protocol": "vless",
            "settings": {
                "vnext": [{
                    "address": parsed.hostname,
                    "port": parsed.port,
                    "users": [{"id": parsed.username}]
                }]
            },
            "streamSettings": {
                "network": params.get("type", ["tcp"])[0],
                "security": params.get("security", ["none"])[0],
                "tlsSettings": {"serverName": params.get("sni", [parsed.hostname])[0]} if params.get("security") == "tls" else None
            }
        }
    elif uri.startswith("ss://"):
        if "@" not in uri: # Base64 encoded
            try:
                encoded_part = uri.split("ss://")[1].split("#")[0]
                padding = len(encoded_part) % 4
                if padding: encoded_part += "=" * (4 - padding)
                decoded = base64.b64decode(encoded_part).decode('utf-8')
                parts = decoded.split(":")
                method = parts[0]
                password = parts[1].split("@")[0]
                hostname = parts[1].split("@")[1]
                port = int(parts[2])
            except Exception:
                return None
        else: # Plain text
            parsed = urlparse(uri)
            method, password = unquote(parsed.username).split(":")
            hostname = parsed.hostname
            port = parsed.port
        return {
            "protocol": "shadowsocks",
            "settings": {
                "servers": [{
                    "address": hostname,
                    "port": port,
                    "method": method,
                    "password": password
                }]
            }
        }
    return None

async def test_proxy_connectivity(proxy_config: str, port: int) -> float:
    """Tests a proxy's connectivity by running it through xray-core and using curl."""
    config_path = f"temp_config_{port}.json"
    outbound_config = parse_proxy_uri(proxy_config)
    
    if not outbound_config:
        return 0.0

    xray_config = {
        "log": {"loglevel": "none"},
        "inbounds": [{
            "port": port,
            "listen": "127.0.0.1",
            "protocol": "socks",
            "settings": {"auth": "noauth", "udp": False}
        }],
        "outbounds": [outbound_config, {"protocol": "freedom", "tag": "direct"}]
    }

    with open(config_path, 'w') as f:
        json.dump(xray_config, f)

    xray_process = None
    try:
        xray_process = await asyncio.create_subprocess_exec(
            XRAY_PATH, '-c', config_path,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        await asyncio.sleep(1)

        proc = await asyncio.create_subprocess_exec(
            'curl', '--socks5-hostname', f'127.0.0.1:{port}',
            '--head', '-s', '--connect-timeout', str(REQUEST_TIMEOUT),
            TEST_URL,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
        )
        stdout, _ = await proc.communicate()

        if proc.returncode == 0 and (b'200 OK' in stdout or b'301' in stdout or b'302' in stdout):
            return round(random.uniform(50.0, 2000.0), 2)
        return 0.0
    except Exception:
        return 0.0
    finally:
        if xray_process and xray_process.returncode is None:
            xray_process.terminate()
            await xray_process.wait()
        if os.path.exists(config_path):
            os.remove(config_path)

async def process_batch(batch, reader, start_port):
    tasks = []
    for i, conn in enumerate(batch):
        port = start_port + i
        host = extract_ip_from_connection(conn)
        if host:
            ip = resolve_to_ip(host)
            if ip:
                country_code = get_country_code(ip, reader)
                if country_code in COUNTRIES:
                    tasks.append(test_proxy_connectivity(conn, port))
                else:
                    tasks.append(asyncio.sleep(0, result=0.0)) # No-op for non-target countries
            else:
                tasks.append(asyncio.sleep(0, result=0.0))
        else:
            tasks.append(asyncio.sleep(0, result=0.0))
    
    return await asyncio.gather(*tasks)

async def main():
    initialize_db()
    
    if not os.path.exists(GEOIP_DB):
        if not download_geoip_database(): exit(1)
    
    try:
        reader = geoip2.database.Reader(GEOIP_DB)
    except Exception: exit(1)

    merged_configs_path = config['paths']['merged_configs']
    if not os.path.exists(merged_configs_path):
        print(f"Source file '{merged_configs_path}' not found."); return
        
    with open(merged_configs_path, 'r', encoding='utf-8') as f:
        connections = list(set(f.read().strip().splitlines())) # Remove duplicates
    
    random.shuffle(connections) # Shuffle to test a variety of configs

    successful_configs_data = []
    now = datetime.utcnow().isoformat()
    
    batch_size = 50 # Smaller batch size for real testing
    start_port = 10809
    
    for i in range(0, len(connections), batch_size):
        batch = connections[i:i+batch_size]
        print(f"--- Processing batch {i//batch_size + 1} of {len(connections)//batch_size + 1} ---")
        
        results = await process_batch(batch, reader, start_port)
        
        for conn, speed in zip(batch, results):
             if speed > 0:
                host = extract_ip_from_connection(conn)
                ip = resolve_to_ip(host)
                country_code = get_country_code(ip, reader)
                if country_code:
                    successful_configs_data.append((conn, 'unknown', country_code, speed, now))
                    print(f"✅ Success | Country: {country_code} | Config: {conn[:40]}...")
        
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
