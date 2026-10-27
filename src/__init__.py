#!/usr/bin/env python3
"""DynDNS - Dynamic DNS Client for IONOS Provider API.

This package provides all components for the DynDNS daemon application
with systemd integration, database support, and modular architecture.

Modules:
    core: Configuration, database, logging, encryption, and exceptions.
    utils: Color codes and utility functions.
    application: Main application business logic.
    daemon: Background process management.
    api: HTTP client and IONOS API integration.
    network: Network utilities and IP detection.
    cli: Command-line interface components.

Typical usage:
    >>> from src import ConfigManager, LoggerManager, Application
    >>> config = ConfigManager('/app', '/app/config.toml')
    >>> logger = LoggerManager.get_logger('dyndns')
    >>> app = Application(config, logger)

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
    DynDNSException,
    DatabaseError,
    ConfigError,
    EncryptionError,
    NetworkError,
    APIError,
    RecordNotFoundError,
    ZoneNotFoundError,
    ValidationError,
    LoggerManager,
    Database,
    ConfigManager,
    EncryptionManager,
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
    '__version__',
    '__author__',
    '__software_name__',
    '__syslog_identifier__',
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
    # Core
    'LoggerManager',
    'Database',
    'ConfigManager',
    'EncryptionManager',
    # Utils
    'Colors',
    'LOG_COLORS',
    'LOG_SYMBOLS',
    # Application
    'Application',
    'DaemonManager',
    'NetworkData',
    'HTTPClient',
]
