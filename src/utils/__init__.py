#!/usr/bin/env python3
"""Utility module for DynDNS.

This module provides utility functions and constants used across the application,
including ANSI color codes for terminal output and logging symbols.

Modules:
    colors: ANSI color codes and logging color/symbol mappings.

Typical usage:
    >>> from src.utils import Colors, LOG_COLORS
    >>> print(f"{Colors.GREEN}Success!{Colors.RESET}")

Author: Manuel Ziel
License: MIT
"""

################################################################################
# PACKAGE IMPORTS
################################################################################

# Local Imports
from .colors import Colors, LOG_COLORS, LOG_SYMBOLS

################################################################################
# PUBLIC API
################################################################################

__all__ = [
    'Colors',
    'LOG_COLORS',
    'LOG_SYMBOLS',
]
