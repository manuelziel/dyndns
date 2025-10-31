#!/bin/bash
# lib/core/essentials.sh
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
# 1. CORE UTILITIES & STATUS
################################################################################

check_root() {
    if [[ ${EUID} -ne 0 ]]; then
        print_error "This operation requires root privileges"
        print_info "Run with sudo: sudo $0 $*"
        return 1
    fi
    return 0
}

################################################################################
# 2. SYSTEM & VALIDATION - Process Management and System Checks
################################################################################

detect_package_manager() {
    # Check in order of specificity
    if command -v apt-get &>/dev/null; then
        echo "apt"
    elif command -v dnf &>/dev/null; then
        echo "dnf"
    elif command -v yum &>/dev/null; then
        echo "yum"
    elif command -v pacman &>/dev/null; then
        echo "pacman"
    elif command -v zypper &>/dev/null; then
        echo "zypper"
    else
        echo "unknown"
    fi
}

# Function to get package name for a package key from PACKAGE_MAPPINGS
get_package_name_for_key() {
    local pkg_key="$1"
    local mapping="${PACKAGE_MAPPINGS[$pkg_key]:-}"
    local package_manager=$(detect_package_manager)

    if [[ -z "${mapping}" ]]; then
        echo "${pkg_key}"  # fallback to key name
        return
    fi
    
    # Parse mapping: "apt:dnf:pacman:zypper"
    IFS=':' read -ra parts <<< "${mapping}"

    case "${package_manager}" in
        "apt")     echo "${parts[0]}" ;;
        "dnf")     echo "${parts[1]:-${parts[0]}}" ;;
        "yum")     echo "${parts[1]:-${parts[0]}}" ;;
        "pacman")  echo "${parts[2]:-${parts[0]}}" ;;
        "zypper")  echo "${parts[3]:-${parts[0]}}" ;;
        *)         echo "${parts[0]}" ;;
    esac
}

is_package_installed() {
    local package="$1"
    local package_manager=$(detect_package_manager)

    case "${package_manager}" in
        "apt")
            dpkg -l "${package}" 2>/dev/null | grep -q "^ii" ;;
        "dnf"|"yum")
            rpm -q "${package}" &>/dev/null ;;
        "pacman")
            pacman -Q "${package}" &>/dev/null ;;
        "zypper")
            rpm -q "${package}" &>/dev/null ;;
        *)
            return 1 ;;
    esac
}

# Check if systemd service exists
has_systemd_service() {
    local service_name="${SERVICE_NAME:-"[SERVICE_NAME]"}"

    if command -v systemctl &>/dev/null; then
        systemctl list-unit-files "${service_name}.service" &>/dev/null 2>&1
    else
        return 1
    fi
}

is_systemd_service_active() {
    local service_name="${SERVICE_NAME:-"[SERVICE_NAME]"}"

    if command -v systemctl &>/dev/null; then
        systemctl is-active "${service_name}.service" &>/dev/null
    else
        return 1
    fi
}

