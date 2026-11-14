#!/bin/bash
# lib/setup/users.sh - Service user, group, and data directory provisioning
#
# DynDNS
#
# Author: Manuel Ziel
# License: MIT

set -euo pipefail

################################################################################
# SERVICE IDENTITY RESOLUTION HELPERS
################################################################################

_normalize_service_user() {
    local raw_user="${1:-root}"
    if [[ -z "${raw_user}" || "${raw_user}" == "[SERVICE_USER]" ]]; then
        printf '%s\n' "root"
        return 0
    fi
    printf '%s\n' "${raw_user}"
}

_normalize_service_group() {
    local raw_group="${1:-}"
    local fallback_user="${2:-root}"
    if [[ -z "${raw_group}" || "${raw_group}" == "[SERVICE_GROUP]" ]]; then
        printf '%s\n' "${fallback_user}"
        return 0
    fi
    printf '%s\n' "${raw_group}"
}

_resolve_private_group() {
    local service_user="$1"
    if getent group "${service_user}" >/dev/null 2>&1; then
        printf '%s\n' "${service_user}"
        return 0
    fi
    id -gn "${service_user}" 2>/dev/null || printf '%s\n' "${service_user}"
}

################################################################################
# SERVICE USER & GROUP LIFECYCLE
################################################################################

_ensure_service_group() {
    local service_group="$1"
    if getent group "${service_group}" >/dev/null 2>&1; then
        print_info "Group already exists: ${service_group}"
        return 0
    fi
    if groupadd --system "${service_group}"; then
        print_success "Created system group: ${service_group}"
        return 0
    fi
    print_error "Failed to create group: ${service_group}"
    return 1
}

_add_supplementary_groups() {
    local service_user="$1"
    local supplementary_groups="$2"
    local group
    [[ -z "${supplementary_groups}" ]] && return 0
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
}

create_service_user() {
    local create_user="${SERVICE_CREATE_USER:-false}"
    local var_lib_dir="${VAR_LIB_DIR:-"[VAR_LIB_DIR]"}"
    local user_home="${SERVICE_USER_HOME:-"${var_lib_dir}"}"
    local user_shell="${SERVICE_USER_SHELL:-/usr/sbin/nologin}"
    local service_user service_group
    service_user="$(_normalize_service_user "${SERVICE_USER:-root}")"
    service_group="$(_normalize_service_group "${SERVICE_GROUP:-}" "${service_user}")"

    [[ "${create_user}" != "true" ]] && return 0
    if [[ "${service_user}" == "root" ]]; then
        print_info "SERVICE_USER=root; skipping user creation"
        return 0
    fi
    _ensure_service_group "${service_group}" || return 1
    if getent passwd "${service_user}" >/dev/null 2>&1; then
        print_info "User already exists: ${service_user}"
    elif useradd --system --gid "${service_group}" \
        --home-dir "${user_home}" --no-create-home \
        --shell "${user_shell}" "${service_user}"; then
        print_success "Created system user: ${service_user} (group: ${service_group})"
    else
        print_error "Failed to create user: ${service_user}"
        return 1
    fi
    _add_supplementary_groups "${service_user}" "${SERVICE_SUPPLEMENTARY_GROUPS:-}"
    return 0
}

