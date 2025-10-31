#!/bin/bash
# lib/setup/system.sh - System utilities and checks
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
# 1. SYSTEM DETECTION & CHECKS
################################################################################

check_internet() {
    print_info "Checking internet connection..."
    
    # Try ping first (faster)
    if ping -c 1 -W 3 8.8.8.8 >/dev/null 2>&1; then
        print_success "Internet connection available"
        return 0
    fi
    
    # Fallback to curl if available
    if command -v curl &>/dev/null; then
        if curl -s --connect-timeout 5 --head https://www.google.com >/dev/null 2>&1; then
            print_success "Internet connection available"
            return 0
        fi
    fi
    
    # Fallback to wget if available
    if command -v wget &>/dev/null; then
        if wget -q --spider --timeout=5 https://www.google.com >/dev/null 2>&1; then
            print_success "Internet connection available"
            return 0
        fi
    fi
    
    print_error "No internet connection detected"
    echo ""
    echo "Internet connection is required to download files and install packages."
    echo "Please check your network connection and try again."
    echo ""
    return 1
}

################################################################################
# 3. DEPENDENCY MANAGEMENT
################################################################################

check_and_install_dependencies() {
    local dependencies=("${!DEPENDENCIES[@]}")
    local pkg_name
    local skip_dependencies="${SKIP_DEPENDENCIES:-0}"
    local force_mode="${FORCE_MODE:-0}"
    local missing_packages=()
    local missing_pkg_keys=()
    
    # Check all dependencies (package-based check)
    for pkg_key in "${dependencies[@]}"; do
        pkg_name=$(get_package_name_for_key "${pkg_key}")
        
        if ! is_package_installed "${pkg_name}"; then
            missing_packages+=("${pkg_name}")
            missing_pkg_keys+=("${pkg_key}")
        fi
    done

    if [[ "${#missing_packages[@]}" -gt 0 ]]; then
        print_warning "Missing packages: ${missing_pkg_keys[*]}"
        print_info "Will install: ${missing_packages[*]}"

        if [[ "${skip_dependencies}" -eq 1 ]]; then
            print_info "Skipping dependency installation (--no-deps)"
            return 1
        fi

        if [[ "${force_mode}" -eq 0 ]]; then
            echo ""
            read -rp "Install missing dependencies automatically? (y/n): " -n 1
            echo ""
            if [[ ! ${REPLY} =~ ^[Yy]$ ]]; then
                print_info "Dependency installation cancelled"
                return 1
            fi
        fi
        
        if check_internet && install_system_dependencies "${missing_packages[@]}"; then
            print_success "Dependencies installed successfully"
            return 0
        else
            print_error "Failed to install dependencies"
            return 1
        fi
    fi
    
    print_success "All dependencies satisfied"
    return 0
}

install_system_dependencies() {
    local packages=("$@")
    local package_manager=$(detect_package_manager)

    if [[ "${#packages[@]}" -eq 0 ]]; then
        print_warning "No packages specified for installation"
        return 0
    fi

    if [[ "${package_manager}" == "unknown" ]]; then
        print_error "No supported package manager found"
        print_info "Please install these packages manually: ${packages[*]}"
        return 1
    fi

    print_info "Installing packages using ${package_manager}: ${packages[*]}"

    case "${package_manager}" in
        "apt")
            apt update && apt install -y "${packages[@]}"
            ;;
        "dnf")
            dnf install -y "${packages[@]}"
            ;;
        "yum")
            yum install -y "${packages[@]}"
            ;;
        "pacman")
            pacman -Syu --noconfirm "${packages[@]}"
            ;;
        "zypper")
            zypper install -y "${packages[@]}"
            ;;
        *)
            print_error "Unsupported package manager: $package_manager"
            return 1
            ;;
    esac
}