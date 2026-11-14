#!/bin/bash
# lib/setup/files.sh - File, directory, and symlink deployment helpers
#
# DynDNS
#
# Author: Manuel Ziel
# License: MIT

set -euo pipefail

################################################################################
# DIRECTORY & CONFIGURATION PERMISSION HELPERS
################################################################################

_ensure_install_parent_dir() {
    local dest_path="$1"
    local etc_dir="${ETC_DIR:-"[ETC_DIR]"}"
    local parent_dir
    parent_dir="$(dirname "${dest_path}")"

    if ! mkdir -p "${parent_dir}"; then
        print_error "Failed to create directory for: ${dest_path}"
        return 1
    fi
    if [[ ! -L "${parent_dir}" ]]; then
        if [[ "${parent_dir}" == "${etc_dir}" || "${parent_dir}" == "${etc_dir}"/* ]]; then
            chmod 00750 "${parent_dir}" 2>/dev/null || true
        elif [[ "${parent_dir}" == /usr/local/* ]]; then
            chmod 00755 "${parent_dir}" 2>/dev/null || true
        fi
    fi
    return 0
}

_normalize_usr_local_dirs() {
    local base_dir dir_path
    for base_dir in "/usr/local" "/usr/local/bin" "/usr/local/libexec" "/usr/local/share" "/usr/local/lib"; do
        if [[ -d "${base_dir}" && ! -L "${base_dir}" ]]; then
            chmod 00755 "${base_dir}" 2>/dev/null || true
        fi
    done
    for dir_path in "${BIN_DIR:-}" "${SHARE_DIR:-}" "${LIB_DIR:-}"; do
        if [[ -n "${dir_path}" && "${dir_path}" == /usr/local/* && -d "${dir_path}" && ! -L "${dir_path}" ]]; then
            find -P "${dir_path}" -not -type l -type d -exec chmod 00755 {} + 2>/dev/null || true
        fi
    done
}

_secure_etc_config() {
    local etc_dir="${ETC_DIR:-"[ETC_DIR]"}"
    local config_file="${CONFIG_FILE:-"${etc_dir}/config.toml"}"
    local service_user service_group target_group="root"
    service_user="$(_normalize_service_user "${SERVICE_USER:-root}")"
    service_group="$(_normalize_service_group "${SERVICE_GROUP:-}" "${service_user}")"

    if getent group "${service_group}" >/dev/null 2>&1; then
        target_group="${service_group}"
    elif [[ "${service_user}" != "root" ]] && getent passwd "${service_user}" >/dev/null 2>&1; then
        target_group="$(id -gn "${service_user}" 2>/dev/null || printf '%s' "root")"
    fi
    if [[ -L "${etc_dir}" || -L "${config_file}" ]]; then
        print_error "Refusing symlinked configuration path in ${etc_dir}"
        return 1
    fi
    if [[ -d "${etc_dir}" ]]; then
        chown -h "root:${target_group}" "${etc_dir}" 2>/dev/null || true
        chmod 00750 "${etc_dir}" 2>/dev/null || true
    fi
    if [[ -f "${config_file}" ]]; then
        chown -h "root:${target_group}" "${config_file}" 2>/dev/null || true
        chmod 0640 "${config_file}" 2>/dev/null || true
    fi
    return 0
}

################################################################################
# SINGLE-ITEM & BATCH FILE DEPLOYMENT
################################################################################

_install_symlink_item() {
    local target_path="$1"
    local dest_path="$2"

    _ensure_install_parent_dir "${dest_path}" || return 1
    if ln -sfn "${target_path}" "${dest_path}"; then
        print_success "Created symlink: ${dest_path} -> ${target_path}"
        return 0
    fi
    print_error "Failed to create symlink: ${dest_path} -> ${target_path}"
    return 1
}

_copy_file_item() {
    local full_source="$1"
    local dest_path="$2"
    local item_type="$3"
    local source_path="$4"
    local etc_dir="${ETC_DIR:-"[ETC_DIR]"}"
    local config_file="${CONFIG_FILE:-"${etc_dir}/config.toml"}"
    local file_mode="0644"

    if [[ "${item_type}" == "executable" ]]; then
        file_mode="0755"
    elif [[ "${dest_path}" == "${config_file}" || "${dest_path}" == "${etc_dir}"/* ]]; then
        file_mode="0640"
    fi
    if [[ -L "${dest_path}" ]]; then
        rm -f -- "${dest_path}"
    fi
    if install -m "${file_mode}" "${full_source}" "${dest_path}"; then
        print_success "Installed: ${source_path} -> ${dest_path}"
        return 0
    fi
    print_error "Failed to copy: ${source_path}"
    return 1
}

_copy_dir_item() {
    local full_source="$1"
    local dest_path="$2"
    local source_path="$3"

    if [[ -e "${dest_path}" || -L "${dest_path}" ]]; then
        safe_rm_rf "${dest_path}" || return 1
    fi
    if ! mkdir -p "${dest_path}"; then
        print_error "Failed to create directory: ${dest_path}"
        return 1
    fi
    if tar -C "${full_source}" --exclude='__pycache__' --exclude='*.py[cod]' -cf - . \
        | tar -C "${dest_path}" --no-same-owner -xf -; then
        find -P "${dest_path}" -not -type l -type d -exec chmod 00755 {} + 2>/dev/null || true
        find -P "${dest_path}" -not -type l -type f -perm /111 -exec chmod 0755 {} + 2>/dev/null || true
        find -P "${dest_path}" -not -type l -type f ! -perm /111 -exec chmod 0644 {} + 2>/dev/null || true
        print_success "Installed directory: ${source_path} -> ${dest_path}"
        return 0
    fi
    print_error "Failed to copy directory: ${source_path}"
    return 1
}

install_single_item() {
    local _dir="${_DIR:-"[DIR]"}"
    local source_path="$1"
    local dest_path="${2%/}"
    local item_type="$3"
    local full_source="${_dir}/${source_path%/}"
    if [[ "${item_type}" == "symlink" ]]; then
        _install_symlink_item "${source_path}" "${dest_path}"
        return $?
    fi
    if [[ ! -e "${full_source}" ]]; then
        print_error "Source not found: ${full_source}"
        return 1
    fi
    _ensure_install_parent_dir "${dest_path}" || return 1
    case "${item_type}" in
        "file"|"executable")
            _copy_file_item "${full_source}" "${dest_path}" "${item_type}" "${source_path}"
            ;;
        "dir")
            _copy_dir_item "${full_source}" "${dest_path}" "${source_path}"
            ;;
        *)
            print_error "Unknown install type: ${item_type}"
            return 1
            ;;
    esac
}

_report_install_files_result() {
    local install_count="$1"
    local failed_count="$2"
    if [[ "${install_count}" -gt 0 ]]; then
        print_success "Successfully installed ${install_count} item(s)"
    fi
    if [[ "${failed_count}" -gt 0 ]]; then
        print_error "Failed to install ${failed_count} item(s)"
        return 1
    fi
    if [[ "${install_count}" -eq 0 ]]; then
        print_warning "No files were installed"
        return 1
    fi
    return 0
}

install_files() {
    local software_name="${SOFTWARE_NAME:-"[SOFTWARE_NAME]"}"
    local -a install_sources=("${INSTALL_SOURCES[@]+"${INSTALL_SOURCES[@]}"}")
    local install_count=0 failed_count=0 item
    local -a parts=()

    print_info "Installing ${software_name} files..."
    if [[ "${#install_sources[@]}" -eq 0 ]]; then
        print_warning "No INSTALL_SOURCES configured - nothing to install"
        print_info "Configure INSTALL_SOURCES array in config.sh"
        return 1
    fi
    for item in "${install_sources[@]}"; do
        [[ -z "${item}" || "${item}" =~ ^[[:space:]]*# ]] && continue
        IFS=':' read -ra parts <<< "${item}"
        if [[ "${#parts[@]}" -ne 3 ]]; then
            print_warning "Invalid install source format: ${item}"
            failed_count=$((failed_count + 1))
        elif install_single_item "${parts[0]}" "${parts[1]}" "${parts[2]}"; then
            install_count=$((install_count + 1))
        else
            failed_count=$((failed_count + 1))
        fi
    done
    _report_install_files_result "${install_count}" "${failed_count}" || return 1
    _normalize_usr_local_dirs
    _secure_etc_config || return 1
    return 0
}
