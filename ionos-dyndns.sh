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

################################################################################
# BOOTSTRAP: Detect installation mode and locate libraries
################################################################################

# Bootstrap: Minimal config to find library location
# Strategy: Derive software name from script name (e.g., "ionos-dyndns.sh" -> "ionos-dyndns")
readonly SCRIPT_NAME="$(basename "${BASH_SOURCE[0]}")"
readonly DERIVED_NAME="${SCRIPT_NAME%.sh}"  # Remove .sh extension

if [[ -f "$_DIR/lib/core/config.sh" ]]; then
    # Development/local mode - load config to get SOFTWARE_DIR_NAME
    source "$_DIR/lib/core/config.sh"
    LIB_BASE_DIR="$_DIR/lib"
else
    # Installed mode - use derived name to find installation
    for share_base in "/usr/local/share" "/usr/share"; do
        potential_dir="${share_base}/${DERIVED_NAME}"
        if [[ -f "${potential_dir}/lib/core/config.sh" ]]; then
            source "${potential_dir}/lib/core/config.sh"
            LIB_BASE_DIR="${potential_dir}/lib"
            break
        fi
    done
fi

# Error if no library directory found
if [[ -z "${LIB_BASE_DIR:-}" ]]; then
    echo "ERROR: No library directory found!" >&2
    echo "Script: ${SCRIPT_NAME} (derived name: ${DERIVED_NAME})" >&2
    echo "Searched locations:" >&2
    echo "  - $_DIR/lib (development mode)" >&2
    echo "  - /usr/local/share/${DERIVED_NAME}/lib (installed mode)" >&2
    echo "  - /usr/share/${DERIVED_NAME}/lib (alternative installed mode)" >&2
    exit 1
fi

# Load remaining core libraries (config.sh already loaded above)
source "$LIB_BASE_DIR/core/colors.sh"
source "$LIB_BASE_DIR/core/logging.sh"  
source "$LIB_BASE_DIR/core/essentials.sh"

# Load runtime-specific libraries
source "$LIB_BASE_DIR/runtime/daemon.sh"
source "$LIB_BASE_DIR/runtime/menu.sh"
source "$LIB_BASE_DIR/runtime/application.sh"

# Load optional modules based on configuration
if [[ ${ENABLE_PYTHON:-0} -eq 1 ]]; then
    source "$LIB_BASE_DIR/modules/python.sh"
fi

# Global flags
QUIET_MODE=0
DAEMON_MODE=0
INTERACTIVE_MODE=0
ACTION=""
CLI_ARGS=()  # Array to store CLI command arguments

################################################################################
# MAIN SCRIPT LOGIC
################################################################################

# Function to exit successfully
successful_exit() {
    local exit_code="${1:-0}"
    exit "${exit_code}"
}

# Function to cleanup and exit with error code
cleanup_and_exit() {
    local exit_code="${1:-1}"
    exit "${exit_code}"
}

# Function to parse command line arguments
parse_arguments() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            # Actions with normalization
            start)
                if [[ -z "${ACTION:-}" ]]; then
                    ACTION="$1"
                    shift
                else
                    print_error "Multiple actions specified: $ACTION and $1"
                    show_help
                    cleanup_and_exit 1
                fi
                ;;
            stop)
                if [[ -z "${ACTION:-}" ]]; then
                    ACTION="$1"
                    shift
                else
                    print_error "Multiple actions specified: $ACTION and $1"
                    show_help
                    cleanup_and_exit 1
                fi
                ;;
            restart)
                if [[ -z "${ACTION:-}" ]]; then
                    ACTION="$1"
                    shift
                else
                    print_error "Multiple actions specified: $ACTION and $1"
                    show_help
                    cleanup_and_exit 1
                fi
                ;;
            recent-logs)
                if [[ -z "${ACTION:-}" ]]; then
                    ACTION="$1"
                    shift
                else
                    print_error "Multiple actions specified: $ACTION and $1"
                    show_help
                    cleanup_and_exit 1
                fi
                ;;
            live-logs)
                if [[ -z "${ACTION:-}" ]]; then
                    ACTION="$1"
                    shift
                else
                    print_error "Multiple actions specified: $ACTION and $1"
                    show_help
                    cleanup_and_exit 1
                fi
                ;;
            setup-env)
                if [[ -z "${ACTION:-}" ]]; then
                    ACTION="$1"
                    shift
                else
                    print_error "Multiple actions specified: $ACTION and $1"
                    show_help
                    cleanup_and_exit 1
                fi
                ;;
            install-deps)
                if [[ -z "${ACTION:-}" ]]; then
                    ACTION="$1"
                    shift
                else
                    print_error "Multiple actions specified: $ACTION and $1"
                    show_help
                    cleanup_and_exit 1
                fi
                ;;
            config)
                if [[ -z "${ACTION:-}" ]]; then
                    ACTION="$1"
                    shift
                else
                    print_error "Multiple actions specified: $ACTION and $1"
                    show_help
                    cleanup_and_exit 1
                fi
                ;;
            import)
                if [[ -z "${ACTION:-}" ]]; then
                    ACTION="$1"
                    shift
                    # Store remaining args for Python CLI
                    CLI_ARGS=("$@")
                    break  # Stop parsing, pass rest to Python
                else
                    print_error "Multiple actions specified: $ACTION and $1"
                    show_help
                    cleanup_and_exit 1
                fi
                ;;
            export)
                if [[ -z "${ACTION:-}" ]]; then
                    ACTION="$1"
                    shift
                    # Store remaining args for Python CLI
                    CLI_ARGS=("$@")
                    break  # Stop parsing, pass rest to Python
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
            --daemon|-d)
                DAEMON_MODE=1
                shift
                ;;
            --quiet|-q)
                QUIET_MODE=1
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
    
    # Handle default action based on flags
    if [[ -z "${ACTION:-}" ]]; then
        if [[ $DAEMON_MODE -eq 1 ]]; then
            # --daemon without action defaults to 'start --daemon'
            ACTION="start"
        else
            # No action or flags defaults to interactive
            ACTION="interactive"
        fi
    fi
}

# Main function
main() {
    # Parse all arguments first
    parse_arguments "$@"
    
    # Define actions that require root privileges
    local requires_root=false
    case "$ACTION" in
        start|stop|restart|setup-env|install-deps)
            requires_root=true
            ;;
        config|import|export)
            # CLI commands don't require root - operate on user's database
            requires_root=true
            ;;
        interactive)
            # Interactive mode requires root for most operations
            requires_root=true
            ;;
    esac
    
    # Check for root privileges if required
    if [[ "$requires_root" == true ]]; then
        if ! check_root; then
            cleanup_and_exit 1
        fi
    fi
    
    # Execute based on action
    case "$ACTION" in
        start)
            if [[ $DAEMON_MODE -eq 1 ]]; then
                start_daemon
            else
                start_application
            fi
            ;;
        stop)
            stop_application
            ;;
        restart)
            restart_application
            ;;
        recent-logs)
            show_recent_logs
            ;;
        live-logs)
            show_live_logs
            ;;
        setup-env)
            setup_python_environment
            ;;
        install-deps)
            install_python_dependencies
            ;;
        config)
            configure_application
            ;;
        import)
            # Pass to Python CLI with all remaining arguments
            start_python_cli "import" "${CLI_ARGS[@]}"
            ;;
        export)
            # Pass to Python CLI with all remaining arguments
            start_python_cli "export" "${CLI_ARGS[@]}"
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
            print_error "Unknown action: $ACTION"
            show_help
            cleanup_and_exit 1
            ;;
    esac
}

# Run main function with all arguments
main "$@"