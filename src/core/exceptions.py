#!/usr/bin/env python3
"""Custom exception classes for DynDNS.

Provides a structured exception hierarchy for consistent error handling
across the application. All custom exceptions inherit from DynDNSException.

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
    """Base exception for all DynDNS errors."""

    def __init__(self, message: str = ExceptionMessages.DEFAULT) -> None:
        """Initialize base exception with default or custom message.

        Args:
            message: Error description.
        """
        self.message = message
        super().__init__(message)


class DatabaseError(DynDNSException):
    """Raised when a database operation fails."""

    def __init__(self, message: str = ExceptionMessages.DATABASE) -> None:
        """Initialize database exception with default or custom message.

        Args:
            message: Error description.
        """
        super().__init__(message)


class DatabaseLockedError(DatabaseError):
    """Raised when the SQLite database is locked beyond the busy timeout."""

    def __init__(self, message: str = ExceptionMessages.DATABASE_LOCKED) -> None:
        """Initialize database-locked exception with default or custom message.

        Args:
            message: Error description.
        """
        super().__init__(message)


class ConfigError(DynDNSException):
    """Raised when configuration loading or parsing fails."""

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
    """Raised when a network operation fails."""

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
    """Raised when input validation fails."""

    def __init__(self, message: str = ExceptionMessages.VALIDATION) -> None:
        """Initialize validation exception with default or custom message.

        Args:
            message: Error description.
        """
        super().__init__(message)
