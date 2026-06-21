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

# Standard Imports
import re

# Local Imports
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
