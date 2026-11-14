#!/bin/bash
# lib/modules/python.sh - Python virtual environment and runtime execution helpers
#
# DynDNS
#
# Author: Manuel Ziel
# License: MIT

set -euo pipefail

################################################################################
# VIRTUAL ENVIRONMENT MANAGEMENT
################################################################################

setup_virtual_environment() {
    local venv_dir="${VENV_DIR:-"[VENV_DIR]"}"

    print_info "Setting up virtual environment..."
    if [[ -L "${venv_dir}" ]]; then
        print_error "Refusing symlinked virtual environment path: ${venv_dir}"
        return 1
    fi

    if [[ -x "${venv_dir}/bin/python3" ]]; then
        print_info "Virtual environment already exists at ${venv_dir}"
        return 0
    fi

    print_info "Creating virtual environment at ${venv_dir}..."
    if python3 -m venv --copies "${venv_dir}"; then
        print_success "Virtual environment created at ${venv_dir}"
        return 0
    fi

    print_error "Failed to create virtual environment at ${venv_dir}"
    return 1
}

activate_virtual_environment() {
    local venv_dir="${VENV_DIR:-"[VENV_DIR]"}"
    local cmd_name="${SOFTWARE_DIR_NAME:-"[SOFTWARE_DIR_NAME]"}"

    if [[ -L "${venv_dir}" || -L "${venv_dir}/bin/activate" ]]; then
        print_error "Refusing symlinked virtual environment path: ${venv_dir}"
        return 1
    fi

    if [[ ! -x "${venv_dir}/bin/python3" || ! -f "${venv_dir}/bin/activate" ]]; then
        print_error "Python virtual environment not found at ${venv_dir}"
        print_info "Initialize it first with: sudo ${cmd_name} setup-env"
        return 1
    fi

    if source "${venv_dir}/bin/activate"; then
        return 0
    fi

    print_error "Failed to activate virtual environment at ${venv_dir}"
    return 1
}

sync_venv_ownership() {
    local venv_dir="${VENV_DIR:-"[VENV_DIR]"}"
    local service_user="${SERVICE_USER:-root}"
    local target_group="${service_user}"

    if [[ "${EUID}" -ne 0 || -L "${venv_dir}" || ! -d "${venv_dir}" ]]; then
        return 0
    fi

    find -P "${venv_dir}" -not -type l -type d -exec chmod 00755 {} + 2>/dev/null || true
    find -P "${venv_dir}" -not -type l -type f -perm /111 -exec chmod 0755 {} + 2>/dev/null || true
    find -P "${venv_dir}" -not -type l -type f ! -perm /111 -exec chmod 0644 {} + 2>/dev/null || true

    if [[ -z "${service_user}" || "${service_user}" == "[SERVICE_USER]" || "${service_user}" == "root" ]]; then
        return 0
    fi
    if ! getent passwd "${service_user}" >/dev/null 2>&1; then
        return 0
    fi
    if ! getent group "${target_group}" >/dev/null 2>&1; then
        target_group="$(id -gn "${service_user}" 2>/dev/null || echo "${service_user}")"
    fi

    chown -hRP "${service_user}:${target_group}" "${venv_dir}" 2>/dev/null || true
    return 0
}

################################################################################
# DEPENDENCY MANAGEMENT
################################################################################

install_python_dependencies() {
    local venv_dir="${VENV_DIR:-"[VENV_DIR]"}"
    local venv_python="${venv_dir}/bin/python3"
    local requirements_file="${REQUIREMENTS_FILE:-"[REQUIREMENTS_FILE]"}"

    if [[ ! -x "${venv_python}" ]]; then
        print_error "Virtual environment Python binary not found: ${venv_python}"
        return 1
    fi

    if [[ ! -f "${requirements_file}" ]]; then
        print_warning "requirements.txt not found, skipping package installation"
        return 0
    fi

    print_info "Installing Python dependencies..."

    if "${venv_python}" -m pip install --disable-pip-version-check --no-index -r "${requirements_file}" -q 2>/dev/null; then
        print_success "All required packages installed"
        return 0
    fi

    if "${venv_python}" -m pip install --disable-pip-version-check --upgrade -r "${requirements_file}" -q; then
        print_success "All required packages installed"
        return 0
    fi

    print_error "Failed to install Python packages"
    return 1
}

