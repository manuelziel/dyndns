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
# PACKAGE IMPORTS
################################################################################

# Local Imports
from .core.constants import AppSettings

from .core import (
    ConfigManager,
    Database,
    EncryptionManager,
    LoggerManager,
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

from .utils import Colors, LOG_COLORS, LOG_SYMBOLS
from .network import NetworkData
from .api import HTTPClient
from .daemon import DaemonManager
from .application import Application

# Package metadata
__version__ = AppSettings.VERSION
__author__ = AppSettings.AUTHOR
__email__ = AppSettings.EMAIL
__description__ = AppSettings.DESCRIPTION
__software_name__ = AppSettings.SOFTWARE_NAME
__syslog_identifier__ = AppSettings.SYSLOG_IDENTIFIER


################################################################################
# PUBLIC API
################################################################################

__all__ = [
    # Metadata
    '__version__',
    '__author__',
    '__software_name__',
    '__syslog_identifier__',
    # Core
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
