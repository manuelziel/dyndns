#!/usr/bin/env python3
"""CLI validation helpers for domain names and IP addresses.

This module provides common validation utilities used by input prompting
and network validation routines.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

import os
import re

from src.cli.constants import ValidationRegex, ValidationLimits

################################################################################
# VALIDATION UTILITY FUNCTIONS
################################################################################

def is_valid_domain(domain: str) -> bool:
    """Validate domain name format according to RFC 1035.

    Args:
        domain: Domain name string to validate.

    Returns:
        True if domain format is valid, False otherwise.
    """
    return re.match(ValidationRegex.DOMAIN, domain.lower()) is not None


def is_valid_ipv4(ip: str) -> bool:
    """Validate IPv4 address format.

    Args:
        ip: IPv4 address string to validate.

    Returns:
        True if address format is valid, False otherwise.
    """
    if not re.match(ValidationRegex.IPV4, ip):
        return False

    octets = ip.split('.')
    return all(ValidationLimits.IPV4_MIN_OCTET <= int(octet) <= ValidationLimits.IPV4_MAX_OCTET for octet in octets)


def is_valid_ipv6(ip: str) -> bool:
    """Validate IPv6 address format.

    Args:
        ip: IPv6 address string to validate.

    Returns:
        True if address format is valid, False otherwise.
    """
    return re.match(ValidationRegex.IPV6, ip) is not None


def is_valid_path(path_str: str) -> bool:
    """Validate that a string is a valid file or directory path.

    Args:
        path_str: The path string to validate.

    Returns:
        True if the path exists, False otherwise.
    """
    return os.path.exists(path_str)


def resolve_path(path: str) -> str:
    """Resolve tilde (~) and relative segments, returning absolute path.

    Args:
        path: Raw path string to resolve.

    Returns:
        Cleaned absolute canonical path.
    """
    return os.path.abspath(os.path.expanduser(path.strip()))


def is_valid_file_path(path: str, must_exist: bool = False) -> bool:
    """Validate path format and optional existence.

    Args:
        path: Path string to validate.
        must_exist: If True, checks if file exists. If False, checks if
            the parent directory is writable/exists.

    Returns:
        True if path is valid, False otherwise.
    """
    if not path:
        return False

    try:
        resolved = resolve_path(path)

        if must_exist:
            return os.path.isfile(resolved)

        if os.path.exists(resolved):
            return os.path.isfile(resolved) and os.access(resolved, os.W_OK)

        parent_dir = os.path.dirname(resolved)
        return os.path.isdir(parent_dir) and os.access(parent_dir, os.W_OK)
    except (ValueError, OSError):
        return False
