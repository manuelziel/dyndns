#!/usr/bin/env python3
"""IONOS DynDNS - Dynamic DNS Client for IONOS Provider API.

This package provides all components for the IONOS DynDNS daemon application
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
    >>> logger = LoggerManager.get_logger('ionos-dyndns')
    >>> app = Application(config, logger)

Author: Manuel Ziel
License: MIT
"""

################################################################################
# PACKAGE METADATA
################################################################################

__version__ = "1.0.3alpha02"
__author__ = "Manuel Ziel"
__email__ = "manuelziel@gmail.com"
__description__ = "Dynamic DNS Client"
__software_name__ = "IONOS-DYNDNS"
__syslog_identifier__ = "ionos-dyndns"  # Used for systemd journal logging

################################################################################
# PACKAGE IMPORTS
################################################################################

# Core module imports
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

# Utils module imports
from .utils import Colors, LOG_COLORS, LOG_SYMBOLS

# Application imports
from .application import Application
from .daemon import DaemonManager
from .network import NetworkData
from .api import HTTPClient

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
