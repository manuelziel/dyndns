#!/usr/bin/env python3
"""
CLI Helper Functions

Provides reusable UI components and utilities for CLI interactions.

Created: 2025-10-27
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
import sys
from typing import Optional, Dict, Any, List, Callable

# Internal imports
from colors import Colors, LOG_SYMBOLS

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
        record_type: DNS record type ('A' or 'AAAA')
        
    Returns:
        Placeholder IP: '0.0.0.0' for A (IPv4), '::' for AAAA (IPv6)
        
    Raises:
        ValueError: If record_type is not 'A' or 'AAAA'
    """
    if record_type == 'A':
        return "0.0.0.0"
    elif record_type == 'AAAA':
        return "::"
    else:
        raise ValueError(f"Unsupported record type: {record_type}")

def row_to_dict(row: Any) -> Optional[Dict[str, Any]]:
    """Convert sqlite3.Row to dictionary."""
    if row is None:
        return None
    return dict(row)

################################################################################
# UI COMPONENTS
################################################################################

def print_status(message: str, color: str = Colors.NC) -> None:
    """Print colored status message."""
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
    """Print formatted status line with consistent alignment."""
    print(f"  {label:<15} {color}{symbol} {message}{Colors.NC}")

def print_section(title: str) -> None:
    """Print section header with border (main screen header)."""
    print()
    print(f"{Colors.BOLD}{Colors.CYAN}═══ {title} ═══{Colors.NC}")
    print()

def print_subsection(title: str) -> None:
    """Print subsection header with border (inline header without extra spacing)."""
    print(f"\n{Colors.CYAN}═══ {title} ═══{Colors.NC}")

def print_banner(software_name: str, mode: str, description: str, version: str) -> None:
    """Print application banner with borders."""
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
    """Wait for user to press Enter."""
    input(f"\n{message}")

def confirm_action(message: str = "Proceed?", default: bool = False) -> bool:
    """Ask user for confirmation (y/N or Y/n)."""
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
    """Get validated integer input from user."""
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
            print_error("Please enter a valid number!")
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
    """Get validated string input from user."""
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
    """Display numbered list and get user selection."""
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
            print_error("Please enter a valid number!")
            continue
        
        choice = int(choice_str)
        
        if choice < 1 or choice > len(items):
            print_error(f"Please select a number between 1 and {len(items)}!")
            continue
        
        selected = items[choice - 1]
        
        # Use row_to_dict for guaranteed sqlite3.Row conversion
        return row_to_dict(selected) if selected else None

################################################################################
# VALIDATION HELPERS
################################################################################

def is_valid_domain(domain: str) -> bool:
    """Validate domain name format (RFC 1035 compatible)."""
    pattern = r'^(?=.{1,253}$)(?!-)[a-z0-9-]{1,63}(?<!-)(\.[a-z0-9-]{1,63})*$'
    return re.match(pattern, domain.lower()) is not None

def is_valid_ipv4(ip: str) -> bool:
    """Validate IPv4 address format."""
    pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
    if not re.match(pattern, ip):
        return False
    
    octets = ip.split('.')
    return all(0 <= int(octet) <= 255 for octet in octets)

def is_valid_ipv6(ip: str) -> bool:
    """Validate IPv6 address format."""
    pattern = r'^([0-9a-fA-F]{0,4}:){2,7}[0-9a-fA-F]{0,4}$'
    return re.match(pattern, ip) is not None

################################################################################
# ZONE/RECORD SELECTION HELPERS
################################################################################

def select_zone(db, prompt: str = "Select Zone ID") -> Optional[Dict]:
    """Display zones and get user selection."""
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
    """Display records for zone and get user selection."""
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
    """Validate zone ID input and fetch zone."""
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
    """Display detailed zone information."""
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
    """Format data as simple ASCII table."""
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