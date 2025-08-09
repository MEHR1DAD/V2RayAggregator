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
# ... (بخش ثابت‌ها بدون تغییر) ...
GLOBAL_TIMEOUT_MINUTES = config['settings'].get('global_timeout_minutes', 170)
WORKFLOW_TIMEOUT_SECONDS = GLOBAL_TIMEOUT_MINUTES * 60
GEOIP_DB = "GeoLite2-City.mmdb"
XRAY_PATH = './xray'
HYSTERIA_PATH = './hysteria'
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
    # آپدیت ساختار جدول برای پشتیبانی از پینگ
    cursor.execute('''CREATE TABLE IF NOT EXISTS configs (
                        config TEXT PRIMARY KEY, 
                        source_url TEXT, 
                        country_code TEXT, 
                        speed_kbps REAL, 
                        ping_ms INTEGER, 
                        last_tested TEXT
                    )''')
    conn.commit()
    conn.close()

def bulk_upsert_to_worker_db(db_path, configs_data):
    if not configs_data: return
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    # آپدیت دستور برای پشتیبانی از پینگ
    cursor.executemany('''INSERT INTO configs (config, source_url, country_code, speed_kbps, ping_ms, last_tested) 
                          VALUES (?, ?, ?, ?, ?, ?) 
                          ON CONFLICT(config) DO UPDATE SET 
                            speed_kbps = excluded.speed_kbps, 
                            ping_ms = excluded.ping_ms,
                            last_tested = excluded.last_tested''', configs_data)
    conn.commit()
    conn.close()

# --- Parser functions ---
# ... (توابع پارسر بدون تغییر) ...
def parse_hysteria2_uri_to_json(uri: str):
    try:
        parsed = urlparse(uri)
        params = parse_qs(parsed.query)
        hysteria_config = {
            "server": f"{parsed.hostname}:{parsed.port}",
            "auth": parsed.username or "",
            "tls": { "sni": params.get("sni", [parsed.hostname])[0], "insecure": "insecure" in params and params["insecure"][0] == "1" },
            "socks5": { "listen": "" }
        }
        return hysteria_config
    except Exception: return None

def parse_proxy_uri_to_xray_json(uri: str):
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
    except Exception: return None
    return None

