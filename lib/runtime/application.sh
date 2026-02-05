#!/bin/bash
# lib/runtime/application.sh - Application runtime functions
#
# IONOS-DYNDNS
#
# Author: Manuel Ziel
# License: MIT
#
# This program is free software: you can redistribute it and/or modify
################################################################################
# 1. CORE APPLICATION LOGIC
################################################################################

do_main_work() {
    start_python_application "$@"
    
    return 0
}

################################################################################
# 2. BASIC APPLICATION CONTROL
################################################################################

send_signal() {
    local pid="$1"
    local signal="$2"
    
    if ! kill -0 "${pid}" 2>/dev/null; then
        if sudo kill -0 "${pid}" 2>/dev/null; then
            sudo kill -"${signal}" "${pid}" 2>/dev/null
            return 0
        fi
        return 1
    fi
    
    # Process accessible without sudo
    kill -"${signal}" "${pid}" 2>/dev/null
    return 0
}

start_application() {
    local software_name="${SOFTWARE_NAME:-"[SOFTWARE_NAME]"}"

    print_info "Starting ${software_name}..."
    
    if is_running; then
        print_warning "${software_name} is already running"
        return 0
    fi
    
    do_main_work "$@"
}

stop_application() {
    local software_name="${SOFTWARE_NAME:-"[SOFTWARE_NAME]"}"
    local pid_file="${PID_FILE}"
    local python_script="${PYTHON_SCRIPT}"
    local count=0
    local max_wait=10
    local all_pids=$(pgrep -f "^python3 .*${python_script}" || true)
    local remaining_pids
    local pid_list=""
    
    print_info "Stopping ${software_name}..."
    
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

    # Send TERM signal to all processes
    for pid in ${all_pids}; do
        send_signal "${pid}" "TERM"
    done

    # Wait for shutdown
    while [[ ${count} -lt ${max_wait} ]]; do
        remaining_pids=$(pgrep -f "^python3 .*${python_script}" || true)
        if [[ -z "${remaining_pids}" ]]; then
            break
        fi
        sleep 1
        ((count++))
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

    remove_pid_file

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
    stop_application
    sleep "${restart_delay}"

    # Pass all arguments to start
    start_application "$@"
}

################################################################################
# 3. ADVANCED APPLICATION CONTROL
################################################################################

run_application() {
    local software_name="${SOFTWARE_NAME:-"[SOFTWARE_NAME]"}"

    setup_signal_handlers

    print_info "${software_name} starting main loop..."

    while true; do
        if ! do_main_work; then
            print_error "Main work failed, retrying in 10 seconds..."
            sleep 10
            continue
        fi
        
        break
    done

    print_info "${software_name} finished"
}

################################################################################
# 4. CONFIGURATION MANAGEMENT
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
    
    if [[ ${ENABLE_PYTHON:-0} -eq 1 ]]; then
        start_python_cli "config"
    else
        print_warning "Python support not enabled"
        print_info "Edit configuration files manually"
    fi
    
    return 0
}