################################################################################
# ENVIRONMENT EXPORT
################################################################################

export_python_environment() {
    local python_src_dir=""
    local share_dir="${SHARE_DIR:-"[SHARE_DIR]"}"
    local debug="${DEBUG_MODE:-${DEBUG:-0}}"
    local verbose="${VERBOSE:-0}"
    local daemon_mode="${DAEMON_MODE:-0}"

    if [[ -n "${share_dir}" && "${share_dir}" != "[SHARE_DIR]" && -d "${share_dir}/src" ]]; then
        python_src_dir="${share_dir}/src"
    elif [[ -n "${_DIR:-}" && -d "${_DIR}/src" ]]; then
        python_src_dir="${_DIR}/src"
    fi
    if [[ -n "${python_src_dir}" ]]; then
        export PYTHON_SRC_DIR="${python_src_dir}"
        print_debug "Using Python modules: ${python_src_dir}"
    fi
    [[ "${debug}" -eq 1 ]] && export DEBUG=1
    [[ "${verbose}" -eq 1 ]] && export VERBOSE=1
    export DAEMON_MODE="${daemon_mode}"
    [[ -n "${SERVICE_USER:-}" ]] && export SERVICE_USER
    [[ -n "${SERVICE_GROUP:-}" ]] && export SERVICE_GROUP
    return 0
}

################################################################################
# APPLICATION MANAGEMENT
################################################################################

_write_python_pid_file() {
    local python_pid="$1"
    local pid_file="${PID_FILE:-"[PID_FILE]"}"
    local pid_dir

    if [[ -z "${pid_file}" || "${pid_file}" == "[PID_FILE]" ]]; then
        return 0
    fi

    pid_dir="$(dirname "${pid_file}")"
    if [[ ! -d "${pid_dir}" ]]; then
        mkdir -p "${pid_dir}" 2>/dev/null || true
    fi

    if [[ ! -d "${pid_dir}" || ! -w "${pid_dir}" ]]; then
        print_warning "Cannot write PID file to ${pid_file}"
        return 0
    fi

    if printf '%s\n' "${python_pid}" > "${pid_file}" 2>/dev/null; then
        print_success "Process started with PID: ${python_pid}"
    else
        print_warning "Process started (PID: ${python_pid}) couldn't write PID file"
    fi
}

_acquire_daemon_lock() {
    local lock_file="${LOCK_FILE:-"[LOCK_FILE]"}"
    local lock_dir

    if [[ -z "${lock_file}" || "${lock_file}" == "[LOCK_FILE]" ]]; then
        return 0
    fi
    if ! command -v flock >/dev/null 2>&1; then
        return 0
    fi

    lock_dir="$(dirname "${lock_file}")"
    if [[ ! -d "${lock_dir}" ]]; then
        mkdir -p "${lock_dir}" 2>/dev/null || true
    fi
    if [[ ! -d "${lock_dir}" || ! -w "${lock_dir}" ]]; then
        return 0
    fi

    exec 9>"${lock_file}" 2>/dev/null || return 0
    if ! flock -n 9; then
        exec 9>&- 2>/dev/null || true
        print_warning "Another instance is already holding lock: ${lock_file}"
        return 1
    fi
    return 0
}

_release_daemon_lock_fd() {
    exec 9>&- 2>/dev/null || true
}

