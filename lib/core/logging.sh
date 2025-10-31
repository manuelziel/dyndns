#!/bin/bash
# lib/core/logging.sh - Logging and output functions
#
# IONOS-DYNDNS Setup Script
# Setup script for Dynamic DNS Client
#
# Created: 2025-04-27
# Author: Manuel Ziel
# License: MIT
#
# This program is free software: you can redistribute it and/or modify

################################################################################
# 1. LOGGING & OUTPUT - Colored and formatted output functions
################################################################################

print_status() {
    local color="${1:-}"
    local message="${2:-}"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    
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

################################################################################
# 2. SHOW LOGS
################################################################################

show_recent_logs() {
    local software_name="${SOFTWARE_NAME:-"[SOFTWARE_NAME]"}"
    local syslog_identifier="${SYSLOG_IDENTIFIER:-"[SYSLOG_IDENTIFIER]"}"
    local version="${VERSION:-"[VERSION]"}"
    local description="${SOFTWARE_DESCRIPTION:-"[SOFTWARE_DESCRIPTION]"}"
    local service_name="${SERVICE_NAME:-"[SERVICE_NAME]"}"

    show_status

    if ! is_running; then
        print_warning "${software_name} is not running. No logs to show."
        echo ""
        read -rp "Press Enter to continue..."
        return 1
    fi
    
    if command -v journalctl &>/dev/null; then
        clear

        print_banner "Logs"
        print_section "Recent Logs"
        
        if is_systemd_service_active; then
            print_info "Showing recent logs for ${software_name} systemd service (last 20 lines)"
            journalctl -u "${service_name}" -n 20 --no-pager 2>/dev/null || {
                print_error "Cannot access systemd logs. Try running with sudo or check permissions."
                return 1
            }
        else
            # Try identifier-based logs (for daemon processes using systemd journal)
            # Use SYSLOG_IDENTIFIER as defined in config.sh
            print_info "Showing recent logs for ${software_name} (last 20 lines)"
            journalctl -t "${syslog_identifier}" -n 20 --no-pager 2>/dev/null || {
                print_error "Cannot access logs. Try running with sudo or check permissions."
                echo "Try: sudo journalctl -t ${syslog_identifier} -n 20"
                echo "Or: sudo journalctl -u ${service_name} -n 20"
                return 1
            }
        fi
        return 0
    else
        print_error "journalctl not available. Cannot show logs."
        return 1
    fi
}

show_live_logs() {
    local software_name="${SOFTWARE_NAME:-"[SOFTWARE_NAME]"}"
    local syslog_identifier="${SYSLOG_IDENTIFIER:-"[SYSLOG_IDENTIFIER]"}"
    local version="${VERSION:-"[VERSION]"}"
    local description="${SOFTWARE_DESCRIPTION:-"[SOFTWARE_DESCRIPTION]"}"
    local service_name="${SERVICE_NAME:-"[SERVICE_NAME]"}"

    if ! is_running; then
        print_warning "${software_name} is not running. No logs to show."
        echo ""
        read -rp "Press Enter to continue..."
        return 1
    fi

    if command -v journalctl &>/dev/null; then
        clear

        print_banner "Live Logs"
        print_section "Live Logs"
        print_info "Press Ctrl+C to exit"

        if is_systemd_service_active; then
            journalctl -u "${service_name}" -f --no-pager 2>/dev/null || {
                print_error "Cannot access systemd logs. Try running with sudo or check permissions."
                return 1
            }
        else
            # Try identifier-based logs (for daemon processes using systemd journal)
            # Use SYSLOG_IDENTIFIER as defined in config.sh
            journalctl -t "${syslog_identifier}" -f --no-pager 2>/dev/null || {
                print_error "Cannot access logs. Try running with sudo or check permissions."
                echo "Try: sudo journalctl -t ${syslog_identifier} -f"
                echo "Or: sudo journalctl -u ${service_name} -f"
                return 1
            }
        fi
        return 0
    else
        print_error "journalctl not available. Cannot show logs."
        return 1
    fi
}