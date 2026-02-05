#!/usr/bin/env python3
"""Core module for IONOS-DYNDNS.

This module provides the core functionality including configuration management,
database operations, logging, encryption, and custom exceptions.

Modules:
    config: TOML configuration loading and management.
    database: SQLite database with connection pooling.
    encryption: Fernet-based encryption for sensitive data.
    logger: Logging with systemd journal integration.
    exceptions: Custom exception hierarchy.
    constants: Application constants and enums.

Typical usage:
    >>> from src.core import ConfigManager, Database, LoggerManager
    >>> config = ConfigManager('/app', '/app/config.toml')
    >>> logger = LoggerManager.get_logger('ionos-dyndns')

Author: Manuel Ziel
License: MIT
"""

################################################################################
# PACKAGE IMPORTS
################################################################################

from .config import ConfigManager
from .database import Database
from .encryption import EncryptionManager
from .logger import LoggerManager
from .exceptions import (
    DynDNSException,
    DatabaseError,
    ConfigError,
    EncryptionError,
    NetworkError,
    APIError,
    RecordNotFoundError,
    ZoneNotFoundError,
    ValidationError
)
from .constants import (
    SyncStatus,
    UpdateStatus,
    RecordType,
    PlaceholderIP,
    Subdomain,
    ExportFormat
)

################################################################################
# PUBLIC API
################################################################################

__all__ = [
    # Core Classes
    'ConfigManager',
    'Database',
    'EncryptionManager',
    'LoggerManager',
    # Exceptions
    'DynDNSException',
    'DatabaseError',
    'ConfigError',
    'EncryptionError',
    'NetworkError',
    'APIError',
    'RecordNotFoundError',
    'ZoneNotFoundError',
    'ValidationError',
    # Constants
    'SyncStatus',
    'UpdateStatus',
    'RecordType',
    'PlaceholderIP',
    'Subdomain',
    'ExportFormat',
]
