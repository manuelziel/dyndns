#!/bin/bash
# lib/setup/install.sh
#
# DynDNS
#
# Author: Manuel Ziel
# License: MIT
#
# This program is free software: you can redistribute it and/or modify

################################################################################
# CORE INSTALLATION FUNCTIONS
################################################################################

if ! command -v setup_optional_function &>/dev/null; then
    setup_optional_function() {
        print_info "No custom setup hook implemented"
        return 0
    }
fi

do_install() {
    local software_name="${SOFTWARE_NAME:-"[SOFTWARE_NAME]"}"
    local force_mode="${FORCE_MODE:-0}"
    local create_service_flag="${CREATE_SERVICE:-false}"
    local service_name="${SERVICE_NAME:-"[SERVICE_NAME]"}"
    local enable_optional_dependency="${ENABLE_OPTIONAL_DEPENDENCY:-0}"

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

    if [[ "${enable_optional_dependency}" -eq 1 ]]; then
        if ! setup_optional_function; then
            print_error "Failed to setup optional dependencies/hooks"
            return 1
        fi
    fi
    
    if ! install_files; then
        return 1
    fi

    if ! create_service_user; then
        print_error "Failed to create service user/group"
        return 1
    fi

    if ! create_data_directory; then
        print_warning "Failed to create data directory, continuing..."
    fi

    if [[ "${create_service_flag}" == "true" ]]; then
        if ! create_service; then
            print_warning "Service creation failed, continuing installation"
        fi
    fi

    print_success "${software_name} installed successfully!"

    echo ""
    print_info "Next steps:"
    echo "  1. Configure: ${software_name} config"
    echo "  2. Enable & start: sudo systemctl enable --now ${service_name}"
    echo "  3. View logs: sudo journalctl -u ${service_name} -f"

    return 0
}

do_update() {
    local software_name="${SOFTWARE_NAME:-"[SOFTWARE_NAME]"}"
    local current_version="$(get_installed_version)"
    local version="${VERSION:-"[VERSION]"}"
    local service_name="${SERVICE_NAME:-"[SERVICE_NAME]"}"
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

    if [[ -n "${service_name}" ]] && [[ "${service_name}" != "[SERVICE_NAME]" ]] && service_active; then
        was_running=true
        print_info "Stopping service for update..."

        if service_stop; then
            print_success "Service stopped"
        else
            print_warning "Failed to stop service, continuing anyway"
        fi
    elif [[ -n "${service_name}" ]] && [[ "${service_name}" != "[SERVICE_NAME]" ]]; then
        print_info "Service is not running, no need to stop"
    fi

    if [[ "${enable_python}" -eq 1 ]]; then
        if ! setup_python_environment; then
            print_warning "Failed to update Python environment, continuing..."
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
    local bin_dir="${BIN_DIR:-"[BIN_DIR]"}"
    local share_dir="${SHARE_DIR:-"[SHARE_DIR]"}"
    local bin_symlink="${BIN_SYMLINK:-"[BIN_SYMLINK]"}"
    local service_name="${SERVICE_NAME:-"[SERVICE_NAME]"}"

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
    
    remove_systemd_services "${service_name}" "${service_path}"

    if [[ -L "${bin_symlink}" ]]; then
        rm -f "${bin_symlink}"
        print_success "Symlink removed: ${bin_symlink}"
    fi

    if [[ -d "${bin_dir}" ]]; then
        rm -rf "${bin_dir}"
        print_success "Binary directory removed: ${bin_dir}"
    fi
 
    if [[ -d "${share_dir}" ]]; then
        rm -rf "${share_dir}"
        print_success "Share directory removed: ${share_dir}"
    fi

    print_success "${software_name} uninstalled completely!"
    
    if [[ "${PURGE_MODE:-0}" -eq 0 ]]; then
        print_info "Note: Data directory ${VAR_LIB_DIR:-/var/lib/[SOFTWARE_DIR_NAME]} was preserved"
        print_info "Use 'purge' or 'uninstall --purge' to remove all data"
    fi

    return 0
}

get_template_unit_files() {
    local template_dir="${_DIR}/systemd"
    if [[ ! -d "${template_dir}" ]]; then
        return 0
    fi
    find "${template_dir}" -maxdepth 1 -type f \( -name "*.service" -o -name "*.target" \) -print0 2>/dev/null
}

