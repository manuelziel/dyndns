#!/bin/bash
# lib/runtime/daemon.sh - Daemon runtime functions
#
# IONOS-DYNDNS
#
# Author: Manuel Ziel
# License: MIT
#
# This program is free software: you can redistribute it and/or modify

################################################################################
# CORE UTILITIES & STATUS
################################################################################

is_running() {
    local pid_file="${PID_FILE}"
    local pid
    local python_script="${PYTHON_SCRIPT:-"${BIN_DIR}/${SOFTWARE_DIR_NAME}.py"}"

    if [[ -f "${pid_file}" ]]; then
        pid=$(cat "${pid_file}" 2>/dev/null)
        if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
            return 0
        else
            rm -f "${pid_file}"
        fi
    fi

    if pgrep -f "^python3 .*${python_script}" > /dev/null 2>&1; then
        return 0
    fi

    return 1
}

get_daemon_status() {
    local software_name="${SOFTWARE_NAME:-"[SOFTWARE_NAME]"}"
    local pid_file="${PID_FILE}"
    local pid

    if is_running; then
        pid=$(cat "${pid_file}" 2>/dev/null)
        print_success "${software_name} is running (PID: ${pid})"
        return 0
    else
        print_warning "${software_name} is not running"
        return 1
    fi
}

################################################################################
# PID FILE MANAGEMENT
################################################################################

create_pid_file() {
    local pid_file="${PID_FILE}"

    echo "$$" > "${pid_file}"
    if [[ $? -ne 0 ]]; then
        print_error "Failed to create PID file: ${pid_file}"
        cleanup_and_exit 1
    fi
}

remove_pid_file() {
    local pid_file="${PID_FILE}"

    if [[ -f "${pid_file}" ]]; then
        rm -f "${pid_file}"
    fi
}

################################################################################
# SIGNAL HANDLING & LIFECYCLE
################################################################################

setup_signal_handlers() {
    trap 'print_info "Received SIGTERM, shutting down gracefully..."; exit 0' TERM
    trap 'print_info "Received SIGINT, shutting down gracefully..."; exit 0' INT
    trap 'print_warning "Received SIGHUP, ignoring signal..."; :' HUP
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
        return 1
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

stop_daemon() {
    local software_name="${SOFTWARE_NAME:-"[SOFTWARE_NAME]"}"

    print_info "Stopping ${software_name}..."

    if ! is_running; then
        print_warning "${software_name} is not running"
        return 0
    fi

    stop_application
    remove_pid_file
    
    return 0
}