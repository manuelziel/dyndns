#!/bin/bash
# lib/core/logging.sh - Logging and output functions
#
# DynDNS
#
# Author: Manuel Ziel
# License: MIT
#
# This program is free software: you can redistribute it and/or modify

################################################################################
# LOGGING & OUTPUT - Colored and formatted output functions
################################################################################

print_status() {
    local color="${1:-}"
    local message="${2:-}"

    echo -e "${color} ${message}${NC}"
}

print_success() {
    [[ ${QUIET_MODE:-0} -eq 1 ]] && return 0
    print_status "${GREEN}✓ ${1} ${NC}"
}

print_error() {
    print_status "${RED}✗ ${1} ${NC}" >&2
}

print_warning() {
    [[ ${QUIET_MODE:-0} -eq 1 ]] && return 0
    print_status "${YELLOW}✗ ${1} ${NC}"
}

print_info() {
    [[ ${QUIET_MODE:-0} -eq 1 ]] && return 0
    print_status "${BLUE}ℹ ${1} ${NC}"
}

print_debug() {
    [[ ${DEBUG_MODE:-0} -eq 0 ]] && return 0
    print_status "${PURPLE} ${1} ${NC}"
}

print_status_line() {
    local label="$1"
    local color="$2" 
    local symbol="$3"
    local message="$4"

    printf "  %-15s ${color}${symbol} ${message}${NC}\n" "${label}:"
}

print_section() {
    local title="$1"

    echo ""
    echo -e "${BOLD}${CYAN}═══ ${title} ═══${NC}"
    echo ""
}

print_banner() {
    local software_name="${SOFTWARE_NAME:-[SOFTWARE_NAME]}"
    local mode="${1:-[MODE]}"
    local description="${SOFTWARE_DESCRIPTION:-[SOFTWARE_DESCRIPTION]}"
    local version="${VERSION:-[VERSION]}"

    echo ""
    echo -e "${BOLD}${CYAN}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}${WHITE}  ${software_name} ${mode}${NC}"
    echo -e "  ${description}"
    echo -e "${DIM}  Version: ${version}${NC}"
    echo -e "${BOLD}${CYAN}═══════════════════════════════════════════════════════════════${NC}"
    echo ""
}
