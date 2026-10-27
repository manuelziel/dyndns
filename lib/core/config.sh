#!/bin/bash
# lib/core/config.sh
#
# DynDNS
#
# Author: Manuel Ziel
# License: MIT

################################################################################
# CONFIGURATION
################################################################################

readonly AUTHOR="Manuel Ziel"
readonly VERSION="1.0.3-alpha.8"
readonly LAST_MODIFIED="2026-10-26"
readonly SOFTWARE_NAME="DynDNS"
readonly SOFTWARE_DESCRIPTION="Dynamic DNS Client for IONOS"

# Generate directory-safe name from SOFTWARE_NAME and export for sourced modules
readonly SOFTWARE_DIR_NAME="$(echo "${SOFTWARE_NAME,,}" | sed 's/[^a-z0-9]/-/g' | sed 's/--*/-/g' | sed 's/^-\|-$//g')"
export SOFTWARE_DIR_NAME  # Export for modules that need it

# Systemd journal identifier (for consistent logging across Python and Bash)
readonly SYSLOG_IDENTIFIER="${SOFTWARE_DIR_NAME}"
export SYSLOG_IDENTIFIER  # Export for Python modules

# Standard installation paths
readonly BIN="/usr/local/bin"
readonly BIN_DIR="/usr/local/libexec/${SOFTWARE_DIR_NAME}"          # Executables go here
readonly BIN_SYMLINK="${BIN}/${SOFTWARE_DIR_NAME}"                  # Main command symlink path
readonly LIB_DIR="/usr/local/lib/${SOFTWARE_DIR_NAME}"              # Software-specific lib directory
readonly SHARE_DIR="/usr/local/share/${SOFTWARE_DIR_NAME}"          # Software-specific share directory
export SHARE_DIR                                                    # Export for modules that need it
readonly ETC_DIR="/etc/${SOFTWARE_DIR_NAME}"                        # Software-specific config directory
readonly VAR_LIB_DIR="/var/lib/${SOFTWARE_DIR_NAME}"                # Application data directory

# Runtime file paths - FHS compliant.
# Uses /run/<name>/ subdirectory, created by systemd RuntimeDirectory=<name>
# with proper ownership for the service user (works for root and non-root).
readonly RUNTIME_DIR="/run/${SOFTWARE_DIR_NAME}"
readonly PID_FILE="${RUNTIME_DIR}/${SOFTWARE_DIR_NAME}.pid"
readonly LOCK_FILE="${RUNTIME_DIR}/${SOFTWARE_DIR_NAME}.lock"
readonly CONFIG_FILE="${ETC_DIR}/config.toml"

# Development/local paths (when not installed)
# readonly DEV_PID_FILE="${_DIR}/${SOFTWARE_DIR_NAME}.pid"
# readonly DEV_CONFIG_FILE="${_DIR}/config/${SOFTWARE_DIR_NAME}.conf"

# Main executable path
readonly MAIN_EXECUTABLE="${BIN_DIR}/${SOFTWARE_DIR_NAME}.sh"

# Python application
readonly PYTHON_SCRIPT="${SHARE_DIR}/dyndns.py"

# Installation source configuration
# Format: "source_path:destination_path:type"
# Types: file, dir, executable, symlink
readonly INSTALL_SOURCES=(
    # Main bash runtime script (in libexec for system executables)
    "dyndns.sh:${BIN_DIR}/dyndns.sh:executable"                         # Main runtime script
    
    # Python application and modules (together in share for simplicity)
    "dyndns.py:${SHARE_DIR}/dyndns.py:executable"                       # Python application
    "src/:${SHARE_DIR}/src/:dir"                                        # Python modules
    
    # System integration (symlink for easy access)
    "${MAIN_EXECUTABLE}:${BIN_SYMLINK}:symlink"                         # Main command symlink
    
    # Library modules (bash runtime support)
    "lib/:${SHARE_DIR}/lib/:dir"                                        # All lib modules for bash runtime
    
    # Configuration files
    "config.toml:${ETC_DIR}/config.toml:file"                           # Main configuration file
    "requirements.txt:${SHARE_DIR}/requirements.txt:file"               # Python dependencies
    
    # Documentation
    "README.md:${SHARE_DIR}/README.md:file"                             # Documentation
    "LICENSE:${SHARE_DIR}/LICENSE:file"                                 # License file
    "CHANGELOG.md:${SHARE_DIR}/CHANGELOG.md:file"                       # Changelog
)

