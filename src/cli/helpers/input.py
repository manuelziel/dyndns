#!/usr/bin/env python3
"""CLI input helpers for retrieving and validating user responses.

This module provides common utilities for prompting the user, handling lists,
confirmations, integer/string inputs, and database selections.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

from typing import Any, Callable, Dict, List, Optional

from src.core.constants import PlaceholderIP
from src.cli.constants import PromptDefaults, CLIConfig, SelectionChoices, PaginationChoices
from src.utils.colors import Colors, LOG_SYMBOLS
from .output import (
    print_error,
    print_warning,
    print_info,
    print_section,
    clear_screen,
    row_to_dict,
)
from .validate import resolve_path, is_valid_file_path


################################################################################
# BASIC INPUT HELPERS
################################################################################

def get_placeholder_ip(record_type: str) -> str:
    """Get appropriate placeholder IP address based on record type.

    Args:
        record_type: DNS record type, either 'A' or 'AAAA'.

    Returns:
        Placeholder IP address.

    Raises:
        ValueError: If record_type is not 'A' or 'AAAA'.
    """
    return PlaceholderIP.get(record_type)


def safe_input(prompt: str = "") -> str:
    """Read input from the user safely, converting EOFError into KeyboardInterrupt.

    Args:
        prompt: The prompt message to display.

    Returns:
        The string entered by the user.

    Raises:
        KeyboardInterrupt: If Ctrl+C or Ctrl+D is pressed.
    """
    try:
        return input(prompt)
    except EOFError:
        print()
        raise KeyboardInterrupt()


def wait_for_enter(message: str = "Press Enter to continue...") -> None:
    """Wait for user to press Enter before continuing.

    Args:
        message: Prompt message to display to the user.
    """
    safe_input(f"\n{message}")


def confirm_action(message: str = "Proceed?", default: bool = False) -> bool:
    """Ask user for confirmation with yes/no prompt.

    Args:
        message: Confirmation prompt text.
        default: Default response if user presses Enter.

    Returns:
        True if user confirmed, False otherwise.
    """
    suffix = " (Y/n): " if default else " (y/N): "
    response = safe_input(f"{message}{suffix}").strip().lower()

    if not response:
        return default

    return response in PromptDefaults.YES


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
        min_val: Minimum allowed value, or None.
        max_val: Maximum allowed value, or None.
        allow_empty: If True, allow empty input.
        default: Default value for empty input.

    Returns:
        Validated integer, or None if empty input is allowed.
    """
    while True:
        value_str = safe_input(f"{prompt}: ").strip()

        if not value_str:
            if default is not None:
                return default
            if allow_empty:
                return None
            print_error("Input cannot be empty!")
            continue

        is_neg = value_str.startswith('-') and value_str[1:].isdigit()
        if not value_str.isdigit() and not is_neg:
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
        allow_empty: If True, allow empty input.
        default: Default value to use for empty input.
        validator: Optional function to validate input.
        error_message: Error message to show for invalid input.

    Returns:
        Validated string, or None if empty input is allowed.
    """
    while True:
        value = safe_input(f"{prompt}: ").strip()

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
    items: List[Any],
    prompt: str = "Select",
    display_func: Optional[Callable[[Any], str]] = None,
    allow_cancel: bool = True
) -> Optional[Any]:
    """Display numbered list and get user selection.

    Args:
        items: List of items to display for selection.
        prompt: Selection prompt text.
        display_func: Optional function to format items.
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
        print(f" {idx}) {display_text}")
    if allow_cancel:
        print(f" {SelectionChoices.CANCEL}) Cancel")

    while True:
        max_idx = len(items)
        cancel_prompt = f" ({SelectionChoices.CANCEL}-{max_idx}): " if allow_cancel else f" (1-{max_idx}): "
        choice_str = safe_input(f"\n{prompt}{cancel_prompt}").strip()
        if (not choice_str or choice_str == SelectionChoices.CANCEL) and allow_cancel:
            return None
        if not choice_str.isdigit():
            print_error("Enter a valid number!")
            continue

        choice = int(choice_str)
        if choice < 1 or choice > max_idx:
            print_error(f"Select a number between 1 and {max_idx}!")
            continue
        selected = items[choice - 1]
        return row_to_dict(selected) if selected else None


