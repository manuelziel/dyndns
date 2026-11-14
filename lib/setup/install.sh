#!/bin/bash
# lib/setup/install.sh - Setup lifecycle orchestration (install, update, uninstall, purge)
#
# DynDNS
#
# Author: Manuel Ziel
# License: MIT

set -euo pipefail

################################################################################
# OPTIONAL HOOKS & USER PROMPTS
################################################################################

if ! command -v setup_optional_function &>/dev/null; then
    setup_optional_function() {
        print_info "No custom setup hook implemented"
        return 0
    }
fi

_print_install_next_steps() {
    local cmd_name="${SOFTWARE_DIR_NAME:-"[SOFTWARE_DIR_NAME]"}"
    local service_name="${SERVICE_NAME:-"[SERVICE_NAME]"}"

    echo ""
    print_info "Next steps:"
    echo "  1. Configure: ${cmd_name} config"
    echo "  2. Enable & start: sudo systemctl enable --now ${service_name}"
    echo "  3. View logs: sudo journalctl -u ${service_name} -f"
}

_confirm_setup_prompt() {
    local prompt_msg="$1"
    local cancel_msg="$2"

    echo ""
    if ! read -rp "${prompt_msg} [y/N]: " -n 1; then
        echo ""
        print_info "${cancel_msg}"
        return 1
    fi
    echo ""
    if [[ ! "${REPLY}" =~ ^[Yy]$ ]]; then
        print_info "${cancel_msg}"
        return 1
    fi
    return 0
}

################################################################################
# INSTALL, UPDATE & REINSTALL ORCHESTRATION
################################################################################

do_install() {
    local software_name="${SOFTWARE_NAME:-"[SOFTWARE_NAME]"}"
    local force_mode="${FORCE_MODE:-0}"

    print_section "Installing ${software_name}"
    if is_installed && [[ "${force_mode}" -eq 0 ]]; then
        print_warning "Software is already installed"
        print_info "Use --force or reinstall to reinstall"
        return 1
    fi
    check_and_install_dependencies || return 1
    if [[ "${ENABLE_OPTIONAL_DEPENDENCY:-0}" -eq 1 ]] && ! setup_optional_function; then
        print_error "Failed to setup optional dependencies/hooks"
        return 1
    fi
    if ! create_service_user; then
        print_error "Failed to create service user/group"
        return 1
    fi
    install_files || return 1
    create_data_directory || print_warning "Failed to create data directory, continuing..."
    if [[ "${ENABLE_PYTHON:-0}" -eq 1 ]] && ! setup_python_environment; then
        print_error "Failed to setup Python virtual environment"
        return 1
    fi
    if [[ "${CREATE_SERVICE:-false}" == "true" ]] && ! create_service; then
        print_warning "Service creation failed, continuing installation"
    fi
    print_success "${software_name} installed successfully!"
    _print_install_next_steps
    return 0
}

_stop_service_for_update() {
    local service_name="$1"
    if [[ -z "${service_name}" || "${service_name}" == "[SERVICE_NAME]" ]]; then
        return 1
    fi
    if ! service_active; then
        print_info "Service is not running, no need to stop"
        return 1
    fi
    print_info "Stopping service for update..."
    if service_stop; then
        print_success "Service stopped"
    else
        print_warning "Failed to stop service, continuing anyway"
    fi
    return 0
}

_restart_service_after_update() {
    local service_name="$1"
    local install_result="$2"
    if [[ "${install_result}" -ne 0 ]]; then
        print_warning "Update failed - service remains stopped"
        print_info "You may need to restart service manually once fixed"
        return 0
    fi
    print_info "Restarting service..."
    if service_restart; then
        print_success "Service restarted successfully"
    else
        print_warning "Failed to restart service - you may need to start it manually"
        print_info "Try: sudo systemctl restart ${service_name}"
        print_info "Check status with: sudo systemctl status ${service_name}"
    fi
}

do_update() {
    local software_name="${SOFTWARE_NAME:-"[SOFTWARE_NAME]"}"
    local version="${VERSION:-"[VERSION]"}"
    local service_name="${SERVICE_NAME:-"[SERVICE_NAME]"}"
    local old_force="${FORCE_MODE:-0}"
    local was_running="false" install_result=0 current_version

    if ! is_installed; then
        print_error "${software_name} is not installed"
        print_info "Run './setup.sh install' first"
        return 1
    fi
    current_version="$(get_installed_version)"
    print_section "Updating ${software_name}"
    print_info "Current version: ${current_version} -> New version: ${version}"
    check_and_install_dependencies || return 1
    if _stop_service_for_update "${service_name}"; then
        was_running="true"
    fi
    FORCE_MODE=1
    if ! do_install; then
        print_error "Update failed!"
        install_result=1
    fi
    FORCE_MODE="${old_force}"
    [[ "${was_running}" == "true" ]] && _restart_service_after_update "${service_name}" "${install_result}"
    [[ "${install_result}" -ne 0 ]] && return 1
    print_success "Update completed successfully!"
    return 0
}