# Service configuration
readonly CREATE_SERVICE=true                                            # Set to false to disable service creation
readonly SERVICE_NAME="${SOFTWARE_DIR_NAME}.service"                    # Service file name
readonly SERVICE_EXEC_START="${BIN_SYMLINK} start --daemon"             # Command to start service (use symlink!)
readonly SERVICE_EXEC_STOP="${BIN_SYMLINK} stop"                        # Command to stop service (use symlink!)
readonly SERVICE_TYPE="forking"                                         # forking (bash launches Python with & and writes PID file)
readonly SERVICE_PIDFILE="${PID_FILE}"                                  # PID file for process tracking
readonly SERVICE_USER="dyndns"                                          # User to run service as (empty = root)
readonly SERVICE_GROUP="dyndns"                                         # Group (empty = same as SERVICE_USER, useful for shared media groups)
readonly SERVICE_CREATE_USER=true                                       # Auto-create user/group during install (system user, no login)
readonly SERVICE_USER_HOME=""                                           # Home dir for created user (empty = VAR_LIB_DIR)
readonly SERVICE_USER_SHELL="/usr/sbin/nologin"                         # Login shell for created user (nologin = secure default)
readonly SERVICE_UMASK=""                                               # Umask (empty = systemd default 0022; "0002" for group-writable files 664/775)
readonly SERVICE_SUPPLEMENTARY_GROUPS=""                                # Extra groups the service user joins (space-separated)
readonly SERVICE_RESTART="always"                                       # no, on-success, on-failure, on-abnormal, on-abort, always
readonly SERVICE_RESTART_SEC="5"                                        # Seconds to wait before restart
readonly SERVICE_AFTER="network-online.target"                          # Dependencies (space-separated)
readonly SERVICE_WANTS="network-online.target"                          # Optional dependencies (space-separated) 
readonly SERVICE_PART_OF=""                                             # Bind to a target (e.g. for multi-service apps)
readonly SERVICE_WANTED_BY="multi-user.target"                          # Install target

# Timeouts (seconds; empty string = systemd default)
readonly SERVICE_TIMEOUT_START_SEC="60"                                 # Max startup time before systemd kills the unit
readonly SERVICE_TIMEOUT_STOP_SEC="15"                                  # Grace period before SIGKILL on stop

# Standard I/O redirection (see systemd.exec(5) for valid values)
readonly SERVICE_STANDARD_OUTPUT="journal"                              # journal | null | syslog | kmsg | file:PATH | ...
readonly SERVICE_STANDARD_ERROR="journal"                               # Usually mirrors SERVICE_STANDARD_OUTPUT
readonly SERVICE_STANDARD_INPUT="null"                                  # null for daemons (no stdin)

# Security hardening (see systemd.exec(5))
#   SERVICE_PROTECT_SYSTEM: off | true | full | strict
#     full   = /usr, /boot, /etc read-only; /var/lib, /home, /media writable
#     strict = everything read-only except ReadWritePaths= (brittle with
#              dynamic or late-mounted data dirs — causes EROFS / 226/NAMESPACE)
readonly SERVICE_NO_NEW_PRIVILEGES="true"                               # Block setuid/fs-capabilities elevation
readonly SERVICE_PRIVATE_TMP="true"                                     # Per-service /tmp and /var/tmp
readonly SERVICE_PROTECT_SYSTEM="full"                                  # full = /usr/boot/efi read-only, /var writable (venv lives there)
readonly SERVICE_PROTECT_HOME=""                                        # Empty = off; "true" blocks /home
readonly SERVICE_RESTART_PREVENT_EXIT_STATUS="0"                        # Exit codes that must NOT trigger Restart= (space-separated)
readonly SERVICE_ENVIRONMENT=""                                         # Custom environment variables (e.g. "DISPLAY=:0")
readonly SERVICE_READ_WRITE_PATHS=""                                    # Additional static paths for ReadWritePaths= (space-separated)