def print_paginated_list(
    items: List[Any],
    print_item_func: Callable[[Any], None],
    page_size: int = CLIConfig.DEFAULT_PAGE_SIZE,
    title: str = "Items",
) -> None:
    """Print a list of items paginated with navigation controls.

    Args:
        items: List of all items to paginate.
        print_item_func: Callback function to print a single item.
        page_size: Number of items per page. Defaults to CLIConfig.DEFAULT_PAGE_SIZE.
        title: Title of the paginated list. Defaults to "Items".
    """
    total_items = len(items)
    if total_items == 0:
        print_info(f"No {title.lower()} found.")
        wait_for_enter()
        return

    page_size = max(1, page_size)
    total_pages = (total_items + page_size - 1) // page_size
    current_page = 1
    while True:
        clear_screen()
        print_section(f"{title} (Page {current_page} of {total_pages})")
        start_index = (current_page - 1) * page_size
        end_index = min(start_index + page_size, total_items)
        for item in items[start_index:end_index]:
            print_item_func(item)
        _print_pagination_controls(
            start_index, end_index, total_items, current_page, total_pages, title
        )
        choice = safe_input("Select an option: ").strip().lower()
        if choice == PaginationChoices.BACK or not choice:
            break
        if choice == PaginationChoices.NEXT and current_page < total_pages:
            current_page += 1
        elif choice == PaginationChoices.PREV and current_page > 1:
            current_page -= 1


def _print_pagination_controls(
    start_index: int,
    end_index: int,
    total_items: int,
    current_page: int,
    total_pages: int,
    title: str,
) -> None:
    """Print pagination footer and available navigation options.

    Args:
        start_index: Zero-based start index of current page.
        end_index: Exclusive end index of current page.
        total_items: Total number of items across all pages.
        current_page: Current 1-based page number.
        total_pages: Total number of pages.
        title: Section title used for item count label.
    """
    print(f"\n{Colors.DIM}{'—' * CLIConfig.BANNER_WIDTH}{Colors.NC}")
    print(f"Showing {start_index + 1}-{end_index} of {total_items} {title.lower()}")
    print()
    options = []
    if current_page < total_pages:
        options.append(f"{Colors.BOLD}{PaginationChoices.NEXT}{Colors.NC}) Next page")
    if current_page > 1:
        options.append(f"{Colors.BOLD}{PaginationChoices.PREV}{Colors.NC}) Previous page")
    options.append(f"{Colors.BOLD}{PaginationChoices.BACK}{Colors.NC}) Back")
    print("Options:  " + "  |  ".join(options))
    print()


################################################################################
# ENTITY SELECTION HELPERS
################################################################################

def select_zone(db: Any, prompt: str = "Select Zone ID") -> Optional[Dict[str, Any]]:
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

    def _zone_display(z: Dict[str, Any]) -> str:
        """Format a zone database row for list display.

        Args:
            z: Zone dictionary row from database.

        Returns:
            Formatted string representation of the zone.
        """
        status_str = f"{LOG_SYMBOLS['SUCCESS']} Enabled" if z['enabled'] else f"{LOG_SYMBOLS['ERROR']} Disabled"
        color = Colors.GREEN if z['enabled'] else Colors.DIM
        return f"{z['zone_name']:<{CLIConfig.ZONE_NAME_WIDTH}} [{color}{status_str}{Colors.NC}]"

    selected = get_choice_from_list(
        zones,
        prompt=prompt,
        display_func=_zone_display
    )

    return row_to_dict(selected) if selected else None


def select_record(db: Any, zone_id: int, prompt: str = "Select Record ID") -> Optional[Dict[str, Any]]:
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

    def _record_display(r: Dict[str, Any]) -> str:
        """Format a record database row for list display.

        Args:
            r: Record dictionary row from database.

        Returns:
            Formatted string representation of the record.
        """
        status_str = f"{LOG_SYMBOLS['SUCCESS']} Enabled" if r['enabled'] else f"{LOG_SYMBOLS['ERROR']} Disabled"
        color = Colors.GREEN if r['enabled'] else Colors.DIM
        return f"{r['record_name']:<{CLIConfig.RECORD_NAME_WIDTH}} {r['record_type']:<{CLIConfig.RECORD_TYPE_WIDTH}} [{color}{status_str}{Colors.NC}]"

    selected = get_choice_from_list(
        records,
        prompt=prompt,
        display_func=_record_display
    )

    return row_to_dict(selected) if selected else None


def get_zone_by_id_validated(db: Any, zone_id_input: str) -> Optional[Dict[str, Any]]:
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

    return row_to_dict(zone)