#!/usr/bin/env python3
"""CLI output helpers for TTY-aware terminal formatting and table display.

Respects ``NO_COLOR`` and non-TTY streams, routes error messages to ``stderr``,
clears interactive screens via ANSI escape sequences without spawning shell
subprocesses, and redacts sensitive URIs before printing.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# IMPORTS & DEPENDENCIES
################################################################################

import json
import os
import sys
from typing import Any, TextIO

from ...core.security import sanitize_log_uri
from ...utils.colors import Colors, LOG_SYMBOLS
from ..constants import CLIConfig, StatusSymbols

################################################################################
# STREAM & COLOR HELPERS
################################################################################


def _use_color(stream: TextIO) -> bool:
    """Return True when ANSI colors should be emitted on ``stream``.

    Args:
        stream: Target output stream (``sys.stdout`` or ``sys.stderr``).

    Returns:
        True when ``NO_COLOR``/``DAEMON_MODE``/``TERM=dumb`` are inactive and TTY.
    """
    if (
        os.environ.get("NO_COLOR")
        or os.environ.get("DAEMON_MODE") == "1"
        or os.environ.get("TERM") == "dumb"
    ):
        return False
    isatty_fn = getattr(stream, "isatty", None)
    return bool(callable(isatty_fn) and isatty_fn())


def row_to_dict(row: Any) -> dict[str, Any] | None:
    """Convert a ``sqlite3.Row`` or mapping object into a plain dictionary.

    Args:
        row: Database row or dictionary, or ``None``.

    Returns:
        Plain dictionary copy or ``None``.
    """
    if row is None:
        return None
    return dict(row)


################################################################################
# STATUS & SECTION OUTPUT FUNCTIONS
################################################################################


def print_status(
    message: str,
    color: str = Colors.NC,
    stream: TextIO | None = None,
) -> None:
    """Write a status message to ``stream`` with optional TTY ANSI color.

    Args:
        message: Text message to print.
        color: ANSI color escape prefix.
        stream: Output stream (defaults to ``sys.stdout``).
    """
    target = stream if stream is not None else sys.stdout
    if _use_color(target) and color:
        print(f"{color}{message}{Colors.NC}", file=target)
    else:
        print(message, file=target)


def print_success(message: str) -> None:
    """Print a green success message with symbol to ``stdout``.

    Args:
        message: Success message text.
    """
    print_status(f"{StatusSymbols.SUCCESS} {message}", Colors.GREEN)


def print_error(message: str) -> None:
    """Print a red error message with symbol to ``stderr``.

    Args:
        message: Error message text.
    """
    print_status(f"{StatusSymbols.ERROR} {message}", Colors.RED, stream=sys.stderr)


def print_warning(message: str) -> None:
    """Print a yellow warning message with symbol to ``stdout``.

    Args:
        message: Warning message text.
    """
    print_status(f"{StatusSymbols.WARNING} {message}", Colors.YELLOW)


def print_info(message: str) -> None:
    """Print a blue informational message with symbol to ``stdout``.

    Args:
        message: Informational message text.
    """
    print_status(f"{StatusSymbols.INFO} {message}", Colors.BLUE)


def print_debug(message: str) -> None:
    """Print an indented purple debug message to ``stdout``.

    Args:
        message: Debug message text.
    """
    print_status(f"  {message}", Colors.PURPLE)


def print_status_line(label: str, color: str, symbol: str, message: str) -> None:
    """Print an aligned status key-value line.

    Args:
        label: Left-aligned label string.
        color: ANSI color escape code.
        symbol: Status symbol glyph.
        message: Status description text.
    """
    if _use_color(sys.stdout):
        print(f"  {label:<{CLIConfig.LABEL_WIDTH}} {color}{symbol} {message}{Colors.NC}")
    else:
        print(f"  {label:<{CLIConfig.LABEL_WIDTH}} {symbol} {message}")


def print_section(title: str) -> None:
    """Print a primary section heading.

    Args:
        title: Section title text.
    """
    print()
    if _use_color(sys.stdout):
        print(f"{Colors.BOLD}{Colors.CYAN}=== {title} ==={Colors.NC}")
    else:
        print(f"=== {title} ===")
    print()


def print_subsection(title: str) -> None:
    """Print a secondary subsection heading.

    Args:
        title: Subsection title text.
    """
    print()
    if _use_color(sys.stdout):
        print(f"{Colors.CYAN}--- {title} ---{Colors.NC}")
    else:
        print(f"--- {title} ---")


def print_banner(
    software_name: str, mode: str, description: str, version: str
) -> None:
    """Print the decorative application banner.

    Args:
        software_name: Application display name.
        mode: Operating mode label.
        description: Short description line.
        version: Application SemVer string.
    """
    border = "=" * CLIConfig.BANNER_WIDTH
    print()
    print_status(border, f"{Colors.BOLD}{Colors.CYAN}")
    print_status(f"  {software_name} {mode}", f"{Colors.BOLD}{Colors.WHITE}")
    print(f"  {description}")
    print_status(f"  Version: {version}", Colors.DIM)
    print_status(border, f"{Colors.BOLD}{Colors.CYAN}")
    print()


def clear_screen() -> None:
    """Clear an interactive TTY screen via ANSI escapes without shell calls."""
    if _use_color(sys.stdout):
        sys.stdout.write(CLIConfig.ANSI_CLEAR_SCREEN)
        sys.stdout.flush()


################################################################################
# TABLE & ENTITY FORMATTING
################################################################################


def format_table(
    headers: list[str],
    rows: list[list[Any]],
    widths: list[int] | None = None,
) -> str:
    """Format tabular data as an aligned plain-text ASCII table.

    Args:
        headers: Column header labels.
        rows: Two-dimensional list of cell values.
        widths: Optional explicit column widths.

    Returns:
        Multi-line formatted ASCII table string.
    """
    col_widths = list(widths) if widths else [len(str(h)) for h in headers]
    if not widths:
        for row in rows:
            for idx, cell in enumerate(row):
                col_widths[idx] = max(col_widths[idx], len(str(cell)))
    header_line = "  ".join(f"{str(h):<{w}}" for h, w in zip(headers, col_widths))
    separator = "  ".join("-" * w for w in col_widths)
    row_lines = [
        "  ".join(f"{str(c):<{w}}" for c, w in zip(row, col_widths)) for row in rows
    ]
    return "\n".join([header_line, separator, *row_lines])


def display_zone_details(zone: dict[str, Any], db: Any) -> None:
    """Display summary details for a zone with masked credentials and URIs.

    Args:
        zone: Zone dictionary from SQLite.
        db: ``Database`` instance for querying related records/configs.
    """
    status = (
        f"{LOG_SYMBOLS['SUCCESS']} Enabled"
        if zone["enabled"]
        else f"{LOG_SYMBOLS['ERROR']} Disabled"
    )
    print(f"\nZone: {zone['zone_name']:<{CLIConfig.ZONE_NAME_WIDTH}} [{status}]")
    print(f"  Zone ID: {zone.get('provider_zone_id') or 'N/A'}")
    dyndns_row = db.get_dyndns_config_by_zone(zone["id"])
    if dyndns_row:
        _print_masked_dyndns_summary(dict(dyndns_row))
    records = db.get_records_by_zone(zone["id"])
    print(f"  Records: {len(records)} configured")


def _print_masked_dyndns_summary(dyndns: dict[str, Any]) -> None:
    """Print masked DynDNS credential and domain metadata for ``display_zone_details``.

    Args:
        dyndns: Decrypted ``dyndns_config`` dictionary.
    """
    print(f"  Bulk ID: {dyndns.get('bulk_id') or 'N/A'}")
    print(f"  API Key: {'*' * CLIConfig.MASK_LENGTH} (encrypted)")
    if dyndns.get("domains"):
        try:
            raw = dyndns["domains"]
            domains = json.loads(raw) if isinstance(raw, str) else raw
            if domains:
                print(f"  Domains: {', '.join(domains)}")
        except (json.JSONDecodeError, ValueError, TypeError):
            pass
    if dyndns.get("update_url"):
        print(f"  Update URL: {sanitize_log_uri(str(dyndns['update_url']))}")
