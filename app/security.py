"""
Security module providing SSRF (Server-Side Request Forgery) protection and URL validation.
Guarantees that the website reader and research tools only fetch legitimate public web pages.
"""

import ipaddress
import logging
import socket
from urllib.parse import urlparse
from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

# List of blocked IP networks (IPv4 and IPv6)
BLOCKED_NETWORKS = [
    # IPv4 Private & Loopback & Link-Local & Reserved
    ipaddress.ip_network("0.0.0.0/8"),          # Current network (local host)
    ipaddress.ip_network("10.0.0.0/8"),         # RFC 1918 Private
    ipaddress.ip_network("100.64.0.0/10"),      # Carrier-grade NAT
    ipaddress.ip_network("127.0.0.0/8"),        # Loopback
    ipaddress.ip_network("169.254.0.0/16"),     # Link-local / Cloud Metadata (AWS/GCP/Azure)
    ipaddress.ip_network("172.16.0.0/12"),      # RFC 1918 Private (172.16.0.0 - 172.31.255.255)
    ipaddress.ip_network("192.0.0.0/24"),       # IETF Protocol Assignments
    ipaddress.ip_network("192.0.2.0/24"),       # Documentation (TEST-NET-1)
    ipaddress.ip_network("192.168.0.0/16"),     # RFC 1918 Private
    ipaddress.ip_network("198.18.0.0/15"),      # Benchmark testing
    ipaddress.ip_network("198.51.100.0/24"),    # Documentation (TEST-NET-2)
    ipaddress.ip_network("203.0.113.0/24"),     # Documentation (TEST-NET-3)
    ipaddress.ip_network("224.0.0.0/4"),        # Multicast
    ipaddress.ip_network("240.0.0.0/4"),        # Reserved for future use
    ipaddress.ip_network("255.255.255.255/32"), # Broadcast

    # IPv6 Loopback, Link-Local, Unique Local, Multicast
    ipaddress.ip_network("::1/128"),            # Loopback
    ipaddress.ip_network("::/128"),             # Unspecified
    ipaddress.ip_network("::ffff:0:0/96"),      # IPv4-mapped IPv6
    ipaddress.ip_network("100::/64"),           # Discard prefix
    ipaddress.ip_network("2001:db8::/32"),      # Documentation
    ipaddress.ip_network("fc00::/7"),           # Unique Local Address (ULA)
    ipaddress.ip_network("fe80::/10"),          # Link-local unicast
    ipaddress.ip_network("ff00::/8"),           # Multicast
]


class SSRFProtectionError(HTTPException):
    """Exception raised when a URL targets a disallowed or private IP network."""

    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Security violation (SSRF protection): {detail}",
        )


def is_ip_disallowed(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """
    Checks if an IP address belongs to any private, loopback, link-local,
    multicast, or reserved range.
    """
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        return True

    # If it is an IPv4-mapped IPv6 address (e.g., ::ffff:192.168.1.1), check the inner IPv4
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        return is_ip_disallowed(ip.ipv4_mapped)

    # Check against explicit blocked networks list
    for network in BLOCKED_NETWORKS:
        if ip in network:
            return True

    return False


def validate_url(url: str) -> str:
    """
    Validates a URL for safe HTTP client fetching:
    1. Ensures scheme is strictly 'http' or 'https'.
    2. Ensures hostname exists.
    3. Resolves DNS and blocks any private/loopback/cloud-metadata IP.
    Returns the normalized URL string or raises SSRFProtectionError.
    """
    if not url or not isinstance(url, str):
        raise SSRFProtectionError("URL must be a non-empty string.")

    url = url.strip()
    try:
        parsed = urlparse(url)
    except Exception as exc:
        raise SSRFProtectionError(f"Malformed URL: {exc}")

    # 1. Scheme check
    if parsed.scheme.lower() not in ("http", "https"):
        raise SSRFProtectionError(
            f"Unsupported URL scheme '{parsed.scheme}'. Only http and https are permitted."
        )

    # 2. Hostname check
    hostname = parsed.hostname
    if not hostname:
        raise SSRFProtectionError("URL missing valid hostname.")

    hostname_clean = hostname.strip().lower()

    # Block obvious local hostname aliases immediately
    blocked_hostnames = {
        "localhost",
        "localhost.localdomain",
        "ip6-localhost",
        "ip6-loopback",
        "metadata.google.internal",
        "instance-data",
    }
    if hostname_clean in blocked_hostnames or hostname_clean.endswith(".localhost"):
        raise SSRFProtectionError(f"Access to local hostname '{hostname_clean}' is prohibited.")

    # 3. DNS resolution and IP verification
    port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)

    try:
        # Resolve all addresses (IPv4 & IPv6) for the hostname
        addr_info = socket.getaddrinfo(
            hostname_clean,
            port,
            proto=socket.IPPROTO_TCP,
        )
    except socket.gaierror as exc:
        raise SSRFProtectionError(
            f"Failed to resolve DNS for host '{hostname_clean}': {exc}"
        )
    except Exception as exc:
        raise SSRFProtectionError(f"DNS lookup error for host '{hostname_clean}': {exc}")

    if not addr_info:
        raise SSRFProtectionError(f"No IP addresses resolved for host '{hostname_clean}'.")

    # Check every resolved IP address
    for info in addr_info:
        sockaddr = info[4]
        ip_str = sockaddr[0]

        try:
            ip_obj = ipaddress.ip_address(ip_str)
        except ValueError:
            raise SSRFProtectionError(f"Invalid resolved IP address: '{ip_str}'")

        if is_ip_disallowed(ip_obj):
            logger.warning(
                "SSRF block: Host '%s' resolved to disallowed IP '%s'",
                hostname_clean,
                ip_str,
            )
            raise SSRFProtectionError(
                f"Host '{hostname_clean}' resolves to restricted IP address '{ip_str}'. Fetching is blocked."
            )

    return url
