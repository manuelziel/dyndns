#!/bin/bash
# lib/runtime/menu.sh - Interactive runtime TUI menu, help, and status views
#
# DynDNS
#
# Author: Manuel Ziel
# License: MIT

set -euo pipefail

################################################################################
# INTERACTIVE MENU
################################################################################

_append_runtime_menu_item() {
    local label="$1"
    local action_key="$2"
    local option_num=$(( ${#MENU_OPTIONS[@]} + 1 ))
    MENU_OPTIONS+=("${option_num}) ${label}")
    MENU_ACTIONS+=("${action_key}")
}

_build_runtime_menu_options() {
    MENU_OPTIONS=()
    MENU_ACTIONS=()
    _append_runtime_menu_item "Status" "show_status"
    _append_runtime_menu_item "Configure" "configure_application"
    _append_runtime_menu_item "Start" "start_application"
    _append_runtime_menu_item "Stop" "stop_application"
    _append_runtime_menu_item "Restart" "restart_application"
    _append_runtime_menu_item "Help" "help"
    _append_runtime_menu_item "Rebuild Virtual Environment" "rebuild_python_environment"
    MENU_MAX_CHOICE="${#MENU_OPTIONS[@]}"
    MENU_OPTIONS+=("0) Exit")
    MENU_ACTIONS+=("exit")
}

_dispatch_runtime_menu_action() {
    local action="$1"

    case "${action}" in
        "start_application")        DAEMON_MODE=1 start_application || true ;;
        "stop_application")         stop_application || true ;;
        "restart_application")      DAEMON_MODE=1 restart_application || true ;;
        "configure_application")    configure_application || true ;;
        "show_status")              show_status || true ;;
        "help")                     show_help || true ;;
        "rebuild_python_environment")
            if [[ "${ENABLE_PYTHON:-0}" -eq 1 ]]; then
                rebuild_python_environment || true
            else
                print_warning "Python support is not enabled in the config."
            fi
            ;;
        "exit")                     print_info "Exiting interactive menu."; return 2 ;;
        *)                          print_error "Invalid action: ${action}" ;;
    esac
    return 0
}

_render_runtime_menu_screen() {
    [[ -t 1 ]] && clear 2>/dev/null || true
    print_banner "Runtime"
    show_status || true
    _build_runtime_menu_options
    echo ""
    print_status "${BLUE:-}" "Available options:"
    printf '  %s\n' "${MENU_OPTIONS[@]}"
    echo ""
}

show_interactive_menu() {
    local choice="" MENU_SELECTED_ACTION="" rc=0
    local -a MENU_OPTIONS=() MENU_ACTIONS=()
    local MENU_MAX_CHOICE=0

    while true; do
        _render_runtime_menu_screen
        if ! read -rp "Enter your choice (0-${MENU_MAX_CHOICE}): " choice; then
            echo ""
            print_info "Input closed (EOF). Exiting interactive menu."
            return 0
        fi
        echo ""
        resolve_menu_choice "${choice}"
        if [[ "${MENU_SELECTED_ACTION}" != "invalid" ]]; then
            rc=0
            _dispatch_runtime_menu_action "${MENU_SELECTED_ACTION}" || rc=$?
            [[ "${rc}" -eq 2 ]] && return 0
        else
            print_error "Invalid selection. Enter a number between 0 and ${MENU_MAX_CHOICE}."
        fi
        if [[ "${MENU_SELECTED_ACTION}" != "configure_application" ]]; then
            echo ""
            read -rp "Press Enter to continue..." || { echo ""; return 0; }
        fi
    done
}

################################################################################
# HELP AND STATUS
################################################################################

show_help() {
    local software_name="${SOFTWARE_NAME:-"[SOFTWARE_NAME]"}" version="${VERSION:-"[VERSION]"}"
    local cmd_name="${SOFTWARE_DIR_NAME:-"[SOFTWARE_DIR_NAME]"}" service_name="${SERVICE_NAME:-"[SERVICE_NAME]"}"
    print_section "${software_name} v${version}"
    cat <<EOF
Usage: ${cmd_name} [ACTION] [OPTIONS]

Actions:
  start                            Start ${software_name}
  stop                             Stop ${software_name}
  restart                          Restart ${software_name}
  setup-env                        Setup Python virtual environment
  config                           Configure ${software_name}
  validate [--file <path>]         Validate configuration syntax
  import <file>                    Import configuration from file
  export [options]                 Export configuration to file/stdout
  status, --info                   Show ${software_name} status
  help, --help, -h                 Show this help
  version, --version, -v           Show version information

Options:
  --interactive, -i                Force interactive mode
  --daemon, -d                     Run in daemon mode (for start action)
  --quiet, -q                      Quiet mode (suppress output)
  --debug                          Enable debug output

Logs: sudo journalctl -u ${service_name} -f
EOF
}

show_status() {
    local install_path="${INSTALL_PATH:-"[INSTALL_PATH]"}"
    local config_file="${CONFIG_FILE:-"[CONFIG_FILE]"}"

    show_software_status
    show_dependencies_status
    show_service_status
    show_daemon_status

    echo ""
    echo "Configuration:"
    echo "  Install path:  ${install_path}"
    echo "  Config file:   ${config_file}"
}
