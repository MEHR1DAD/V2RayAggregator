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
from urllib.parse import urlparse, unquote, parse_qs

from utils import extract_ip_from_connection, resolve_to_ip, get_country_code

# --- Load Configuration ---
with open("config.yml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

# --- Constants ---
GEOIP_DB = "GeoLite2-City.mmdb"
XRAY_PATH = './xray'
REQUEST_TIMEOUT = config['settings']['exp_country']['request_timeout']
SPEED_TEST_URL = config['settings']['exp_country']['speed_test_url']
SPEED_TEST_TIMEOUT = config['settings']['exp_country']['speed_test_timeout']
BATCH_SIZE = config['settings']['exp_country']['batch_size']
TASK_TIMEOUT = 60
START_TIME = time.time()
WORKFLOW_TIMEOUT_SECONDS = 53 * 60

# --- Helper functions (unchanged) ---
def is_approaching_timeout(): return (time.time() - START_TIME) >= WORKFLOW_TIMEOUT_SECONDS
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

# --- FINAL PARSER WITH VERBOSE LOGGING ---
def parse_proxy_uri_to_xray_json(uri: str):
    try:
        if uri.startswith("vless://"):
            parsed = urlparse(uri); params = parse_qs(parsed.query); user_object = {"id": parsed.username, "encryption": "none", "flow": params.get("flow", [""])[0]}; stream_settings = {"network": params.get("type", ["tcp"])[0], "security": params.get("security", ["none"])[0]};
            if stream_settings["security"] == "tls": stream_settings["tlsSettings"] = {"serverName": params.get("sni", [parsed.hostname])[0]}
            if stream_settings["network"] == "ws": stream_settings["wsSettings"] = {"path": params.get("path", ["/"])[0], "headers": {"Host": params.get("host", [parsed.hostname])[0]}}
            return {"protocol": "vless", "settings": {"vnext": [{"address": parsed.hostname, "port": parsed.port, "users": [user_object]}]}, "streamSettings": stream_settings}
        
        elif uri.startswith("vmess://"):
            encoded_part = uri.split("#")[0].replace("vmess://", "").strip(); padding = len(encoded_part) % 4
            if padding: encoded_part += "=" * (4 - padding)
            decoded_json_str = base64.b64decode(encoded_part).decode('utf-8', errors='ignore'); vmess_data = json.loads(decoded_json_str)
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
            if '@' not in uri_no_fragment.split("ss://")[1]:
                encoded_part = uri_no_fragment.replace("ss://", "").strip()
                padding = len(encoded_part) % 4
                if padding: encoded_part += "=" * (4 - padding)
                decoded = base64.urlsafe_b64decode(encoded_part).decode('utf-8', errors='ignore')
                creds, server = decoded.rsplit('@', 1)
                hostname, port_str = server.rsplit(':', 1)
            else:
                parsed = urlparse(uri_no_fragment)
                encoded_user_info = unquote(parsed.username)
                padding = len(encoded_user_info) % 4
                if padding: encoded_user_info += "=" * (4 - padding)
                decoded_user_info = base64.urlsafe_b64decode(encoded_user_info).decode('utf-8', errors='ignore')
                creds = decoded_user_info
                server = f"{parsed.hostname}:{parsed.port}"
            method, password = creds.split(":", 1)
            hostname, port_str = server.rsplit(':', 1)
            return {"protocol": "shadowsocks", "settings": {"servers": [{"address": hostname, "port": int(port_str), "method": method, "password": password}]}}
    
    except Exception as e:
        # THE CRITICAL DEBUG LINE
        print(f"DEBUG: Parser failed for URI {uri[:40]}... Error: {e}")
        return None
    return None

# --- test_proxy_speed and other functions remain unchanged ---
async def test_proxy_speed(proxy_config: str, port: int) -> float:
    config_path = f"temp_config_{port}.json"
    xray_process = None
    outbound_config = parse_proxy_uri_to_xray_json(proxy_config)
    if not outbound_config: return 0.0
    xray_config = {"log": {"loglevel": "warning"}, "inbounds": [{"port": port, "listen": "127.0.0.1", "protocol": "socks", "settings": {"auth": "noauth", "udp": False}}], "outbounds": [outbound_config]}
    try:
        with open(config_path, 'w') as f: json.dump(xray_config, f)
        xray_command = [XRAY_PATH, '-c', config_path]
        xray_process = await asyncio.create_subprocess_exec(*xray_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        await asyncio.sleep(2)
        if xray_process.returncode is not None: return 0.0
        curl_cmd = ['curl', '--socks5-hostname', f'127.0.0.1:{port}', '-w', '%{speed_download}', '-o', '/dev/null', '-s', '--connect-timeout', str(REQUEST_TIMEOUT), '--max-time', str(SPEED_TEST_TIMEOUT), SPEED_TEST_URL]
        proc = await asyncio.create_subprocess_exec(*curl_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0 and stdout:
            try:
                speed_bytes_per_sec = float(stdout.decode('utf-8').strip())
                return speed_bytes_per_sec / 1024
            except (ValueError, TypeError): return 0.0
        else: return 0.0
    except Exception: return 0.0
    finally:
        if xray_process and xray_process.returncode is None:
            try: xray_process.terminate(); await xray_process.wait()
            except ProcessLookupError: pass
        if os.path.exists(config_path): os.remove(config_path)
async def process_batch(batch, reader, start_port):
    tasks = [];
    for i, conn in enumerate(batch):
        task = asyncio.wait_for(test_proxy_speed(conn, start_port + i), timeout=TASK_TIMEOUT);
        tasks.append(task)
    results = await asyncio.gather(*tasks, return_exceptions=True)
    successful_in_batch = []
    now = datetime.utcnow().isoformat()
    for conn, result in zip(batch, results):
        if isinstance(result, float) and result > 1:
            speed_kbps = result
            host = extract_ip_from_connection(conn); ip = resolve_to_ip(host); country_code = get_country_code(ip, reader)
            if country_code:
                successful_in_batch.append((conn, 'speed-tested', country_code, round(speed_kbps, 2), now))
                print(f"✅ Success ({round(speed_kbps)} KB/s) | Country: {country_code} | Config: {conn[:40]}...")
    return successful_in_batch
async def main(input_path, db_path):
    initialize_worker_db(db_path)
    if not os.path.exists(GEOIP_DB): return
    if not os.path.exists(input_path): return
    try:
        reader = geoip2.database.Reader(GEOIP_DB)
    except Exception as e:
        print(f"Error loading GeoIP database: {e}")
        return
    with open(input_path, 'r', encoding='utf-8') as f:
        connections_to_test = f.read().strip().splitlines()
    if not connections_to_test: return
    print(f"--- Worker starting Speed Test on {len(connections_to_test)} candidates ---")
    start_port = 10900
    for i in range(0, len(connections_to_test), BATCH_SIZE):
        if is_approaching_timeout():
            print("⏰ Approaching workflow timeout. Stopping speed tests for this worker.")
            break
        batch = connections_to_test[i:i+BATCH_SIZE]
        print(f"--- Processing speed test batch {i//BATCH_SIZE + 1} ---")
        successful_in_batch = await process_batch(batch, reader, start_port)
        if successful_in_batch:
            bulk_upsert_to_worker_db(db_path, successful_in_batch)
    reader.close()
    print("\nSpeed test worker finished.")
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run speed test on a batch of configs.")
    parser.add_argument('--input', required=True); parser.add_argument('--db-file', required=True);
    args = parser.parse_args(); asyncio.run(main(args.input, args.db_file))
