#!/bin/bash
# lib/core/config.sh - Central software metadata, FHS paths, and service settings
#
# DynDNS
#
# Author: Manuel Ziel
# License: MIT

set -euo pipefail

################################################################################
# CONFIGURATION
################################################################################

readonly AUTHOR="Manuel Ziel"
readonly VERSION="1.0.4"
readonly LAST_MODIFIED="2026-11-14"
readonly SOFTWARE_NAME="DynDNS"
readonly SOFTWARE_DESCRIPTION="Dynamic DNS Client for IONOS"

# Generate directory-safe name from SOFTWARE_NAME and validate before building FHS paths
_derived_software_dir_name="$(printf '%s' "${SOFTWARE_NAME,,}" | sed 's/[^a-z0-9]/-/g; s/--*/-/g; s/^-\|-$//g')"
readonly SOFTWARE_DIR_NAME="${_derived_software_dir_name}"
unset _derived_software_dir_name

if [[ -z "${SOFTWARE_DIR_NAME}" || ! "${SOFTWARE_DIR_NAME}" =~ ^[a-z0-9][a-z0-9_-]*$ ]]; then
    printf 'ERROR: Invalid or empty SOFTWARE_DIR_NAME "%s" derived from SOFTWARE_NAME "%s"\n' \
        "${SOFTWARE_DIR_NAME}" "${SOFTWARE_NAME}" >&2
    exit 1
fi
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

# Main executable path (installed target)
readonly MAIN_EXECUTABLE="${BIN_DIR}/${SOFTWARE_DIR_NAME}.sh"

# Runtime and Python environment paths:
# In installed mode (and during setup.sh lifecycle actions), use FHS 3.0 paths.
# In uninstalled local development mode (./dyndns.sh from repository checkout),
# fall back cleanly to local project paths under _DIR.
if [[ "${SETUP_CONTEXT:-0}" -ne 1 && "${0##*/}" != "setup.sh" && ! -f "${MAIN_EXECUTABLE}" && -n "${_DIR:-}" && -f "${_DIR}/lib/core/config.sh" ]]; then
    readonly DEV_MODE=1
    readonly DATA_DIR="${_DIR}"
    readonly RUNTIME_DIR="${_DIR}/.run"
    readonly CONFIG_FILE="${_DIR}/config.toml"
    readonly VENV_DIR="${_DIR}/.venv"
    readonly REQUIREMENTS_FILE="${_DIR}/requirements.txt"
    readonly PYTHON_SCRIPT="${_DIR}/dyndns.py"
else
    readonly DEV_MODE=0
    readonly DATA_DIR="${VAR_LIB_DIR}"                              # FHS 3.0 data directory alias for Python
    readonly RUNTIME_DIR="/run/${SOFTWARE_DIR_NAME}"                # Volatile tmpfs runtime directory
    readonly CONFIG_FILE="${ETC_DIR}/config.toml"                   # Installed TOML configuration
    readonly VENV_DIR="${VAR_LIB_DIR}/venv"                         # Virtual environment location (writable runtime state)
    readonly REQUIREMENTS_FILE="${SHARE_DIR}/requirements.txt"      # Installed Python dependencies
    readonly PYTHON_SCRIPT="${SHARE_DIR}/${SOFTWARE_DIR_NAME}.py"   # Installed Python entry point
fi

readonly PID_FILE="${RUNTIME_DIR}/${SOFTWARE_DIR_NAME}.pid"
readonly LOCK_FILE="${RUNTIME_DIR}/${SOFTWARE_DIR_NAME}.lock"
export DEV_MODE

