#!/usr/bin/env python3
"""DynDNS - Dynamic DNS Client for IONOS Provider API.

Provides all components for the DynDNS daemon and CLI application with systemd
integration, SQLite WAL persistence, encrypted credentials, and modular services.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# PACKAGE METADATA
################################################################################

from .core.constants import AppSettings

__version__ = AppSettings.VERSION
__author__ = AppSettings.AUTHOR
__email__ = AppSettings.EMAIL
__description__ = AppSettings.DESCRIPTION
__software_name__ = AppSettings.SOFTWARE_NAME
__syslog_identifier__ = AppSettings.SYSLOG_IDENTIFIER

################################################################################
# PACKAGE IMPORTS
################################################################################

from .core import (
    APIError,
    ConfigError,
    ConfigManager,
    Database,
    DatabaseError,
    DatabaseLockedError,
    DynDNSException,
    EncryptionError,
    EncryptionManager,
    LoggerManager,
    NetworkError,
    RecordNotFoundError,
    ValidationError,
    ZoneNotFoundError,
    sanitize_log_uri,
)
from .utils import Colors, LOG_COLORS, LOG_SYMBOLS
from .network import NetworkData
from .api import HTTPClient
from .daemon import DaemonManager
from .application import Application

################################################################################
# PUBLIC API
################################################################################

__all__ = [
    # Metadata
    "__version__",
    "__author__",
    "__software_name__",
    "__syslog_identifier__",
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
    # Core
    "ConfigManager",
    "Database",
    "EncryptionManager",
    "LoggerManager",
    "sanitize_log_uri",
    # Utils
    "Colors",
    "LOG_COLORS",
    "LOG_SYMBOLS",
    # Application
    "Application",
    "DaemonManager",
    "HTTPClient",
    "NetworkData",
]
