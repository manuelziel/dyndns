#!/bin/bash
# lib/core/config.sh - Configuration variables and paths
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
# CONFIGURATION
################################################################################

readonly AUTHOR="Manuel Ziel"
readonly VERSION="1.0.3alpha01"
readonly LAST_MODIFIED="2025-10-29"
readonly SOFTWARE_NAME="IONOS-DYNDNS"
readonly SOFTWARE_DESCRIPTION="Dynamic DNS Client for IONOS"

# Generate directory-safe name from SOFTWARE_NAME and export for sourced modules
readonly SOFTWARE_DIR_NAME=$(echo "${SOFTWARE_NAME,,}" | sed 's/[^a-z0-9]/-/g' | sed 's/--*/-/g' | sed 's/^-\|-$//g')
export SOFTWARE_DIR_NAME                                            # Export for modules that need it

# Systemd journal identifier (for consistent logging across Python and Bash)
readonly SYSLOG_IDENTIFIER="${SOFTWARE_DIR_NAME}"
export SYSLOG_IDENTIFIER                                            # Export for Python modules

# Standard installation paths
readonly BIN="/usr/local/bin"
readonly BIN_DIR="/usr/local/libexec/${SOFTWARE_DIR_NAME}"          # Executables go here
readonly BIN_SYMLINK="${BIN}/${SOFTWARE_DIR_NAME}"                  # Main command symlink path
readonly LIB_DIR="/usr/local/lib/${SOFTWARE_DIR_NAME}"              # Software-specific lib directory
readonly SHARE_DIR="/usr/local/share/${SOFTWARE_DIR_NAME}"          # Software-specific share directory
export SHARE_DIR                                                    # Export for modules that need it
readonly ETC_DIR="/etc/${SOFTWARE_DIR_NAME}"                        # Software-specific config directory
readonly VAR_DIR="/var/${SOFTWARE_DIR_NAME}"                        # System var directory

# Runtime file paths
readonly PID_FILE="/run/${SOFTWARE_DIR_NAME}.pid"
readonly LOCK_FILE="/run/${SOFTWARE_DIR_NAME}.lock"
readonly CONFIG_FILE="${SHARE_DIR}/config.toml"

# Development/local paths (when not installed)
# readonly DEV_PID_FILE="${_DIR}/${SOFTWARE_DIR_NAME}.pid"
# readonly DEV_CONFIG_FILE="${_DIR}/config/${SOFTWARE_DIR_NAME}.conf"

# Main executable path
readonly MAIN_EXECUTABLE="${BIN_DIR}/${SOFTWARE_DIR_NAME}.sh"

# Python script path
readonly PYTHON_SCRIPT="${SHARE_DIR}/ionos-dyndns.py"

# Installation source configuration 
# Format: "source_path:destination_path:type"
# Types: file, dir, executable, symlink
readonly INSTALL_SOURCES=(
    # Main bash runtime script
    "ionos-dyndns.sh:${BIN_DIR}/ionos-dyndns.sh:executable"     # Main runtime script

    # Python application and modules
    "ionos-dyndns.py:${SHARE_DIR}/ionos-dyndns.py:executable"   # Python application
    "src/:${SHARE_DIR}/src/:dir"                                # Python modules
    
    # System integration (symlink for easy access)
    "${MAIN_EXECUTABLE}:${BIN_SYMLINK}:symlink"                 # Main command symlink
    
    # Library modules (bash runtime support) - FIXED PATH
    "lib/:${SHARE_DIR}/lib/:dir"                                # All lib modules for bash runtime
    
    # Configuration files
    "config.toml:${SHARE_DIR}/config.toml:file"                 # Main configuration file
    "requirements.txt:${SHARE_DIR}/requirements.txt:file"       # Python dependencies
    
    # Documentation
    "README.md:${SHARE_DIR}/README.md:file"                     # Documentation
    "LICENSE:${SHARE_DIR}/LICENSE:file"                         # License file
    "CHANGELOG.md:${SHARE_DIR}/CHANGELOG.md:file"               # Changelog
)

# Service configuration
readonly CREATE_SERVICE=true                            # Set to false to disable service creation
readonly SERVICE_NAME="${SOFTWARE_DIR_NAME}.service"    # Service file name
readonly SERVICE_EXEC_START="${BIN_SYMLINK} start --daemon"  # Command to start service (use symlink!)
readonly SERVICE_EXEC_STOP="${BIN_SYMLINK} stop"        # Command to stop service (use symlink!)
readonly SERVICE_TYPE="simple"                          # simple, forking, oneshot, notify, idle
readonly SERVICE_USER="root"                            # User to run service as (empty = root)
readonly SERVICE_RESTART="on-failure"                   # no, on-success, on-failure, on-abnormal, on-abort, always
readonly SERVICE_RESTART_SEC="10"                       # Seconds to wait before restart
readonly SERVICE_AFTER="network-online.target"          # Dependencies (space-separated)
readonly SERVICE_WANTS="network-online.target"          # Optional dependencies (space-separated) 
readonly SERVICE_WANTED_BY="multi-user.target"          # Install target