# Installation source configuration
# Format: "source_path:destination_path:type"
# Types: file, dir, executable, symlink
readonly INSTALL_SOURCES=(
    # Main bash runtime script (in libexec for system executables)
    "dyndns.sh:${BIN_DIR}/${SOFTWARE_DIR_NAME}.sh:executable"           # Main runtime script

    # Python application and modules (together in share for simplicity)
    "dyndns.py:${SHARE_DIR}/${SOFTWARE_DIR_NAME}.py:executable"         # Python application
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
readonly SERVICE_GROUP="dyndns"                                         # Group (empty = same as SERVICE_USER)
readonly SERVICE_CREATE_USER=true                                       # Auto-create user/group during install (system user, no login)
readonly SERVICE_USER_HOME=""                                           # Home dir for created user (empty = VAR_LIB_DIR)
readonly SERVICE_USER_SHELL="/usr/sbin/nologin"                         # Login shell for created user (nologin = secure default)
readonly SERVICE_UMASK=""                                               # Umask (empty = systemd default 0022)
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
readonly SERVICE_NO_NEW_PRIVILEGES="true"                               # Block setuid/fs-capabilities elevation
readonly SERVICE_PRIVATE_TMP="true"                                     # Per-service /tmp and /var/tmp
readonly SERVICE_PRIVATE_DEVICES="true"                                 # Isolate /dev ("false" for GPIO/I2C/SPI/UART)
readonly SERVICE_PROTECT_SYSTEM="full"                                  # Mount /usr, /boot, /etc read-only
readonly SERVICE_PROTECT_HOME="true"                                    # Isolate /home, /root, /run/user
readonly SERVICE_PROTECT_KERNEL_TUNABLES="true"                         # Mount /proc/sys and /sys read-only
readonly SERVICE_PROTECT_CONTROL_GROUPS="true"                          # Mount /sys/fs/cgroup read-only
readonly SERVICE_RESTRICT_SUIDSGID="true"                               # Block creating SUID/SGID files
readonly SERVICE_LOCK_PERSONALITY="true"                                # Lock kernel execution domain
readonly SERVICE_RESTART_PREVENT_EXIT_STATUS="0"                        # Exit codes that must NOT trigger Restart= (space-separated)
readonly SERVICE_ENVIRONMENT=""                                         # Custom environment variables (e.g. DISPLAY=:0 FOO="bar baz")
readonly SERVICE_READ_WRITE_PATHS=""                                    # Additional static paths for ReadWritePaths= (space-separated)

# Data directory permissions for paths read from the application config file
readonly DATA_DIR_MODE="2775"                                           # Default: shared group access
readonly DATA_DIR_CONFIG_KEYS=""                                        # Optional TOML path keys to pre-create & whitelist

# Service paths
readonly SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}"

# Runtime & connectivity timeouts (seconds)
readonly DAEMON_INIT_DELAY=3                                            # Seconds to verify background daemon startup
readonly DAEMON_STOP_MAX_WAIT=10                                        # Max seconds to wait for SIGTERM shutdown
readonly DAEMON_STOP_POLL_INTERVAL=1                                    # Seconds between shutdown liveness polls
readonly DAEMON_RESTART_DELAY=2                                         # Pause in seconds between stop and start
readonly NET_PING_TIMEOUT=3                                             # ICMP ping probe timeout in seconds
readonly NET_HTTP_TIMEOUT=5                                             # HTTP connectivity probe timeout in seconds
readonly NET_PROBE_IP="1.1.1.1"                                         # ICMP connectivity probe host
readonly NET_PROBE_URL="https://connectivitycheck.gstatic.com/generate_204"

# Compatibility
readonly INSTALL_PATH="${MAIN_EXECUTABLE}"  # Used by is_installed(), uninstall, menu

# System package mappings per distribution
# Format: ["key"]="apt-package:dnf-package:pacman-package:zypper-package"
declare -A PACKAGE_MAPPINGS=(
    ["systemd"]="systemd:systemd:systemd:systemd"
    ["python3"]="python3:python3:python:python3"
    ["python3-pip"]="python3-pip:python3-pip:python-pip:python3-pip"
    ["python3-venv"]="python3-venv:python3-virtualenv:python-virtualenv:python3-venv"
    ["curl"]="curl:curl:curl:curl"
)

# Required dependencies - use keys from PACKAGE_MAPPINGS
declare -A DEPENDENCIES=(
    ["systemd"]=1
)

# Feature flags
readonly ENABLE_PYTHON=1

# Add optional dependencies based on feature flags
if [[ "${ENABLE_PYTHON}" -eq 1 ]]; then
    DEPENDENCIES["python3"]=1
    DEPENDENCIES["python3-pip"]=1
    DEPENDENCIES["python3-venv"]=1
fi

readonly ENABLE_OPTIONAL_DEPENDENCY=0

if [[ "${ENABLE_OPTIONAL_DEPENDENCY}" -eq 1 ]]; then
    DEPENDENCIES["curl"]=1
fi

# Python environment exports (paths resolved above for installed or local dev mode)
export VENV_DIR                                                         # Export for Python subprocess
export DATA_DIR                                                         # Export for Python subprocess
export RUNTIME_DIR                                                      # Export volatile tmpfs runtime dir (/run/<name>)
export CONFIG_FILE                                                      # Export for Python subprocess
export PID_FILE                                                         # Export for Python subprocess
# Note: PYTHON_SRC_DIR is set dynamically in python.sh export_python_environment()
