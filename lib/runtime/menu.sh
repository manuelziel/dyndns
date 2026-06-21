#!/bin/bash
# lib/runtime/menu.sh - Interactive menu functions
#
# DynDNS
#
# Author: Manuel Ziel
# License: MIT
#
# This program is free software: you can redistribute it and/or modify

################################################################################
# INTERACTIVE MENU
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

        options+=("${option_num}) Start")
        option_actions+=("start_application")
        ((option_num++))

        options+=("${option_num}) Stop")
        option_actions+=("stop_application")
        ((option_num++))

        options+=("${option_num}) Restart")
        option_actions+=("restart_application")
        ((option_num++))

        options+=("${option_num}) Setup Virtual Environment")
        option_actions+=("setup_virtual_environment")
        ((option_num++))

        options+=("${option_num}) Configure")
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
                    export DAEMON_MODE=1
                    start_application
                    ;;
                "stop_application")
                    stop_application
                    ;;
                "restart_application")
                    export DAEMON_MODE=1
                    restart_application
                    ;;
                "setup_virtual_environment")
                    if [[ ${enable_python} -eq 1 ]]; then
                        setup_virtual_environment
                    else
                        print_warning "Python support is not enabled in the config."
                    fi
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
            print_error "Invalid selection. Enter a number between 0 and ${max_choice}."
        fi

        if [[ "${action:-}" != "exit" ]] && [[ "${action:-}" != "configure_application" ]] && [[ "${action:-}" != "restart_application" ]]; then
            echo ""
            read -rp "Press Enter to continue..." 
        fi
    done
}

################################################################################
# HELP AND STATUS
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
    echo "  start                            # Start ${software_name}"
    echo "  stop                             # Stop ${software_name}"
    echo "  restart                          # Restart ${software_name}"
    echo "  setup-env                        # Setup Python virtual environment"
    echo "  config                           # Configure ${software_name}"
    echo "  status                           # Show ${software_name} status"
    echo "  help, --help, -h                 # Show this help"
    echo "  version                          # Show version information"
    echo ""
    echo "Options:"
    echo "  --interactive, -i                # Force interactive mode"
    echo "  --daemon, -d                     # Run in daemon mode (for start action)"
    echo "  --quiet, -q                      # Quiet mode (suppress output)"
    echo "  --version, -v                    # Show version information"
    echo "  --help, -h                       # Show this help"
    echo ""
    echo "Examples:"
    echo "  ${cmd_name} start                # Start ${software_name}"
    echo "  ${cmd_name} start --daemon       # Start as daemon"
    echo "  ${cmd_name} stop                 # Stop ${software_name}"
    echo "  ${cmd_name} restart              # Restart ${software_name}"
    echo "  ${cmd_name} setup-env            # Setup Python virtual environment"
    echo ""
    echo "View logs:"
    echo "  sudo journalctl -u ${SERVICE_NAME:-${cmd_name}} -n 50 --no-pager"
    echo "  sudo journalctl -u ${SERVICE_NAME:-${cmd_name}} -f"
    echo ""
    echo "  ${cmd_name} config               # Configure application"
    echo "  ${cmd_name} status               # Show status"
    echo "  ${cmd_name} --interactive        # Show interactive menu"
    echo "  ${cmd_name} --help               # Show this help"
    echo "  ${cmd_name} --version            # Show version information"
    echo ""
}

show_status() {
    local install_path="${INSTALL_PATH:-"[INSTALL_PATH]"}"
    local config_file="${CONFIG_FILE:-"[CONFIG_FILE]"}"

    show_software_status
    show_dependencies_status
    show_service_status
    show_daemon_status
    
    echo ""
    echo "Configuration:"
    echo "  Install path:  ${install_path}"
    echo "  Config file:   ${config_file}"
}