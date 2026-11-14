#!/bin/bash
# lib/setup/system.sh - Connectivity checks and system package installation
#
# DynDNS
#
# Author: Manuel Ziel
# License: MIT

set -euo pipefail

################################################################################
# SYSTEM DETECTION & CHECKS
################################################################################

check_internet() {
    local ping_timeout="${NET_PING_TIMEOUT:-3}"
    local http_timeout="${NET_HTTP_TIMEOUT:-5}"
    local probe_ip="${NET_PROBE_IP:-1.1.1.1}"
    local probe_url="${NET_PROBE_URL:-https://connectivitycheck.gstatic.com/generate_204}"

    print_info "Checking internet connection..."

    if command -v ping &>/dev/null && ping -c 1 -W "${ping_timeout}" "${probe_ip}" >/dev/null 2>&1; then
        print_success "Internet connection available"
        return 0
    fi

    if command -v curl &>/dev/null \
        && curl -fsS --connect-timeout "${http_timeout}" --head "${probe_url}" >/dev/null 2>&1; then
        print_success "Internet connection available"
        return 0
    fi

    if command -v wget &>/dev/null \
        && wget -q --spider --timeout="${http_timeout}" "${probe_url}" >/dev/null 2>&1; then
        print_success "Internet connection available"
        return 0
    fi

    print_warning "External internet probe did not respond"
    return 1
}

show_internet_status() {
    if check_internet >/dev/null 2>&1; then
        print_status_line "Internet" "${GREEN}" "✓" "Connected"
    else
        print_status_line "Internet" "${YELLOW}" "✗" "Not available"
    fi
}

################################################################################
# DEPENDENCY MANAGEMENT
################################################################################

_confirm_dependency_install() {
    local force_mode="${FORCE_MODE:-0}"

    if [[ "${force_mode}" -eq 1 ]]; then
        return 0
    fi

    echo ""
    if ! read -rp "Install missing dependencies automatically? [y/N]: " -n 1; then
        echo ""
        print_info "Dependency installation cancelled"
        return 1
    fi
    echo ""

    if [[ ! "${REPLY}" =~ ^[Yy]$ ]]; then
        print_info "Dependency installation cancelled"
        return 1
    fi
    return 0
}

_install_missing_packages() {
    local missing_packages=("$@")
    print_info "Will install: ${missing_packages[*]}"
    _confirm_dependency_install || return 1
    if ! check_internet; then
        print_warning "Attempting package installation via configured local mirror/proxy..."
    fi
    if install_system_dependencies "${missing_packages[@]}"; then
        print_success "Dependencies installed successfully"
        return 0
    fi
    print_error "Failed to install dependencies"
    return 1
}

check_and_install_dependencies() {
    local dependencies=("${!DEPENDENCIES[@]}")
    local missing_packages=() missing_pkg_keys=() pkg_key pkg_name

    for pkg_key in "${dependencies[@]}"; do
        pkg_name="$(get_package_name_for_key "${pkg_key}")"
        if ! is_package_installed "${pkg_name}"; then
            missing_packages+=("${pkg_name}")
            missing_pkg_keys+=("${pkg_key}")
        fi
    done
    if [[ "${#missing_packages[@]}" -eq 0 ]]; then
        print_success "All dependencies satisfied"
        return 0
    fi
    print_warning "Missing packages: ${missing_pkg_keys[*]}"
    if [[ "${SKIP_DEPENDENCIES:-0}" -eq 1 ]]; then
        print_info "Skipping dependency installation (--no-deps)"
        return 0
    fi
    _install_missing_packages "${missing_packages[@]}"
}

install_system_dependencies() {
    local packages=("$@")
    local package_manager

    if [[ "${#packages[@]}" -eq 0 ]]; then
        print_warning "No packages specified for installation"
        return 0
    fi

    package_manager="$(detect_package_manager)"
    if [[ "${package_manager}" == "unknown" ]]; then
        print_error "No supported package manager found"
        print_info "Install these packages manually: ${packages[*]}"
        return 1
    fi

    print_info "Installing packages using ${package_manager}: ${packages[*]}"
    case "${package_manager}" in
        "apt")
            DEBIAN_FRONTEND=noninteractive apt-get update \
                && DEBIAN_FRONTEND=noninteractive apt-get install -y "${packages[@]}"
            ;;
        "dnf")    dnf install -y "${packages[@]}" ;;
        "yum")    yum install -y "${packages[@]}" ;;
        "pacman") pacman -Syu --noconfirm "${packages[@]}" ;;
        "zypper") zypper install -y "${packages[@]}" ;;
        *)
            print_error "Unsupported package manager: ${package_manager}"
            return 1
            ;;
    esac
}
