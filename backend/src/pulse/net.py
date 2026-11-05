"""Which network addresses Pulse may connect to on a user's behalf."""

import ipaddress
from collections.abc import Iterable
from urllib.parse import urlsplit


def is_public_ip(address: str) -> bool:
    """True for addresses on the public internet: not loopback, private, link-local
    (cloud metadata services live there), carrier-grade NAT or otherwise reserved."""
    ip = ipaddress.ip_address(address.split("%", 1)[0])  # drop an IPv6 zone index
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global


def is_push_endpoint(url: str, hosts: Iterable[str]) -> bool:
    """An https URL on one of ``hosts`` or their subdomains, on the default port."""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return False
    host = (parts.hostname or "").rstrip(".").lower()
    if parts.scheme != "https" or port not in (None, 443) or parts.username or parts.password:
        return False
    return any(host == h or host.endswith("." + h) for h in hosts)
