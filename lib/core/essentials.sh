#!/bin/bash
# lib/core/essentials.sh - Core privilege, package, service, and status helpers
#
# DynDNS
#
# Author: Manuel Ziel
# License: MIT

set -euo pipefail

################################################################################
# CORE UTILITIES & STATUS
################################################################################

check_root() {
    if [[ "${EUID}" -ne 0 ]]; then
        print_error "This operation requires root privileges"
        print_info "Run with sudo: sudo $0 $*"
        return 1
    fi
    return 0
}

# Check if the current user is allowed to run the application at runtime.
# Accepts root (EUID 0) or the configured SERVICE_USER (when set and not root).
check_runtime_user() {
    local service_user="${SERVICE_USER:-root}"

    if [[ "${EUID}" -eq 0 || "${DEV_MODE:-0}" -eq 1 ]]; then
        return 0
    fi
    if [[ -n "${service_user}" && "${service_user}" != "[SERVICE_USER]" && "${service_user}" != "root" ]]; then
        if [[ "$(id -un)" == "${service_user}" ]]; then
            return 0
        fi
        print_error "This operation must run as root or as '${service_user}'"
        print_info "Run with sudo: sudo $0 $*"
        return 1
    fi
    print_error "This operation requires root privileges"
    print_info "Run with sudo: sudo $0 $*"
    return 1
}

set_single_action() {
    local target_action="$1"
    local raw_token="${2:-$1}"

    if [[ -z "${ACTION:-}" ]]; then
        ACTION="${target_action}"
        return 0
    fi
    print_error "Multiple actions specified: ${ACTION} and ${raw_token}"
    return 1
}

resolve_menu_choice() {
    local choice="$1"
    if [[ "${choice}" == "0" ]]; then
        MENU_SELECTED_ACTION="exit"
    elif [[ "${choice}" =~ ^[0-9]+$ && "${choice}" -ge 1 && "${choice}" -le "${MENU_MAX_CHOICE}" ]]; then
        MENU_SELECTED_ACTION="${MENU_ACTIONS[$((choice - 1))]:-unknown}"
    else
        MENU_SELECTED_ACTION="invalid"
    fi
}

################################################################################
# FILESYSTEM SAFETY - Guarded Recursive Deletion
################################################################################

_is_allowed_rm_target() {
    local normalized="$1"
    if [[ "${normalized}" =~ ^(/var/lib|/etc|/usr/local/share|/usr/local/libexec|/usr/local/lib|/run)/[a-zA-Z0-9][a-zA-Z0-9._+-]*(/[a-zA-Z0-9._+-]+)*$ ]]; then
        return 0
    fi
    [[ -n "${_DIR:-}" && "${_DIR}" == /* && ! -L "${_DIR}" && "${normalized}" == "${_DIR%/}/.venv" ]]
}

safe_rm_rf() {
    local raw_path="${1:-}"
    local normalized="${raw_path}"

    if [[ -z "${raw_path}" || "${raw_path}" == *"["* || "${raw_path}" == *"]"* || "${raw_path}" != /* ]]; then
        print_error "Refusing unsafe recursive delete on invalid path: '${raw_path}'"
        return 1
    fi
    while [[ "${normalized}" == *"//"* ]]; do
        normalized="${normalized//\/\//\/}"
    done
    while [[ "${normalized}" != "/" && "${normalized}" == */ ]]; do
        normalized="${normalized%/}"
    done
    if [[ "/${normalized}/" == *"/./"* || "/${normalized}/" == *"/../"* ]]; then
        print_error "Refusing recursive delete on traversal path: '${raw_path}'"
        return 1
    fi
    if ! _is_allowed_rm_target "${normalized}"; then
        print_error "Refusing recursive delete outside allowed FHS prefixes: '${normalized}'"
        return 1
    fi
    rm -rf --preserve-root -- "${normalized}"
}