# --- توابع تست جدید ---
async def run_ping_test_with_curl(port: int):
    """پینگ (latency) را با استفاده از time_connect در curl اندازه‌گیری می‌کند."""
    curl_cmd = ['curl', '--socks5-hostname', f'127.0.0.1:{port}', '-w', '%{time_connect}', '-o', '/dev/null', '-s', '--connect-timeout', str(REQUEST_TIMEOUT), 'https://speed.cloudflare.com/']
    proc = await asyncio.create_subprocess_exec(*curl_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, _ = await proc.communicate()
    if proc.returncode == 0 and stdout:
        try:
            connect_time_sec = float(stdout.decode('utf-8').strip())
            return int(connect_time_sec * 1000) # تبدیل به میلی‌ثانیه
        except (ValueError, TypeError):
            return 9999 # مقدار بالا برای خطای پینگ
    return 9999

async def run_speed_test_with_curl(port: int):
    # ... (این تابع بدون تغییر) ...
    speed_test_url = random.choice(SPEED_TEST_URLS)
    curl_cmd = ['curl', '--socks5-hostname', f'127.0.0.1:{port}', '-w', '%{speed_download}', '-o', '/dev/null', '-s', '--connect-timeout', str(REQUEST_TIMEOUT), '--max-time', str(SPEED_TEST_TIMEOUT), speed_test_url]
    proc = await asyncio.create_subprocess_exec(*curl_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, _ = await proc.communicate()
    if proc.returncode == 0 and stdout:
        try:
            speed_bytes_per_sec = float(stdout.decode('utf-8').strip())
            return (speed_bytes_per_sec * 8) / 1024
        except (ValueError, TypeError): return 0.0
    return 0.0

# --- توابع تست اصلی اصلاح‌شده ---
async def test_xray_speed(proxy_config: str, port: int):
    # ... (منطق این تابع اصلاح می‌شود تا هم پینگ و هم سرعت را برگرداند) ...
    config_path = f"temp_xray_config_{port}.json"
    process = None
    outbound_config = parse_proxy_uri_to_xray_json(proxy_config)
    if not outbound_config: return None

    xray_config = {"log": {"loglevel": "warning"}, "inbounds": [{"port": port, "listen": "127.0.0.1", "protocol": "socks", "settings": {"auth": "noauth", "udp": False}}], "outbounds": [outbound_config]}
    
    try:
        with open(config_path, 'w') as f: json.dump(xray_config, f)
        command = [XRAY_PATH, '-c', config_path]
        process = await asyncio.create_subprocess_exec(*command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        await asyncio.sleep(2)
        
        if process.returncode is not None: return None
        
        # اجرای هر دو تست
        ping_task = run_ping_test_with_curl(port)
        speed_task = run_speed_test_with_curl(port)
        ping_ms, speed_kbps = await asyncio.gather(ping_task, speed_task)

        if speed_kbps > 1: # فقط در صورت موفقیت تست سرعت، نتیجه را معتبر بدان
            return {"speed": speed_kbps, "ping": ping_ms}
        return None
    except Exception:
        return None
    finally:
        if process and process.returncode is None:
            try: process.terminate(); await process.wait()
            except ProcessLookupError: pass
        if os.path.exists(config_path): os.remove(config_path)

async def test_hysteria2_speed(proxy_config: str, port: int):
    # ... (این تابع هم برای برگرداندن پینگ و سرعت اصلاح می‌شود) ...
    config_path = f"temp_hysteria_config_{port}.json"
    process = None
    hysteria_config = parse_hysteria2_uri_to_json(proxy_config)
    if not hysteria_config: return None

    hysteria_config["socks5"]["listen"] = f"127.0.0.1:{port}"
    
    try:
        with open(config_path, 'w') as f: json.dump(hysteria_config, f)
        command = [HYSTERIA_PATH, "client", "-c", config_path]
        process = await asyncio.create_subprocess_exec(*command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        await asyncio.sleep(3)
        
        if process.returncode is not None: return None

        ping_task = run_ping_test_with_curl(port)
        speed_task = run_speed_test_with_curl(port)
        ping_ms, speed_kbps = await asyncio.gather(ping_task, speed_task)

        if speed_kbps > 1:
            return {"speed": speed_kbps, "ping": ping_ms}
        return None
    except Exception:
        return None
    finally:
        if process and process.returncode is None:
            try: process.terminate(); await process.wait()
            except ProcessLookupError: pass
        if os.path.exists(config_path): os.remove(config_path)

# --- Dispatcher and Batch Processing ---
async def test_proxy(proxy_config: str, port: int):
    protocol = proxy_config.split("://")[0]
    if protocol in ["vless", "vmess", "trojan", "ss"]:
        return await test_xray_speed(proxy_config, port)
    elif protocol == "hysteria2":
        return await test_hysteria2_speed(proxy_config, port)
    else:
        return None

async def process_batch(batch, reader, start_port):
    tasks = [asyncio.wait_for(test_proxy(conn, start_port + i), timeout=TASK_TIMEOUT) for i, conn in enumerate(batch)]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    successful_in_batch = []
    now = datetime.utcnow().isoformat()
    
    for conn, result in zip(batch, results):
        # حالا نتیجه یک دیکشنری است
        if isinstance(result, dict) and result.get("speed") > 1:
            speed_kbps = result["speed"]
            ping_ms = result["ping"]
            
            host_port_str = extract_ip_from_connection(conn)
            if not host_port_str or ':' not in host_port_str: continue
            
            host, _ = host_port_str.rsplit(':', 1)
            ip = await asyncio.to_thread(resolve_to_ip, host)
            if not ip: continue

            country_code = await asyncio.to_thread(get_country_code, ip, reader)
            
            if country_code:
                # اضافه کردن پینگ به داده‌های ارسالی به دیتابیس
                successful_in_batch.append((conn, 'speed-tested', country_code, round(speed_kbps, 2), ping_ms, now))
                print(f"✅ Success (Speed: {round(speed_kbps)} Kbps, Ping: {ping_ms}ms) | Country: {country_code} | Config: {conn[:40]}...")
            
    return successful_in_batch

# ... (تابع main بدون تغییر) ...
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

    print(f"--- Worker starting Speed & Ping Test on {len(connections_to_test)} candidates ---")
    start_port = 10900
    
    for i in range(0, len(connections_to_test), BATCH_SIZE):
        if is_approaching_timeout():
            print("⏰ Approaching workflow timeout. Stopping tests for this worker."); break
        
        batch = connections_to_test[i:i + BATCH_SIZE]
        print(f"--- Processing test batch {i//BATCH_SIZE + 1} ---")
        
        successful_in_batch = await process_batch(batch, reader, start_port)
        if successful_in_batch:
            bulk_upsert_to_worker_db(db_path, successful_in_batch)
    
    reader.close()
    print("\nTest worker finished.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run speed and ping test on a batch of configs.")
    parser.add_argument('--input', required=True)
    parser.add_argument('--db-file', required=True)
    args = parser.parse_args()
    asyncio.run(main(args.input, args.db_file))