_launch_python_daemon() {
    local python_bin="$1"
    local python_script="$2"
    local pid_file="${PID_FILE:-"[PID_FILE]"}"
    local init_delay="${DAEMON_INIT_DELAY:-3}"
    local python_pid

    shift 2
    if ! _acquire_daemon_lock; then
        return 1
    fi

    "${python_bin}" "${python_script}" "$@" &
    python_pid=$!
    _release_daemon_lock_fd

    _write_python_pid_file "${python_pid}"
    sleep "${init_delay}"

    if kill -0 "${python_pid}" 2>/dev/null; then
        return 0
    fi

    print_error "Application failed to start"
    rm -f "${pid_file}"
    return 1
}

_run_python_foreground() {
    local python_bin="$1"
    local python_script="$2"
    local exit_code=0
    shift 2

    _acquire_daemon_lock || return 1
    "${python_bin}" "${python_script}" "$@" || exit_code=$?
    _release_daemon_lock_fd
    if [[ "${exit_code}" -eq 0 ]]; then
        print_success "Application completed successfully"
    else
        print_error "Application failed with exit code: ${exit_code}"
    fi
    return "${exit_code}"
}

start_python_application() {
    local enable_python="${ENABLE_PYTHON:-0}"
    local venv_dir="${VENV_DIR:-"[VENV_DIR]"}"
    local python_bin="${venv_dir}/bin/python3"
    local python_script="${PYTHON_SCRIPT:-"[PYTHON_SCRIPT]"}"
    local daemon_mode="${DAEMON_MODE:-0}"
    local exit_code=0

    if [[ "${enable_python}" -ne 1 ]]; then
        print_error "Python support is not enabled (ENABLE_PYTHON=${enable_python})"
        return 1
    fi
    if ! activate_virtual_environment || [[ ! -f "${python_script}" ]]; then
        [[ -f "${python_script}" ]] || print_error "Python script not found: ${python_script}"
        return 1
    fi

    export_python_environment
    print_info "Executing: ${python_script} $*"
    if [[ "${daemon_mode}" -eq 1 ]]; then
        _launch_python_daemon "${python_bin}" "${python_script}" "$@" || exit_code=$?
    else
        _run_python_foreground "${python_bin}" "${python_script}" "$@" || exit_code=$?
    fi
    return "${exit_code}"
}

start_python_cli() {
    local enable_python="${ENABLE_PYTHON:-0}"
    local venv_dir="${VENV_DIR:-"[VENV_DIR]"}"
    local python_bin="${venv_dir}/bin/python3"
    local python_script="${PYTHON_SCRIPT:-"[PYTHON_SCRIPT]"}"
    local cli_command="$1"
    local exit_code=0

    shift

    if [[ "${enable_python}" -ne 1 ]]; then
        print_error "Python support is not enabled (ENABLE_PYTHON=${enable_python})"
        return 1
    fi
    if ! activate_virtual_environment; then
        return 1
    fi
    if [[ ! -f "${python_script}" ]]; then
        print_error "Python script not found: ${python_script}"
        return 1
    fi

    export_python_environment
    "${python_bin}" "${python_script}" "${cli_command}" "$@" || exit_code=$?
    if [[ "${exit_code}" -ne 0 ]]; then
        print_error "CLI command failed with exit code: ${exit_code}"
    fi
    return "${exit_code}"
}

################################################################################
# ORCHESTRATION
################################################################################

setup_python_environment() {
    if ! setup_virtual_environment; then
        return 1
    fi

    if ! activate_virtual_environment; then
        return 1
    fi

    if ! install_python_dependencies; then
        return 1
    fi

    sync_venv_ownership
    return 0
}

rebuild_python_environment() {
    local venv_dir="${VENV_DIR:-"[VENV_DIR]"}"

    print_info "Rebuilding Python virtual environment..."

    if [[ -d "${venv_dir}" || -L "${venv_dir}" ]]; then
        print_info "Removing existing virtual environment at ${venv_dir}..."
        safe_rm_rf "${venv_dir}" || return 1
    fi

    if ! setup_python_environment; then
        return 1
    fi

    print_success "Python virtual environment rebuilt successfully"
    return 0
}
