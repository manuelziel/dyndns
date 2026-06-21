#!/usr/bin/env python3
"""ANSI color codes and logging symbols for terminal output.

This module provides centralized color definitions used by the logging system,
CLI helpers, and other modules requiring colored terminal output.

The color codes are compatible with bash colors.sh for consistent appearance
across Python and Bash components.

Typical usage:
    >>> from src.utils.colors import Colors, LOG_COLORS
    >>> print(f"{Colors.GREEN}Success{Colors.RESET}")
    >>> print(f"{LOG_COLORS['ERROR']}Error occurred{Colors.RESET}")

Author: Manuel Ziel
License: MIT
"""

################################################################################
# ANSI COLOR CODES
################################################################################

class Colors:
    """ANSI escape codes for terminal text formatting.

    Provides color constants for consistent terminal output. Compatible with
    bash colors.sh definitions for uniform appearance.

    Attributes:
        RED: Red text (0;31m).
        GREEN: Green text (0;32m).
        YELLOW: Bold yellow text (1;33m).
        BLUE: Blue text (0;34m).
        PURPLE: Purple text (0;35m).
        CYAN: Cyan text (0;36m).
        WHITE: Bold white text (1;37m).
        BOLD_RED: Bold red text (1;31m).
        BOLD_GREEN: Bold green text (1;32m).
        BOLD_YELLOW: Bold yellow text (1;33m).
        BOLD: Bold formatting (1m).
        DIM: Dim formatting (2m).
        NC: No color / reset (0m).
        RESET: Alias for NC.

    Typical usage:
        >>> print(f"{Colors.RED}Error{Colors.RESET}")
        >>> print(f"{Colors.BOLD}Important{Colors.NC}")
    """

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

#: Mapping of log levels to ANSI color codes.
#: Used by ColoredFormatter in logger.py to colorize log output.
#: Keys match Python logging level names.
LOG_COLORS: dict[str, str] = {
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

#: Mapping of log levels to Unicode symbols.
#: Used by ColoredFormatter in logger.py to prefix log messages.
#: Level symbols are intentionally empty: color already conveys the level,
#: and a redundant checkmark/cross on every line dilutes its signal value.
#: BULLET and ARROW remain as semantic list/transition markers.
LOG_SYMBOLS: dict[str, str] = {
    'DEBUG': '',
    'INFO': '',
    'WARNING': '',
    'ERROR': '',
    'CRITICAL': '',
    'SUCCESS': '',
    'BULLET': '*',
    'ARROW': '>'
}
