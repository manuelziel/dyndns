#!/bin/bash
# lib/runtime/daemon.sh
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

# Function to check if application is running
is_running() {
    local pid_file="${PID_FILE}"
    local pid

    if [[ -f "${pid_file}" ]]; then
        pid=$(cat "${pid_file}" 2>/dev/null)
        if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
            return 0
        else
            rm -f "${pid_file}"
        fi
    fi
    return 1
}

# Function to get daemon status
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
# 2. PID FILE MANAGEMENT
################################################################################

# Function to create PID file
create_pid_file() {
    local pid_file="${PID_FILE}"

    echo "$$" > "${pid_file}"
    if [[ $? -ne 0 ]]; then
        print_error "Failed to create PID file: ${pid_file}"
        cleanup_and_exit 1
    fi
}

# Function to remove PID file
remove_pid_file() {
    local pid_file="${PID_FILE}"

    if [[ -f "${pid_file}" ]]; then
        rm -f "${pid_file}"
    fi
}

################################################################################
# 3. SIGNAL HANDLING & LIFECYCLE
################################################################################

setup_signal_handlers() {
    trap 'print_info "Received SIGTERM, shutting down gracefully..."; exit 0' TERM
    trap 'print_info "Received SIGINT, shutting down gracefully..."; exit 0' INT
    trap 'print_warning "Received SIGHUP, ignoring signal..."; :' HUP
}

################################################################################
# 4. DAEMON OPERATIONS
################################################################################

start_daemon() {
    local software_name="${SOFTWARE_NAME:-"[SOFTWARE_NAME]"}"
    local enable_python="${ENABLE_PYTHON:-0}"

    print_info "Starting ${software_name} in daemon mode..."

    if is_running; then
        print_warning "${software_name} is already running"
        return 0
    fi
    
    create_pid_file

    if [[ "${enable_python}" -eq 1 ]]; then
        if ! setup_python_environment; then
            print_error "Failed to setup Python environment"
            cleanup_and_exit 1
        fi
    fi    
    do_main_work --daemon
}

stop_daemon() {
    local software_name="${SOFTWARE_NAME:-"[SOFTWARE_NAME]"}"
    local pid_file="${PID_FILE}"
    local pid

    print_info "Stopping ${software_name}..."

    if ! is_running; then
        print_warning "${software_name} is not running"
        return 0
    fi

    # Get the PID from the PID file when we know the service is running
    pid=$(cat "${pid_file}" 2>/dev/null)
    stop_application

    if kill "${pid}" 2>/dev/null; then
        print_success "${software_name} stopped successfully"
        remove_pid_file
        return 0
    else
        print_error "Failed to stop ${software_name}"
        return 1
    fi
}