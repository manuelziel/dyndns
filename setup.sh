#!/bin/bash
#
# IONOS-DYNDNS Setup Script
# Setup script for Dynamic DNS Client
#
# Created: 2025-04-27
# Author: Manuel Ziel
# License: MIT
#
# This program is free software: you can redistribute it and/or modify

# Enable strict error handling
set -euo pipefail

readonly _DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load core libraries (shared between setup.sh and start.sh)
source "${_DIR}/lib/core/colors.sh"
source "${_DIR}/lib/core/logging.sh"
source "${_DIR}/lib/core/config.sh"
source "${_DIR}/lib/core/essentials.sh"

# Load setup-specific libraries
source "${_DIR}/lib/setup/system.sh"
source "${_DIR}/lib/setup/install.sh"
source "${_DIR}/lib/setup/menu.sh"

# Load optional modules based on configuration
if [[ "${ENABLE_PYTHON:-0}" -eq 1 ]]; then
    source "${_DIR}/lib/modules/python.sh"
fi

# Global flags
QUIET_MODE=0
FORCE_MODE=0
SKIP_DEPENDENCIES=0
ACTION=""

################################################################################
# MAIN SCRIPT LOGIC
################################################################################

successful_exit() {
    local exit_code="${1:-0}"
    exit "${exit_code}"
}

cleanup_and_exit() {
    local exit_code="${1:-1}"
    exit "${exit_code}"
}

parse_arguments() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            # Actions with normalization
            install)
                if [[ -z "${ACTION:-}" ]]; then
                    ACTION="install"
                    shift
                else
                    print_error "Multiple actions specified: $ACTION and $1"
                    show_help
                    cleanup_and_exit 1
                fi
                ;;
            update|--upgrade)
                if [[ -z "${ACTION:-}" ]]; then
                    ACTION="update"
                    shift
                else
                    print_error "Multiple actions specified: $ACTION and $1"
                    show_help
                    cleanup_and_exit 1
                fi
                ;;
            reinstall|--reinstall)
                if [[ -z "${ACTION:-}" ]]; then
                    ACTION="reinstall"
                    shift
                else
                    print_error "Multiple actions specified: $ACTION and $1"
                    show_help
                    cleanup_and_exit 1
                fi
                ;;
            uninstall|--remove)
                if [[ -z "${ACTION:-}" ]]; then
                    ACTION="uninstall"
                    shift
                else
                    print_error "Multiple actions specified: $ACTION and $1"
                    show_help
                    cleanup_and_exit 1
                fi
                ;;
            status|--info)
                if [[ -z "${ACTION:-}" ]]; then
                    ACTION="status"
                    shift
                else
                    print_error "Multiple actions specified: $ACTION and $1"
                    show_help
                    cleanup_and_exit 1
                fi
                ;;
            help|-h)
                if [[ -z "${ACTION:-}" ]]; then
                    ACTION="help"
                    shift
                else
                    print_error "Multiple actions specified: $ACTION and $1"
                    show_help
                    cleanup_and_exit 1
                fi
                ;;
            version|--version|-v)
                if [[ -z "${ACTION:-}" ]]; then
                    ACTION="version"
                    shift
                else
                    print_error "Multiple actions specified: $ACTION and $1"
                    show_help
                    cleanup_and_exit 1
                fi
                ;;
            --interactive|-i)
                ACTION="interactive"
                shift
                ;;
                
            # Flags
            --quiet|-q)
                QUIET_MODE=1
                shift
                ;;
            --force|-f)
                FORCE_MODE=1
                shift
                ;;
            --no-deps)
                SKIP_DEPENDENCIES=1
                shift
                ;;
            --debug)
                DEBUG_MODE=1
                shift
                ;;
                
            # Error handling
            -*)
                print_error "Unknown option: $1"
                show_help
                cleanup_and_exit 1
                ;;
            *)
                print_error "Unknown argument: $1"
                show_help
                cleanup_and_exit 1
                ;;
        esac
    done
    
    # Default to interactive if no action specified
    if [[ -z "${ACTION:-}" ]]; then
        ACTION="interactive"
    fi
}

main() {
    parse_arguments "$@"
    
    local requires_root=false
    case "$ACTION" in
        install|update|reinstall|uninstall)
            requires_root=true
            ;;
        interactive)
            requires_root=true
            ;;
    esac
    
    if [[ "$requires_root" == true ]]; then
        if ! check_root; then
            cleanup_and_exit 1
        fi
    fi
    
    # Execute based on action
    case "${ACTION}" in
        install)
            do_install
            ;;
        update)
            do_update
            ;;
        reinstall)
            do_reinstall
            ;;
        uninstall)
            do_uninstall
            ;;
        status)
            show_status
            ;;
        help)
            show_help
            ;;
        version)
            show_version
            ;;
        interactive)
            show_interactive_menu
            ;;
        *)
            print_error "Unknown action: ${ACTION}"
            show_help
            cleanup_and_exit 1
            ;;
    esac
}

main "$@"