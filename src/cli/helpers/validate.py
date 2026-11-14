#!/usr/bin/env python3
"""CLI validation helpers for domain names, IP literals, and filesystem paths.

Uses ``re.fullmatch`` for RFC 1035 domain syntax and Python's standard
``ipaddress`` module for strict IPv4/IPv6 validation.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

import ipaddress
import os
import re

from ..constants import ValidationRegex

################################################################################
# VALIDATION UTILITY FUNCTIONS
################################################################################


def is_valid_domain(domain: str) -> bool:
    """Validate a domain name according to RFC 1035 label rules.

    Args:
        domain: Candidate domain name string.

    Returns:
        True if ``domain`` matches RFC 1035 syntax, False otherwise.
    """
    if not domain or not domain.strip():
        return False
    return re.fullmatch(ValidationRegex.DOMAIN, domain.strip().lower()) is not None


def is_valid_ipv4(ip: str) -> bool:
    """Validate an IPv4 address string using ``ipaddress.IPv4Address``.

    Args:
        ip: Candidate IPv4 address string.

    Returns:
        True if ``ip`` is a valid canonical IPv4 literal, False otherwise.
    """
    if not ip:
        return False
    try:
        ipaddress.IPv4Address(ip.strip())
        return True
    except ipaddress.AddressValueError:
        return False


def is_valid_ipv6(ip: str) -> bool:
    """Validate an IPv6 address string using ``ipaddress.IPv6Address``.

    Args:
        ip: Candidate IPv6 address string.

    Returns:
        True if ``ip`` is a valid IPv6 literal, False otherwise.
    """
    if not ip:
        return False
    try:
        ipaddress.IPv6Address(ip.strip())
        return True
    except ipaddress.AddressValueError:
        return False


def is_valid_path(path_str: str) -> bool:
    """Return True if ``path_str`` points to an existing filesystem entry.

    Args:
        path_str: Path string to check.

    Returns:
        Boolean existence status.
    """
    return bool(path_str) and os.path.exists(path_str)


def resolve_path(path: str) -> str:
    """Expand ``~`` and relative segments into an absolute path.

    Args:
        path: Raw user-supplied path string.

    Returns:
        Normalized absolute path string.
    """
    return os.path.abspath(os.path.expanduser(path.strip()))


def is_valid_file_path(path: str, must_exist: bool = False) -> bool:
    """Validate file path readability or parent directory writability.

    Args:
        path: Raw path string to check.
        must_exist: Require an existing regular file when True.

    Returns:
        True when ``path`` satisfies the requested file/directory constraints.
    """
    if not path or not path.strip():
        return False
    try:
        resolved = resolve_path(path)
        if os.path.islink(resolved):
            return False
        if must_exist:
            return os.path.isfile(resolved) and os.access(resolved, os.R_OK)
        if os.path.exists(resolved):
            return os.path.isfile(resolved) and os.access(resolved, os.W_OK)
        parent_dir = os.path.dirname(resolved)
        return os.path.isdir(parent_dir) and os.access(parent_dir, os.W_OK)
    except (ValueError, OSError):
        return False
