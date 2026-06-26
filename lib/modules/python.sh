#!/bin/bash
# lib/modules/python.sh
#
# DynDNS
#
# Author: Manuel Ziel
# License: MIT
#
# This program is free software: you can redistribute it and/or modify

################################################################################
# VIRTUAL ENVIRONMENT MANAGEMENT
################################################################################

setup_virtual_environment() {
    local venv_dir="${VENV_DIR:-"[VENV_DIR]"}"

    print_info "Setting up virtual environment..."

    if [[ -d "${venv_dir}" ]]; then
        print_info "Virtual environment already exists"
        return 0
    fi

    print_info "Creating virtual environment..."
    if python3 -m venv --copies "${venv_dir}"; then
        print_success "Virtual environment created at ${venv_dir}"
        return 0
    else
        print_error "Failed to create virtual environment"
        return 1
    fi
}

activate_virtual_environment() {
    local venv_dir="${VENV_DIR:-"[VENV_DIR]"}"

    print_info "Activating virtual environment..."

    if [[ -d "${venv_dir}" ]]; then
        if source "${venv_dir}/bin/activate"; then
            print_success "Virtual environment activated"
            return 0
        else
            print_error "Failed to activate virtual environment"
            return 1
        fi
    else
        print_warning "Virtual environment not found, creating new one..."
        if setup_virtual_environment; then
            if source "${venv_dir}/bin/activate"; then
                print_success "Virtual environment activated"
                return 0
            else
                print_error "Failed to activate virtual environment"
                return 1
            fi
        else
            print_error "Failed to create virtual environment"
            return 1
        fi
    fi
}

################################################################################
# DEPENDENCY MANAGEMENT
################################################################################

install_python_dependencies() {
    local requirements_file="${REQUIREMENTS_FILE:-"[REQUIREMENTS_FILE]"}"

    print_info "Installing Python dependencies..."

    if [[ -f "${requirements_file}" ]]; then
        # Fast offline check - verify all packages are already installed
        if pip install --no-index --no-deps -r "${requirements_file}" -q 2>/dev/null; then
            print_success "All required packages installed"
            return 0
        fi

        # Packages missing - need network install
        if pip install --upgrade -r "${requirements_file}" -q; then
            print_success "All required packages installed"
            return 0
        else
            print_error "Failed to install Python packages"
            return 1
        fi
    else
        print_warning "requirements.txt not found, skipping package installation"
        return 0
    fi
}

################################################################################
# ENVIRONMENT EXPORT
################################################################################

export_python_environment() {
    local python_src_dir
    local share_dir="${SHARE_DIR:-"[SHARE_DIR]"}"
    local software_dir_name="${SOFTWARE_DIR_NAME:-"[SOFTWARE_DIR_NAME]"}"
    local pid_file="${PID_FILE:-"[PID_FILE]"}"
    local config_file="${RUNTIME_CONFIG_FILE:-"[RUNTIME_CONFIG_FILE]"}"
    local data_dir="${DATA_DIR:-"[DATA_DIR]"}"
    local venv_dir="${VENV_DIR:-"[VENV_DIR]"}"
    local debug="${DEBUG:-0}"
    local verbose="${VERBOSE:-0}"


    print_info "Exporting Python environment variables..."

    # Use installed Python modules
    if [[ -n "${share_dir}" && "${share_dir}" != "[SHARE_DIR]" && -d "${share_dir}/src" ]]; then
        python_src_dir="${share_dir}/src"
        print_info "Using Python modules: ${python_src_dir}"
    else
        python_src_dir=""
        print_warning "Python src directory not found, Python script will auto-detect"
    fi

    # Export Python-related environment variables
    # Note: PID_FILE, CONFIG_FILE, DATA_DIR, VENV_DIR already exported in config.sh
    if [[ -n "${python_src_dir}" ]]; then
        export PYTHON_SRC_DIR="${python_src_dir}"
    fi

    if [[ "${debug:-0}" -eq 1 ]]; then
        export DEBUG=1
    fi
    if [[ "${verbose:-0}" -eq 1 ]]; then
        export VERBOSE=1
    fi

    # Export daemon mode for Python logger (suppress console handler in daemon mode)
    local daemon_mode="${DAEMON_MODE:-0}"
    export DAEMON_MODE="${daemon_mode}"

    # Export service user/group so the Python ownership helper can hand
    # off files created by root-invoked admin CLI actions (config, import,
    # export) to the unprivileged service user.
    if [[ -n "${SERVICE_USER:-}" ]]; then
        export SERVICE_USER
    fi
    if [[ -n "${SERVICE_GROUP:-}" ]]; then
        export SERVICE_GROUP
    fi

    print_success "Python environment variables exported"
}