remove_service_user() {
    local create_user="${SERVICE_CREATE_USER:-false}"
    local service_user service_group remaining_members
    service_user="$(_normalize_service_user "${SERVICE_USER:-root}")"
    service_group="$(_normalize_service_group "${SERVICE_GROUP:-}" "${service_user}")"

    if [[ "${create_user}" != "true" || "${service_user}" == "root" ]]; then
        return 0
    fi
    if getent passwd "${service_user}" >/dev/null 2>&1; then
        if userdel "${service_user}" 2>/dev/null; then
            print_success "Removed user: ${service_user}"
        else
            print_warning "Failed to remove user: ${service_user}"
        fi
    fi
    if [[ "${service_group}" != "${service_user}" ]] && getent group "${service_group}" >/dev/null 2>&1; then
        remaining_members="$(getent group "${service_group}" | cut -d: -f4)"
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

################################################################################
# DATA DIRECTORY & CONFIGURED PATH PROVISIONING
################################################################################

_sync_data_dir_tree() {
    local var_lib_dir="$1"
    local venv_dir="$2"
    local service_user="$3"
    local service_group="$4"
    local dir_mode="$5"

    if [[ "${service_user}" != "root" ]]; then
        if getent passwd "${service_user}" >/dev/null 2>&1; then
            if chown -h "${service_user}:${service_group}" "${var_lib_dir}" 2>/dev/null; then
                find -P "${var_lib_dir}" -mindepth 1 -path "${venv_dir}" -prune -o \
                    -not -type l ! -name ".encryption_key" ! -name "*.key" \
                    -exec chown -h "${service_user}:${service_group}" {} + 2>/dev/null || true
                print_info "Set ownership recursively: ${service_user}:${service_group}"
            else
                print_warning "Failed to set ownership on ${var_lib_dir}"
            fi
        else
            print_warning "Service user ${service_user} not found; skipping chown"
        fi
    fi

    chmod "${dir_mode}" "${var_lib_dir}" 2>/dev/null || true
    find -P "${var_lib_dir}" -mindepth 1 -path "${venv_dir}" -prune -o \
        -not -type l ! -name ".encryption_key" ! -name "*.key" \
        -exec chmod u+rwX,g+rwX {} + 2>/dev/null || true
}

_secure_venv_directory() {
    local venv_dir="$1"
    local service_user="$2"
    local private_group

    if [[ -L "${venv_dir}" ]]; then
        print_warning "Refusing to modify symlinked venv directory: ${venv_dir}"
        return 1
    fi
    if [[ ! -d "${venv_dir}" ]]; then
        return 0
    fi

    find -P "${venv_dir}" -not -type l -type d -exec chmod 00755 {} + 2>/dev/null || true
    find -P "${venv_dir}" -not -type l -type f -perm /111 -exec chmod 0755 {} + 2>/dev/null || true
    find -P "${venv_dir}" -not -type l -type f ! -perm /111 -exec chmod 0644 {} + 2>/dev/null || true

    if [[ "${service_user}" != "root" ]] && getent passwd "${service_user}" >/dev/null 2>&1; then
        private_group="$(_resolve_private_group "${service_user}")"
        chown -hRP "${service_user}:${private_group}" "${venv_dir}" 2>/dev/null || true
    fi
    return 0
}

_secure_encryption_keys() {
    local var_lib_dir="$1"
    local venv_dir="$2"
    local service_user="$3"
    local private_group

    find -P "${var_lib_dir}" -mindepth 1 \
        -path "${venv_dir}" -prune -o \
        -type f \( -name ".encryption_key" -o -name "*.key" \) \
        -exec chmod 0600 {} + 2>/dev/null || true

    if [[ "${service_user}" != "root" ]] && getent passwd "${service_user}" >/dev/null 2>&1; then
        private_group="$(_resolve_private_group "${service_user}")"
        find -P "${var_lib_dir}" -mindepth 1 \
            -path "${venv_dir}" -prune -o \
            -type f \( -name ".encryption_key" -o -name "*.key" \) \
            -exec chown -h "${service_user}:${private_group}" {} + 2>/dev/null || true
    fi
    return 0
}

create_data_directory() {
    local var_lib_dir="${VAR_LIB_DIR:-"[VAR_LIB_DIR]"}"
    local venv_dir="${VENV_DIR:-}"
    local service_user service_group dir_mode="00755"
    service_user="$(_normalize_service_user "${SERVICE_USER:-root}")"
    service_group="$(_normalize_service_group "${SERVICE_GROUP:-}" "${service_user}")"
    if [[ -z "${venv_dir}" || "${venv_dir}" == "[VENV_DIR]" ]]; then
        venv_dir="${var_lib_dir}/venv"
    fi
    if [[ "${service_group}" != "${service_user}" ]]; then
        dir_mode="${DATA_DIR_MODE:-2775}"
    fi
    print_info "Creating data directory: ${var_lib_dir}"
    if [[ -L "${var_lib_dir}" ]]; then
        print_error "Refusing symlinked data directory: ${var_lib_dir}"
        return 1
    fi
    if [[ ! -d "${var_lib_dir}" ]]; then
        if ! mkdir -p "${var_lib_dir}" 2>/dev/null; then
            print_error "Failed to create data directory: ${var_lib_dir}"
            return 1
        fi
        print_success "Created data directory: ${var_lib_dir}"
    fi
    _sync_data_dir_tree "${var_lib_dir}" "${venv_dir}" "${service_user}" "${service_group}" "${dir_mode}"
    _secure_venv_directory "${venv_dir}" "${service_user}" || return 1
    _secure_encryption_keys "${var_lib_dir}" "${venv_dir}" "${service_user}"
    return 0
}

_extract_toml_path_value() {
    local config_file="$1"
    local target_key="$2"
    local leaf_key="${target_key##*.}"
    local parsed_value=""
    if command -v python3 >/dev/null 2>&1; then
        if parsed_value="$(python3 - "${config_file}" "${target_key}" 2>/dev/null <<'PY'
import sys, tomllib
with open(sys.argv[1], "rb") as handle:
    data = tomllib.load(handle)
key, cur = sys.argv[2], data
for part in key.split("."):
    cur = cur.get(part) if isinstance(cur, dict) else None
if isinstance(cur, str) and cur.strip():
    print(cur.strip()); raise SystemExit(0)
queue = [data]
while queue:
    node = queue.pop(0)
    if isinstance(node, dict):
        if isinstance(node.get(key), str) and node[key].strip():
            print(node[key].strip()); raise SystemExit(0)
        queue.extend(node.values())
PY
        )"; then
            printf '%s\n' "${parsed_value}"
            return 0
        fi
    fi
    sed -n -E "s/^[[:space:]]*${leaf_key}[[:space:]]*=[[:space:]]*[\"']([^\"'#]+)[\"'].*/\\1/p" \
        "${config_file}" 2>/dev/null | head -n1 || true
}

