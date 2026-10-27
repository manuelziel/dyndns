#!/usr/bin/env python3
"""Core module for DynDNS.

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
    >>> logger = LoggerManager.get_logger('dyndns')

Author: Manuel Ziel
License: MIT
"""

################################################################################
# PACKAGE IMPORTS
################################################################################

from .constants import (
    AppSettings,
    SyncStatus,
    UpdateStatus,
    RecordType,
    PlaceholderIP,
    Subdomain,
    ExportFormat,
    HTTPMethod,
    HTTPStatus,
    HTTPHeader,
    HTTPHeaderValue,
    EnvKeys,
    SystemDefaults,
    EncryptionDefaults,
    AppPaths,
    ProviderAPI,
    NetworkAPI,
    DNSDefaults,
    LoggingDefaults,
    DaemonDefaults,
    DatabaseDefaults,
    UpdateMethod,
    ExceptionMessages,
)
from .exceptions import (
    DynDNSException,
    DatabaseError,
    ConfigError,
    EncryptionError,
    NetworkError,
    APIError,
    RecordNotFoundError,
    ZoneNotFoundError,
    ValidationError,
)
from .logger import LoggerManager
from .ownership import ensure_service_ownership
from .encryption import EncryptionManager
from .database import Database
from .config import ConfigManager

################################################################################
# PUBLIC API
################################################################################

__all__ = [
    # Constants
    'AppSettings',
    'SyncStatus',
    'UpdateStatus',
    'RecordType',
    'PlaceholderIP',
    'Subdomain',
    'ExportFormat',
    'HTTPMethod',
    'HTTPStatus',
    'HTTPHeader',
    'HTTPHeaderValue',
    'EnvKeys',
    'SystemDefaults',
    'EncryptionDefaults',
    'AppPaths',
    'ProviderAPI',
    'NetworkAPI',
    'DNSDefaults',
    'LoggingDefaults',
    'DaemonDefaults',
    'DatabaseDefaults',
    'UpdateMethod',
    'ExceptionMessages',
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
    # Helpers
    'ensure_service_ownership',
    # Core Classes
    'LoggerManager',
    'EncryptionManager',
    'Database',
    'ConfigManager',
]
