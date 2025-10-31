#!/bin/bash
# lib/setup/install.sh - Installation and management functions
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
# 1. CORE INSTALLATION FUNCTIONS
################################################################################

do_install() {
    local software_name="${SOFTWARE_NAME:-"[SOFTWARE_NAME]"}"
    local force_mode="${FORCE_MODE:-0}"
    local create_service_flag="${CREATE_SERVICE:-false}"
    local service_name="${SERVICE_NAME:-"[service-name].service"}"

    print_section "Installing ${software_name}"

    if is_installed && [[ "${force_mode}" -eq 0 ]]; then
        print_warning "Software is already installed"
        print_info "Use --force or reinstall to reinstall"
        return 1
    fi
    
    if ! check_dependencies; then
        return 1
    fi
    
    backup_installation || true  # Don't fail if backup fails
    
    if ! install_files; then
        return 1
    fi

    if [[ "${create_service_flag}" == "true" ]]; then
        if create_service; then
            echo ""
            read -rp "Do you want to start and enable the service now? (y/n): " -n 1
            echo ""
            if [[ "${REPLY}" =~ ^[Yy]$ ]]; then
                if service_enabled && service_restart; then
                    print_success "Service started and enabled"
                else 
                    print_warning "Failed to start/enable service - you may need to do this manually"
                    print_info "Try: sudo systemctl start ${service_name}"
                    print_info "Enable on boot with: sudo systemctl enable ${service_name}"
                    print_info "Check status with: sudo systemctl status ${service_name}"
                fi
            else 
                print_info "You can start the service later with: sudo systemctl start ${service_name}"
                print_info "Enable on boot with: sudo systemctl enable ${service_name}"
                print_info "Check status with: sudo systemctl status ${service_name}"
            fi
        else 
            print_warning "Service creation failed, but continuing installation"
        fi
    fi

    print_success "${software_name} installed successfully!"

    echo ""
    print_info "Next steps:"
    echo "  • Configure: $0 --configure"
    echo "  • View status: $0 --status"
    
    return 0
}

do_update() {
    local software_name="${SOFTWARE_NAME:-"[SOFTWARE_NAME]"}"
    local current_version="$(get_installed_version)"
    local version="${VERSION:-"[VERSION]"}"
    local service_name="${SERVICE_NAME:-"[service-name].service"}"
    local old_force="${FORCE_MODE:-0}"
    local was_running="false"
    local enable_python="${ENABLE_PYTHON:-0}"
    local enable_optional_dependency="${ENABLE_OPTIONAL_DEPENDENCY:-0}"
    local install_result="0"

    if ! is_installed; then
        print_error "${software_name} is not installed"
        print_info "Use --install to install first"
        return 1
    fi

    print_section "Updating ${software_name}"
    print_info "Current version: ${current_version} -> New version: ${version}"

    FORCE_MODE=1

    if ! backup_installation; then
        print_warning "Backup failed, update continues"
    fi

    if [[ -n "${service_name}" ]] && [[ "${service_name}" != "[service-name].service" ]] && service_active; then
        was_running=true
        print_info "Stopping service for update..."

        if service_stop; then
            print_success "Service stopped"
        else
            print_warning "Failed to stop service, continuing anyway"
        fi
    elif [[ -n "${service_name}" ]] && [[ "${service_name}" != "[service-name].service" ]]; then
        print_info "Service is not running, no need to stop"
    fi

    if [[ "${enable_python}" -eq 1 ]]; then
        if ! setup_python_environment; then
            print_warning "Failed to update Python environment, but continuing..."
        fi
    fi

    # Optional dependencies. Create your own setup function in lib/optional.sh
    if [[ "${enable_optional_dependency}" -eq 1 ]]; then
        if ! setup_optional_function; then
            print_error "Failed to setup or install optional dependencies, but continuing..."
        fi
    fi
    
    if ! do_install; then
        print_error "Update failed!"
        install_result=1
    fi

    if [[ "${was_running}" == "true" ]] && [[ "${install_result}" -eq 0 ]]; then
        print_info "Restarting service..."
        if service_restart; then
            print_success "Service restarted successfully"
        else
            print_warning "Failed to restart service - you may need to start it manually"
            print_info "Try: sudo systemctl restart ${service_name}"
            print_info "Check status with: sudo systemctl status ${service_name}"
        fi
    elif [[ "${was_running}" == "true" ]] && [[ "${install_result}" -ne 0 ]]; then
        print_warning "Update failed - service remains stopped"
        print_info "You may need to restore from backup and restart service manually"
    fi
    
    # Restore original FORCE_MODE
    FORCE_MODE="${old_force}"

    if [[ "${install_result}" -eq 0 ]]; then
        print_success "Update completed successfully!"
        return 0
    else
        return 1
    fi
}

do_reinstall() {
    local software_name="${SOFTWARE_NAME:-"[SOFTWARE_NAME]"}"

    #print_section "Reinstalling ${software_name}"

    if FORCE_MODE=1 do_uninstall && FORCE_MODE=1 do_install; then
        print_success "Reinstallation completed successfully"
        return 0
    else
        print_error "Reinstallation failed"
        return 1
    fi
}