do_reinstall() {
    if FORCE_MODE=1 do_uninstall && FORCE_MODE=1 do_install; then
        print_success "Reinstallation completed successfully"
        return 0
    fi
    print_error "Reinstallation failed"
    return 1
}

################################################################################
# UNINSTALL & PURGE ORCHESTRATION
################################################################################

_cleanup_installed_artifacts() {
    local bin_dir="${BIN_DIR:-"[BIN_DIR]"}"
    local share_dir="${SHARE_DIR:-"[SHARE_DIR]"}"
    local runtime_dir="${RUNTIME_DIR:-"[RUNTIME_DIR]"}"
    local bin_symlink="${BIN_SYMLINK:-"[BIN_SYMLINK]"}"

    remove_systemd_services "${SERVICE_NAME:-"[SERVICE_NAME]"}" "${SERVICE_PATH:-"[SERVICE_PATH]"}"
    if [[ -L "${bin_symlink}" ]]; then
        rm -f -- "${bin_symlink}"
        print_success "Symlink removed: ${bin_symlink}"
    fi
    if [[ -d "${bin_dir}" || -L "${bin_dir}" ]]; then
        safe_rm_rf "${bin_dir}" || return 1
        print_success "Binary directory removed: ${bin_dir}"
    fi
    if [[ -d "${share_dir}" || -L "${share_dir}" ]]; then
        safe_rm_rf "${share_dir}" || return 1
        print_success "Share directory removed: ${share_dir}"
    fi
    if [[ -d "${runtime_dir}" || -L "${runtime_dir}" ]]; then
        safe_rm_rf "${runtime_dir}" || return 1
        print_success "Runtime directory removed: ${runtime_dir}"
    fi
    return 0
}

do_uninstall() {
    local software_name="${SOFTWARE_NAME:-"[SOFTWARE_NAME]"}"

    print_section "Uninstalling ${software_name}"
    if ! is_installed; then
        print_warning "${software_name} is not installed"
        return 0
    fi
    if [[ "${FORCE_MODE:-0}" -eq 0 ]]; then
        _confirm_setup_prompt "Are you sure you want to uninstall ${software_name}?" "Uninstall cancelled" || return 0
    fi
    _cleanup_installed_artifacts || return 1
    print_success "${software_name} uninstalled completely!"
    if [[ "${PURGE_MODE:-0}" -eq 0 ]]; then
        print_info "Note: Data directory ${VAR_LIB_DIR:-"[VAR_LIB_DIR]"} was preserved"
        print_info "Use 'purge' or 'uninstall --purge' to remove all data"
    fi
    return 0
}

do_purge() {
    local software_name="${SOFTWARE_NAME:-"[SOFTWARE_NAME]"}"
    local var_lib_dir="${VAR_LIB_DIR:-"[VAR_LIB_DIR]"}"
    local etc_dir="${ETC_DIR:-"[ETC_DIR]"}"

    print_section "Purging ${software_name}"
    print_warning "This will remove ALL data"
    print_warning "Data directory: ${var_lib_dir}"
    if [[ "${FORCE_MODE:-0}" -eq 0 ]]; then
        _confirm_setup_prompt "Are you ABSOLUTELY sure? This cannot be undone!" "Purge cancelled" || return 0
    fi
    _cleanup_installed_artifacts || return 1
    if [[ -d "${var_lib_dir}" || -L "${var_lib_dir}" ]]; then
        print_info "Removing data directory: ${var_lib_dir}"
        safe_rm_rf "${var_lib_dir}" || return 1
        print_success "Data directory removed: ${var_lib_dir}"
    else
        print_info "Data directory not found: ${var_lib_dir}"
    fi
    if [[ -d "${etc_dir}" || -L "${etc_dir}" ]]; then
        print_info "Removing config directory: ${etc_dir}"
        safe_rm_rf "${etc_dir}" || return 1
        print_success "Config directory removed: ${etc_dir}"
    fi
    remove_service_user
    print_success "${software_name} purged completely! All data removed."
    return 0
}
