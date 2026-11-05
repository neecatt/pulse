"""Which network addresses Pulse may connect to on a user's behalf."""

import ipaddress


def is_public_ip(address: str) -> bool:
    """True for addresses on the public internet: not loopback, private, link-local
    (cloud metadata services live there), carrier-grade NAT or otherwise reserved."""
    ip = ipaddress.ip_address(address.split("%", 1)[0])  # drop an IPv6 zone index
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global
