#!/bin/bash
# lib/runtime/application.sh
#
# DynDNS
#
# Author: Manuel Ziel
# License: MIT

################################################################################
# CORE APPLICATION LOGIC
################################################################################

do_main_work() {
    start_python_application "$@"

    return $?
}

# Return 0 if start/stop/restart should be delegated to systemctl.
# True when a systemd unit is installed AND SERVICE_USER differs from the
# current user. Running the daemon directly as root in that case would
# create data files with the wrong ownership and break the next
# systemd-managed start with "readonly database" or similar errors.
should_delegate_to_systemctl() {
    local service_user="${SERVICE_USER:-root}"
    local service_name="${SERVICE_NAME:-${SOFTWARE_DIR_NAME}.service}"

    if ! command -v systemctl >/dev/null 2>&1; then
        return 1
    fi
    if ! systemctl list-unit-files --no-legend "${service_name}" 2>/dev/null \
            | grep -q "^${service_name}"; then
        return 1
    fi
    if [[ -z "${service_user}" || "${service_user}" == "$(id -un)" ]]; then
        return 1
    fi
    return 0
}

################################################################################
# BASIC APPLICATION CONTROL
################################################################################

send_signal() {
    local pid="$1"
    local signal="$2"
    
    if ! kill -0 "${pid}" 2>/dev/null; then
        if sudo kill -0 "${pid}" 2>/dev/null; then
            sudo kill -"${signal}" "${pid}" 2>/dev/null
            return $?
        fi
        return 1
    fi
    
    kill -"${signal}" "${pid}" 2>/dev/null
    return $?
}

start_application() {
    local software_name="${SOFTWARE_NAME:-"[SOFTWARE_NAME]"}"
    local service_name="${SERVICE_NAME:-${SOFTWARE_DIR_NAME}.service}"

    print_info "Starting ${software_name}..."

    if is_running; then
        print_warning "${software_name} is already running"
        return $?
    fi

    # Delegate to systemd so the daemon runs under the configured SERVICE_USER
    # instead of the invoking root shell (prevents root-owned data files).
    if should_delegate_to_systemctl; then
        print_info "Delegating to systemd: systemctl start ${service_name}"
        service_start
        return $?
    fi

    do_main_work "$@"
}

stop_application() {
    local software_name="${SOFTWARE_NAME:-"[SOFTWARE_NAME]"}"
    local service_name="${SERVICE_NAME:-${SOFTWARE_DIR_NAME}.service}"
    local pid_file="${PID_FILE}"
    local python_script="${PYTHON_SCRIPT}"
    local count=0
    local max_wait=10

    print_info "Stopping ${software_name}..."

    # Prefer systemd when it owns the lifecycle; direct kill would leave
    # the unit in a failed state and trigger auto-restart.
    if should_delegate_to_systemctl; then
        print_info "Delegating to systemd: systemctl stop ${service_name}"
        service_stop
        return $?
    fi

    local all_pids=$(pgrep -f "^python3 .*${python_script}" || true)
    local remaining_pids
    local pid_list=""
    
    # Format PIDs as comma-separated list for better readability
    if [[ -n "${all_pids}" ]]; then
        local pid_count=$(echo "${all_pids}" | wc -l)
        pid_list=$(echo "${all_pids}" | tr '\n' ',' | sed 's/,/, /g' | sed 's/, $//')
        print_info "Found ${pid_count} process(es): ${pid_list}"
    else
        remove_pid_file
        print_info "${software_name} is not running"
        return 0
    fi

    print_info "Sending termination signal to processes..."
    for pid in ${all_pids}; do
        send_signal "${pid}" "TERM"
    done

    print_info "Waiting to terminate the processes..."
    while [[ "${count}" -lt "${max_wait}" ]]; do
        remaining_pids=$(pgrep -f "^python3 .*${python_script}" || true)
        if [[ -z "${remaining_pids}" ]]; then
            break
        fi
        sleep 1
        count=$((count + 1))
    done

    # Force kill any remaining processes
    remaining_pids=$(pgrep -f "^python3 .*${python_script}" || true)
    if [[ -n "${remaining_pids}" ]]; then
        print_warning "Processes did not terminate, forcing shutdown..."
        for pid in ${remaining_pids}; do
            send_signal "${pid}" "KILL"
        done
        sleep 1
    fi

    print_info "Cleaning up..."
    remove_pid_file
    remaining_pids=$(pgrep -f "^python3 .*${python_script}" || true)

    if [[ -z "${remaining_pids}" ]]; then
        print_success "${software_name} stopped"
    else
        print_error "Failed to stop some processes"
        return 1
    fi
}

restart_application() {
    local software_name="${SOFTWARE_NAME:-"[SOFTWARE_NAME]"}"
    local restart_delay=2

    print_info "Restarting ${software_name}..."

    # stop_application and start_application already delegate to systemctl
    # when appropriate; no need to duplicate the branch here.
    stop_application
    sleep "${restart_delay}"

    start_application "$@"
}

################################################################################
# CONFIGURATION MANAGEMENT
################################################################################

configure_application() {
    local software_name="${SOFTWARE_NAME:-"[SOFTWARE_NAME]"}"
    local config_file="${CONFIG_FILE:-"[CONFIG_FILE]"}"
    local pid_file="${PID_FILE}"

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
        start_python_cli "config"
    else
        print_warning "Python support not enabled"
        print_info "Edit configuration files manually"
    fi

    return $?
}