setup_data_directories() {
    local config_file="${CONFIG_FILE:-"[CONFIG_FILE]"}"
    if [[ ! -f "${config_file}" || -z "${DATA_DIR_CONFIG_KEYS:-}" ]]; then
        return 0
    fi

    local data_dir_mode="${DATA_DIR_MODE:-2775}"
    local service_user service_group key dir_value
    service_user="$(_normalize_service_user "${SERVICE_USER:-root}")"
    service_group="$(_normalize_service_group "${SERVICE_GROUP:-}" "${service_user}")"

    for key in ${DATA_DIR_CONFIG_KEYS}; do
        dir_value="$(_extract_toml_path_value "${config_file}" "${key}")"
        [[ -z "${dir_value}" ]] && continue
        if [[ -L "${dir_value}" ]]; then
            print_warning "Refusing symlinked directory for ${key}: ${dir_value}"
            continue
        fi
        if [[ ! -d "${dir_value}" ]] && ! mkdir -p "${dir_value}" 2>/dev/null; then
            print_warning "Failed to create ${key}: ${dir_value}"
            continue
        fi
        if [[ "${service_user}" != "root" ]] && getent passwd "${service_user}" >/dev/null 2>&1; then
            chown -h "${service_user}:${service_group}" "${dir_value}" 2>/dev/null || \
                print_warning "Failed to chown ${dir_value}"
        fi
        chmod "${data_dir_mode}" "${dir_value}" 2>/dev/null || \
            print_warning "Failed to chmod ${data_dir_mode} ${dir_value}"
    done
}
