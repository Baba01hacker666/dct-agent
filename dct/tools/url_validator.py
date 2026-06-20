"""
URL validation for safe web fetching.
Blocks internal/private IPs, cloud metadata endpoints, and non-HTTP schemes.
"""

from __future__ import annotations
import ipaddress
import socket
import urllib.parse

# Blocks subnets stolen from real SSRF filters used by GitLab,
# server-side-request-forgery prevention guides and OWASP
_BLOCKED_SUBNETS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # includes AWS/cloud metadata
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),  # CGNAT RFC 6598
    ipaddress.ip_network("192.0.2.0/24"),  # TEST-NET-1
    ipaddress.ip_network("198.18.0.0/15"),  # benchmarking
    ipaddress.ip_network("198.51.100.0/24"),  # TEST-NET-2
    ipaddress.ip_network("203.0.113.0/24"),  # TEST-NET-3
    ipaddress.ip_network("224.0.0.0/4"),  # multicast
    ipaddress.ip_network("240.0.0.0/4"),  # reserved
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("::/128"),
    ipaddress.ip_network("ff00::/8"),
]


def validate_url(url: str) -> str | None:
    """
    Validate a URL is safe to fetch.
    Returns the normalized URL on success, or an error string on failure.
    """
    if not url.startswith(("http://", "https://")):
        return "Only http:// and https:// URLs are allowed."

    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        return f"Invalid URL: {url!r}"

    hostname = parsed.hostname
    if not hostname:
        return f"No hostname in URL: {url!r}"

    # Resolve hostname to IP addresses
    try:
        addrs = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC)
    except socket.gaierror as e:
        return f"DNS resolution failed for {hostname}: {e}"

    for family, _, _, _, sockaddr in addrs:
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue

        for net in _BLOCKED_SUBNETS:
            if ip in net:
                return (
                    f"Blocked URL {url!r}: resolves to internal/private IP "
                    f"{ip_str} (in {net})."
                )

    return None  # no error
