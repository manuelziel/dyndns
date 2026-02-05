#!/usr/bin/env python3
"""CLI helper functions for reusable UI components and utilities.

This module provides common CLI utilities including colored output,
user input validation, confirmation prompts, and selection helpers
for zones and records.

Typical usage:
    >>> from cli_helpers import print_success, confirm_action
    >>> print_success("Operation completed")
    >>> if confirm_action("Proceed?"):
    ...     do_something()

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

# Standard library imports
import json
import os
import re
from typing import Optional, Dict, Any, Callable

# Internal imports
from .utils.colors import Colors, LOG_SYMBOLS
from .core.constants import PlaceholderIP

################################################################################
# EXPORTS
################################################################################

__all__ = [
    'Colors',
    'get_placeholder_ip',
    'row_to_dict',
    'print_success', 'print_error', 'print_warning', 'print_info', 'print_debug',
    'print_status', 'print_status_line', 'print_section', 'print_subsection', 'print_banner',
    'clear_screen', 'wait_for_enter', 'confirm_action', 'get_valid_int',
    'select_zone', 'select_record', 'format_table'
]

################################################################################
# UTILITY FUNCTIONS
################################################################################

def get_placeholder_ip(record_type: str) -> str:
    """Get appropriate placeholder IP address based on record type.

    Args:
        record_type: DNS record type, either 'A' or 'AAAA'.

    Returns:
        Placeholder IP address: '0.0.0.0' for A (IPv4), '::' for AAAA (IPv6).

    Raises:
        ValueError: If record_type is not 'A' or 'AAAA'.
    """
    return PlaceholderIP.get(record_type)

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

################################################################################
# UI COMPONENTS
################################################################################

def print_status(message: str, color: str = Colors.NC) -> None:
    """Print a colored status message to the terminal.

    Args:
        message: Message text to print.
        color: ANSI color code to apply.
    """
    print(f"{color}{message}{Colors.NC}")

def print_success(message: str) -> None:
    """Print success message with symbol from LOG_SYMBOLS."""
    print_status(f"{LOG_SYMBOLS['SUCCESS']} {message}", Colors.GREEN)

def print_error(message: str) -> None:
    """Print error message with symbol from LOG_SYMBOLS."""
    print_status(f"{LOG_SYMBOLS['ERROR']} {message}", Colors.RED)

def print_warning(message: str) -> None:
    """Print warning message with symbol from LOG_SYMBOLS."""
    print_status(f"{LOG_SYMBOLS['WARNING']} {message}", Colors.YELLOW)

def print_info(message: str) -> None:
    """Print info message with symbol from LOG_SYMBOLS."""
    print_status(f"{LOG_SYMBOLS['INFO']} {message}", Colors.BLUE)

def print_debug(message: str) -> None:
    """Print debug message."""
    print_status(f"  {message}", Colors.PURPLE)

def print_status_line(label: str, color: str, symbol: str, message: str) -> None:
    """Print a formatted status line with consistent alignment.

    Args:
        label: Left-aligned label text (15 character width).
        color: ANSI color code for the status.
        symbol: Status symbol to display.
        message: Status message text.
    """
    print(f"  {label:<15} {color}{symbol} {message}{Colors.NC}")

def print_section(title: str) -> None:
    """Print a section header with decorative border.

    Used for main screen headers with extra spacing.

    Args:
        title: Section title text to display.
    """
    print()
    print(f"{Colors.BOLD}{Colors.CYAN}═══ {title} ═══{Colors.NC}")
    print()

def print_subsection(title: str) -> None:
    """Print a subsection header with border.

    Used for inline headers without extra vertical spacing.

    Args:
        title: Subsection title text to display.
    """
    print(f"\n{Colors.CYAN}═══ {title} ═══{Colors.NC}")

def print_banner(software_name: str, mode: str, description: str, version: str) -> None:
    """Print the application banner with decorative borders.

    Args:
        software_name: Name of the application.
        mode: Current operating mode (e.g., 'Configuration').
        description: Brief application description.
        version: Version string to display.
    """
    print()
    print(f"{Colors.BOLD}{Colors.CYAN}{'═' * 63}{Colors.NC}")
    print(f"{Colors.BOLD}{Colors.WHITE}  {software_name} {mode}{Colors.NC}")
    print(f"  {description}")
    print(f"{Colors.DIM}  Version: {version}{Colors.NC}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'═' * 63}{Colors.NC}")
    print()

def clear_screen() -> None:
    """Clear terminal screen (cross-platform)."""
    os.system('clear' if os.name == 'posix' else 'cls')

################################################################################
# INPUT HELPERS (validation, confirmation, etc.)
################################################################################

def wait_for_enter(message: str = "Press Enter to continue...") -> None:
    """Wait for user to press Enter before continuing.

    Args:
        message: Prompt message to display to the user.
    """
    input(f"\n{message}")

def confirm_action(message: str = "Proceed?", default: bool = False) -> bool:
    """Ask user for confirmation with yes/no prompt.

    Args:
        message: Confirmation prompt text.
        default: Default response if user presses Enter.

    Returns:
        True if user confirmed, False otherwise.
    """
    suffix = " (Y/n): " if default else " (y/N): "
    response = input(f"{message}{suffix}").strip().lower()
    
    if not response:
        return default
    
    return response in ['y', 'yes']

def get_valid_int(
    prompt: str,
    min_val: Optional[int] = None,
    max_val: Optional[int] = None,
    allow_empty: bool = False,
    default: Optional[int] = None
) -> Optional[int]:
    """Get validated integer input from user with optional constraints.

    Args:
        prompt: Input prompt to display.
        min_val: Minimum allowed value, or None for no minimum.
        max_val: Maximum allowed value, or None for no maximum.
        allow_empty: If True, allow empty input returning None.
        default: Default value to use for empty input.

    Returns:
        Validated integer, or None if empty input is allowed.
    """
    while True:
        value_str = input(f"{prompt}: ").strip()
        
        if not value_str:
            if default is not None:
                return default
            if allow_empty:
                return None
            print_error("Input cannot be empty!")
            continue
        
        if not value_str.isdigit() and not (value_str.startswith('-') and value_str[1:].isdigit()):
            print_error("Enter a valid number!")
            continue
        
        value = int(value_str)
        
        if min_val is not None and value < min_val:
            print_error(f"Value must be at least {min_val}!")
            continue
        
        if max_val is not None and value > max_val:
            print_error(f"Value must be at most {max_val}!")
            continue
        
        return value

def get_valid_string(
    prompt: str,
    allow_empty: bool = False,
    default: Optional[str] = None,
    validator: Optional[Callable[[str], bool]] = None,
    error_message: str = "Invalid input!"
) -> Optional[str]:
    """Get validated string input from user with optional validation.

    Args:
        prompt: Input prompt to display.
        allow_empty: If True, allow empty input returning None.
        default: Default value to use for empty input.
        validator: Optional function to validate input, returns True if valid.
        error_message: Error message to show for invalid input.

    Returns:
        Validated string, or None if empty input is allowed.
    """
    while True:
        value = input(f"{prompt}: ").strip()
        
        if not value:
            if default is not None:
                return default
            if allow_empty:
                return None
            print_error("Input cannot be empty!")
            continue
        
        if validator and not validator(value):
            print_error(error_message)
            continue
        
        return value

def get_choice_from_list(
    items: list,
    prompt: str = "Select",
    display_func: Optional[Callable[[Any], str]] = None,
    allow_cancel: bool = True
) -> Optional[Any]:
    """Display numbered list and get user selection.

    Args:
        items: List of items to display for selection.
        prompt: Selection prompt text.
        display_func: Optional function to format items for display.
        allow_cancel: If True, allow cancellation with 0.

    Returns:
        Selected item as dictionary, or None if cancelled.
    """
    if not items:
        print_warning("No items available.")
        return None
    
    print()
    for idx, item in enumerate(items, start=1):
        display_text = display_func(item) if display_func else str(item)
        print(f"{idx:2d}. {display_text}")
    
    if allow_cancel:
        print(" 0. Cancel")
    
    while True:
        if allow_cancel:
            choice_str = input(f"\n{prompt} (0-{len(items)}): ").strip()
        else:
            choice_str = input(f"\n{prompt} (1-{len(items)}): ").strip()
        
        if not choice_str and allow_cancel:
            return None
        
        if choice_str == '0' and allow_cancel:
            return None
        
        if not choice_str.isdigit():
            print_error("Enter a valid number!")
            continue
        
        choice = int(choice_str)
        
        if choice < 1 or choice > len(items):
            print_error(f"Select a number between 1 and {len(items)}!")
            continue
        
        selected = items[choice - 1]
        
        return row_to_dict(selected) if selected else None

################################################################################
# VALIDATION HELPERS
################################################################################

def is_valid_domain(domain: str) -> bool:
    """Validate domain name format according to RFC 1035.

    Args:
        domain: Domain name string to validate.

    Returns:
        True if domain format is valid, False otherwise.
    """
    pattern = r'^(?=.{1,253}$)(?!-)[a-z0-9-]{1,63}(?<!-)(\.[a-z0-9-]{1,63})*$'
    return re.match(pattern, domain.lower()) is not None

def is_valid_ipv4(ip: str) -> bool:
    """Validate IPv4 address format.

    Args:
        ip: IPv4 address string to validate.

    Returns:
        True if address format is valid, False otherwise.
    """
    pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
    if not re.match(pattern, ip):
        return False
    
    octets = ip.split('.')
    return all(0 <= int(octet) <= 255 for octet in octets)

def is_valid_ipv6(ip: str) -> bool:
    """Validate IPv6 address format.

    Args:
        ip: IPv6 address string to validate.

    Returns:
        True if address format is valid, False otherwise.
    """
    pattern = r'^([0-9a-fA-F]{0,4}:){2,7}[0-9a-fA-F]{0,4}$'
    return re.match(pattern, ip) is not None

################################################################################
# ZONE/RECORD SELECTION HELPERS
################################################################################

def select_zone(db, prompt: str = "Select Zone ID") -> Optional[Dict]:
    """Display available zones and get user selection.

    Args:
        db: Database instance for retrieving zones.
        prompt: Selection prompt text.

    Returns:
        Selected zone as dictionary, or None if cancelled or no zones.
    """
    zones = db.get_all_zones()
    if not zones:
        print_warning("No zones configured.")
        wait_for_enter()
        return None
    
    selected = get_choice_from_list(
        zones,
        prompt=prompt,
        display_func=lambda z: f"{z['zone_name']:<30} [{Colors.GREEN if z['enabled'] else Colors.DIM}{f'{LOG_SYMBOLS["SUCCESS"]} Enabled' if z['enabled'] else f'{LOG_SYMBOLS["ERROR"]} Disabled'}{Colors.NC}]"
    )
    
    return row_to_dict(selected) if selected else None

def select_record(db, zone_id: int, prompt: str = "Select Record ID") -> Optional[Dict]:
    """Display records for a zone and get user selection.

    Args:
        db: Database instance for retrieving records.
        zone_id: Zone database ID to list records for.
        prompt: Selection prompt text.

    Returns:
        Selected record as dictionary, or None if cancelled or no records.
    """
    records = db.get_records_by_zone(zone_id, enabled_only=False)
    
    if not records:
        print_warning("No records configured for this zone.")
        wait_for_enter()
        return None
    
    selected = get_choice_from_list(
        records,
        prompt=prompt,
        display_func=lambda r: f"{r['record_name']:<40} {r['record_type']:<5} [{Colors.GREEN if r['enabled'] else Colors.DIM}{f'{LOG_SYMBOLS["SUCCESS"]} Enabled' if r['enabled'] else f'{LOG_SYMBOLS["ERROR"]} Disabled'}{Colors.NC}]"
    )
    
    return row_to_dict(selected) if selected else None

def get_zone_by_id_validated(db, zone_id_input: str) -> Optional[Dict]:
    """Validate zone ID input and fetch zone from database.

    Args:
        db: Database instance for retrieving zones.
        zone_id_input: Zone ID as string input.

    Returns:
        Zone dictionary if found, or None if invalid or not found.
    """
    if not zone_id_input.isdigit():
        print_error("Invalid Zone ID - must be a number")
        wait_for_enter()
        return None
    
    zone = db.get_zone_by_id(int(zone_id_input))
    
    if not zone:
        print_error(f"Zone ID {zone_id_input} not found!")
        wait_for_enter()
        return None
    
    return zone

def display_zone_details(zone: Dict, db) -> None:
    """Display detailed zone information including credentials and records.

    Args:
        zone: Zone dictionary with zone data.
        db: Database instance for retrieving related data.
    """
    status = f'{LOG_SYMBOLS["SUCCESS"]} Enabled' if zone['enabled'] else f'{LOG_SYMBOLS["ERROR"]} Disabled'
    print(f"\nZone: {zone['zone_name']:<30} [{status}]")
    print(f"  Zone ID: {zone.get('provider_zone_id', 'N/A')}")
    
    dyndns_row = db.get_dyndns_config_by_zone(zone['id'])
    if dyndns_row:
        dyndns = dict(dyndns_row)
        print(f"  Bulk ID: {dyndns.get('bulk_id', 'N/A')}")
        print(f"  API Key: {'*' * 20} (encrypted)")
        
        if dyndns.get('domains'):
            try:
                domains = json.loads(dyndns['domains']) if isinstance(dyndns['domains'], str) else dyndns['domains']
                if domains:
                    print(f"  Domains: {', '.join(domains)}")
            except (json.JSONDecodeError, ValueError, TypeError):
                pass
    
    records = db.get_records_by_zone(zone['id'])
    print(f"  Records: {len(records)} configured")

################################################################################
# DISPLAY HELPERS
################################################################################

def format_table(headers: list, rows: list, widths: Optional[list] = None) -> str:
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