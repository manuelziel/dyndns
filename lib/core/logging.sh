#!/bin/bash
# lib/core/logging.sh - Formatted status, banner, and stderr logging helpers
#
# DynDNS
#
# Author: Manuel Ziel
# License: MIT

set -euo pipefail

################################################################################
# LOGGING & OUTPUT - Colored and formatted output functions
################################################################################

if ! declare -F should_use_colors >/dev/null 2>&1; then
    should_use_colors() {
        [[ -t 1 && -z "${NO_COLOR:-}" && "${TERM:-}" != "dumb" && "${DAEMON_MODE:-0}" -ne 1 ]]
    }
fi

print_status() {
    local color="${1:-}"
    local message="${2:-}"
    local reset="${NC:-}"

    if [[ "$#" -eq 1 ]]; then
        message="${1}"
        color=""
    fi
    if ! should_use_colors; then
        color=""
        reset=""
    fi
    printf "%b%s%b\n" "${color}" "${message}" "${reset}"
}

print_success() {
    if [[ "${QUIET_MODE:-0}" -eq 1 ]]; then
        return 0
    fi
    print_status "${GREEN:-}" "✓ ${1:-}"
}

print_error() {
    print_status "${RED:-}" "✗ ${1:-}" >&2
}

print_warning() {
    if [[ "${QUIET_MODE:-0}" -eq 1 ]]; then
        return 0
    fi
    print_status "${YELLOW:-}" "✗ ${1:-}"
}

print_info() {
    if [[ "${QUIET_MODE:-0}" -eq 1 ]]; then
        return 0
    fi
    print_status "${BLUE:-}" "ℹ ${1:-}"
}

print_debug() {
    if [[ "${DEBUG_MODE:-0}" -eq 0 ]]; then
        return 0
    fi
    print_status "${PURPLE:-}" "  ${1:-}"
}

print_status_line() {
    local label="${1:-}"
    local color="${2:-}"
    local symbol="${3:-}"
    local message="${4:-}"
    local NC="${NC:-}"

    if ! should_use_colors; then
        color=""
        NC=""
    fi
    printf "  %-15s %b%s %s%b\n" "${label}:" "${color}" "${symbol}" "${message}" "${NC}"
}

print_section() {
    local title="$*"
    local BOLD="${BOLD:-}"
    local CYAN="${CYAN:-}"
    local NC="${NC:-}"

    if ! should_use_colors; then
        BOLD=""
        CYAN=""
        NC=""
    fi
    printf "\n%b═══ %s ═══%b\n\n" "${BOLD}${CYAN}" "${title}" "${NC}"
}

print_banner() {
    local software_name="${SOFTWARE_NAME:-"[SOFTWARE_NAME]"}"
    local mode="${1:-"[MODE]"}"
    local description="${SOFTWARE_DESCRIPTION:-"[SOFTWARE_DESCRIPTION]"}"
    local version="${VERSION:-"[VERSION]"}"
    local BOLD="${BOLD:-}" CYAN="${CYAN:-}" WHITE="${WHITE:-}" DIM="${DIM:-}" NC="${NC:-}"

    if ! should_use_colors; then
        BOLD=""
        CYAN=""
        WHITE=""
        DIM=""
        NC=""
    fi
    printf "\n%b═══════════════════════════════════════════════════════════════%b\n" "${BOLD}${CYAN}" "${NC}"
    printf "%b  %s %s%b\n" "${BOLD}${WHITE}" "${software_name}" "${mode}" "${NC}"
    printf "  %s\n" "${description}"
    printf "%b  Version: %s%b\n" "${DIM}" "${version}" "${NC}"
    printf "%b═══════════════════════════════════════════════════════════════%b\n\n" "${BOLD}${CYAN}" "${NC}"
}
