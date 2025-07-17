import requests
import base64
import json
import re
import socket
import geoip2.database

def extract_ip_from_connection(connection: str):
    # This function is used to get host and port
    # For many URI schemes, it returns host:port
    if not connection or not isinstance(connection, str):
        return None

    host_port = None
    try:
        if connection.startswith(("vless://", "trojan://", "ss://")):
            # Format: protocol://user@host:port
            at_split = connection.split('@')
            if len(at_split) > 1:
                host_port = at_split[1].split('?')[0].split('#')[0]
        elif connection.startswith("vmess://"):
            encoded_part = connection.split("vmess://")[1]
            padding = len(encoded_part) % 4
            if padding:
                encoded_part += "=" * (4 - padding)
            decoded_json = base64.b64decode(encoded_part).decode("utf-8")
            data = json.loads(decoded_json)
            host_port = f"{data.get('add')}:{data.get('port')}"

    except Exception:
        return None

    return host_port

def resolve_to_ip(host: str) -> str | None:
    """Resolves a domain name to an IP address."""
    if not host or not isinstance(host, str):
        return None
    if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", host):
        return host
    try:
        return socket.gethostbyname(host)
    except (socket.gaierror, UnicodeError):
        return None

def get_country_code(ip: str, reader: geoip2.database.Reader) -> str | None:
    """Gets the ISO country code from an IP address."""
    try:
        if not ip: return None
        return reader.city(ip).country.iso_code
    except geoip2.errors.AddressNotFoundError:
        return None
    except Exception:
        return None