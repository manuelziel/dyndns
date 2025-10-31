#!/bin/bash
# lib/setup/menu.sh - Interactive menu functions
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
    
    while true; do
        clear
        print_banner "Setup"
        
        show_status
        
        # Build menu options based on current state
        options=()
        option_actions=()
        option_num=1
        
        if is_installed; then
            options+=("${option_num}) Update ${software_name}")
            option_actions+=("update")
            ((option_num++))
            
            options+=("${option_num}) Reinstall (current version)")
            option_actions+=("reinstall")
            ((option_num++))

            options+=("${option_num}) Uninstall ${software_name}")
            option_actions+=("uninstall")
            ((option_num++))
            
            # Service management options
            if [[ -n "${service_name}" ]] && [[ "${service_name}" != "[service-name].service" ]]; then
                if service_active; then
                    options+=("${option_num}) Stop service")
                    option_actions+=("stop")
                    ((option_num++))
                else
                    options+=("${option_num}) Start service")
                    option_actions+=("start")
                    ((option_num++))
                fi
                
                if service_enabled; then
                    options+=("${option_num}) Disable auto-start")
                    option_actions+=("disable")
                    ((option_num++))
                else
                    options+=("${option_num}) Enable auto-start")
                    option_actions+=("enable")
                    ((option_num++))
                fi
            fi

            options+=("${option_num}) View detailed status")
            option_actions+=("status")
            ((option_num++))
        else
            options+=("${option_num}) Install ${software_name}")
            option_actions+=("install")
            ((option_num++))
            
            options+=("${option_num}) Check system requirements")
            option_actions+=("requirements")
            ((option_num++))

            options+=("${option_num}) Show version information")
            option_actions+=("version")
            ((option_num++))
        fi

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
                "install")
                    if check_and_install_dependencies; then
                        do_install
                        break
                    else
                        print_error "Cannot proceed with installation"
                    fi
                    ;;
                "update")
                    if check_and_install_dependencies; then
                        do_update
                        break
                    else
                        print_error "Cannot proceed with update"
                    fi
                    ;;
                "reinstall")
                    if check_and_install_dependencies; then
                        do_reinstall
                        break
                    else
                        print_error "Cannot proceed with reinstallation"
                    fi
                    ;;
                "uninstall")
                    do_uninstall
                    break
                    ;;
                "start")
                    if service_start; then
                        print_success "Service started successfully"
                    else
                        print_error "Failed to start service"
                    fi
                    ;;
                "stop")
                    if service_stop; then
                        print_success "Service stopped successfully"
                    else
                        print_error "Failed to stop service"
                    fi
                    ;;
                "enable")
                    if service_enable; then
                        print_success "Auto-start enabled"
                    else
                        print_error "Failed to enable auto-start"
                    fi
                    ;;
                "disable")
                    if service_disable; then
                        print_success "Auto-start disabled"
                    else
                        print_error "Failed to disable auto-start"
                    fi
                    ;;
                "status")
                    show_status
                    ;;
                "requirements")
                    show_requirements
                    ;;
                "version")
                    show_version
                    ;;
                "exit")
                    print_info "Cancelled by user."
                    return 0
                    ;;
                *)
                    print_error "Unknown action: ${action}"
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

    print_section "${software_name}" "Setup" "v${version}"
    echo ""
    echo "Usage: $0 [ACTION] [OPTIONS]"
    echo ""
    echo "Actions:"
    echo "  install                     Install ${software_name}"
    echo "  update                      Update to latest version"
    echo "  reinstall                   Reinstall current version"
    echo "  uninstall                   Uninstall ${software_name}"
    echo "  status                      Show installation status"
    echo "  help, -h                    Show this help message"
    echo "  version                     Show version information"
    echo ""
    echo "Options (can be combined):"
    echo "  --upgrade                   Upgrade to latest version"
    echo "  --remove                    Remove ${software_name}"
    echo "  --info                      Show installation status"
    echo "  --version, -v               Show version information"
    echo "  --interactive, -i           Force interactive mode (default)"
    echo "  --quiet, -q                 Suppress non-essential output"
    echo "  --force, -f                 Skip confirmation prompts"
    echo "  --no-deps                   Skip dependency checking"
    echo "  --debug                     Enable debug output"
    echo ""
    echo "Examples:"
    echo "  $0                          Interactive setup menu (default)"
    echo "  $0 install                  Install with prompts"
    echo "  $0 install --force          Silent installation"
    echo "  $0 update                   Update existing installation"
    echo "  $0 status                   Show current status"
    echo "  $0 --debug                  Enable debug output"
    echo ""
}

show_status() {    
    show_software_status
    show_dependencies_status
    show_internet_status
}