import os
import json
import asyncio
import subprocess
from datetime import datetime
import geoip2.database
import yaml
import re
import time
import argparse
import sqlite3
import base64
import random
from urllib.parse import urlparse, unquote, parse_qs

from utils import extract_ip_from_connection, resolve_to_ip, get_country_code

# --- Load Configuration ---
with open("config.yml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

# --- Constants ---
GLOBAL_TIMEOUT_MINUTES = config['settings'].get('global_timeout_minutes', 170)
WORKFLOW_TIMEOUT_SECONDS = GLOBAL_TIMEOUT_MINUTES * 60
GEOIP_DB = "GeoLite2-City.mmdb"
XRAY_PATH = './xray'
HYSTERIA_PATH = './hysteria' # path to hysteria client
REQUEST_TIMEOUT = config['settings']['exp_country']['request_timeout']
SPEED_TEST_URLS = config['settings']['exp_country']['speed_test_urls']
SPEED_TEST_TIMEOUT = config['settings']['exp_country']['speed_test_timeout']
BATCH_SIZE = config['settings']['exp_country']['batch_size']
TASK_TIMEOUT = 60
START_TIME = time.time()


# --- Helper functions ---
def is_approaching_timeout():
    return (time.time() - START_TIME) >= WORKFLOW_TIMEOUT_SECONDS

def initialize_worker_db(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS configs (config TEXT PRIMARY KEY, source_url TEXT, country_code TEXT, speed_kbps REAL, last_tested TEXT)''')
    conn.commit()
    conn.close()

def bulk_upsert_to_worker_db(db_path, configs_data):
    if not configs_data: return
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.executemany('''INSERT INTO configs (config, source_url, country_code, speed_kbps, last_tested) VALUES (?, ?, ?, ?, ?) ON CONFLICT(config) DO UPDATE SET speed_kbps = excluded.speed_kbps, last_tested = excluded.last_tested''', configs_data)
    conn.commit()
    conn.close()

# --- Parser functions ---
def parse_hysteria2_uri_to_json(uri: str):
    try:
        parsed = urlparse(uri)
        params = parse_qs(parsed.query)
        
        hysteria_config = {
            "server": f"{parsed.hostname}:{parsed.port}",
            "auth": parsed.username or "",
            "tls": {
                "sni": params.get("sni", [parsed.hostname])[0],
                "insecure": "insecure" in params and params["insecure"][0] == "1"
            },
            "socks5": { 
                "listen": "" # Will be filled in later
            }
        }
        return hysteria_config
    except Exception as e:
        print(f"[HY2-DEBUG] Failed to parse URI: {uri[:50]}... Error: {e}")
        return None

def parse_proxy_uri_to_xray_json(uri: str):
    # This function remains unchanged for xray protocols
    try:
        if uri.startswith("vless://"):
            parsed = urlparse(uri); params = parse_qs(parsed.query); user_object = {"id": parsed.username, "encryption": "none", "flow": params.get("flow", [""])[0]}; stream_settings = {"network": params.get("type", ["tcp"])[0], "security": params.get("security", ["none"])[0]};
            if stream_settings["security"] == "tls": stream_settings["tlsSettings"] = {"serverName": params.get("sni", [parsed.hostname])[0]}
            if stream_settings["network"] == "ws": stream_settings["wsSettings"] = {"path": params.get("path", ["/"])[0], "headers": {"Host": params.get("host", [parsed.hostname])[0]}}
            return {"protocol": "vless", "settings": {"vnext": [{"address": parsed.hostname, "port": parsed.port, "users": [user_object]}]}, "streamSettings": stream_settings}
        elif uri.startswith("vmess://"):
            encoded_part = uri.replace("vmess://", "").strip(); padding = len(encoded_part) % 4;
            if padding: encoded_part += "=" * (4 - padding)
            decoded_json_str = base64.b64decode(encoded_part).decode('utf-8'); vmess_data = json.loads(decoded_json_str)
            if not all(k in vmess_data for k in ['add', 'port', 'id']): return None
            user_object = {"id": vmess_data.get("id"), "alterId": int(vmess_data.get("aid", 0)), "security": vmess_data.get("scy", "auto")}; stream_settings = {"network": vmess_data.get("net", "tcp"),"security": vmess_data.get("tls", "none")}
            if stream_settings["security"] == "tls": stream_settings["tlsSettings"] = {"serverName": vmess_data.get("sni", vmess_data.get("host", vmess_data.get("add")))}
            if stream_settings["network"] == "ws": stream_settings["wsSettings"] = {"path": vmess_data.get("path", "/"), "headers": {"Host": vmess_data.get("host", vmess_data.get("add"))}}
            return {"protocol": "vmess", "settings": {"vnext": [{"address": vmess_data.get("add"), "port": int(vmess_data.get("port")), "users": [user_object]}]}, "streamSettings": stream_settings}
        elif uri.startswith("trojan://"):
            parsed = urlparse(uri); params = parse_qs(parsed.query)
            if not parsed.username: return None
            return {"protocol": "trojan", "settings": {"servers": [{"address": parsed.hostname, "port": parsed.port, "password": parsed.username}]}, "streamSettings": {"network": "tcp", "security": "tls", "tlsSettings": {"serverName": params.get("sni", [parsed.hostname])[0]}}}
        elif uri.startswith("ss://"):
            uri_no_fragment = uri.split("#")[0]
            if '@' in uri_no_fragment:
                parsed = urlparse(uri_no_fragment); encoded_user_info = unquote(parsed.username); padding = len(encoded_user_info) % 4
                if padding: encoded_user_info += "=" * (4 - padding)
                decoded_user_info = base64.urlsafe_b64decode(encoded_user_info).decode('utf-8', errors='ignore'); creds = decoded_user_info; server = f"{parsed.hostname}:{parsed.port}"
            else:
                encoded_part = uri_no_fragment.replace("ss://", "").strip(); padding = len(encoded_part) % 4
                if padding: encoded_part += "=" * (4 - padding)
                decoded = base64.urlsafe_b64decode(encoded_part).decode('utf-8', errors='ignore')
                if '@' not in decoded: return None
                creds, server = decoded.rsplit('@', 1)
            if ":" not in creds or ":" not in server: return None
            method, password = creds.split(":", 1); hostname, port_str = server.rsplit(':', 1)
            return {"protocol": "shadowsocks", "settings": {"servers": [{"address": hostname, "port": int(port_str), "method": method, "password": password}]}}
    except Exception:
        return None
    return None

# --- Speed Test Functions ---
async def run_speed_test_with_curl(port: int):
    speed_test_url = random.choice(SPEED_TEST_URLS)
    curl_cmd = ['curl', '--socks5-hostname', f'127.0.0.1:{port}', '-w', '%{speed_download}', '-o', '/dev/null', '-s', '--connect-timeout', str(REQUEST_TIMEOUT), '--max-time', str(SPEED_TEST_TIMEOUT), speed_test_url]
    proc = await asyncio.create_subprocess_exec(*curl_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, stderr = await proc.communicate()
    
    if proc.returncode == 0 and stdout:
        try:
            speed_bytes_per_sec = float(stdout.decode('utf-8').strip())
            return (speed_bytes_per_sec * 8) / 1024  # Convert to Kbps
        except (ValueError, TypeError):
            return 0.0
    # Print curl errors if any
    if stderr:
        print(f"[CURL-DEBUG] Curl failed for port {port}. Error: {stderr.decode('utf-8', errors='ignore').strip()}")
    return 0.0

async def test_xray_speed(proxy_config: str, port: int):
    config_path = f"temp_xray_config_{port}.json"
    process = None
    outbound_config = parse_proxy_uri_to_xray_json(proxy_config)
    if not outbound_config:
        return 0.0

    xray_config = {"log": {"loglevel": "warning"}, "inbounds": [{"port": port, "listen": "127.0.0.1", "protocol": "socks", "settings": {"auth": "noauth", "udp": False}}], "outbounds": [outbound_config]}
    
    try:
        with open(config_path, 'w') as f: json.dump(xray_config, f)
        
        command = [XRAY_PATH, '-c', config_path]
        process = await asyncio.create_subprocess_exec(*command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        await asyncio.sleep(2)
        
        if process.returncode is not None: return 0.0
        return await run_speed_test_with_curl(port)
    except Exception:
        return 0.0
    finally:
        if process and process.returncode is None:
            try: process.terminate(); await process.wait()
            except ProcessLookupError: pass
        if os.path.exists(config_path): os.remove(config_path)

async def test_hysteria2_speed(proxy_config: str, port: int):
    print(f"[HY2-DEBUG] Starting test for {proxy_config[:50]}...")
    config_path = f"temp_hysteria_config_{port}.json"
    process = None
    hysteria_config = parse_hysteria2_uri_to_json(proxy_config)
    if not hysteria_config:
        return 0.0

    hysteria_config["socks5"]["listen"] = f"127.0.0.1:{port}"
    
    try:
        with open(config_path, 'w') as f: json.dump(hysteria_config, f)
        
        command = [HYSTERIA_PATH, "client", "-c", config_path]
        print(f"[HY2-DEBUG] Executing command: {' '.join(command)}")
        
        process = await asyncio.create_subprocess_exec(
            *command, 
            stdout=asyncio.subprocess.PIPE, 
            stderr=asyncio.subprocess.PIPE
        )
        await asyncio.sleep(3) # Increased sleep time for hysteria2
        
        if process.returncode is not None:
            stdout, stderr = await process.communicate()
            print(f"[HY2-DEBUG] Hysteria client failed to start for port {port}.")
            if stderr:
                print(f"[HY2-ERROR] {stderr.decode('utf-8', errors='ignore').strip()}")
            return 0.0

        return await run_speed_test_with_curl(port)
    except Exception as e:
        print(f"[HY2-DEBUG] Exception during test for port {port}: {e}")
        return 0.0
    finally:
        if process and process.returncode is None:
            try: 
                process.terminate()
                stdout, stderr = await process.communicate()
                if stderr:
                    print(f"[HY2-SHUTDOWN-ERROR] {stderr.decode('utf-8', errors='ignore').strip()}")
            except ProcessLookupError: pass
        if os.path.exists(config_path): os.remove(config_path)

# --- Dispatcher and Batch Processing ---
async def test_proxy(proxy_config: str, port: int):
    """Dispatcher function to select the correct speed test."""
    protocol = proxy_config.split("://")[0]
    if protocol in ["vless", "vmess", "trojan", "ss"]:
        return await test_xray_speed(proxy_config, port)
    elif protocol == "hysteria2":
        return await test_hysteria2_speed(proxy_config, port)
    else:
        return 0.0

async def process_batch(batch, reader, start_port):
    tasks = []
    for i, conn in enumerate(batch):
        task = asyncio.wait_for(test_proxy(conn, start_port + i), timeout=TASK_TIMEOUT)
        tasks.append(task)
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    successful_in_batch = []
    now = datetime.utcnow().isoformat()
    
    for conn, result in zip(batch, results):
        if isinstance(result, float) and result > 1: # Speed in Kbps
            host_port_str = extract_ip_from_connection(conn)
            if not host_port_str or ':' not in host_port_str: continue
            
            host, _ = host_port_str.rsplit(':', 1)
            ip = await asyncio.to_thread(resolve_to_ip, host)
            if not ip: continue

            country_code = await asyncio.to_thread(get_country_code, ip, reader)
            
            if country_code:
                successful_in_batch.append((conn, 'speed-tested', country_code, round(result, 2), now))
                print(f"✅ Success ({round(result)} Kbps) | Country: {country_code} | Config: {conn[:40]}...")
            
    return successful_in_batch

async def main(input_path, db_path):
    initialize_worker_db(db_path)
    if not os.path.exists(GEOIP_DB) or not os.path.exists(input_path): return

    try:
        reader = geoip2.database.Reader(GEOIP_DB)
    except Exception as e:
        print(f"Error loading GeoIP database: {e}"); return

    with open(input_path, 'r', encoding='utf-8') as f:
        connections_to_test = f.read().strip().splitlines()
    
    if not connections_to_test:
        reader.close(); return

    print(f"--- Worker starting Speed Test on {len(connections_to_test)} candidates ---")
    start_port = 10900
    
    for i in range(0, len(connections_to_test), BATCH_SIZE):
        if is_approaching_timeout():
            print("⏰ Approaching workflow timeout. Stopping speed tests for this worker."); break
        
        batch = connections_to_test[i:i + BATCH_SIZE]
        print(f"--- Processing speed test batch {i//BATCH_SIZE + 1} ---")
        
        successful_in_batch = await process_batch(batch, reader, start_port)
        if successful_in_batch:
            bulk_upsert_to_worker_db(db_path, successful_in_batch)
    
    reader.close()
    print("\nSpeed test worker finished.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run speed test on a batch of configs.")
    parser.add_argument('--input', required=True)
    parser.add_argument('--db-file', required=True)
    args = parser.parse_args()
    asyncio.run(main(args.input, args.db_file))
