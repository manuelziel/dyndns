#!/usr/bin/env python3
"""CLI helper packages for input, output, and validation utilities.

This package exposes reusable functions for handling interactive CLI operations.

Author: Manuel Ziel
License: MIT
"""

################################################################################
# PACKAGE IMPORTS
################################################################################

from .validate import (
    is_valid_domain,
    is_valid_ipv4,
    is_valid_ipv6
)

from .output import (
    row_to_dict,
    print_status,
    print_success,
    print_error,
    print_warning,
    print_info,
    print_debug,
    print_status_line,
    print_section,
    print_subsection,
    print_banner,
    clear_screen,
    format_table,
    display_zone_details
)

from .input import (
    get_placeholder_ip,
    safe_input,
    wait_for_enter,
    confirm_action,
    get_valid_int,
    get_valid_string,
    get_choice_from_list,
    select_zone,
    select_record,
    get_zone_by_id_validated,
    resolve_path,
    is_valid_file_path
)

################################################################################
# PUBLIC API
################################################################################

__all__ = [
    # Input
    'get_placeholder_ip',
    'safe_input',
    'wait_for_enter',
    'confirm_action',
    'get_valid_int',
    'get_valid_string',
    'get_choice_from_list',
    'select_zone',
    'select_record',
    'get_zone_by_id_validated',
    'resolve_path',
    'is_valid_file_path',
    # Output
    'row_to_dict',
    'print_status',
    'print_success',
    'print_error',
    'print_warning',
    'print_info',
    'print_debug',
    'print_status_line',
    'print_section',
    'print_subsection',
    'print_banner',
    'clear_screen',
    'format_table',
    'display_zone_details',
    # Validate
    'is_valid_domain',
    'is_valid_ipv4',
    'is_valid_ipv6'
]