remove_systemd_services() {
    local service_name="$1"
    local service_path="$2"
    local template_files=()
    local unit_file target_name filename dest_path

    while IFS= read -r -d '' file; do
        template_files+=("$file")
    done < <(get_template_unit_files)

    if [[ ${#template_files[@]} -gt 0 ]]; then
        print_info "Stopping and removing systemd services..."
        for unit_file in "${template_files[@]}"; do
            filename=$(basename "${unit_file}")
            target_name="${filename}"
            if [[ "${filename}" == "template.service" ]]; then
                target_name="${service_name}"
            fi
            
            if systemctl is-active --quiet "${target_name}" 2>/dev/null; then
                systemctl stop "${target_name}" 2>/dev/null || true
            fi
            if systemctl is-enabled --quiet "${target_name}" 2>/dev/null; then
                systemctl disable --quiet "${target_name}" 2>/dev/null || true
            fi
            
            dest_path="/etc/systemd/system/${target_name}"
            if rm -f "${dest_path}" 2>/dev/null; then
                print_success "Removed service file: ${dest_path}"
            fi
        done
        service_daemon_reload
    elif service_exists; then
        # Fallback to single-service legacy uninstallation
        print_info "Stopping and removing service..."
        if service_stop && service_disable; then
            print_success "Service stopped and disabled"
            if rm -f "${service_path}"; then
                print_success "Service file removed"
                service_daemon_reload
            fi
        fi
    fi
}

do_purge() {
    local software_name="${SOFTWARE_NAME:-"[SOFTWARE_NAME]"}"
    local force_mode="${FORCE_MODE:-0}"
    local var_lib_dir="${VAR_LIB_DIR:-"/var/lib/[VAR_LIB_DIR]"}"
    local etc_dir="${ETC_DIR:-"/etc/[SOFTWARE_DIR_NAME]"}"

    print_section "Purging ${software_name}"
    print_warning "This will remove ALL data"
    print_warning "Data directory: ${var_lib_dir}"
    
    if [[ "${force_mode}" -eq 0 ]]; then
        echo ""
        read -rp "Are you ABSOLUTELY sure? This cannot be undone! (y/n): " -n 1
        echo ""
        if [[ ! "${REPLY}" =~ ^[Yy]$ ]]; then
            print_info "Purge cancelled"
            return 0
        fi
    fi

    FORCE_MODE=1 PURGE_MODE=1 do_uninstall

    if [[ -d "${var_lib_dir}" ]]; then
        print_info "Removing data directory: ${var_lib_dir}"
        rm -rf "${var_lib_dir}"
        print_success "Data directory removed: ${var_lib_dir}"
    else
        print_info "Data directory not found: ${var_lib_dir}"
    fi

    if [[ -d "${etc_dir}" ]]; then
        print_info "Removing config directory: ${etc_dir}"
        rm -rf "${etc_dir}"
        print_success "Config directory removed: ${etc_dir}"
    fi

    remove_service_user

    print_success "${software_name} purged completely! All data removed."
    return 0
}

################################################################################
# HELPER FUNCTIONS - Setup and Utilities  
################################################################################

create_service_user() {
    local create_user="${SERVICE_CREATE_USER:-false}"
    local service_user="${SERVICE_USER:-root}"
    local service_group="${SERVICE_GROUP:-${service_user}}"
    local user_home="${SERVICE_USER_HOME:-${VAR_LIB_DIR}}"
    local user_shell="${SERVICE_USER_SHELL:-/usr/sbin/nologin}"
    local supplementary_groups="${SERVICE_SUPPLEMENTARY_GROUPS:-}"
    local group

    if [[ "${create_user}" != "true" ]]; then
        return 0
    fi

    if [[ "${service_user}" == "root" ]]; then
        print_info "SERVICE_USER=root; skipping user creation"
        return 0
    fi

    if getent group "${service_group}" >/dev/null 2>&1; then
        print_info "Group already exists: ${service_group}"
    else
        if groupadd --system "${service_group}"; then
            print_success "Created system group: ${service_group}"
        else
            print_error "Failed to create group: ${service_group}"
            return 1
        fi
    fi

    if getent passwd "${service_user}" >/dev/null 2>&1; then
        print_info "User already exists: ${service_user}"
    else
        if useradd --system --gid "${service_group}" \
                   --home-dir "${user_home}" --no-create-home \
                   --shell "${user_shell}" "${service_user}"; then
            print_success "Created system user: ${service_user} (group: ${service_group})"
        else
            print_error "Failed to create user: ${service_user}"
            return 1
        fi
    fi

    if [[ -n "${supplementary_groups}" ]]; then
        for group in ${supplementary_groups}; do
            if ! getent group "${group}" >/dev/null 2>&1; then
                print_warning "Supplementary group not found: ${group} (skipping)"
                continue
            fi
            if usermod --append --groups "${group}" "${service_user}"; then
                print_info "Added ${service_user} to group: ${group}"
            else
                print_warning "Failed to add ${service_user} to group: ${group}"
            fi
        done
    fi

    return 0
}

create_data_directory() {
    local var_lib_dir="${VAR_LIB_DIR:-"[VAR_LIB_DIR]"}"
    local service_user="${SERVICE_USER:-root}"
    local service_group="${SERVICE_GROUP:-${service_user}}"
    local dir_mode="755"

    # Use DATA_DIR_MODE (from config.sh) when a shared group is configured
    # so new files and subdirectories inherit the group automatically via SGID.
    if [[ "${service_group}" != "${service_user}" ]]; then
        dir_mode="${DATA_DIR_MODE:-2775}"
    fi

    print_info "Creating data directory: ${var_lib_dir}"

    if [[ ! -d "${var_lib_dir}" ]]; then
        if ! mkdir -p "${var_lib_dir}" 2>/dev/null; then
            print_error "Failed to create data directory: ${var_lib_dir}"
            print_info "You may need to create it manually: sudo mkdir -p ${var_lib_dir}"
            return 1
        fi
        print_success "Created data directory: ${var_lib_dir}"
    else
        print_info "Data directory already exists"
    fi

    # Recursive: on reinstall/update, pre-existing files (e.g. SQLite DB from
    # a previous root-owned install) must be transferred to the new user too,
    # otherwise the service fails with "attempt to write a readonly database".
    if [[ "${service_user}" != "root" ]]; then
        if getent passwd "${service_user}" >/dev/null 2>&1; then
            if chown -R "${service_user}:${service_group}" "${var_lib_dir}" 2>/dev/null; then
                print_info "Set ownership recursively: ${service_user}:${service_group}"
            else
                print_warning "Failed to set ownership on ${var_lib_dir}"
            fi
        else
            print_warning "Service user ${service_user} not found; skipping chown"
        fi
    fi

    chmod "${dir_mode}" "${var_lib_dir}" 2>/dev/null || true

    if [[ -d "${var_lib_dir}" ]]; then
        chmod -R u+rwX,g+rwX "${var_lib_dir}" 2>/dev/null || true
    fi
    return 0
}

remove_service_user() {
    local create_user="${SERVICE_CREATE_USER:-false}"
    local service_user="${SERVICE_USER:-root}"
    local service_group="${SERVICE_GROUP:-${service_user}}"

    if [[ "${create_user}" != "true" ]] || [[ "${service_user}" == "root" ]]; then
        return 0
    fi

    if getent passwd "${service_user}" >/dev/null 2>&1; then
        if userdel "${service_user}" 2>/dev/null; then
            print_success "Removed user: ${service_user}"
        else
            print_warning "Failed to remove user: ${service_user}"
        fi
    fi

    if [[ "${service_group}" != "${service_user}" ]] && \
       getent group "${service_group}" >/dev/null 2>&1; then
        local remaining_members
        remaining_members=$(getent group "${service_group}" | cut -d: -f4)
        if [[ -n "${remaining_members}" ]]; then
            print_info "Keeping group '${service_group}' (still has members: ${remaining_members})"
        elif groupdel "${service_group}" 2>/dev/null; then
            print_success "Removed group: ${service_group}"
        else
            print_warning "Failed to remove group: ${service_group}"
        fi
    fi

    return 0
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
                    install_count=$((install_count + 1))
                else
                    failed_count=$((failed_count + 1))
                fi
            else
                print_warning "Invalid install source format: $item"
                failed_count=$((failed_count + 1))
            fi
        done
    else
        print_warning "No INSTALL_SOURCES configured - nothing to install"
        print_info "Configure INSTALL_SOURCES array in config.sh"
    fi
    
    if [[ "$install_count" -gt 0 ]]; then
        print_success "Successfully installed $install_count item(s)"
    fi
    
    if [[ "$failed_count" -gt 0 ]]; then
        print_error "Failed to install $failed_count item(s)"
        return 1
    fi
    
    if [[ "$install_count" -eq 0 ]]; then
        print_warning "No files were installed"
        return 1
    fi
    
    return 0
}

install_single_item() {
    local _dir="${_DIR:-"[DIR]"}"
    local source_path="$1"
    local dest_path="$2" 
    local item_type="$3"
    local full_source="${_dir}/${source_path}"
    
    if [[ "$item_type" == "symlink" ]]; then
        full_source="$source_path"
        
        mkdir -p "$(dirname "$dest_path")" || {
            print_error "Failed to create directory for: $dest_path"
            return 1
        }
        
        if ln -sf "$full_source" "$dest_path"; then
            print_success "Created symlink: $dest_path -> $full_source"
            return 0
        else
            print_error "Failed to create symlink: $dest_path -> $full_source"
            return 1
        fi
    fi
    
    if [[ ! -e "$full_source" ]]; then
        print_error "Source not found: $full_source"
        return 1
    fi
    
    mkdir -p "$(dirname "$dest_path")" || {
        print_error "Failed to create directory for: $dest_path"
        return 1
    }
    
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
            rm -rf "$dest_path"
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

setup_data_directories() {
    if [[ ! -f "${CONFIG_FILE}" || -z "${DATA_DIR_CONFIG_KEYS:-}" ]]; then
        return 0
    fi

    local data_dir_mode="${DATA_DIR_MODE:-2775}"
    local service_user="${SERVICE_USER:-root}"
    local service_group="${SERVICE_GROUP:-${service_user}}"
    local key dir_value

    for key in ${DATA_DIR_CONFIG_KEYS}; do
        dir_value=$(grep -E "^${key}\s*=" "${CONFIG_FILE}" 2>/dev/null \
            | sed 's/^[^=]*=\s*"//;s/"\s*$//' | head -1)
        if [[ -z "${dir_value}" ]]; then
            continue
        fi

        if [[ ! -d "${dir_value}" ]]; then
            if mkdir -p "${dir_value}" 2>/dev/null; then
                print_info "Created ${key}: ${dir_value}"
            else
                print_warning "Failed to create ${key}: ${dir_value}"
            fi
        fi
        
        if [[ -d "${dir_value}" && "${service_user}" != "root" ]]; then
            if getent passwd "${service_user}" >/dev/null 2>&1; then
                chown "${service_user}:${service_group}" "${dir_value}" 2>/dev/null || \
                    print_warning "Failed to chown ${dir_value}"
            fi
        fi
        chmod "${data_dir_mode}" "${dir_value}" 2>/dev/null || \
            print_warning "Failed to chmod ${data_dir_mode} ${dir_value}"
    done
}

customize_systemd_unit() {
    local dest_path="$1"
    local software_name="${SOFTWARE_NAME:-"[SOFTWARE_NAME]"}"
    local service_after="${SERVICE_AFTER:-network.target}"
    local service_wants="${SERVICE_WANTS:-}"
    local service_type="${SERVICE_TYPE:-simple}"
    local service_exec_start="${SERVICE_EXEC_START:-/usr/bin/[executable-name]}"
    local service_exec_stop="${SERVICE_EXEC_STOP:-/usr/bin/[executable-name] stop}"
    local service_restart="${SERVICE_RESTART:-on-failure}"
    local service_restart_sec="${SERVICE_RESTART_SEC:-5}"
    local service_user="${SERVICE_USER:-root}"
    local service_group="${SERVICE_GROUP:-${service_user}}"
    local service_umask="${SERVICE_UMASK:-}"
    local service_supplementary_groups="${SERVICE_SUPPLEMENTARY_GROUPS:-}"
    local service_part_of="${SERVICE_PART_OF:-}"
    local service_environment="${SERVICE_ENVIRONMENT:-}"
    local service_read_write_paths="${SERVICE_READ_WRITE_PATHS:-}"
    local service_wanted_by="${SERVICE_WANTED_BY:-multi-user.target}"

    # Determine RuntimeDirectoryMode based on User/Group
    local runtime_dir_mode="0755"
    if [[ "${service_group}" != "${service_user}" ]]; then
        runtime_dir_mode="0775"
    fi

    if ! sed -i \
        -e "s|{{SOFTWARE_NAME}}|${software_name}|g" \
        -e "s|{{SERVICE_AFTER}}|${service_after}|g" \
        -e "s|{{SERVICE_WANTS}}|${service_wants}|g" \
        -e "s|{{SERVICE_TYPE}}|${service_type}|g" \
        -e "s|{{SERVICE_USER}}|${service_user}|g" \
        -e "s|{{SERVICE_GROUP}}|${service_group}|g" \
        -e "s|{{SHARE_DIR}}|${SHARE_DIR}|g" \
        -e "s|{{SOFTWARE_DIR_NAME}}|${SOFTWARE_DIR_NAME}|g" \
        -e "s|{{RUNTIME_DIRECTORY_MODE}}|${runtime_dir_mode}|g" \
        -e "s|{{SERVICE_UMASK}}|${service_umask}|g" \
        -e "s|{{SERVICE_SUPPLEMENTARY_GROUPS}}|${service_supplementary_groups}|g" \
        -e "s|{{SERVICE_PIDFILE}}|${SERVICE_PIDFILE:-}|g" \
        -e "s|{{SERVICE_EXEC_START}}|${service_exec_start}|g" \
        -e "s|{{SERVICE_EXEC_STOP}}|${service_exec_stop}|g" \
        -e "s|{{SERVICE_RESTART}}|${service_restart}|g" \
        -e "s|{{SERVICE_RESTART_PREVENT_EXIT_STATUS}}|${SERVICE_RESTART_PREVENT_EXIT_STATUS:-0}|g" \
        -e "s|{{SERVICE_RESTART_SEC}}|${service_restart_sec:-5}|g" \
        -e "s|{{SERVICE_TIMEOUT_START_SEC}}|${SERVICE_TIMEOUT_START_SEC:-60}|g" \
        -e "s|{{SERVICE_TIMEOUT_STOP_SEC}}|${SERVICE_TIMEOUT_STOP_SEC:-15}|g" \
        -e "s|{{SERVICE_STANDARD_OUTPUT}}|${SERVICE_STANDARD_OUTPUT:-journal}|g" \
        -e "s|{{SERVICE_STANDARD_ERROR}}|${SERVICE_STANDARD_ERROR:-journal}|g" \
        -e "s|{{SERVICE_STANDARD_INPUT}}|${SERVICE_STANDARD_INPUT:-null}|g" \
        -e "s|{{SERVICE_NO_NEW_PRIVILEGES}}|${SERVICE_NO_NEW_PRIVILEGES:-true}|g" \
        -e "s|{{SERVICE_PRIVATE_TMP}}|${SERVICE_PRIVATE_TMP:-true}|g" \
        -e "s|{{SERVICE_PROTECT_SYSTEM}}|${SERVICE_PROTECT_SYSTEM:-full}|g" \
        -e "s|{{SERVICE_PROTECT_HOME}}|${SERVICE_PROTECT_HOME:-}|g" \
        -e "s|{{SERVICE_ENVIRONMENT}}|${service_environment}|g" \
        -e "s|{{SERVICE_READ_WRITE_PATHS}}|${service_read_write_paths}|g" \
        -e "s|{{SERVICE_PART_OF}}|${service_part_of}|g" \
        -e "s|{{SERVICE_WANTED_BY}}|${service_wanted_by}|g" \
        "${dest_path}"; then
        print_error "Failed to customize systemd unit file: $(basename "${dest_path}")"
        return 1
    fi
    return 0
}

deploy_single_systemd_unit() {
    local unit_file="$1"
    local filename=$(basename "${unit_file}")
    local target_name="${filename}"
    local service_name="${SERVICE_NAME:-"[SERVICE_NAME]"}"

    if [[ "${filename}" == "template.service" ]]; then
        target_name="${service_name}"
    fi

    local dest_path="/etc/systemd/system/${target_name}"

    print_info "Deploying systemd unit: ${target_name}"

    if ! cp "${unit_file}" "${dest_path}"; then
        print_error "Failed to copy systemd unit file to ${dest_path}"
        return 1
    fi

    if ! chmod 644 "${dest_path}"; then
        print_warning "Failed to set permissions on ${dest_path} to 644"
    fi

    customize_systemd_unit "${dest_path}" || return 1

    # Clean up empty lines or lines with empty values (e.g., "PIDFile=" or "Environment=""") using POSIX BRE
    sed -i '/^[A-Za-z0-9]\{1,\}=[[:space:]]*$/d' "${dest_path}"
    sed -i '/^[A-Za-z0-9]\{1,\}=""[[:space:]]*$/d' "${dest_path}"
    return 0
}

create_service() {
    local service_name="${SERVICE_NAME:-"[SERVICE_NAME]"}"
    local template_dir="${_DIR}/systemd"

    if [[ -z "${service_name}" ]] || [[ "${service_name}" == "[SERVICE_NAME]" ]]; then
        print_info "No service configuration needed (${service_name} not configured)"
        return 0
    fi

    if [[ ! -d "${template_dir}" ]]; then
        print_error "Systemd template directory not found: ${template_dir}"
        return 1
    fi

    local template_files=()
    while IFS= read -r -d '' file; do
        template_files+=("$file")
    done < <(get_template_unit_files)

    if [[ ${#template_files[@]} -eq 0 ]]; then
        print_error "No systemd unit files (*.service, *.target) found in ${template_dir}"
        return 1
    fi

    print_info "Creating systemd services from template directory..."

    local unit_file
    for unit_file in "${template_files[@]}"; do
        deploy_single_systemd_unit "${unit_file}" || return 1
    done

    setup_data_directories

    if service_daemon_reload; then
        print_success "Systemd units successfully deployed."
        return 0
    else
        print_warning "Failed to reload systemd daemon."
        return 1
    fi
}