################################################################################
# SYSTEM & VALIDATION - Process Management and System Checks
################################################################################

detect_package_manager() {
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

is_package_installed() {
    local package="$1"
    local package_manager pkg_status
    package_manager="$(detect_package_manager)"
    case "${package_manager}" in
        "apt")
            pkg_status="$(dpkg-query -W -f='${db:Status-Status}' "${package}" 2>/dev/null || true)"
            [[ "${pkg_status}" == "installed" ]]
            ;;
        "dnf"|"yum"|"zypper") rpm -q "${package}" &>/dev/null ;;
        "pacman")             pacman -Q "${package}" &>/dev/null ;;
        *)                    return 1 ;;
    esac
}

get_package_name_for_key() {
    local pkg_key="$1"
    local mapping="${PACKAGE_MAPPINGS[$pkg_key]:-}"
    local package_manager
    local parts=()

    if [[ -z "${mapping}" ]]; then
        echo "${pkg_key}"
        return 0
    fi

    package_manager="$(detect_package_manager)"
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

check_dependencies() {
    local dependencies=("${!DEPENDENCIES[@]}")
    local missing_deps=()
    local pkg_key package_name

    if [[ "${SKIP_DEPENDENCIES:-0}" -eq 1 ]]; then
        return 0
    fi

    for pkg_key in "${dependencies[@]}"; do
        package_name="$(get_package_name_for_key "${pkg_key}")"
        if ! is_package_installed "${package_name}"; then
            missing_deps+=("${pkg_key}")
        fi
    done

    [[ "${#missing_deps[@]}" -eq 0 ]]
}

################################################################################
# INSTALLATION STATUS
################################################################################

is_installed() {
    local install_path="${INSTALL_PATH:-"[INSTALL_PATH]"}"
    [[ -f "${install_path}" ]]
}

get_installed_version() {
    local bin_symlink="${BIN_SYMLINK:-"[BIN_SYMLINK]"}"
    local version_output=""

    if ! is_installed; then
        echo "not installed"
        return 0
    fi
    if [[ ! -x "${bin_symlink}" ]]; then
        echo "unknown"
        return 0
    fi

    version_output="$("${bin_symlink}" --version 2>/dev/null \
        | grep -oE 'v?[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?' \
        | head -n1 | sed 's/^v//' || true)"
    echo "${version_output:-unknown}"
}

################################################################################
# SERVICE MANAGEMENT
################################################################################

service_exists() {
    local service_path="${SERVICE_PATH:-"[SERVICE_PATH]"}"
    [[ -f "${service_path}" ]]
}

service_active() {
    local service_name="${SERVICE_NAME:-"[SERVICE_NAME]"}"
    systemctl is-active --quiet "${service_name}" 2>/dev/null
}

service_enabled() {
    local service_name="${SERVICE_NAME:-"[SERVICE_NAME]"}"
    systemctl is-enabled --quiet "${service_name}" 2>/dev/null
}

service_enable() {
    local service_name="${SERVICE_NAME:-"[SERVICE_NAME]"}"
    systemctl enable --quiet "${service_name}"
}

service_disable() {
    local service_name="${SERVICE_NAME:-"[SERVICE_NAME]"}"
    systemctl disable --quiet "${service_name}"
}

service_start() {
    local service_name="${SERVICE_NAME:-"[SERVICE_NAME]"}"

    if service_active; then
        return 0
    fi
    systemctl start "${service_name}"
}

service_restart() {
    local service_name="${SERVICE_NAME:-"[SERVICE_NAME]"}"
    systemctl restart --quiet "${service_name}"
}

service_stop() {
    local service_name="${SERVICE_NAME:-"[SERVICE_NAME]"}"

    if ! service_active; then
        return 0
    fi
    systemctl stop "${service_name}"
}

service_daemon_reload() {
    systemctl daemon-reload
}

get_service_status() {
    if ! service_exists; then
        echo "not installed"
        return 0
    fi

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
}

################################################################################
# MENU & SERVICE STATUS
################################################################################

show_software_status() {
    local install_path="${INSTALL_PATH:-"[INSTALL_PATH]"}"
    local version size modified

    if ! is_installed; then
        print_status_line "Software" "${YELLOW}" "✗" "Not installed"
        return 0
    fi

    version="$(get_installed_version)"
    print_status_line "Installed" "${BLUE}" "ℹ" " v${version}"
    print_status_line "Location" "${BLUE}" "ℹ" "${install_path}"

    if [[ -f "${install_path}" ]]; then
        size="$(ls -lh "${install_path}" 2>/dev/null | awk '{print $5}' || true)"
        modified="$(stat -c %y "${install_path}" 2>/dev/null | cut -d. -f1 || true)"
        print_status_line "Size" "${BLUE}" "ℹ" "${size:-unknown}"
        print_status_line "Modified" "${BLUE}" "ℹ" "${modified:-unknown}"
    fi
}

show_dependencies_status() {
    if [[ "${SKIP_DEPENDENCIES:-0}" -eq 1 ]]; then
        print_status_line "Dependencies" "${YELLOW}" "✗" "Check skipped (--no-deps)"
    elif check_dependencies >/dev/null 2>&1; then
        print_status_line "Dependencies" "${GREEN}" "✓" "All satisfied"
    else
        print_status_line "Dependencies" "${RED}" "✗" "Missing packages"
    fi
}

show_service_status() {
    local service_name="${SERVICE_NAME:-"[SERVICE_NAME]"}"
    local service_status

    if ! is_installed || [[ -z "${service_name}" || "${service_name}" == "[SERVICE_NAME]" ]]; then
        return 0
    fi

    service_status="$(get_service_status)"
    case "${service_status}" in
        "running (enabled)")
            print_status_line "Service" "${GREEN}" "✓" "${service_status}"
            ;;
        "running (disabled)"|"stopped"*)
            print_status_line "Service" "${YELLOW}" "✗" "${service_status}"
            ;;
        *)
            print_status_line "Service" "${RED}" "✗" "${service_status}"
            ;;
    esac
}

