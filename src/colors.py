#!/usr/bin/env python3
"""
ANSI Color Codes - Central color definitions for terminal output
Used by: logger.py, cli_helpers.py, config.py

Created: 2025-10-27
Author: Manuel Ziel
License: MIT

This program is free software: you can redistribute it and/or modify
"""

################################################################################
# ANSI COLOR CODES
################################################################################

class Colors:
    """ANSI color codes for terminal output."""
    # Basic colors
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    PURPLE = '\033[0;35m'
    CYAN = '\033[0;36m'
    WHITE = '\033[1;37m'
    
    # Bold colors
    BOLD_RED = '\033[1;31m'
    BOLD_GREEN = '\033[1;32m'
    BOLD_YELLOW = '\033[1;33m'
    
    # Formatting
    BOLD = '\033[1m'
    DIM = '\033[2m'
    
    # Reset
    NC = '\033[0m'      # No Color / Reset
    RESET = '\033[0m'   # Alias for NC

################################################################################
# LOGGING COLOR MAP
################################################################################

LOG_COLORS = {
    'DEBUG': Colors.BLUE,
    'INFO': Colors.NC,
    'WARNING': Colors.YELLOW,
    'ERROR': Colors.RED,
    'CRITICAL': Colors.BOLD_RED,
    'SUCCESS': Colors.GREEN,
    'RESET': Colors.RESET
}

################################################################################
# LOGGING SYMBOLS
################################################################################

LOG_SYMBOLS = {
    'DEBUG': 'd',
    'INFO': 'ℹ',
    'WARNING': '✗',
    'ERROR': '✗',
    'CRITICAL': '✗',
    'SUCCESS': '✓',
    'BULLET': '*',
    'ARROW': '>'
}