# Data directory permissions for paths read from the application config
# file (listed in DATA_DIR_CONFIG_KEYS). Applied on install/update and
# whitelisted via ReadWritePaths= in the systemd unit.
#   "2775" = group-writable, SGID (files inherit group)      — shared group
#   "2777" = world-writable, SGID                            — NFS, any UID
#   "3777" = world-writable + sticky (only owner/root deletes) — safer shared
readonly DATA_DIR_MODE="2775"                                           # Default: shared group access

# Space-separated list of TOML/INI keys whose values are filesystem paths.
# These directories are pre-created on install (chown SERVICE_USER:SERVICE_GROUP,
# chmod DATA_DIR_MODE) and added to the systemd unit as -ReadWritePaths=
# (leading '-' tolerates missing paths at runtime, avoiding 226/NAMESPACE).
# Leave empty to disable the whole feature.
readonly DATA_DIR_CONFIG_KEYS=""                                        # e.g. "source_dir target_dir temp_dir"

# Examples for different service types:
# Web service with database dependency:
# readonly SERVICE_AFTER="network.target postgresql.service"
# readonly SERVICE_WANTS="postgresql.service"
# readonly SERVICE_USER="www-data"

# Dedicated system user with shared media group (recommended for file servers):
# readonly SERVICE_USER="myapp"
# readonly SERVICE_GROUP="media"
# readonly SERVICE_CREATE_USER=true
# readonly SERVICE_UMASK="0002"
# readonly SERVICE_SUPPLEMENTARY_GROUPS=""

# Python daemon (default - uses exec to replace shell with Python):
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
readonly CURRENT_USER="$(whoami)"

# Environment directory (calculated from config.sh location)
# Go up two levels: lib/core/config.sh -> lib/core -> lib -> project_root
readonly ENV_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# Compatibility
readonly INSTALL_PATH="${MAIN_EXECUTABLE}"  # Used by is_installed(), uninstall, menu

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
readonly ENABLE_OPTIONAL_DEPENDENCY=0

# Add optional dependencies based on feature flags
if [[ "${ENABLE_PYTHON}" -eq 1 ]]; then
    DEPENDENCIES["python3"]=1
    DEPENDENCIES["python3-pip"]=1
    DEPENDENCIES["python3-venv"]=1
    DEPENDENCIES["pkg-config"]=1
    DEPENDENCIES["libsystemd-dev"]=1
fi

# Add other optional dependencies here. Variable used in install.sh
if [[ "${ENABLE_OPTIONAL_DEPENDENCY}" -eq 1 ]]; then
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
# All paths are for installed mode.
# VENV lives under VAR_LIB_DIR (not SHARE_DIR) because the service user needs
# write access to install/update packages; SHARE_DIR is read-only per FHS.
readonly VENV_DIR="${VAR_LIB_DIR}/venv"                                 # Virtual environment location (writable runtime state)
export VENV_DIR                                                         # Export for Python subprocess
export DATA_DIR                                                         # Export for Python subprocess
export CONFIG_FILE                                                      # Export for Python subprocess
export PID_FILE                                                         # Export for Python subprocess
readonly PYTHON_INSTALLED_SRC_DIR="${SHARE_DIR}/src"                    # Python source modules
readonly PYTHON_INSTALLED_SCRIPT="${SHARE_DIR}/dyndns.py"               # Main Python script
readonly REQUIREMENTS_FILE="${SHARE_DIR}/requirements.txt"              # Python dependencies
# Note: PYTHON_SRC_DIR is set dynamically in python.sh export_python_environment()