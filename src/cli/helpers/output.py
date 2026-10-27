#!/usr/bin/env python3
"""CLI output helpers for formatting and displaying data.

This module provides common utilities for printing formatted sections,
banners, success/error status messages, and tables.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

import json
import os
from typing import Any, Dict, List, Optional

from src.utils.colors import Colors, LOG_SYMBOLS
from src.cli.constants import CLIConfig


################################################################################
# UI OUTPUT FUNCTIONS
################################################################################

def row_to_dict(row: Any) -> Optional[Dict[str, Any]]:
    """Convert sqlite3.Row object to dictionary.

    Args:
        row: sqlite3.Row object or None.

    Returns:
        Dictionary representation of the row, or None if input is None.
    """
    if row is None:
        return None
    return dict(row)


def print_status(message: str, color: str = Colors.NC) -> None:
    """Print a colored status message to the terminal.

    Args:
        message: Message text to print.
        color: ANSI color code to apply.
    """
    print(f"{color}{message}{Colors.NC}")


def print_success(message: str) -> None:
    """Print success message with symbol from LOG_SYMBOLS.

    Args:
        message: The success message.
    """
    symbol = LOG_SYMBOLS['SUCCESS']
    prefix = f"{symbol} " if symbol else ""
    print_status(f"{prefix}{message}", Colors.GREEN)


def print_error(message: str) -> None:
    """Print error message with symbol from LOG_SYMBOLS.

    Args:
        message: The error message.
    """
    symbol = LOG_SYMBOLS['ERROR']
    prefix = f"{symbol} " if symbol else ""
    print_status(f"{prefix}{message}", Colors.RED)


def print_warning(message: str) -> None:
    """Print warning message with symbol from LOG_SYMBOLS.

    Args:
        message: The warning message.
    """
    symbol = LOG_SYMBOLS['WARNING']
    prefix = f"{symbol} " if symbol else ""
    print_status(f"{prefix}{message}", Colors.YELLOW)


def print_info(message: str) -> None:
    """Print info message with symbol from LOG_SYMBOLS.

    Args:
        message: The info message.
    """
    symbol = LOG_SYMBOLS['INFO']
    prefix = f"{symbol} " if symbol else ""
    print_status(f"{prefix}{message}", Colors.BLUE)


def print_debug(message: str) -> None:
    """Print debug message.

    Args:
        message: The debug message.
    """
    print_status(f"  {message}", Colors.PURPLE)


def print_status_line(label: str, color: str, symbol: str, message: str) -> None:
    """Print a formatted status line with consistent alignment.

    Args:
        label: Left-aligned label text (15 character width).
        color: ANSI color code for the status.
        symbol: Status symbol to display.
        message: Status message text.
    """
    print(f"  {label:<{CLIConfig.LABEL_WIDTH}} {color}{symbol} {message}{Colors.NC}")


def print_section(title: str) -> None:
    """Print a section header with decorative border.

    Args:
        title: Section title text to display.
    """
    print()
    print(f"{Colors.BOLD}{Colors.CYAN}═══ {title} ═══{Colors.NC}")
    print()


def print_subsection(title: str) -> None:
    """Print a subsection header with border.

    Args:
        title: Subsection title text to display.
    """
    print(f"\n{Colors.CYAN}═══ {title} ═══{Colors.NC}")


def print_banner(software_name: str, mode: str, description: str, version: str) -> None:
    """Print the application banner with decorative borders.

    Args:
        software_name: Name of the application.
        mode: Current operating mode.
        description: Brief application description.
        version: Version string to display.
    """
    print()
    print(f"{Colors.BOLD}{Colors.CYAN}{'═' * CLIConfig.BANNER_WIDTH}{Colors.NC}")
    print(f"{Colors.BOLD}{Colors.WHITE}  {software_name} {mode}{Colors.NC}")
    print(f"  {description}")
    print(f"{Colors.DIM}  Version: {version}{Colors.NC}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'═' * CLIConfig.BANNER_WIDTH}{Colors.NC}")
    print()


def clear_screen() -> None:
    """Clear terminal screen (cross-platform)."""
    os.system('clear' if os.name == 'posix' else 'cls')


def format_table(headers: List[str], rows: List[List[Any]], widths: Optional[List[int]] = None) -> str:
    """Format data as a simple ASCII table.

    Args:
        headers: List of column header names.
        rows: List of row data, each row is a list of cell values.
        widths: Optional list of column widths, auto-calculated if None.

    Returns:
        Formatted table string with headers, separator, and data rows.
    """
    if not widths:
        widths = [len(str(h)) for h in headers]
        for row in rows:
            for idx, cell in enumerate(row):
                widths[idx] = max(widths[idx], len(str(cell)))

    header_line = "  ".join(f"{str(h):<{w}}" for h, w in zip(headers, widths))
    separator = "  ".join("-" * w for w in widths)

    row_lines = []
    for row in rows:
        row_line = "  ".join(f"{str(c):<{w}}" for c, w in zip(row, widths))
        row_lines.append(row_line)

    return "\n".join([header_line, separator] + row_lines)


def display_zone_details(zone: Dict[str, Any], db: Any) -> None:
    """Display detailed zone information including credentials and records.

    Args:
        zone: Zone dictionary with zone data.
        db: Database instance for retrieving related data.
    """
    status = f'{LOG_SYMBOLS["SUCCESS"]} Enabled' if zone['enabled'] else f'{LOG_SYMBOLS["ERROR"]} Disabled'
    print(f"\nZone: {zone['zone_name']:<{CLIConfig.ZONE_NAME_WIDTH}} [{status}]")
    print(f"  Zone ID: {zone.get('provider_zone_id', 'N/A')}")

    dyndns_row = db.get_dyndns_config_by_zone(zone['id'])
    if dyndns_row:
        dyndns = dict(dyndns_row)
        print(f"  Bulk ID: {dyndns.get('bulk_id', 'N/A')}")
        print(f"  API Key: {'*' * CLIConfig.MASK_LENGTH} (encrypted)")

        if dyndns.get('domains'):
            try:
                domains = json.loads(dyndns['domains']) if isinstance(dyndns['domains'], str) else dyndns['domains']
                if domains:
                    print(f"  Domains: {', '.join(domains)}")
            except (json.JSONDecodeError, ValueError, TypeError):
                pass

    records = db.get_records_by_zone(zone['id'])
    print(f"  Records: {len(records)} configured")
