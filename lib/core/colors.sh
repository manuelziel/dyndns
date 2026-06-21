#!/bin/bash
# lib/core/colors.sh - Color definitions and styling
#
# DynDNS
#
# Author: Manuel Ziel
# License: MIT
#
# This program is free software: you can redistribute it and/or modify

################################################################################
# COLOR DEFINITIONS
################################################################################

readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly PURPLE='\033[0;35m'
readonly CYAN='\033[0;36m'
readonly WHITE='\033[1;37m'
readonly BOLD='\033[1m'
readonly DIM='\033[2m'
readonly NC='\033[0m' # No Color

################################################################################
# UTILITY FUNCTIONS
################################################################################

strip_colors() {
    echo "$1" | sed 's/\x1b\[[0-9;]*m//g'
}