#!/bin/bash
# lib/runtime/application.sh - Application lifecycle control and configuration
#
# DynDNS
#
# Author: Manuel Ziel
# License: MIT

set -euo pipefail

################################################################################
# CORE APPLICATION LOGIC
################################################################################

do_main_work() {
    local exit_code=0

    start_python_application "$@" || exit_code=$?
    return "${exit_code}"
}

# Return 0 if start/stop/restart should be delegated to systemctl.
# Delegates whenever the systemd unit is installed and we are NOT already
# executing inside a systemd unit invocation (INVOCATION_ID / SYSTEMD_EXEC_PID).
should_delegate_to_systemctl() {
    if [[ -n "${INVOCATION_ID:-}" || -n "${SYSTEMD_EXEC_PID:-}" ]]; then
        return 1
    fi
    if ! command -v systemctl >/dev/null 2>&1; then
        return 1
    fi
    service_exists
}

################################################################################
# BASIC APPLICATION CONTROL
################################################################################

send_signal() {
    local pid="$1"
    local signal="$2"
    local exit_code=0

    if kill -0 "${pid}" 2>/dev/null; then
        kill -"${signal}" "${pid}" 2>/dev/null || exit_code=$?
        return "${exit_code}"
    fi

    return 1
}

_resolve_stop_target_pids() {
    local pid_file="${PID_FILE:-"[PID_FILE]"}"
    local pid=""

    if [[ -f "${pid_file}" ]]; then
        pid="$(tr -d '[:space:]' < "${pid_file}" 2>/dev/null || true)"
        if _is_daemon_pid "${pid}"; then
            echo "${pid}"
            return 0
        fi
    fi

    _find_fallback_daemon_pids
}

_filter_alive_daemon_pids() {
    local pid_list="$1"
    local pid

    for pid in ${pid_list}; do
        if _is_daemon_pid "${pid}"; then
            echo "${pid}"
        fi
    done
}

_terminate_daemon_pids() {
    local target_pids="$1"
    local max_wait="${DAEMON_STOP_MAX_WAIT:-10}"
    local poll_interval="${DAEMON_STOP_POLL_INTERVAL:-1}"
    local count=0 remaining_pids="" pid

    print_info "Sending termination signal to processes..."
    for pid in ${target_pids}; do
        send_signal "${pid}" "TERM" || true
    done

    print_info "Waiting to terminate the processes..."
    while [[ "${count}" -lt "${max_wait}" ]]; do
        remaining_pids="$(_filter_alive_daemon_pids "${target_pids}")"
        [[ -z "${remaining_pids}" ]] && return 0
        sleep "${poll_interval}"
        count=$((count + 1))
    done

    print_warning "Processes did not terminate, forcing shutdown..."
    for pid in ${remaining_pids}; do
        send_signal "${pid}" "KILL" || true
    done
    sleep "${poll_interval}"
    remaining_pids="$(_filter_alive_daemon_pids "${target_pids}")"
    [[ -z "${remaining_pids}" ]]
}

start_application() {
    local software_name="${SOFTWARE_NAME:-"[SOFTWARE_NAME]"}"
    local service_name="${SERVICE_NAME:-"[SERVICE_NAME]"}"
    local exit_code=0

    print_info "Starting ${software_name}..."

    if should_delegate_to_systemctl; then
        print_info "Delegating to systemd: systemctl start ${service_name}"
        service_start || exit_code=$?
        return "${exit_code}"
    fi

    if is_running; then
        print_warning "${software_name} is already running"
        return 0
    fi

    do_main_work "$@" || exit_code=$?
    return "${exit_code}"
}

start_daemon() {
    local software_name="${SOFTWARE_NAME:-"[SOFTWARE_NAME]"}"
    local service_name="${SERVICE_NAME:-"[SERVICE_NAME]"}"
    local exit_code=0

    print_info "Starting ${software_name} in daemon mode..."

    if should_delegate_to_systemctl; then
        print_info "Delegating to systemd: systemctl start ${service_name}"
        service_start || exit_code=$?
        return "${exit_code}"
    fi

    if is_running; then
        print_warning "${software_name} is already running"
        return 0
    fi

    do_main_work "$@" || exit_code=$?
    return "${exit_code}"
}

_log_stop_targets() {
    local target_pids="$1"
    local pid_count pid_list
    pid_count="$(printf '%s\n' "${target_pids}" | wc -l)"
    pid_list="$(printf '%s\n' "${target_pids}" | tr '\n' ',' | sed 's/,/, /g; s/, $//')"
    print_info "Found ${pid_count} process(es): ${pid_list}"
}

stop_application() {
    local software_name="${SOFTWARE_NAME:-"[SOFTWARE_NAME]"}"
    local service_name="${SERVICE_NAME:-"[SERVICE_NAME]"}"
    local exit_code=0 target_pids=""

    print_info "Stopping ${software_name}..."
    if should_delegate_to_systemctl; then
        print_info "Delegating to systemd: systemctl stop ${service_name}"
        service_stop || exit_code=$?
        return "${exit_code}"
    fi
    target_pids="$(_resolve_stop_target_pids)"
    if [[ -z "${target_pids}" ]]; then
        remove_pid_file
        print_info "${software_name} is not running"
        return 0
    fi
    _log_stop_targets "${target_pids}"
    if _terminate_daemon_pids "${target_pids}"; then
        remove_pid_file
        print_success "${software_name} stopped"
        return 0
    fi
    print_error "Failed to stop some processes"
    return 1
}

restart_application() {
    local software_name="${SOFTWARE_NAME:-"[SOFTWARE_NAME]"}"
    local service_name="${SERVICE_NAME:-"[SERVICE_NAME]"}"
    local restart_delay="${DAEMON_RESTART_DELAY:-2}"
    local exit_code=0

    print_info "Restarting ${software_name}..."

    if should_delegate_to_systemctl; then
        print_info "Delegating to systemd: systemctl restart ${service_name}"
        service_restart || exit_code=$?
        return "${exit_code}"
    fi

    stop_application || exit_code=$?
    if [[ "${exit_code}" -ne 0 ]]; then
        return "${exit_code}"
    fi
    sleep "${restart_delay}"

    start_application "$@" || exit_code=$?
    return "${exit_code}"
}

################################################################################
# CONFIGURATION MANAGEMENT
################################################################################

configure_application() {
    local software_name="${SOFTWARE_NAME:-"[SOFTWARE_NAME]"}"
    local config_file="${CONFIG_FILE:-"[CONFIG_FILE]"}"
    local exit_code=0

    print_section "Configuring ${software_name}"

    if is_running; then
        print_info "Daemon is currently ${GREEN}running${NC}"
        print_info "Configuration changes may require daemon restart to take effect"
    else
        print_info "Daemon is currently ${DIM}not running${NC}"
    fi

    echo ""
    print_info "Configuration options:"
    echo "  • Config file: ${config_file}"
    echo ""

    print_info "Starting interactive configuration menu..."

    if [[ "${ENABLE_PYTHON:-0}" -eq 1 ]]; then
        start_python_cli "config" "$@" || exit_code=$?
    else
        print_warning "Python support not enabled"
        print_info "Edit configuration files manually"
    fi

    return "${exit_code}"
}
