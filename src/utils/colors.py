#!/usr/bin/env python3
"""ANSI color codes and logging symbols for terminal output.

Provides centralized color definitions and Unicode status symbols shared across
the logging subsystem, CLI helpers, and runtime services.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# ANSI COLOR CODES
################################################################################


class Colors:
    """ANSI escape codes for terminal text formatting."""

    # Basic colors
    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[1;33m"
    BLUE = "\033[0;34m"
    PURPLE = "\033[0;35m"
    CYAN = "\033[0;36m"
    WHITE = "\033[1;37m"

    # Bold colors
    BOLD_RED = "\033[1;31m"
    BOLD_GREEN = "\033[1;32m"
    BOLD_YELLOW = "\033[1;33m"

    # Formatting
    BOLD = "\033[1m"
    DIM = "\033[2m"

    # Reset
    NC = "\033[0m"
    RESET = "\033[0m"


################################################################################
# LOGGING COLOR MAP
################################################################################

LOG_COLORS: dict[str, str] = {
    "DEBUG": Colors.BLUE,
    "INFO": Colors.NC,
    "WARNING": Colors.YELLOW,
    "ERROR": Colors.RED,
    "CRITICAL": Colors.BOLD_RED,
    "SUCCESS": Colors.GREEN,
    "RESET": Colors.RESET,
}

################################################################################
# LOGGING & STATUS SYMBOLS
################################################################################

LOG_SYMBOLS: dict[str, str] = {
    "DEBUG": "d",
    "INFO": "ℹ",
    "WARNING": "✗",
    "ERROR": "✗",
    "CRITICAL": "✗",
    "SUCCESS": "✓",
    "BULLET": "*",
    "ARROW": ">",
}
