#!/bin/bash
# dyndns.sh - Runtime launcher, daemon controller, and CLI dispatcher
#
# DynDNS
#
# Author: Manuel Ziel
# License: MIT

# Enable strict error handling
set -euo pipefail

# Ensure files created by this script (DB, config, state) are group-writable.
# 0002 = rw-rw-r-- / rwxrwxr-x.
umask 0002

_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly _DIR="${_script_dir}"
unset _script_dir

################################################################################
# BOOTSTRAP: Detect installation mode and locate libraries
################################################################################

_script_name="$(basename "${BASH_SOURCE[0]}")"
readonly SCRIPT_NAME="${_script_name}"
unset _script_name
readonly DERIVED_NAME="${SCRIPT_NAME%.sh}"  # Remove .sh extension

if [[ -f "${_DIR}/lib/core/config.sh" ]]; then
    source "${_DIR}/lib/core/config.sh"
    LIB_BASE_DIR="${_DIR}/lib"
else
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
    echo "  - ${_DIR}/lib (development mode)" >&2
    echo "  - /usr/local/share/${DERIVED_NAME}/lib (installed mode)" >&2
    echo "  - /usr/share/${DERIVED_NAME}/lib (alternative installed mode)" >&2
    exit 1
fi

# Load remaining core libraries (config.sh already loaded above)
source "${LIB_BASE_DIR}/core/colors.sh"
source "${LIB_BASE_DIR}/core/logging.sh"
source "${LIB_BASE_DIR}/core/essentials.sh"

# Load optional shared modules before runtime orchestrators
if [[ "${ENABLE_PYTHON:-0}" -eq 1 ]]; then
    source "${LIB_BASE_DIR}/modules/python.sh"
fi

# Load runtime-specific libraries (strict bottom-up DAG)
source "${LIB_BASE_DIR}/runtime/daemon.sh"
source "${LIB_BASE_DIR}/runtime/application.sh"
source "${LIB_BASE_DIR}/runtime/menu.sh"

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

_abort_invalid_cli() {
    show_help
    cleanup_and_exit 1
}

_parse_runtime_token() {
    case "$1" in
        start|stop|restart|setup-env) set_single_action "$1" "$1" || _abort_invalid_cli ;;
        status|--info)                set_single_action "status" "$1" || _abort_invalid_cli ;;
        help|--help|-h)               set_single_action "help" "$1" || _abort_invalid_cli ;;
        version|--version|-v)         set_single_action "version" "$1" || _abort_invalid_cli ;;
        --interactive|-i)             INTERACTIVE_MODE=1 ;;
        --daemon|-d)
            DAEMON_MODE=1
            declare -F init_colors >/dev/null 2>&1 && init_colors
            ;;
        --quiet|-q)                   QUIET_MODE=1 ;;
        --debug)                      DEBUG_MODE=1 ;;
        -*)                           print_error "Unknown option: $1"; _abort_invalid_cli ;;
        *)                            print_error "Unknown argument: $1"; _abort_invalid_cli ;;
    esac
    return 0
}

parse_arguments() {
    while [[ "$#" -gt 0 ]]; do
        case "$1" in
            config|import|export|validate)
                set_single_action "$1" "$1" || _abort_invalid_cli
                shift
                CLI_ARGS=("$@")
                break
                ;;
            --)
                shift
                PYTHON_ARGS=("$@")
                break
                ;;
            *)
                _parse_runtime_token "$1"
                shift
                ;;
        esac
    done
    if [[ -z "${ACTION:-}" ]]; then
        if [[ "${DAEMON_MODE}" -eq 1 && "${INTERACTIVE_MODE}" -eq 0 ]]; then
            ACTION="start"
        else
            ACTION="interactive"
        fi
    fi
}

_dispatch_runtime_action() {
    case "${ACTION}" in
        start)
            if [[ "${DAEMON_MODE}" -eq 1 ]]; then
                start_daemon "${PYTHON_ARGS[@]+"${PYTHON_ARGS[@]}"}"
            else
                start_application "${PYTHON_ARGS[@]+"${PYTHON_ARGS[@]}"}"
            fi
            ;;
        stop)                    stop_application ;;
        restart)                 restart_application "${PYTHON_ARGS[@]+"${PYTHON_ARGS[@]}"}" ;;
        setup-env)               setup_python_environment ;;
        config)                  configure_application "${CLI_ARGS[@]+"${CLI_ARGS[@]}"}" ;;
        import|export|validate)  start_python_cli "${ACTION}" "${CLI_ARGS[@]+"${CLI_ARGS[@]}"}" ;;
        status)                  show_status ;;
        help)                    show_help ;;
        version)                 show_version ;;
        interactive)             show_interactive_menu ;;
        *)
            print_error "Unknown action: ${ACTION}"
            _abort_invalid_cli
            ;;
    esac
}

main() {
    parse_arguments "$@"
    case "${ACTION}" in
        start|stop|restart|setup-env|config|import|export|validate|interactive)
            if ! check_runtime_user "$@"; then
                cleanup_and_exit 1
            fi
            ;;
    esac
    _dispatch_runtime_action
}

main "$@"
