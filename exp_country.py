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
REQUEST_TIMEOUT = config['settings']['request_timeout']
XRAY_PATH = './xray'
SAMPLE_SIZE = 5000
LIVENESS_TEST_URL = "http://www.google.com/generate_204"

PROTOCOLS_TO_TEST = ["vless", "trojan", "ss", "vmess"]
INPUT_DIR = "protocol_configs"

# (The download_geoip_database and get_country_code functions remain unchanged)
def download_geoip_database():
    # ...
    pass

def get_country_code(ip, reader):
    # ...
    pass

def parse_proxy_uri(uri: str):
    # (This function is correct and remains unchanged)
    pass

async def test_proxy_speed(proxy_config: str, port: int) -> float:
    """Performs a lightweight liveness check using xray and curl."""
    config_path = f"temp_config_{port}.json"
    xray_process = None
    
    try:
        outbound_config = parse_proxy_uri(proxy_config)
        if not outbound_config:
            return 0.0

        xray_config = {
            "log": {"loglevel": "warning"},
            "inbounds": [{"port": port, "listen": "127.0.0.1", "protocol": "socks", "settings": {"auth": "noauth", "udp": False}}],
            "outbounds": [outbound_config]
        }

        # FIX: Move file writing inside the try block
        with open(config_path, 'w') as f:
            json.dump(xray_config, f)

        xray_process = await asyncio.create_subprocess_exec(
            XRAY_PATH, '-c', config_path,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        await asyncio.sleep(1.5)

        proc = await asyncio.create_subprocess_exec(
            'curl', '--socks5-hostname', f'127.0.0.1:{port}',
            '--connect-timeout', str(REQUEST_TIMEOUT),
            '--head', '-s', LIVENESS_TEST_URL,
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
        )
        _, curl_stderr = await proc.communicate()

        if proc.returncode == 0:
            return 1.0
        else:
            return 0.0
            
    except Exception:
        # Any exception in this block will result in a failure
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

# (The process_batch and main functions remain unchanged)
async def process_batch(batch, reader, start_port):
    # ...
    pass

async def main():
    # ...
    pass

if __name__ == "__main__":
    if not os.path.exists('config.yml'):
        print("FATAL: config.yml not found.")
    else:
        asyncio.run(main())