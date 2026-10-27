#!/bin/bash
# dyndns.sh
#
# DynDNS
#
# Author: Manuel Ziel
# License: MIT

# Enable strict error handling
set -euo pipefail

# Ensure files created by this script (DB, config, logs) are group-writable.
# The service may run as SERVICE_USER:SERVICE_GROUP; a root-invoked menu
# action must not leave behind mode-0644 files that lock out the service
# user. 0002 = rw-rw-r-- / rwxrwxr-x.
umask 0002

readonly _DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

################################################################################
# BOOTSTRAP: Detect installation mode and locate libraries
################################################################################

readonly SCRIPT_NAME="$(basename "${BASH_SOURCE[0]}")"
readonly DERIVED_NAME="${SCRIPT_NAME%.sh}"

if [[ -f "$_DIR/lib/core/config.sh" ]]; then
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

if [[ -z "${LIB_BASE_DIR:-}" ]]; then
    echo "ERROR: No library directory found!" >&2
    echo "Script: ${SCRIPT_NAME} (derived name: ${DERIVED_NAME})" >&2
    echo "Searched locations:" >&2
    echo "  - $_DIR/lib (development mode)" >&2
    echo "  - /usr/local/share/${DERIVED_NAME}/lib (installed mode)" >&2
    echo "  - /usr/share/${DERIVED_NAME}/lib (alternative installed mode)" >&2
    exit 1
fi

# Load remaining core libraries (config.sh already loaded)
source "$LIB_BASE_DIR/core/colors.sh"
source "$LIB_BASE_DIR/core/logging.sh"  
source "$LIB_BASE_DIR/core/essentials.sh"

# Load runtime-specific libraries
source "$LIB_BASE_DIR/runtime/daemon.sh"
source "$LIB_BASE_DIR/runtime/menu.sh"
source "$LIB_BASE_DIR/runtime/application.sh"

# Load optional modules based on configuration
if [[ "${ENABLE_PYTHON:-0}" -eq 1 ]]; then
    source "$LIB_BASE_DIR/modules/python.sh"
fi

# Global flags
QUIET_MODE=0
DAEMON_MODE=0
INTERACTIVE_MODE=0
DEBUG_MODE=0
ACTION=""
CLI_ARGS=()
PYTHON_ARGS=()

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
            start|stop|restart)
                if [[ -z "${ACTION:-}" ]]; then
                    ACTION="$1"
                    shift
                else
                    print_error "Multiple actions specified: $ACTION and $1"
                    show_help
                    cleanup_and_exit 1
                fi
                ;;
            setup-env|config)
                if [[ -z "${ACTION:-}" ]]; then
                    ACTION="$1"
                    shift
                else
                    print_error "Multiple actions specified: $ACTION and $1"
                    show_help
                    cleanup_and_exit 1
                fi
                ;;
            # CLI commands — pass remaining args to Python CLI
            import|export)
                if [[ -z "${ACTION:-}" ]]; then
                    ACTION="$1"
                    shift
                    CLI_ARGS=("$@")
                    break
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
            help|--help|-h)
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
            --debug)
                DEBUG_MODE=1
                shift
                ;;
            --)
                shift
                PYTHON_ARGS=("$@")
                break
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
        if [[ "$DAEMON_MODE" -eq 1 ]]; then
            ACTION="start"
        else
            ACTION="interactive"
        fi
    fi
}

main() {
    parse_arguments "$@"
    local requires_root=false

    case "$ACTION" in
        start|stop|restart|setup-env)
            requires_root=true
            ;;
        config|import|export)
            requires_root=true
            ;;
        interactive)
            requires_root=true
            ;;
    esac
    
    if [[ "$requires_root" == true ]]; then
        if ! check_runtime_user; then
            cleanup_and_exit 1
        fi
    fi

    case "$ACTION" in
        start)
            if [[ "$DAEMON_MODE" -eq 1 ]]; then
                start_daemon "${PYTHON_ARGS[@]}"
            else
                start_application "${PYTHON_ARGS[@]}"
            fi
            ;;
        stop)
            stop_application
            ;;
        restart)
            restart_application "${PYTHON_ARGS[@]}"
            ;;
        setup-env)
            setup_python_environment
            ;;
        config)
            configure_application
            ;;
        import|export)
            start_python_cli "${ACTION}" "${CLI_ARGS[@]}"
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

    successful_exit 0
}

main "$@"