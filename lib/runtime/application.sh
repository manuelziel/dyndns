#!/bin/bash
# lib/runtime/application.sh
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
# 1. CORE APPLICATION LOGIC
################################################################################

do_main_work() {
    # For IONOS-DYNDNS: Start Python application
    start_python_application "$@"
    
    #print_success "Main work completed"
    
    return 0
}

################################################################################
# 2. BASIC APPLICATION CONTROL  
################################################################################

start_application() {
    local software_name="${SOFTWARE_NAME:-"[SOFTWARE_NAME]"}"

    print_info "Starting ${software_name}..."
    
    if is_running; then
        print_warning "${software_name} is already running"
        return 0
    fi
    
    do_main_work

    # print_success "${software_name} running successfully"
}

stop_application() {
    local software_name="${SOFTWARE_NAME:-"[SOFTWARE_NAME]"}"
    local pid_file="${PID_FILE}"
    local pid
    local count=0

    print_info "Stopping ${software_name}..."

    if [[ -f "${pid_file}" ]]; then
        pid=$(cat "${pid_file}" 2>/dev/null)
        if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
            print_info "Sending TERM signal to process ${pid}"
            kill -TERM "${pid}"
            
            # Wait for graceful shutdown
            while [[ ${count} -lt 10 ]] && kill -0 "${pid}" 2>/dev/null; do
                sleep 1
                ((count++))
            done
            
            # Force kill if still running
            if kill -0 "${pid}" 2>/dev/null; then
                print_warning "Process still running, forcing shutdown"
                kill -KILL "${pid}" 2>/dev/null
            fi
        fi
        rm -f "${pid_file}"
    fi

    print_success "${software_name} stopped"
}

restart_application() {
    local software_name="${SOFTWARE_NAME:-"[SOFTWARE_NAME]"}"

    print_info "Restarting ${software_name}..."
    stop_application
    sleep 2
    start_application
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

# Can be called while daemon is running or when stopped
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
    echo "  • Configuration file: ${config_file}"
    echo "  • PID file: ${pid_file}"
    echo ""
    
    print_info "Starting interactive configuration menu..."
    
    if [[ ${ENABLE_PYTHON:-0} -eq 1 ]]; then
        # Pass "config" command to Python CLI
        # CLI runs independently - can configure even while daemon is running
        start_python_cli "config"
    else
        print_warning "Python support not enabled"
        print_info "Edit configuration files manually"
    fi
    
    return 0
}