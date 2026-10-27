#!/bin/bash
# lib/runtime/daemon.sh
#
# DynDNS
#
# Author: Manuel Ziel
# License: MIT

################################################################################
# CORE UTILITIES & STATUS
################################################################################

is_running() {
    local pid_file="${PID_FILE}"
    local pid
    local python_script="${PYTHON_SCRIPT:-"${BIN_DIR}/${SOFTWARE_DIR_NAME}.py"}"

    # Check PID file first
    if [[ -f "${pid_file}" ]]; then
        pid=$(cat "${pid_file}" 2>/dev/null)
        if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
            return 0
        else
            rm -f "${pid_file}"
        fi
    fi

    # More specific pattern to avoid false positives (e.g., editors)
    if pgrep -f "^python3 .*${python_script}" > /dev/null 2>&1; then
        return 0
    fi

    return 1
}

################################################################################
# PID FILE MANAGEMENT
################################################################################

remove_pid_file() {
    local pid_file="${PID_FILE}"

    if [[ -f "${pid_file}" ]]; then
        rm -f "${pid_file}"
    fi
}

################################################################################
# DAEMON OPERATIONS
################################################################################

start_daemon() {
    local software_name="${SOFTWARE_NAME:-"[SOFTWARE_NAME]"}"
    local enable_python="${ENABLE_PYTHON:-0}"

    print_info "Starting ${software_name} in daemon mode..."

    if is_running; then
        print_warning "${software_name} is already running"
        return 0
    fi

    # Note: PID file is created by start_python_application() with the Python PID
    # Do NOT create PID file here with bash's $$ - that would be wrong for forking services
    if [[ "${enable_python}" -eq 1 ]]; then
        if ! setup_python_environment; then
            print_error "Failed to setup Python environment"
            cleanup_and_exit 1
        fi
    fi

    do_main_work "$@"
}
