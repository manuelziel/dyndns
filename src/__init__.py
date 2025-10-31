#!/usr/bin/env python3
"""
DYNDNS

Dynamic DNS Client

Created: 2025-10-29
Author: Manuel Ziel
License: MIT
"""

# Package metadata
__version__ = "1.0.3alpha01"
__author__ = "Manuel Ziel"
__email__ = "manuelziel@gmail.com"
__description__ = "Dynamic DNS Client"
__software_name__ = "IONOS-DYNDNS"
__syslog_identifier__ = "ionos-dyndns"  # Used for systemd journal logging

# Package imports
from .colors import Colors, LOG_COLORS, LOG_SYMBOLS
from .config import ConfigManager
from .database import Database 
from .logger import LoggerManager
from .application import Application
from .daemon import DaemonManager 
from .network import NetworkData
from .api import HTTPClient

__all__ = [
    'Colors',
    'LOG_COLORS',
    'LOG_SYMBOLS',
    'ConfigManager',
    'Database', 
    'LoggerManager',
    'Application',
    'DaemonManager', 
    'NetworkData',
    'HTTPClient',
]