################################################################################
# APPLICATION MANAGEMENT
################################################################################

start_python_application() {
    local enable_python="${ENABLE_PYTHON:-0}"
    local python_script="${PYTHON_SCRIPT:-"${BIN_DIR}/${SOFTWARE_DIR_NAME}.py"}"
    local daemon_mode="${DAEMON_MODE:-0}"
    local init_delay=3

    if [[ "${enable_python}" -ne 1 ]]; then
        print_error "Python support is not enabled (ENABLE_PYTHON=${enable_python})"
        return 1
    fi

    if ! setup_python_environment; then
        print_error "Failed to setup Python environment"
        return 1
    fi

    export_python_environment

    if [[ ! -f "${python_script}" ]]; then
        print_error "Python script not found: ${python_script}"
        return 1
    fi

    print_info "Executing: ${python_script} $*"

    # Check if running in daemon mode or single-run mode
    if [[ "${daemon_mode}" -eq 1 ]]; then
        # Note: Output still goes to terminal for interactive debugging
        # For production daemon, redirect to log: >> "${LOG_FILE}" 2>&1
        python3 "${python_script}" "$@" &
        local python_pid=$!

        # Save PID to file with safety checks
        local pid_file="${PID_FILE}"
        if [[ -n "${pid_file}" ]]; then
            local pid_dir=$(dirname "${pid_file}")
            # Try to create the runtime directory if missing (for manual runs;
            # systemd creates it via RuntimeDirectory= for service starts).
            if [[ ! -d "${pid_dir}" ]]; then
                mkdir -p "${pid_dir}" 2>/dev/null || true
            fi
            # Ensure PID directory exists and is writable
            if [[ ! -d "${pid_dir}" ]] || [[ ! -w "${pid_dir}" ]]; then
                print_warning "Cannot write PID file to ${pid_file}"
            else
                if echo "${python_pid}" > "${pid_file}" 2>/dev/null; then
                    print_success "Process started with PID: ${python_pid}"
                else
                    print_warning "Process started (PID: ${python_pid}) couldn't write PID file"
                fi
            fi
        fi

        # Give process time to initialize
        sleep "${init_delay}"

        if kill -0 "${python_pid}" 2>/dev/null; then
            # print_success "Application started successfully"
            return 0
        else
            print_error "Application failed to start"
            rm -f "${pid_file}"
            return 1
        fi
    else
        # Single-run mode: Run in foreground (blocking)
        python3 "${python_script}" "$@"
        local exit_code=$?
        
        if [[ ${exit_code} -eq 0 ]]; then
            print_success "Application completed successfully"
        else
            print_error "Application failed with exit code: ${exit_code}"
        fi
        
        return ${exit_code}
    fi
}

# Usage: start_python_cli "config"
#        start_python_cli "import" "config.yaml"
#        start_python_cli "export" "--output" "backup.yaml"
start_python_cli() {
    local enable_python="${ENABLE_PYTHON:-0}"
    local python_script="${PYTHON_SCRIPT:-"${BIN_DIR}/${SOFTWARE_DIR_NAME}.py"}"
    local venv_dir="${VENV_DIR:-}"
    local python_bin="python3"
    local cli_command="$1"
    local exit_code

    shift  # Remove first argument, rest are CLI args

    if [[ "${enable_python}" -ne 1 ]]; then
        print_error "Python support is not enabled (ENABLE_PYTHON=${enable_python})"
        return 1
    fi

    if ! setup_python_environment; then
        print_error "Failed to setup Python environment"
        return 1
    fi

    export_python_environment

    if [[ ! -f "${python_script}" ]]; then
        print_error "Python script not found: ${python_script}"
        return 1
    fi

    # Prefer the venv interpreter when available. Admin CLI actions
    # (config/import/export) run as the caller (typically root via sudo);
    # the Python ownership helper hands off created files to SERVICE_USER
    # so the systemd service retains access.
    if [[ -x "${venv_dir}/bin/python3" ]]; then
        python_bin="${venv_dir}/bin/python3"
    fi

    "${python_bin}" "${python_script}" "${cli_command}" "$@"
    exit_code=$?

    if [[ ${exit_code} -ne 0 ]]; then
        print_error "CLI command failed with exit code: ${exit_code}"
    fi

    return ${exit_code}
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

    return 0
}