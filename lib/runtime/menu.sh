#!/bin/bash
# lib/runtime/menu.sh - Interactive menu functions
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
# 1. INTERACTIVE MENU
################################################################################

show_interactive_menu() {
    local software_name="${SOFTWARE_NAME:-"[SOFTWARE_NAME]"}"
    local version="${VERSION:-"[VERSION]"}"
    local description="${SOFTWARE_DESCRIPTION:-"[SOFTWARE_DESCRIPTION]"}"
    local service_name="${SERVICE_NAME:-"[SERVICE_NAME]"}"
    local choice
    local options=()
    local option_actions=()
    local option_num=1
    local action
    local enable_python="${ENABLE_PYTHON:-0}"

    while true; do
        clear
        print_banner "Runtime"

        show_status

        options=()
        option_actions=()
        option_num=1

        options+=("${option_num}) Start Application")
        option_actions+=("start_application")
        ((option_num++))

        options+=("${option_num}) Stop Application")
        option_actions+=("stop_application")
        ((option_num++))

        options+=("${option_num}) Restart Application")
        option_actions+=("restart_application")
        ((option_num++))

        options+=("${option_num}) Show Recent Logs")
        option_actions+=("show_recent_logs")
        ((option_num++))

        options+=("${option_num}) Show Live Logs")
        option_actions+=("show_live_logs")
        ((option_num++))

        options+=("${option_num}) Setup Virtual Environment")
        option_actions+=("setup_virtual_environment")
        ((option_num++))

        options+=("${option_num}) Install Dependencies")
        option_actions+=("install_dependencies")
        ((option_num++))

        options+=("${option_num}) Configure Application")
        option_actions+=("configure_application")
        ((option_num++))

        options+=("${option_num}) Show Status")
        option_actions+=("show_status")
        ((option_num++))

        options+=("${option_num}) Help")
        option_actions+=("help")
        ((option_num++))

        local max_choice=$((option_num - 1))

        options+=("0) Exit")
        option_actions+=("exit")

        echo ""
        echo -e "${BLUE}Available options:${NC}"
        printf '%s\n' "${options[@]}" | sed 's/^/  /'
        echo ""

        read -rp "Enter your choice (0-${max_choice}): " choice
        echo ""

        # Validate and execute choice
        if [[ "${choice}" == "0" ]]; then
            action="exit"
        elif [[ "${choice}" =~ ^[0-9]+$ ]] && [[ "${choice}" -ge 1 ]] && [[ "${choice}" -le "${max_choice}" ]]; then
            action="${option_actions[$((choice-1))]:-unknown}"
        else
            action="invalid"
        fi

        if [[ "${action}" != "invalid" ]]; then

            case "${action}" in
                "start_application")
                    start_application
                    ;;
                "stop_application")
                    stop_application
                    ;;
                "restart_application")
                    restart_application
                    ;;
                "show_recent_logs")
                    show_recent_logs
                    ;;
                "show_live_logs")
                    show_live_logs
                    ;;
                "setup_virtual_environment")
                    if [[ ${enable_python} -eq 1 ]]; then
                        setup_virtual_environment
                    else
                        print_warning "Python support is not enabled in the config."
                    fi
                    ;;
                "install_dependencies")
                    install_dependencies
                    ;;
                "configure_application")
                    configure_application
                    ;;
                "show_status")
                    show_status
                    ;;
                "help")
                    show_help
                    ;;
                "exit")
                    print_info "Exiting interactive menu."
                    return 0
                    ;;
                *)
                    print_error "Invalid action: $action"
                    read -rp "Press Enter to continue..."
                    ;;
            esac
        else
            print_error "Invalid selection. Please enter a number between 0 and ${max_choice}."
            read -rp "Press Enter to continue..."
        fi

        if [[ "${action:-}" != "exit" ]]; then
            echo ""
            read -rp "Press Enter to continue..." 
        fi
    done
}

################################################################################
# 2. HELP AND STATUS
################################################################################

show_help() {
    local software_name="${SOFTWARE_NAME:-"[SOFTWARE_NAME]"}"
    local version="${VERSION:-"[VERSION]"}"
    local cmd_name="${SOFTWARE_DIR_NAME:-$(basename "$0")}"

    print_section "${software_name}" "v${version}"
    echo ""
    echo "Usage: ${cmd_name} [ACTION] [OPTIONS]"
    echo ""
    echo "Actions:"
    echo "  start                   # Start ${software_name}"
    echo "  stop                    # Stop ${software_name}"
    echo "  restart                 # Restart ${software_name}"
    echo "  recent-logs             # Show recent ${software_name} logs"
    echo "  live-logs               # Show live ${software_name} logs"
    echo "  setup-env               # Setup Python virtual environment"
    echo "  install-deps            # Install ${software_name} dependencies"
    echo "  config                  # Configure ${software_name}"
    echo "  status                  # Show ${software_name} status"
    echo "  help, -h                # Show this help"
    echo "  version                 # Show version information"
    echo ""
    echo "Options:"
    echo "  --interactive, -i       # Force interactive mode"
    echo "  --daemon, -d            # Run in daemon mode (for start action)"
    echo "  --quiet, -q             # Quiet mode (suppress output)"
    echo "  --version, -v           # Show version information"
    echo "  --help, -h              # Show this help"
    echo ""
    echo "Examples:"
    echo "  ${cmd_name} start                # Start ${software_name}"
    echo "  ${cmd_name} start --daemon       # Start as daemon"
    echo "  ${cmd_name} stop                 # Stop ${software_name}"
    echo "  ${cmd_name} restart              # Restart ${software_name}"
    echo "  ${cmd_name} recent-logs          # Show recent logs"
    echo "  ${cmd_name} live-logs            # Show live logs"
    echo "  ${cmd_name} setup-env            # Setup Python virtual environment"
    echo "  ${cmd_name} install-deps         # Install dependencies"
    echo "  ${cmd_name} config               # Configure application"
    echo "  ${cmd_name} status               # Show status"
    echo "  ${cmd_name} --interactive        # Show interactive menu"
    echo "  ${cmd_name} --help               # Show this help"
    echo "  ${cmd_name} --version            # Show version information"
    echo ""
}

show_status() {
    local install_path="${INSTALL_PATH:-"[INSTALL_PATH]"}"
    local pid_file="${PID_FILE:-"[PID_FILE]"}"
    local config_file="${CONFIG_FILE:-"[CONFIG_FILE]"}"

    show_software_status
    show_dependencies_status
    show_service_status
    show_daemon_status
    
    echo ""
    echo "Configuration:"
    echo "  File directory: ${install_path}"
    echo "  PID file: ${pid_file}"
    echo "  Config file: ${config_file}"
}