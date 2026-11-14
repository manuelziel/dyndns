#!/usr/bin/env python3
"""CLI helper package for interactive input, TTY output, and validation.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# PACKAGE IMPORTS
################################################################################

from .validate import (
    is_valid_domain,
    is_valid_file_path,
    is_valid_ipv4,
    is_valid_ipv6,
    is_valid_path,
    resolve_path,
)
from .output import (
    clear_screen,
    display_zone_details,
    format_table,
    print_banner,
    print_debug,
    print_error,
    print_info,
    print_section,
    print_status,
    print_status_line,
    print_subsection,
    print_success,
    print_warning,
    row_to_dict,
)
from .input import (
    confirm_action,
    get_choice_from_list,
    get_placeholder_ip,
    get_valid_int,
    get_valid_string,
    get_zone_by_id_validated,
    print_paginated_list,
    safe_input,
    select_record,
    select_zone,
    wait_for_enter,
)

################################################################################
# PUBLIC API
################################################################################

__all__ = [
    # Input
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
    # Output
    "clear_screen",
    "display_zone_details",
    "format_table",
    "print_banner",
    "print_debug",
    "print_error",
    "print_info",
    "print_section",
    "print_status",
    "print_status_line",
    "print_subsection",
    "print_success",
    "print_warning",
    "row_to_dict",
    # Validate
    "is_valid_domain",
    "is_valid_ipv4",
    "is_valid_ipv6",
    "is_valid_path",
]