check_dependencies() {
    local dependencies=("${!DEPENDENCIES[@]}")
    local missing_deps=()
    
    for pkg_key in "${dependencies[@]}"; do
        local package_name=$(get_package_name_for_key "${pkg_key}")
        if ! is_package_installed "${package_name}"; then
            missing_deps+=("${pkg_key}")
        fi
    done
    
    if [[ ${#missing_deps[@]} -gt 0 ]]; then
        return 1
    fi
    
    return 0
}

################################################################################
# 2. INSTALLATION STATUS
################################################################################ 

is_installed() {
    local install_path="${INSTALL_PATH:-"[FILE_DIR]"}"
    [[ -f "$install_path" ]]
}

get_installed_version() {
    local bin_symlink="${BIN_SYMLINK}"
    
    if is_installed; then
        if [[ -x "${bin_symlink}" ]]; then
            local version_output
            version_output=$("${bin_symlink}" --version 2>/dev/null | grep -oE 'v?[0-9]+\.[0-9]+\.[0-9]+[a-zA-Z0-9]*' | head -n1 | sed 's/^v//')
            if [[ -n "${version_output}" ]]; then
                echo "${version_output}"
            else
                echo "unknown"
            fi
        else
            echo "unknown"
        fi
    else
        echo "not installed"
    fi
}

################################################################################
# 3. Service Management
################################################################################

service_exists() {
    local service_name="${SERVICE_NAME:-"[SERVICE_NAME]"}"
    local service_path="${SERVICE_PATH:-"/etc/systemd/system/${service_name}"}"
    
    if [[ -f "${service_path}" ]]; then
        return 0
    else
        return 1
    fi
}

service_active() {
    local service_name="${SERVICE_NAME:-"[SERVICE_NAME]"}"

    if systemctl is-active --quiet "${service_name}"; then
        return 0
    else
        return 1
    fi
}

service_enabled() {
    local service_name="${SERVICE_NAME:-"[SERVICE_NAME]"}"

    if systemctl is-enabled --quiet "${service_name}"; then
        return 0
    else
        return 1
    fi
}

service_enable() {
    local service_name="${SERVICE_NAME:-"[SERVICE_NAME]"}"

    if systemctl enable --quiet "${service_name}"; then
        return 0
    else
        return 1
    fi
}

service_disable() {
    local service_name="${SERVICE_NAME:-"[SERVICE_NAME]"}"
    
    if systemctl disable --quiet "${service_name}"; then
        return 0
    else
        return 1
    fi
}

service_start() {
    local service_name="${SERVICE_NAME:-"[SERVICE_NAME]"}"

    if systemctl start --quiet "${service_name}"; then
        return 0
    else
        return 1
    fi    
}

service_restart() {
    local service_name="${SERVICE_NAME:-"[SERVICE_NAME]"}"

    if systemctl restart --quiet "${service_name}"; then
        return 0
    else
        return 1
    fi    
}

service_stop() {
    local service_name="${SERVICE_NAME:-"[SERVICE_NAME]"}"

    if service_active; then
        if systemctl stop "${service_name}"; then
            return 0
        else
            return 1
        fi
    else
        return 0
    fi
}

service_daemon_reload() {
    if systemctl daemon-reload; then
        return 0
    else
        return 1
    fi
}

get_service_status() {
    if service_exists; then
        if service_active; then
            if service_enabled; then
                echo "running (enabled)"
            else
                echo "running (disabled)"
            fi
        else
            if service_enabled; then
                echo "stopped (enabled)"
            else
                echo "stopped (disabled)"
            fi
        fi
    else
        echo "not installed"
    fi
}

################################################################################
# 4. Menu & Version
################################################################################

show_software_status() {
    local version="$(get_installed_version)"
    local install_path="${INSTALL_PATH:-"[INSTALL_PATH]"}"
    local size="$(ls -lh "${install_path}" 2>/dev/null | awk '{print $5}')"
    local modified="$(stat -c %y "${install_path}" 2>/dev/null | cut -d. -f1)"

    if is_installed; then
        print_status_line "Installed version" "${BLUE}" "ℹ" " v${version}"
        print_status_line "Location" "${BLUE}" "ℹ" "${install_path}"

        if [[ -f "${install_path}" ]]; then
            print_status_line "Size" "${BLUE}" "ℹ" "${size}"
            print_status_line "Modified" "${BLUE}" "ℹ" "${modified}"
        fi
    else
        print_status_line "Software" "${YELLOW}" "✗" "Not installed"
    fi
}

show_dependencies_status() {
    if check_dependencies >/dev/null 2>&1; then
        print_status_line "Dependencies" "${GREEN}" "✓" "All satisfied"
    else
        print_status_line "Dependencies" "${RED}" "✗" "Missing packages"
    fi
}

show_service_status() {
    local service_name="${SERVICE_NAME:-"[SERVICE_NAME]"}"
    local service_status="$(get_service_status)"

    if is_installed; then
        if [[ -n "${service_name}" ]] && [[ "${service_name}" != "[service-name].service" ]]; then
            case "${service_status}" in
                "running (enabled)")
                    print_status_line "Service" "${GREEN}" "✓" "${service_status}"
                    ;;
                "running (disabled)")
                    print_status_line "Service" "${YELLOW}" "✗" "${service_status}"
                    ;;
                "stopped"*)
                    print_status_line "Service" "${YELLOW}" "✗" "${service_status}"
                    ;;
                *)
                    print_status_line "Service" "${RED}" "✗" "${service_status}"
                    ;;
            esac
        fi
    fi
}

show_daemon_status() {
    local software_name="${SOFTWARE_NAME:-"[SOFTWARE_NAME]"}"
    local pid="$(cat "${PID_FILE}" 2>/dev/null)"
    
    if is_running; then
        print_success "${software_name} is running (PID: ${pid:-'unknown'})"

        if [[ -n "${pid}" ]]; then
            echo "  Process ID: ${pid}"
            echo "  Start time: $(ps -o lstart= -p "${pid}" 2>/dev/null || echo 'unknown')"
            echo "  CPU usage: $(ps -o %cpu= -p "${pid}" 2>/dev/null || echo 'unknown')%"
            echo "  Memory usage: $(ps -o %mem= -p "${pid}" 2>/dev/null || echo 'unknown')%"
        fi
    else
        print_warning "${software_name} is not running"
    fi
}

show_internet_status() {
    if check_internet >/dev/null 2>&1; then
        print_status_line "Internet" "${GREEN}" "✓" "Connected"
    else
        print_status_line "Internet" "${YELLOW}" "✗" "Not available"
    fi
}

show_requirements() {
    local software_name=${SOFTWARE_NAME:-"[SOFTWARE_NAME]"}
    local dependencies="$(printf '%s, ' "${!DEPENDENCIES[@]}" | sed 's/, $//')"
    local service_name=${SERVICE_NAME:-"[SERVICE_NAME]"}
    local service_path=${SERVICE_PATH:-"[SERVICE_PATH]"}
    local install_path=${INSTALL_PATH}

    print_section "System Requirements"

    echo "Required for ${software_name}:"
    echo "  • Operating System: Linux with systemd"
    echo "  • Required commands: ${dependencies:-"none"}"
    echo "  • Installation path: ${install_path}"
    if [[ -n "${service_name}" ]] && [[ "${service_name}" != "[service-name].service" ]]; then
        echo "  • Service file: ${service_path}"
    fi
}

show_version() {
    local software_name=${SOFTWARE_NAME:-"[SOFTWARE_NAME]"}
    local version=${VERSION:-"[VERSION]"}
    local last_modified=${LAST_MODIFIED:-"[LAST_MODIFIED]"}
    local author=${AUTHOR:-"[AUTHOR]"}

    echo "${software_name}"
    echo "Version: v${version} (${last_modified})"
    echo "Author: ${author}"
    echo "License: MIT"
}