do_uninstall() {
    local software_name="${SOFTWARE_NAME:-"[SOFTWARE_NAME]"}"
    local force_mode="${FORCE_MODE:-0}"
    local service_path="${SERVICE_PATH:-"[SERVICE_PATH]"}"
    local install_path="${INSTALL_PATH:-"[INSTALL_PATH]"}"
    local bin_dir="${BIN_DIR}"
    local share_dir="${SHARE_DIR}"
    local bin_symlink="${BIN_SYMLINK}"

    print_section "Uninstalling ${software_name}"

    if ! is_installed; then
        print_warning "${software_name} is not installed"
        return 0
    fi
    
    if [[ "${force_mode}" -eq 0 ]]; then
        echo ""
        read -rp "Are you sure you want to uninstall ${software_name}? (y/n): " -n 1
        echo ""
        if [[ ! "${REPLY}" =~ ^[Yy]$ ]]; then
            print_info "Uninstall cancelled"
            return 0
        fi
    fi
    
    # Stop and remove service first
    if service_exists; then
        print_info "Stopping and removing service..."

        if service_stop && service_disable; then
            print_success "Service stopped and disabled"
            if rm -f "${service_path}"; then
                print_success "Service file removed"
                service_daemon_reload
            else
                print_warning "Failed to remove service file, but continuing..."
            fi
        else
            print_warning "Failed to stop/disable service, but continuing..."
        fi
    fi

    # Remove symlink
    if [[ -L "${bin_symlink}" ]]; then
        rm -f "${bin_symlink}"
        print_success "Symlink removed: ${bin_symlink}"
    fi

    # Remove entire bin directory
    if [[ -d "${bin_dir}" ]]; then
        rm -rf "${bin_dir}"
        print_success "Binary directory removed: ${bin_dir}"
    fi

    # Remove entire share directory  
    if [[ -d "${share_dir}" ]]; then
        rm -rf "${share_dir}"
        print_success "Share directory removed: ${share_dir}"
    fi

    print_success "${software_name} uninstalled completely!"
    return 0
}

do_configure() {
    local software_name="${SOFTWARE_NAME:-"[SOFTWARE_NAME]"}"
    local config_file="${CONFIG_FILE:-"[CONFIG_FILE]"}"

    print_section "Configuring ${software_name}"

    if ! is_installed; then
        print_error "${software_name} is not installed"
        print_info "Use --install to install first"
        return 1
    fi
    
    print_info "Configuration options:"
    echo "  • Service management: systemctl <start|stop|enable|disable> ${service_name}"
    echo "  • Configuration files: ${config_file}"

    # Add configuration logic here
    print_warning "Interactive configuration not implemented yet"
    print_info "Configure manually for now"
    
    return 0
}

################################################################################
# 2. HELPER FUNCTIONS - Setup and Utilities  
################################################################################

setup_directories() {
    local config_dir="${CONFIG_DIR:-"[CONFIG_DIR]"}"
    local data_dir="${DATA_DIR:-"[DATA_DIR]"}"

    print_info "Setting up directories..."
    
    mkdir -p "${config_dir}" 2>/dev/null || true
    mkdir -p "${data_dir}" 2>/dev/null || true
}

backup_installation() {
    local install_path="${INSTALL_PATH:-"[INSTALL_PATH]"}"
    local backup_path="${install_path}.backup.$(date +%Y%m%d_%H%M%S)"

    if is_installed; then
        print_info "Creating backup of current installation..."

        if cp "$install_path" "$backup_path" 2>/dev/null; then
            print_success "Backup created: $backup_path"
            return 0
        else
            print_warning "Failed to create backup"
            return 1
        fi
    fi
    return 0
}

