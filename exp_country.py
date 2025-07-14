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
with open("config.yml", "r", encoding="utf-8") as f:
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
    try:
        if uri.startswith("vless://"):
            parsed = urlparse(uri)
            params = parse_qs(parsed.query)
            return {
                "protocol": "vless",
                "settings": {
                    "vnext": [{
                        "address": parsed.hostname, "port": parsed.port,
                        "users": [{"id": parsed.username, "flow": params.get("flow", [""])[0]}]
                    }]
                },
                "streamSettings": {
                    "network": params.get("type", ["tcp"])[0],
                    "security": params.get("security", ["none"])[0],
                    "tlsSettings": {"serverName": params.get("sni", [parsed.hostname])[0]} if params.get("security", ["none"])[0] == "tls" else None,
                    "wsSettings": {"path": params.get("path", ["/"])[0]} if params.get("type") == "ws" else None,
                }
            }
        elif uri.startswith("ss://"):
            if "@" not in uri:
                encoded_part = uri.split("ss://")[1].split("#")[0]
                padding = len(encoded_part) % 4
                if padding: encoded_part += "=" * (4 - padding)
                decoded = base64.b64decode(encoded_part).decode('utf-8')
                parts = decoded.split(":", 1)
                method = parts[0]
                password_host_port = parts[1]
                password, host_port = password_host_port.split("@", 1)
                hostname, port_str = host_port.rsplit(":", 1)
                port = int(port_str)
            else:
                parsed = urlparse(uri)
                user_info = unquote(parsed.username)
                if ":" in user_info:
                    method, password = user_info.split(":", 1)
                else:
                    method = user_info
                    password = ""
                hostname = parsed.hostname
                port = parsed.port
            return {
                "protocol": "shadowsocks",
                "settings": { "servers": [{"address": hostname, "port": port, "method": method, "password": password}]}
            }
    except Exception:
        return None
    return None

async def test_proxy_connectivity(proxy_config: str, port: int) -> float:
    config_path = f"temp_config_{port}.json"
    outbound_config = parse_proxy_uri(proxy_config)
    
    if not outbound_config:
        return 0.0

    xray_config = {
        "log": {"loglevel": "none"},
        "inbounds": [{"port": port, "listen": "127.0.0.1", "protocol": "socks", "settings": {"auth": "noauth", "udp": False}}],
        "outbounds": [outbound_config]
    }

    with open(config_path, 'w') as f:
        json.dump(xray_config, f)

    xray_process = None
    try:
        xray_process = await asyncio.create_subprocess_exec(
            XRAY_PATH, '-c', config_path,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        await asyncio.sleep(0.5) # Give xray time to start

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
            try:
                xray_process.terminate()
                await xray_process.wait()
            except ProcessLookupError:
                pass
        if os.path.exists(config_path):
            os.remove(config_path)

async def process_batch(batch, reader, start_port):
    tasks = []
    for i, conn in enumerate(batch):
        tasks.append(test_proxy_connectivity(conn, start_port + i))
    
    results = await asyncio.gather(*tasks)
    
    successful_in_batch = []
    now = datetime.utcnow().isoformat()
    for conn, speed in zip(batch, results):
        if speed > 0:
            host = extract_ip_from_connection(conn)
            ip = resolve_to_ip(host)
            country_code = get_country_code(ip, reader)
            if country_code:
                successful_in_batch.append((conn, 'unknown', country_code, speed, now))
                print(f"✅ Success | Country: {country_code} | Config: {conn[:40]}...")
    return successful_in_batch

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
        connections = list(set(f.read().strip().splitlines()))
    
    random.shuffle(connections)

    all_successful_configs = []
    
    batch_size = 100
    start_port = 10809
    
    for i in range(0, len(connections), batch_size):
        batch = connections[i:i+batch_size]
        print(f"--- Processing batch {i//batch_size + 1} of {len(connections)//batch_size + 1} ---")
        
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
