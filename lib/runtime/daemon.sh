#!/bin/bash
# lib/runtime/daemon.sh - Daemon status inspection and PID file helpers
#
# DynDNS
#
# Author: Manuel Ziel
# License: MIT

set -euo pipefail

################################################################################
# CORE UTILITIES & STATUS
################################################################################

_pid_exists() {
    local pid="$1"
    local err_msg=""

    [[ "${pid}" =~ ^[0-9]+$ && "${pid}" -gt 0 ]] || return 1
    [[ -d "/proc/${pid}" ]] && return 0
    kill -0 "${pid}" 2>/dev/null && return 0
    err_msg="$(LC_ALL=C kill -0 "${pid}" 2>&1 || true)"
    [[ "${err_msg}" == *"Operation not permitted"* || "${err_msg}" == *"EPERM"* ]]
}

_is_daemon_pid() {
    local pid="$1"
    local python_script="${PYTHON_SCRIPT:-"[PYTHON_SCRIPT]"}"
    local cmd_tokens=""
    local token

    _pid_exists "${pid}" || return 1

    if [[ -r "/proc/${pid}/cmdline" ]]; then
        cmd_tokens="$(tr '\0' '\n' < "/proc/${pid}/cmdline" 2>/dev/null || true)"
    else
        cmd_tokens="$(ps -p "${pid}" -o args= 2>/dev/null | tr ' ' '\n' || true)"
    fi

    [[ -n "${cmd_tokens}" && "${cmd_tokens}" == *"${python_script}"* ]] || return 1

    while IFS= read -r token; do
        case "${token}" in
            config|import|export|validate|--version|-v|--help|-h)
                return 1
                ;;
        esac
    done <<< "${cmd_tokens}"
    return 0
}

_find_fallback_daemon_pids() {
    local python_script="${PYTHON_SCRIPT:-"[PYTHON_SCRIPT]"}"
    local candidates=""
    local pid

    candidates="$(pgrep -f "(^|/)python3([0-9.]*)?[[:space:]].*${python_script}" 2>/dev/null || true)"
    [[ -n "${candidates}" ]] || return 0

    for pid in ${candidates}; do
        if _is_daemon_pid "${pid}"; then
            echo "${pid}"
        fi
    done
}

_get_running_pid() {
    local pid_file="${PID_FILE:-"[PID_FILE]"}"
    local service_name="${SERVICE_NAME:-"[SERVICE_NAME]"}"
    local pid=""

    if [[ -f "${pid_file}" ]]; then
        pid="$(tr -d '[:space:]' < "${pid_file}" 2>/dev/null || true)"
        if _is_daemon_pid "${pid}"; then
            echo "${pid}"
            return 0
        fi
    fi

    if command -v systemctl >/dev/null 2>&1 && service_exists && service_active; then
        pid="$(systemctl show -p MainPID --value "${service_name}" 2>/dev/null || true)"
        if [[ "${pid}" =~ ^[0-9]+$ && "${pid}" -gt 0 ]]; then
            echo "${pid}"
        fi
        return 0
    fi

    pid="$(_find_fallback_daemon_pids | head -n1 || true)"
    if [[ -n "${pid}" ]]; then
        echo "${pid}"
        return 0
    fi

    return 1
}

is_running() {
    _get_running_pid >/dev/null 2>&1
}

show_daemon_status() {
    local software_name="${SOFTWARE_NAME:-"[SOFTWARE_NAME]"}"
    local pid=""
    local start_time="unknown"

    if pid="$(_get_running_pid)"; then
        print_success "${software_name} is running (PID: ${pid:-unknown})"
        if [[ -n "${pid}" ]]; then
            start_time="$(ps -o lstart= -p "${pid}" 2>/dev/null | sed 's/^[[:space:]]*//' || true)"
            echo "  Process ID: ${pid}"
            echo "  Start time: ${start_time:-unknown}"
        fi
    else
        print_warning "${software_name} is not running"
    fi
}

################################################################################
# PID FILE MANAGEMENT
################################################################################

remove_pid_file() {
    local pid_file="${PID_FILE:-"[PID_FILE]"}"

    if [[ -f "${pid_file}" ]]; then
        rm -f "${pid_file}"
    fi
}
