#!/bin/bash
# setup.sh - Interactive and CLI setup, update, uninstall, and purge orchestrator
#
# DynDNS
#
# Author: Manuel Ziel
# License: MIT

# Enable strict error handling
set -euo pipefail

_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly _DIR="${_script_dir}"
readonly SETUP_CONTEXT=1
unset _script_dir

# Load core libraries (shared between setup.sh and dyndns.sh)
source "${_DIR}/lib/core/config.sh"
source "${_DIR}/lib/core/colors.sh"
source "${_DIR}/lib/core/logging.sh"
source "${_DIR}/lib/core/essentials.sh"

# Load optional shared modules before top-level setup orchestrators
if [[ "${ENABLE_PYTHON:-0}" -eq 1 ]]; then
    source "${_DIR}/lib/modules/python.sh"
fi

# Load setup-specific libraries (strict bottom-up DAG)
source "${_DIR}/lib/setup/system.sh"
source "${_DIR}/lib/setup/users.sh"
source "${_DIR}/lib/setup/files.sh"
source "${_DIR}/lib/setup/systemd.sh"
source "${_DIR}/lib/setup/install.sh"
source "${_DIR}/lib/setup/menu.sh"

# Global flags
QUIET_MODE=0
FORCE_MODE=0
SKIP_DEPENDENCIES=0
PURGE_MODE=0
INTERACTIVE_MODE=0
DEBUG_MODE=0
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

_abort_invalid_cli() {
    show_help
    cleanup_and_exit 1
}

_parse_setup_option() {
    case "$1" in
        install)                set_single_action "install" "$1" || _abort_invalid_cli ;;
        update|--upgrade)       set_single_action "update" "$1" || _abort_invalid_cli ;;
        reinstall|--reinstall)  set_single_action "reinstall" "$1" || _abort_invalid_cli ;;
        uninstall|--remove)     set_single_action "uninstall" "$1" || _abort_invalid_cli ;;
        purge)                  set_single_action "purge" "$1" || _abort_invalid_cli ;;
        status|--info)          set_single_action "status" "$1" || _abort_invalid_cli ;;
        help|--help|-h)         set_single_action "help" "$1" || _abort_invalid_cli ;;
        version|--version|-v)   set_single_action "version" "$1" || _abort_invalid_cli ;;
        --interactive|-i)       INTERACTIVE_MODE=1 ;;
        --quiet|-q)             QUIET_MODE=1 ;;
        --force|-f)             FORCE_MODE=1 ;;
        --no-deps)              SKIP_DEPENDENCIES=1 ;;
        --debug)                DEBUG_MODE=1 ;;
        --purge)                PURGE_MODE=1 ;;
        -*)                     print_error "Unknown option: $1"; _abort_invalid_cli ;;
        *)                      print_error "Unknown argument: $1"; _abort_invalid_cli ;;
    esac
    return 0
}

parse_arguments() {
    while [[ "$#" -gt 0 ]]; do
        _parse_setup_option "$1"
        shift
    done
    if [[ -z "${ACTION:-}" ]]; then
        if [[ "${PURGE_MODE}" -eq 1 ]]; then
            ACTION="purge"
        else
            ACTION="interactive"
        fi
    fi
}

_dispatch_setup_action() {
    case "${ACTION}" in
        install)     do_install ;;
        update)      do_update ;;
        reinstall)   do_reinstall ;;
        uninstall)
            if [[ "${PURGE_MODE}" -eq 1 ]]; then
                do_purge
            else
                do_uninstall
            fi
            ;;
        purge)       do_purge ;;
        status)      show_status ;;
        help)        show_help ;;
        version)     show_version ;;
        interactive) show_interactive_menu ;;
        *)
            print_error "Unknown action: ${ACTION}"
            _abort_invalid_cli
            ;;
    esac
}

main() {
    parse_arguments "$@"
    case "${ACTION}" in
        install|update|reinstall|uninstall|purge|interactive)
            if ! check_root "$@"; then
                cleanup_and_exit 1
            fi
            ;;
    esac
    _dispatch_setup_action
    successful_exit 0
}

main "$@"