install_files() {
    local software_name="${SOFTWARE_NAME:-"[SOFTWARE_NAME]"}"
    local -a install_sources=("${INSTALL_SOURCES[@]}")
    local install_count=0
    local failed_count=0
    local source
    local dest
    local type

    print_info "Installing ${software_name} files..."
    
    # Process INSTALL_SOURCES array if defined
    if [[ "${#install_sources[@]}" -gt 0 ]]; then
        for item in "${install_sources[@]}"; do
            # Skip empty or comment lines
            [[ -z "$item" || "$item" =~ ^[[:space:]]*# ]] && continue
            
            # Parse item: "source:destination:type"
            IFS=':' read -ra parts <<< "$item"
            if [[ ${#parts[@]} -eq 3 ]]; then
                source="${parts[0]}"
                dest="${parts[1]}"
                type="${parts[2]}"
                
                if install_single_item "$source" "$dest" "$type"; then
                    ((install_count++))
                else
                    ((failed_count++))
                fi
            else
                print_warning "Invalid install source format: $item"
                ((failed_count++))
            fi
        done
    else
        print_warning "No INSTALL_SOURCES configured - nothing to install"
        print_info "Please configure INSTALL_SOURCES array in config.sh"
    fi
    
    if [[ $install_count -gt 0 ]]; then
        print_success "Successfully installed $install_count item(s)"
    fi
    
    if [[ $failed_count -gt 0 ]]; then
        print_error "Failed to install $failed_count item(s)"
        return 1
    fi
    
    if [[ $install_count -eq 0 ]]; then
        print_warning "No files were installed"
        return 1
    fi
    
    return 0
}

install_single_item() {
    local _dir="${_DIR}"
    local source_path="$1"
    local dest_path="$2" 
    local item_type="$3"
    local full_source="${_dir}/${source_path}"
    
    # Special handling for symlinks - source_path is the target, not relative to _dir
    if [[ "$item_type" == "symlink" ]]; then
        full_source="$source_path"
        
        mkdir -p "$(dirname "$dest_path")" || {
            print_error "Failed to create directory for: $dest_path"
            return 1
        }
        
        # Create symlink
        if ln -sf "$full_source" "$dest_path"; then
            print_success "Created symlink: $dest_path -> $full_source"
            return 0
        else
            print_error "Failed to create symlink: $dest_path -> $full_source"
            return 1
        fi
    fi
    
    # Check if source exists (for non-symlink types)
    if [[ ! -e "$full_source" ]]; then
        print_error "Source not found: $full_source"
        return 1
    fi
    
    # Create destination directory
    mkdir -p "$(dirname "$dest_path")" || {
        print_error "Failed to create directory for: $dest_path"
        return 1
    }
    
    # Copy based on type
    case "$item_type" in
        "file"|"executable")
            if cp "$full_source" "$dest_path"; then
                [[ "$item_type" == "executable" ]] && chmod +x "$dest_path"
                print_success "Installed: $source_path -> $dest_path"
                return 0
            else
                print_error "Failed to copy: $source_path"
                return 1
            fi
            ;;
        "dir")
            if cp -r "$full_source" "$dest_path"; then
                print_success "Installed directory: $source_path -> $dest_path"
                return 0
            else
                print_error "Failed to copy directory: $source_path"
                return 1
            fi
            ;;
        *)
            print_error "Unknown install type: $item_type"
            return 1
            ;;
    esac
}

create_service() {
    local service_name="${SERVICE_NAME:-"[service-name].service"}"
    local service_content
    local service_after="${SERVICE_AFTER:-network.target}"
    local service_wants="${SERVICE_WANTS:-}"
    local service_type="${SERVICE_TYPE:-simple}"
    local service_exec_start="${SERVICE_EXEC_START:-/usr/bin/[executable-name]}"
    local service_exec_stop="${SERVICE_EXEC_STOP:-/usr/bin/[executable-name] stop}"
    local service_restart="${SERVICE_RESTART:-on-failure}"
    local service_restart_sec="${SERVICE_RESTART_SEC:-5}"
    local service_user="${SERVICE_USER:-root}"
    local service_wanted_by="${SERVICE_WANTED_BY:-multi-user.target}"
    local service_path="${SERVICE_PATH:-/etc/systemd/system/${service_name}}"

    if [[ -z "${service_name}" ]] || [[ "${service_name}" == "[service-name].service" ]]; then
        print_info "No service configuration needed (SERVICE_NAME not configured)"
        return 0
    fi

    print_info "Creating systemd service: ${service_name}"

    service_content="[Unit]
Description=${software_name} Service
After=${service_after}"

    if [[ -n "${service_wants}" ]]; then
        service_content+="\nWants=${service_wants}"
    fi
    
    service_content+="\n
[Service]
Type=${service_type}
User=${service_user}
Group=${service_user}
WorkingDirectory=${SHARE_DIR}
ExecStart=${service_exec_start}
ExecStop=${service_exec_stop}"

    if [[ "${service_restart}" != "no" ]]; then
        service_content+="\nRestart=${service_restart}"
        if [[ -n "${service_restart_sec}" ]] && [[ "${service_restart_sec}" != "0" ]]; then
            service_content+="\nRestartSec=${service_restart_sec}"
        fi
    fi
    
    service_content+="\nStandardOutput=journal"
    service_content+="\nStandardError=journal"
    service_content+="\nSyslogIdentifier=${SOFTWARE_DIR_NAME}"
    
    # Security hardening
    service_content+="\n\n# Security hardening"
    service_content+="\nNoNewPrivileges=true"
    service_content+="\nPrivateTmp=true"
    service_content+="\nProtectSystem=strict"
    service_content+="\nProtectHome=true"
    service_content+="\nReadWritePaths=${SHARE_DIR}"
    service_content+="\nReadWritePaths=/run"
    
    service_content+="\n
[Install]
WantedBy=${service_wanted_by}"

    if echo -e "${service_content}" > "${service_path}"; then
        if service_daemon_reload; then
            print_success "Service created: ${service_path}"
            print_info "Service configuration:"
            print_info "  • Type: ${service_type}"
            print_info "  • Executable: ${service_exec_start}"
            print_info "  • User: ${service_user:-root}"
            print_info "  • Restart: ${service_restart}"
        else
            print_warning "Service created, but failed to reload systemd daemon"
            return 1
        fi
        return 0
    else
        print_error "Failed to create service file"
        return 1
    fi
}