show_requirements() {
    local software_name="${SOFTWARE_NAME:-"[SOFTWARE_NAME]"}"
    local service_name="${SERVICE_NAME:-"[SERVICE_NAME]"}"
    local service_path="${SERVICE_PATH:-"[SERVICE_PATH]"}"
    local install_path="${INSTALL_PATH:-"[INSTALL_PATH]"}"
    local dependencies="none"
    local os_info="Linux"

    if [[ "${#DEPENDENCIES[@]}" -gt 0 ]]; then
        dependencies="$(printf '%s, ' "${!DEPENDENCIES[@]}" | sed 's/, $//')"
    fi

    if [[ -r /etc/os-release ]]; then
        os_info="$(. /etc/os-release 2>/dev/null && printf '%s' "${PRETTY_NAME:-${NAME:-Linux}}" || true)"
        os_info="${os_info:-Linux}"
    fi

    print_section "System Requirements"
    echo "Required for ${software_name}:"
    echo "  • Operating System: ${os_info}"
    echo "  • Required packages: ${dependencies}"
    echo "  • Installation path: ${install_path}"
    if [[ -n "${service_name}" && "${service_name}" != "[SERVICE_NAME]" ]]; then
        echo "  • Service file: ${service_path}"
    fi
}

show_version() {
    local software_name="${SOFTWARE_NAME:-"[SOFTWARE_NAME]"}"
    local version="${VERSION:-"[VERSION]"}"
    local last_modified="${LAST_MODIFIED:-"[LAST_MODIFIED]"}"
    local author="${AUTHOR:-"[AUTHOR]"}"

    echo "${software_name}"
    echo "Version: v${version} (${last_modified})"
    echo "Author: ${author}"
    echo "License: MIT"
}
