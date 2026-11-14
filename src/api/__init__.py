#!/usr/bin/env python3
"""API package for the DynDNS application.

Provides the session-backed ``HTTPClient`` and ``ProviderDNSClient``.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# PACKAGE IMPORTS
################################################################################

from .http_client import HTTPClient
from .provider import ProviderDNSClient

################################################################################
# PUBLIC API
################################################################################

__all__ = [
    "HTTPClient",
    "ProviderDNSClient",
]
