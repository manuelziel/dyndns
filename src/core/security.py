#!/usr/bin/env python3
"""URI and log secret sanitization utilities for DynDNS.

Provides stateless helpers to redact embedded URI credentials and sensitive
query parameters (including IONOS DynDNS ``?q=`` update tokens and API keys)
before writing URLs or error messages to logs or terminal output.

Typical usage:
    >>> from src.core.security import sanitize_log_uri
    >>> sanitize_log_uri("https://ipv4.api.hosting.ionos.com/dns/v1/dyndns?q=secret")
    'https://ipv4.api.hosting.ionos.com/dns/v1/dyndns?q=**REDACTED**'

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

import re

from .constants import SecurityDefaults

_USERINFO_PATTERN = re.compile(r"([a-zA-Z][a-zA-Z0-9+.-]*://[^/\s:@]+:)([^@\s/]+)(@)")
_SENSITIVE_QUERY_PATTERN = re.compile(
    r"(?i)([?&](?:" + "|".join(SecurityDefaults.SENSITIVE_QUERY_KEYS) + r")=)([^&#\s]*)"
)

################################################################################
# LOG & URI SANITIZATION HELPERS
################################################################################


def sanitize_log_uri(uri: str | None) -> str:
    """Redact URI userinfo secrets and sensitive query parameters from ``uri``.

    Args:
        uri: Raw request URL or log message string.

    Returns:
        Sanitized string with secret values replaced by ``'**REDACTED**'``.
    """
    if not uri:
        return ""
    redacted_userinfo = _USERINFO_PATTERN.sub(
        r"\1" + SecurityDefaults.REDACTED_VALUE + r"\3",
        str(uri),
    )
    return _SENSITIVE_QUERY_PATTERN.sub(
        r"\1" + SecurityDefaults.REDACTED_VALUE,
        redacted_userinfo,
    )
