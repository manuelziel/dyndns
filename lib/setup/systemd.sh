#!/bin/bash
# lib/setup/systemd.sh - Systemd unit template rendering and lifecycle helpers
#
# DynDNS
#
# Author: Manuel Ziel
# License: MIT

set -euo pipefail

################################################################################
# TEMPLATE DISCOVERY & PLACEHOLDER SUBSTITUTION
################################################################################

get_template_unit_files() {
    local _dir="${_DIR:-"[DIR]"}"
    local template_dir="${_dir}/systemd"
    if [[ ! -d "${template_dir}" ]]; then
        return 0
    fi
    find "${template_dir}" -maxdepth 1 -type f \( -name "*.service" -o -name "*.target" \) -print0 2>/dev/null
}

_collect_dynamic_read_write_paths() {
    local config_file="${CONFIG_FILE:-}"
    if [[ -z "${config_file}" || ! -f "${config_file}" || -z "${DATA_DIR_CONFIG_KEYS:-}" ]]; then
        return 0
    fi
    local key dir_value formatted_entry
    local entries=()
    for key in ${DATA_DIR_CONFIG_KEYS}; do
        dir_value="$(_extract_toml_path_value "${config_file}" "${key}")"
        if [[ -z "${dir_value}" || "${dir_value}" != /* || "${dir_value}" == *$'\n'* ]]; then
            continue
        fi
        if [[ "${dir_value}" == *[[:space:]]* ]]; then
            formatted_entry="\"-${dir_value//\"/\\\"}\""
        else
            formatted_entry="-${dir_value}"
        fi
        entries+=("${formatted_entry}")
    done
    if [[ "${#entries[@]}" -gt 0 ]]; then
        printf '%s\n' "${entries[*]}"
    fi
}

_apply_unit_core_placeholders() {
    local content="$1"
    local service_user service_group runtime_dir_mode="0755" state_dir_mode="0755"
    service_user="$(_normalize_service_user "${SERVICE_USER:-root}")"
    service_group="$(_normalize_service_group "${SERVICE_GROUP:-}" "${service_user}")"
    if [[ "${service_group}" != "${service_user}" ]]; then
        runtime_dir_mode="0775"
        state_dir_mode="${DATA_DIR_MODE:-2775}"
    fi
    content="${content//"{{SOFTWARE_NAME}}"/"${SOFTWARE_NAME:-[SOFTWARE_NAME]}"}"
    content="${content//"{{SERVICE_AFTER}}"/"${SERVICE_AFTER:-network.target}"}"
    content="${content//"{{SERVICE_WANTS}}"/"${SERVICE_WANTS:-}"}"
    content="${content//"{{SERVICE_PART_OF}}"/"${SERVICE_PART_OF:-}"}"
    content="${content//"{{SERVICE_TYPE}}"/"${SERVICE_TYPE:-simple}"}"
    content="${content//"{{SERVICE_USER}}"/"${service_user}"}"
    content="${content//"{{SERVICE_GROUP}}"/"${service_group}"}"
    content="${content//"{{SHARE_DIR}}"/"${SHARE_DIR:-[SHARE_DIR]}"}"
    content="${content//"{{SOFTWARE_DIR_NAME}}"/"${SOFTWARE_DIR_NAME:-[SOFTWARE_DIR_NAME]}"}"
    content="${content//"{{RUNTIME_DIRECTORY_MODE}}"/"${runtime_dir_mode}"}"
    content="${content//"{{STATE_DIRECTORY_MODE}}"/"${state_dir_mode}"}"
    content="${content//"{{SERVICE_UMASK}}"/"${SERVICE_UMASK:-}"}"
    content="${content//"{{SERVICE_SUPPLEMENTARY_GROUPS}}"/"${SERVICE_SUPPLEMENTARY_GROUPS:-}"}"
    content="${content//"{{SERVICE_PIDFILE}}"/"${SERVICE_PIDFILE:-}"}"
    content="${content//"{{SERVICE_ENVIRONMENT}}"/"${SERVICE_ENVIRONMENT:-}"}"
    content="${content//"{{SERVICE_WANTED_BY}}"/"${SERVICE_WANTED_BY:-multi-user.target}"}"
    printf '%s\n' "${content}"
}

_apply_unit_runtime_and_security_placeholders() {
    local content="$1"
    local software_dir="${SOFTWARE_DIR_NAME:-[SOFTWARE_DIR_NAME]}"
    local var_lib_dir="${VAR_LIB_DIR:-/var/lib/${software_dir}}"
    local dynamic_rw_paths
    dynamic_rw_paths="$(_collect_dynamic_read_write_paths)"
    content="${content//"{{SERVICE_EXEC_START}}"/"${SERVICE_EXEC_START:-[SERVICE_EXEC_START]}"}"
    content="${content//"{{SERVICE_EXEC_STOP}}"/"${SERVICE_EXEC_STOP:-[SERVICE_EXEC_STOP]}"}"
    content="${content//"{{SERVICE_RESTART}}"/"${SERVICE_RESTART:-on-failure}"}"
    content="${content//"{{SERVICE_RESTART_PREVENT_EXIT_STATUS}}"/"${SERVICE_RESTART_PREVENT_EXIT_STATUS:-0}"}"
    content="${content//"{{SERVICE_RESTART_SEC}}"/"${SERVICE_RESTART_SEC:-5}"}"
    content="${content//"{{SERVICE_TIMEOUT_START_SEC}}"/"${SERVICE_TIMEOUT_START_SEC:-60}"}"
    content="${content//"{{SERVICE_TIMEOUT_STOP_SEC}}"/"${SERVICE_TIMEOUT_STOP_SEC:-15}"}"
    content="${content//"{{SERVICE_STANDARD_OUTPUT}}"/"${SERVICE_STANDARD_OUTPUT:-journal}"}"
    content="${content//"{{SERVICE_STANDARD_ERROR}}"/"${SERVICE_STANDARD_ERROR:-journal}"}"
    content="${content//"{{SERVICE_STANDARD_INPUT}}"/"${SERVICE_STANDARD_INPUT:-null}"}"
    content="${content//"{{SERVICE_NO_NEW_PRIVILEGES}}"/"${SERVICE_NO_NEW_PRIVILEGES:-true}"}"
    content="${content//"{{SERVICE_PRIVATE_TMP}}"/"${SERVICE_PRIVATE_TMP:-true}"}"
    content="${content//"{{SERVICE_PRIVATE_DEVICES}}"/"${SERVICE_PRIVATE_DEVICES:-true}"}"
    content="${content//"{{SERVICE_PROTECT_SYSTEM}}"/"${SERVICE_PROTECT_SYSTEM:-full}"}"
    content="${content//"{{SERVICE_PROTECT_HOME}}"/"${SERVICE_PROTECT_HOME:-true}"}"
    content="${content//"{{SERVICE_PROTECT_KERNEL_TUNABLES}}"/"${SERVICE_PROTECT_KERNEL_TUNABLES:-true}"}"
    content="${content//"{{SERVICE_PROTECT_CONTROL_GROUPS}}"/"${SERVICE_PROTECT_CONTROL_GROUPS:-true}"}"
    content="${content//"{{SERVICE_RESTRICT_SUIDSGID}}"/"${SERVICE_RESTRICT_SUIDSGID:-true}"}"
    content="${content//"{{SERVICE_LOCK_PERSONALITY}}"/"${SERVICE_LOCK_PERSONALITY:-true}"}"
    content="${content//"{{VAR_LIB_DIR}}"/"${var_lib_dir}"}"
    content="${content//"{{DYNAMIC_READ_WRITE_PATHS}}"/"${dynamic_rw_paths}"}"
    content="${content//"{{SERVICE_READ_WRITE_PATHS}}"/"${SERVICE_READ_WRITE_PATHS:-}"}"
    printf '%s\n' "${content}"
}

customize_systemd_unit() {
    local target_file="$1"
    if [[ ! -f "${target_file}" ]]; then
        print_error "Systemd unit file not found: ${target_file}"
        return 1
    fi
    local content
    if ! content="$(<"${target_file}")"; then
        print_error "Failed to read systemd unit template: $(basename "${target_file}")"
        return 1
    fi
    content="$(_apply_unit_core_placeholders "${content}")"
    content="$(_apply_unit_runtime_and_security_placeholders "${content}")"
    if ! printf '%s\n' "${content}" \
        | grep -Ev '^[A-Za-z0-9]+=[[:space:]]*("")?[[:space:]]*$' > "${target_file}"; then
        print_error "Failed to render systemd unit file: $(basename "${target_file}")"
        return 1
    fi
    return 0
}

################################################################################
# ATOMIC DEPLOYMENT & REMOVAL
################################################################################

deploy_single_systemd_unit() {
    local unit_file="$1"
    local filename="${unit_file##*/}"
    local target_name="${filename}"
    local service_name="${SERVICE_NAME:-"[SERVICE_NAME]"}"
    local unit_dir="${SYSTEMD_UNIT_DIR:-/etc/systemd/system}"
    if [[ "${filename}" == "template.service" ]]; then
        target_name="${service_name}"
    fi
    local dest_path="${unit_dir}/${target_name}"
    print_info "Deploying systemd unit: ${target_name}"
    local rc=0
    (
        set -euo pipefail
        tmp_unit="$(mktemp)"
        trap 'rm -f -- "${tmp_unit}"' EXIT ERR INT TERM
        cp -P "${unit_file}" "${tmp_unit}" || exit 1
        customize_systemd_unit "${tmp_unit}" || exit 1
        [[ -L "${dest_path}" ]] && rm -f -- "${dest_path}"
        install -m 0644 "${tmp_unit}" "${dest_path}" || exit 1
    ) || rc=$?
    if [[ "${rc}" -ne 0 ]]; then
        print_error "Failed to deploy systemd unit: ${target_name}"
        return 1
    fi
    return 0
}

create_service() {
    local service_name="${SERVICE_NAME:-"[SERVICE_NAME]"}"
    local template_dir="${_DIR:-"[DIR]"}/systemd"
    if [[ -z "${service_name}" || "${service_name}" == "[SERVICE_NAME]" ]]; then
        print_info "No service configuration needed (${service_name} not configured)"
        return 0
    fi
    if [[ ! -d "${template_dir}" ]]; then
        print_error "Systemd template directory not found: ${template_dir}"
        return 1
    fi
    local template_files=() file unit_file
    while IFS= read -r -d '' file; do
        template_files+=("${file}")
    done < <(get_template_unit_files)
    if [[ "${#template_files[@]}" -eq 0 ]]; then
        print_error "No systemd unit files (*.service, *.target) found in ${template_dir}"
        return 1
    fi
    print_info "Creating systemd services from template directory..."
    setup_data_directories
    for unit_file in "${template_files[@]}"; do
        deploy_single_systemd_unit "${unit_file}" || return 1
    done
    if service_daemon_reload; then
        print_success "Systemd units successfully deployed."
        return 0
    fi
    print_warning "Failed to reload systemd daemon."
    return 1
}

_stop_and_remove_unit() {
    local target_name="$1"
    local unit_dir="${SYSTEMD_UNIT_DIR:-/etc/systemd/system}"
    local dest_path="${unit_dir}/${target_name}"

    if systemctl is-active --quiet "${target_name}" 2>/dev/null; then
        systemctl stop "${target_name}" 2>/dev/null || true
    fi
    if systemctl is-enabled --quiet "${target_name}" 2>/dev/null; then
        systemctl disable --quiet "${target_name}" 2>/dev/null || true
    fi
    if [[ -e "${dest_path}" || -L "${dest_path}" ]] && rm -f -- "${dest_path}" 2>/dev/null; then
        print_success "Removed service file: ${dest_path}"
    fi
}

remove_systemd_services() {
    local service_name="$1"
    local service_path="$2"
    local template_files=() file unit_file filename target_name

    while IFS= read -r -d '' file; do
        template_files+=("${file}")
    done < <(get_template_unit_files)

    if [[ "${#template_files[@]}" -gt 0 ]]; then
        print_info "Stopping and removing systemd services..."
        for unit_file in "${template_files[@]}"; do
            filename="${unit_file##*/}"
            target_name="${filename}"
            [[ "${filename}" == "template.service" ]] && target_name="${service_name}"
            _stop_and_remove_unit "${target_name}"
        done
        service_daemon_reload || true
        return 0
    fi
    if service_exists; then
        print_info "Stopping and removing service..."
        if service_stop && service_disable && rm -f -- "${service_path}"; then
            print_success "Service stopped, disabled, and unit removed"
            service_daemon_reload || true
        fi
    fi
}
