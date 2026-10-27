#!/usr/bin/env python3
"""Custom exception classes for DynDNS.

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
# IMPORTS & DEPENDENCIES
################################################################################

from .constants import ExceptionMessages

################################################################################
# EXCEPTION HIERARCHY
################################################################################

class DynDNSException(Exception):
    """Base exception for all DynDNS errors.

    All custom exceptions inherit from this class to enable catching
    all application-specific errors with a single except clause.
    """

    def __init__(self, message: str = ExceptionMessages.DEFAULT) -> None:
        """Initialize base exception with default or custom message.

        Args:
            message: Error description.
        """
        super().__init__(message)


class DatabaseError(DynDNSException):
    """Raised when a database operation fails.

    Covers SQLite errors, connection issues, and query failures.
    """

    def __init__(self, message: str = ExceptionMessages.DATABASE) -> None:
        """Initialize database exception with default or custom message.

        Args:
            message: Error description.
        """
        super().__init__(message)


class ConfigError(DynDNSException):
    """Raised when configuration loading or parsing fails.

    Covers TOML parsing errors, missing required keys, and invalid values.
    """

    def __init__(self, message: str = ExceptionMessages.CONFIG) -> None:
        """Initialize configuration exception with default or custom message.

        Args:
            message: Error description.
        """
        super().__init__(message)


class EncryptionError(DynDNSException):
    """Raised when encryption or decryption operation fails."""

    def __init__(self, message: str = ExceptionMessages.ENCRYPTION) -> None:
        """Initialize encryption exception with default or custom message.

        Args:
            message: Error description.
        """
        super().__init__(message)


class NetworkError(DynDNSException):
    """Raised when a network operation fails.

    Covers IP detection issues, connectivity problems, and timeouts.
    """

    def __init__(self, message: str = ExceptionMessages.NETWORK) -> None:
        """Initialize network exception with default or custom message.

        Args:
            message: Error description.
        """
        super().__init__(message)


class APIError(DynDNSException):
    """Raised when provider API communication fails."""

    def __init__(self, message: str = ExceptionMessages.API) -> None:
        """Initialize API exception with default or custom message.

        Args:
            message: Error description.
        """
        super().__init__(message)


class RecordNotFoundError(APIError):
    """Raised when requested DNS record is not found on provider (HTTP 404)."""

    def __init__(self, message: str = ExceptionMessages.RECORD_NOT_FOUND) -> None:
        """Initialize record-not-found exception with default or custom message.

        Args:
            message: Error description.
        """
        super().__init__(message)


class ZoneNotFoundError(APIError):
    """Raised when requested DNS zone is not found on provider (HTTP 404)."""

    def __init__(self, message: str = ExceptionMessages.ZONE_NOT_FOUND) -> None:
        """Initialize zone-not-found exception with default or custom message.

        Args:
            message: Error description.
        """
        super().__init__(message)


class ValidationError(DynDNSException):
    """Raised when input validation fails.

    Covers invalid domains, IP addresses, zone IDs, and constraint violations.
    """

    def __init__(self, message: str = ExceptionMessages.VALIDATION) -> None:
        """Initialize validation exception with default or custom message.

        Args:
            message: Error description.
        """
        super().__init__(message)
