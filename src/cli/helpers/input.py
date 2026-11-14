#!/usr/bin/env python3
"""CLI input helpers for interactive prompts, pagination, and entity selection.

Provides reusable functions for safe user input, yes/no confirmations,
validated numbers/strings, paginated views, and SQLite entity pickers.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

from collections.abc import Callable
from typing import Any

from ...core.constants import PlaceholderIP
from ...utils.colors import Colors, LOG_SYMBOLS
from ..constants import (
    CLIConfig,
    PaginationChoices,
    PromptDefaults,
    SelectionChoices,
)
from .output import (
    clear_screen,
    print_error,
    print_info,
    print_section,
    print_warning,
    row_to_dict,
)
from .validate import is_valid_file_path, resolve_path

################################################################################
# BASIC INPUT HELPERS
################################################################################


def get_placeholder_ip(record_type: str) -> str:
    """Return the placeholder IP address matching ``record_type``.

    Args:
        record_type: DNS record type (``'A'`` or ``'AAAA'``).

    Returns:
        Placeholder IP literal string.
    """
    return PlaceholderIP.get(record_type)


def safe_input(prompt: str = "") -> str:
    """Read a line from ``stdin``, converting ``EOFError`` to ``KeyboardInterrupt``.

    Args:
        prompt: Prompt text displayed prior to reading.

    Returns:
        Raw string entered by the user.

    Raises:
        KeyboardInterrupt: On Ctrl+C or EOF (Ctrl+D / closed stdin).
    """
    try:
        return input(prompt)
    except EOFError as exc:
        print()
        raise KeyboardInterrupt from exc


def wait_for_enter(message: str = "Press Enter to continue...") -> None:
    """Pause execution until the user presses Enter.

    Args:
        message: Prompt displayed while waiting.
    """
    safe_input(f"\n{message}")


def confirm_action(message: str = "Proceed?", default: bool = False) -> bool:
    """Prompt the user for a boolean yes/no confirmation.

    Args:
        message: Question presented to the user.
        default: Default boolean returned on empty Enter input.

    Returns:
        True when confirmed, False otherwise.
    """
    suffix = " [Y/n]: " if default else " [y/N]: "
    response = safe_input(f"{message}{suffix}").strip().lower()
    if not response:
        return default
    return response in PromptDefaults.YES


def get_valid_int(
    prompt: str,
    min_val: int | None = None,
    max_val: int | None = None,
    allow_empty: bool = False,
    default: int | None = None,
) -> int | None:
    """Prompt repeatedly until a valid bounded integer is entered.

    Args:
        prompt: Input prompt label.
        min_val: Optional inclusive lower bound.
        max_val: Optional inclusive upper bound.
        allow_empty: Allow empty input returning ``None``.
        default: Default integer returned on empty input.

    Returns:
        Validated integer or ``None`` when ``allow_empty`` is True.
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
        is_neg = value_str.startswith("-") and value_str[1:].isdigit()
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
    default: str | None = None,
    validator: Callable[[str], bool] | None = None,
    error_message: str = "Invalid input!",
) -> str | None:
    """Prompt repeatedly until a valid string is entered.

    Args:
        prompt: Input prompt label.
        allow_empty: Allow empty input returning ``None``.
        default: Default string returned on empty input.
        validator: Optional predicate validating non-empty strings.
        error_message: Error message printed when ``validator`` returns False.

    Returns:
        Validated string or ``None`` when ``allow_empty`` is True.
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


################################################################################
# LIST SELECTION & PAGINATION HELPERS
################################################################################


def get_choice_from_list(
    items: list[Any],
    prompt: str = "Select",
    display_func: Callable[[Any], str] | None = None,
    allow_cancel: bool = True,
) -> dict[str, Any] | None:
    """Render a numbered menu of ``items`` and return the selected item.

    Args:
        items: Sequence of items to present.
        prompt: Selection prompt prefix.
        display_func: Optional formatter turning an item into a label.
        allow_cancel: Include ``0) Cancel`` option when True.

    Returns:
        Selected item converted via ``row_to_dict``, or ``None`` on cancel.
    """
    if not items:
        print_warning("No items available.")
        return None
    print()
    for idx, item in enumerate(items, start=1):
        label = display_func(item) if display_func else str(item)
        print(f" {idx}) {label}")
    if allow_cancel:
        print(f" {SelectionChoices.CANCEL}) Cancel")
    return _read_list_selection(items, prompt, allow_cancel)


def _read_list_selection(
    items: list[Any], prompt: str, allow_cancel: bool
) -> dict[str, Any] | None:
    """Read and validate the numeric selection index for ``get_choice_from_list``.

    Args:
        items: Non-empty sequence of selectable items.
        prompt: Selection prompt prefix.
        allow_cancel: Whether ``0`` or empty input cancels selection.

    Returns:
        Selected item dictionary or ``None`` on cancellation.
    """
    max_idx = len(items)
    range_hint = f" ({SelectionChoices.CANCEL}-{max_idx}): " if allow_cancel else f" (1-{max_idx}): "
    while True:
        choice_str = safe_input(f"\n{prompt}{range_hint}").strip()
        if (not choice_str or choice_str == SelectionChoices.CANCEL) and allow_cancel:
            return None
        if not choice_str.isdigit():
            print_error("Enter a valid number!")
            continue
        choice = int(choice_str)
        if 1 <= choice <= max_idx:
            selected = items[choice - 1]
            return row_to_dict(selected) if selected else None
        print_error(f"Select a number between 1 and {max_idx}!")


def print_paginated_list(
    items: list[Any],
    print_item_func: Callable[[Any], None],
    page_size: int = CLIConfig.DEFAULT_PAGE_SIZE,
    title: str = "Items",
) -> None:
    """Render ``items`` interactively across navigable pages.

    Args:
        items: Full list of items to display.
        print_item_func: Callback printing one item.
        page_size: Maximum items shown per page.
        title: Heading title for the paginated list.
    """
    total_items = len(items)
    if total_items == 0:
        print_info(f"No {title.lower()} found.")
        wait_for_enter()
        return
    eff_size = max(1, page_size)
    total_pages = (total_items + eff_size - 1) // eff_size
    current_page = 1
    while True:
        clear_screen()
        print_section(f"{title} (Page {current_page} of {total_pages})")
        start_idx = (current_page - 1) * eff_size
        end_idx = min(start_idx + eff_size, total_items)
        for item in items[start_idx:end_idx]:
            print_item_func(item)
        _print_pagination_controls(
            start_idx, end_idx, total_items, current_page, total_pages, title
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
    """Print pagination summary footer and navigation hints.

    Args:
        start_index: Zero-based start offset of current page.
        end_index: Exclusive end offset of current page.
        total_items: Total number of items.
        current_page: Active 1-based page number.
        total_pages: Total page count.
        title: Display title used in summary line.
    """
    print(f"\n{Colors.DIM}{'-' * CLIConfig.BANNER_WIDTH}{Colors.NC}")
    print(f"Showing {start_index + 1}-{end_index} of {total_items} {title.lower()}\n")
    options: list[str] = []
    if current_page < total_pages:
        options.append(f"{Colors.BOLD}{PaginationChoices.NEXT}{Colors.NC}) Next page")
    if current_page > 1:
        options.append(f"{Colors.BOLD}{PaginationChoices.PREV}{Colors.NC}) Previous page")
    options.append(f"{Colors.BOLD}{PaginationChoices.BACK}{Colors.NC}) Back")
    print("Options:  " + "  |  ".join(options) + "\n")


################################################################################
# DATABASE ENTITY SELECTION HELPERS
################################################################################


def select_zone(db: Any, prompt: str = "Select Zone ID") -> dict[str, Any] | None:
    """Present configured zones and return the user's selected zone dictionary.

    Args:
        db: ``Database`` instance.
        prompt: Selection prompt label.

    Returns:
        Selected zone dictionary or ``None`` if cancelled/empty.
    """
    zones = db.get_all_zones()
    if not zones:
        print_warning("No zones configured.")
        wait_for_enter()
        return None

    def _zone_display(zone: dict[str, Any]) -> str:
        """Format a single zone row for interactive selection."""
        status_str = (
            f"{LOG_SYMBOLS['SUCCESS']} Enabled"
            if zone["enabled"]
            else f"{LOG_SYMBOLS['ERROR']} Disabled"
        )
        color = Colors.GREEN if zone["enabled"] else Colors.DIM
        return f"{zone['zone_name']:<{CLIConfig.ZONE_NAME_WIDTH}} [{color}{status_str}{Colors.NC}]"

    selected = get_choice_from_list(zones, prompt=prompt, display_func=_zone_display)
    return row_to_dict(selected) if selected else None


def select_record(
    db: Any, zone_id: int, prompt: str = "Select Record ID"
) -> dict[str, Any] | None:
    """Present records belonging to ``zone_id`` and return the selected record.

    Args:
        db: ``Database`` instance.
        zone_id: Zone database ID.
        prompt: Selection prompt label.

    Returns:
        Selected record dictionary or ``None`` if cancelled/empty.
    """
    records = db.get_records_by_zone(zone_id, enabled_only=False)
    if not records:
        print_warning("No records configured for this zone.")
        wait_for_enter()
        return None

    def _record_display(rec: dict[str, Any]) -> str:
        """Format a single record row for interactive selection."""
        status_str = (
            f"{LOG_SYMBOLS['SUCCESS']} Enabled"
            if rec["enabled"]
            else f"{LOG_SYMBOLS['ERROR']} Disabled"
        )
        color = Colors.GREEN if rec["enabled"] else Colors.DIM
        return (
            f"{rec['record_name']:<{CLIConfig.RECORD_NAME_WIDTH}} "
            f"{rec['record_type']:<{CLIConfig.RECORD_TYPE_WIDTH}} "
            f"[{color}{status_str}{Colors.NC}]"
        )

    selected = get_choice_from_list(records, prompt=prompt, display_func=_record_display)
    return row_to_dict(selected) if selected else None


def get_zone_by_id_validated(db: Any, zone_id_input: str) -> dict[str, Any] | None:
    """Validate numeric ``zone_id_input`` and return the matching zone row.

    Args:
        db: ``Database`` instance.
        zone_id_input: Raw user string representing a zone ID.

    Returns:
        Zone dictionary if found, or ``None`` when invalid/missing.
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


__all__ = [
    "confirm_action",
    "get_choice_from_list",
    "get_placeholder_ip",
    "get_valid_int",
    "get_valid_string",
    "get_zone_by_id_validated",
    "is_valid_file_path",
    "print_paginated_list",
    "resolve_path",
    "safe_input",
    "select_record",
    "select_zone",
    "wait_for_enter",
]
