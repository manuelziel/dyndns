#!/bin/bash
# lib/setup/menu.sh - Interactive setup TUI menu, help, and status views
#
# DynDNS
#
# Author: Manuel Ziel
# License: MIT

set -euo pipefail

################################################################################
# INTERACTIVE MENU
################################################################################

_append_setup_menu_item() {
    local label="$1"
    local action_key="$2"
    local option_num=$(( ${#MENU_OPTIONS[@]} + 1 ))
    MENU_OPTIONS+=("${option_num}) ${label}")
    MENU_ACTIONS+=("${action_key}")
}

_build_setup_menu_options() {
    local software_name="${SOFTWARE_NAME:-"[SOFTWARE_NAME]"}"
    MENU_OPTIONS=()
    MENU_ACTIONS=()
    if is_installed; then
        _append_setup_menu_item "Update" "update"
        _append_setup_menu_item "Reinstall" "reinstall"
        _append_setup_menu_item "Uninstall" "uninstall"
        _append_setup_menu_item "Purge" "purge"
        _append_setup_menu_item "View detailed status" "status"
    else
        _append_setup_menu_item "Install ${software_name}" "install"
        _append_setup_menu_item "Check system requirements" "requirements"
        _append_setup_menu_item "Show version information" "version"
    fi
    MENU_MAX_CHOICE="${#MENU_OPTIONS[@]}"
    MENU_OPTIONS+=("0) Exit")
    MENU_ACTIONS+=("exit")
}

_dispatch_setup_menu_action() {
    local action="$1"

    case "${action}" in
        "install")      if do_install; then return 2; fi ;;
        "update")       if do_update; then return 2; fi ;;
        "reinstall")    if do_reinstall; then return 2; fi ;;
        "uninstall")    if do_uninstall; then return 2; fi ;;
        "purge")        if do_purge; then return 2; fi ;;
        "status")       show_status || true ;;
        "requirements") show_requirements || true ;;
        "version")      show_version || true ;;
        "exit")         print_info "Cancelled by user."; return 2 ;;
        *)              print_error "Unknown action: ${action}" ;;
    esac
    return 0
}

_render_setup_menu_screen() {
    [[ -t 1 ]] && clear 2>/dev/null || true
    print_banner "Setup"
    show_status || true
    _build_setup_menu_options
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
        _render_setup_menu_screen
        if ! read -rp "Enter your choice (0-${MENU_MAX_CHOICE}): " choice; then
            echo ""
            print_info "Input closed (EOF). Exiting setup menu."
            return 0
        fi
        echo ""
        resolve_menu_choice "${choice}"
        if [[ "${MENU_SELECTED_ACTION}" != "invalid" ]]; then
            rc=0
            _dispatch_setup_menu_action "${MENU_SELECTED_ACTION}" || rc=$?
            [[ "${rc}" -eq 2 ]] && return 0
        else
            print_error "Invalid selection. Enter a number between 0 and ${MENU_MAX_CHOICE}."
        fi
        echo ""
        read -rp "Press Enter to continue..." || { echo ""; return 0; }
    done
}

################################################################################
# HELP AND STATUS
################################################################################

show_help() {
    local software_name="${SOFTWARE_NAME:-"[SOFTWARE_NAME]"}" version="${VERSION:-"[VERSION]"}"
    print_section "${software_name} Setup v${version}"
    cat <<EOF
Usage: $0 [ACTION] [OPTIONS]

Actions:
  install                     Install ${software_name}
  update, --upgrade           Update to latest version
  reinstall, --reinstall      Reinstall current version
  uninstall, --remove         Uninstall ${software_name}
  purge, --purge              Completely remove including all data
  status, --info              Show installation status
  help, --help, -h            Show this help message
  version, --version, -v      Show version information

Options:
  --interactive, -i           Force interactive mode (default)
  --quiet, -q                 Suppress non-essential output
  --force, -f                 Skip confirmation prompts
  --no-deps                   Skip dependency checking
  --debug                     Enable debug output

Examples:
  $0                          Interactive setup menu (default)
  $0 install --force          Silent installation
  $0 update                   Update existing installation
EOF
}

show_status() {
    show_software_status
    show_dependencies_status
    show_internet_status
}
