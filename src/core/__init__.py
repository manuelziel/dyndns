#!/usr/bin/env python3
"""Core module for DynDNS.

Provides configuration management, SQLite connection pooling, Fernet
encryption, native systemd journald socket logging, URI secret redaction,
ownership handoff, constants, and custom exceptions in strict bottom-up DAG order.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# PACKAGE IMPORTS (Bottom-Up DAG Order)
################################################################################

from .constants import (
    AppPaths,
    AppSettings,
    DaemonDefaults,
    DatabaseDefaults,
    DNSDefaults,
    EncryptionDefaults,
    EnvKeys,
    ExceptionMessages,
    ExportFormat,
    HTTPHeader,
    HTTPHeaderValue,
    HTTPMethod,
    HTTPStatus,
    LoggingDefaults,
    NetworkAPI,
    OwnershipDefaults,
    PlaceholderIP,
    ProviderAPI,
    RecordType,
    SecurityDefaults,
    StorageConstants,
    Subdomain,
    SyncStatus,
    UpdateMethod,
    UpdateStatus,
)
from .exceptions import (
    APIError,
    ConfigError,
    DatabaseError,
    DatabaseLockedError,
    DynDNSException,
    EncryptionError,
    NetworkError,
    RecordNotFoundError,
    ValidationError,
    ZoneNotFoundError,
)
from .security import sanitize_log_uri
from .ownership import ensure_service_ownership
from .encryption import EncryptionManager
from .logger import LoggerManager
from .database import Database
from .config import ConfigManager

################################################################################
# PUBLIC API
################################################################################

__all__ = [
    # Constants
    "AppPaths",
    "AppSettings",
    "DaemonDefaults",
    "DatabaseDefaults",
    "DNSDefaults",
    "EncryptionDefaults",
    "EnvKeys",
    "ExceptionMessages",
    "ExportFormat",
    "HTTPHeader",
    "HTTPHeaderValue",
    "HTTPMethod",
    "HTTPStatus",
    "LoggingDefaults",
    "NetworkAPI",
    "OwnershipDefaults",
    "PlaceholderIP",
    "ProviderAPI",
    "RecordType",
    "SecurityDefaults",
    "StorageConstants",
    "Subdomain",
    "SyncStatus",
    "UpdateMethod",
    "UpdateStatus",
    # Exceptions
    "APIError",
    "ConfigError",
    "DatabaseError",
    "DatabaseLockedError",
    "DynDNSException",
    "EncryptionError",
    "NetworkError",
    "RecordNotFoundError",
    "ValidationError",
    "ZoneNotFoundError",
    # Helpers
    "ensure_service_ownership",
    "sanitize_log_uri",
    # Core Classes
    "ConfigManager",
    "Database",
    "EncryptionManager",
    "LoggerManager",
]
