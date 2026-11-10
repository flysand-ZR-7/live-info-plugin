"""
Unit tests for SSRF protection and URL validation.
"""

import socket
from unittest.mock import patch
import pytest

from app.security import SSRFProtectionError, validate_url


def test_reject_non_http_schemes():
    with pytest.raises(SSRFProtectionError, match="Unsupported URL scheme"):
        validate_url("file:///etc/passwd")

    with pytest.raises(SSRFProtectionError, match="Unsupported URL scheme"):
        validate_url("ftp://ftp.example.com")

    with pytest.raises(SSRFProtectionError, match="Unsupported URL scheme"):
        validate_url("gopher://localhost:70")


def test_reject_localhost():
    with pytest.raises(SSRFProtectionError, match="prohibited"):
        validate_url("http://localhost/admin")

    with pytest.raises(SSRFProtectionError, match="prohibited"):
        validate_url("http://localhost:8080/search")


def test_reject_private_ipv4():
    # 127.0.0.1 Loopback
    with pytest.raises(SSRFProtectionError, match="restricted IP address"):
        validate_url("http://127.0.0.1:8000/metrics")

    # 10.0.0.1 Private
    with pytest.raises(SSRFProtectionError, match="restricted IP address"):
        validate_url("http://10.0.0.1/internal")

    # 192.168.1.1 Private
    with pytest.raises(SSRFProtectionError, match="restricted IP address"):
        validate_url("http://192.168.1.1:8080/")

    # 172.16.0.1 Private
    with pytest.raises(SSRFProtectionError, match="restricted IP address"):
        validate_url("http://172.16.0.1/")


def test_reject_cloud_metadata():
    # AWS / GCP / Azure metadata service IP
    with pytest.raises(SSRFProtectionError, match="restricted IP address"):
        validate_url("http://169.254.169.254/latest/meta-data/")


def test_reject_dns_rebinding_to_private_ip():
    # Mock socket.getaddrinfo to simulate evil.com resolving to a private IP
    fake_addr_info = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.10.10.10", 80))]
    with patch("socket.getaddrinfo", return_value=fake_addr_info):
        with pytest.raises(SSRFProtectionError, match="restricted IP address '10.10.10.10'"):
            validate_url("http://evil-attacker-site.com/steal")


def test_allow_legitimate_public_url():
    # Mock socket.getaddrinfo to resolve to a public IP
    public_addr_info = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
    with patch("socket.getaddrinfo", return_value=public_addr_info):
        valid = validate_url("https://example.com/articles/news")
        assert valid == "https://example.com/articles/news"