# Examples for different service types:
# Web service with database dependency:
# readonly SERVICE_AFTER="network.target postgresql.service"
# readonly SERVICE_WANTS="postgresql.service"
# readonly SERVICE_USER="www-data"

# Python daemon:
# readonly SERVICE_TYPE="simple" 
# readonly SERVICE_RESTART="on-failure"
# readonly SERVICE_USER="myapp"

# One-shot script:
# readonly SERVICE_TYPE="oneshot"
# readonly SERVICE_RESTART="no"

# Service paths
readonly SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}"

# Configuration and data directories
readonly CONFIG_DIR="${HOME}/.config/${SOFTWARE_DIR_NAME}"
readonly DATA_DIR="${HOME}/.local/share/${SOFTWARE_DIR_NAME}"
readonly SLOTS_FILE="${CONFIG_DIR}/slots.conf"

# Current user
readonly CURRENT_USER=$(whoami)

# Environment directory (calculated from config.sh location)
# Go up two levels: lib/core/config.sh -> lib/core -> lib -> project_root
readonly ENV_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# Compatibility
readonly INSTALL_PATH="${MAIN_EXECUTABLE}"  # Used by is_installed(), backup, uninstall, menu

# System dependencies mapping: [command]="package-name"
# - [command]: The command that must be available in PATH
# - "package": The system package name to install if command is missing
#
# Example: ["python3"]="python3" means:
#   - Check if 'python' command exists
#   - If not, install package 'python3'
#
# Package name mappings per distribution
# Format: "apt-package:dnf-package:pacman-package:zypper-package"
# Keys are used in DEPENDENCIES array below
declare -A PACKAGE_MAPPINGS=(
    ["systemd"]="systemd:systemd:systemd:systemd"
    ["python3"]="python3:python3:python:python3"
    ["python3-pip"]="python3-pip:python3-pip:python-pip:python3-pip"
    ["python3-venv"]="python3-venv:python3-virtualenv:python-virtualenv:python3-venv"
    ["pkg-config"]="pkg-config:pkg-config:pkg-config:pkg-config"
    ["libsystemd-dev"]="libsystemd-dev:systemd-devel:systemd:systemd-devel"
    ["curl"]="curl:curl:curl:curl"
    ["wget"]="wget:wget:wget:wget"
    ["git"]="git:git:git:git"
    ["postgresql-client"]="postgresql:postgresql:postgresql:postgresql"
    ["mysql-client"]="mysql:mysql:mysql:mysql"
)

# Required dependencies - use keys from PACKAGE_MAPPINGS
declare -A DEPENDENCIES=(
    ["systemd"]=1
)

# Feature flags - set to 1 to enable optional dependency groups
readonly ENABLE_PYTHON=1
readonly ENABLE_OPTIONAL_DEPENDENCY=0  # --- IGNORE ---

# Add optional dependencies based on feature flags
if [[ ${ENABLE_PYTHON} -eq 1 ]]; then
    DEPENDENCIES["python3"]=1
    DEPENDENCIES["python3-pip"]=1
    DEPENDENCIES["python3-venv"]=1
    DEPENDENCIES["pkg-config"]=1
    DEPENDENCIES["libsystemd-dev"]=1
fi

# Add other optional dependencies here. Variable used in install.sh
if [[ ${ENABLE_OPTIONAL_DEPENDENCY} -eq 1 ]]; then
    DEPENDENCIES["curl"]=1
    DEPENDENCIES["git"]=1
fi

# Optional dependencies (uncomment and modify as needed)
# Basic tools:
# DEPENDENCIES["curl"]=1            # HTTP client tool
# DEPENDENCIES["wget"]=1            # File downloader  
# DEPENDENCIES["git"]=1             # Version control system

# Database tools:
# DEPENDENCIES["psql"]=1            # PostgreSQL client
# DEPENDENCIES["mysql"]=1           # MySQL client

# Note: Package names are automatically resolved from PACKAGE_MAPPINGS above
# You only need to specify which commands are required here

# Python environment settings (for Python projects)
# All paths are for installed mode
readonly VENV_DIR="${SHARE_DIR}/lib/venv"                           # Virtual environment location
export VENV_DIR                                                     # Export for Python subprocess
export DATA_DIR                                                     # Export for Python subprocess
export CONFIG_FILE                                                  # Export for Python subprocess
export PID_FILE                                                     # Export for Python subprocess
readonly PYTHON_INSTALLED_SRC_DIR="${SHARE_DIR}/src"                # Python source modules
readonly PYTHON_INSTALLED_SCRIPT="${SHARE_DIR}/ionos-dyndns.py"     # Main Python script
readonly REQUIREMENTS_FILE="${SHARE_DIR}/requirements.txt"          # Python dependencies