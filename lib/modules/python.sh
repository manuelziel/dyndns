#!/bin/bash
# lib/modules/python.sh - Python virtual environment management
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
# 1. VIRTUAL ENVIRONMENT MANAGEMENT
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
# 2. DEPENDENCY MANAGEMENT
################################################################################

install_python_dependencies() {
    local requirements_file="${REQUIREMENTS_FILE:-"[REQUIREMENTS_FILE]"}"

    print_info "Installing Python dependencies..."

    if [[ -f "${requirements_file}" ]]; then
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
# 3. ENVIRONMENT EXPORT
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
    
    # Export debug and verbose flags if set
    if [[ "${debug:-0}" -eq 1 ]]; then
        export DEBUG=1
    fi
    if [[ "${verbose:-0}" -eq 1 ]]; then
        export VERBOSE=1
    fi
    
    print_success "Python environment variables exported"
}

################################################################################
# 4. APPLICATION MANAGEMENT
################################################################################

start_python_application() {
    local enable_python="${ENABLE_PYTHON:-0}"
    local python_script="${PYTHON_SCRIPT:-"${BIN_DIR}/${SOFTWARE_DIR_NAME}.py"}"

    #print_info "Starting Python application..."

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
    python3 "${python_script}" "$@"
    local exit_code=$?
    
    if [[ ${exit_code} -eq 0 ]]; then
        print_success "Application completed successfully"
    else
        print_error "Application failed with exit code: ${exit_code}"
    fi
    
    return ${exit_code}
}

start_python_cli() {
    local enable_python="${ENABLE_PYTHON:-0}"
    local python_script="${PYTHON_SCRIPT:-"${BIN_DIR}/${SOFTWARE_DIR_NAME}.py"}"
    local cli_command="$1"
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
    
    python3 "${python_script}" "${cli_command}" "$@"
    local exit_code=$?
    
    if [[ ${exit_code} -ne 0 ]]; then
        print_error "CLI command failed with exit code: ${exit_code}"
    fi
    
    return ${exit_code}
}

################################################################################
# 5. ORCHESTRATION
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