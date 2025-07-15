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
COUNTRIES = config['countries']
REQUEST_TIMEOUT = config['settings']['request_timeout']
XRAY_PATH = './xray'
SAMPLE_SIZE = 5000
# *** URL for a lightweight liveness check ***
LIVENESS_TEST_URL = "http://www.google.com/generate_204"
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
    """A more robust parser for proxy URIs."""
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
    except Exception as e:
        # لاگ کردن خطای پارس برای دیباگ
        print(f"    - Parser Error for {uri[:30]}...: {e}")
        return None
    return None

async def test_proxy_speed(proxy_config: str, port: int) -> float:
    """Performs a lightweight liveness check using xray and curl."""
    config_path = f"temp_config_{port}.json"
    outbound_config = parse_proxy_uri(proxy_config)

    if not outbound_config:
        return 0.0

    xray_config = {
        "log": {"loglevel": "info"}, # Log level set to info to get more details
        "inbounds": [{"port": port, "listen": "127.0.0.1", "protocol": "socks", "settings": {"auth": "noauth", "udp": False}}],
        "outbounds": [outbound_config]
    }

    with open(config_path, 'w') as f:
