#!/usr/bin/env python3
"""Custom exception classes for IONOS DynDNS.

Provides a structured exception hierarchy for consistent error handling
across the application. All custom exceptions inherit from DynDNSException.

Exception Hierarchy:
    DynDNSException (Base)
    ├── DatabaseError: Database operations (sqlite3 errors)
    ├── ConfigError: Configuration issues (TOML parsing, missing keys)
    ├── EncryptionError: Encryption/Decryption failures
    ├── NetworkError: Network connectivity issues (IP detection)
    ├── APIError: Provider API communication
    │   ├── RecordNotFoundError: DNS record not found (404)
    │   └── ZoneNotFoundError: DNS zone not found (404)
    └── ValidationError: Input validation failures

Typical usage:
    >>> from src.core.exceptions import ConfigError, DatabaseError
    >>> try:
    ...     config = load_config('missing.toml')
    ... except ConfigError as e:
    ...     logger.error(f'Config error: {e}')

Author: Manuel Ziel
License: MIT
"""

################################################################################
# BASE EXCEPTION
################################################################################

class DynDNSException(Exception):
    """Base exception for all IONOS DynDNS errors."""
    pass

################################################################################
# CONFIGURATION & DATA ERRORS
################################################################################

class DatabaseError(DynDNSException):
    """Database operation failed (SQLite errors, connection issues)."""
    pass


class ConfigError(DynDNSException):
    """Configuration error (TOML parsing, missing keys, invalid values)."""
    pass


class EncryptionError(DynDNSException):
    """Encryption/Decryption operation failed."""
    pass

################################################################################
# NETWORK & API ERRORS
################################################################################

class NetworkError(DynDNSException):
    """Network operation failed (IP detection, connectivity issues)."""
    pass


class APIError(DynDNSException):
    """Provider API communication error."""
    pass


class RecordNotFoundError(APIError):
    """DNS record not found on provider (404)."""
    pass


class ZoneNotFoundError(APIError):
    """DNS zone not found on provider (404)."""
    pass

################################################################################
# VALIDATION ERRORS
################################################################################

class ValidationError(DynDNSException):
    """Input validation failed (invalid domain, IP, zone ID)."""
    pass
