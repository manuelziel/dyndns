#!/bin/bash
# lib/core/colors.sh - Terminal color palette and TTY detection helpers
#
# DynDNS
#
# Author: Manuel Ziel
# License: MIT

set -euo pipefail

################################################################################
# COLOR DEFINITIONS & TERMINAL DETECTION
################################################################################

should_use_colors() {
    if [[ ! -t 1 || -n "${NO_COLOR:-}" || "${TERM:-}" == "dumb" || "${DAEMON_MODE:-0}" -eq 1 ]]; then
        return 1
    fi
    return 0
}

init_colors() {
    if should_use_colors; then
        RED=$'\033[0;31m'
        GREEN=$'\033[0;32m'
        YELLOW=$'\033[1;33m'
        BLUE=$'\033[0;34m'
        PURPLE=$'\033[0;35m'
        CYAN=$'\033[0;36m'
        WHITE=$'\033[1;37m'
        BOLD=$'\033[1m'
        DIM=$'\033[2m'
        NC=$'\033[0m'
    else
        RED=""
        GREEN=""
        YELLOW=""
        BLUE=""
        PURPLE=""
        CYAN=""
        WHITE=""
        BOLD=""
        DIM=""
        NC=""
    fi
}

init_colors
